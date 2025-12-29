"""Chat Orchestrator service layer with RAG, Bedrock, Response Validation, and Escalation Routing."""

import json
import time
from typing import Any, cast
from uuid import uuid4

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from botocore.exceptions import ClientError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from models import ChatRequest, ChatResponse, RAGOptions, SourceDocument

logger = Logger(child=True)
tracer = Tracer()
metrics = Metrics()


class RAGRetrieverClient:
    """Client for invoking the RAG Retriever Lambda function."""

    def __init__(self, function_name: str, lambda_client: Any = None) -> None:
        self.function_name = function_name
        self.client = lambda_client or boto3.client("lambda")

    @tracer.capture_method
    def retrieve(self, query: str, tenant_id: str, options: RAGOptions) -> list[SourceDocument]:
        """
        Retrieve relevant documents from the knowledge base.
        Returns an empty list if retrieval fails (non-fatal error).
        """
        try:
            payload = {
                "query": query,
                "tenant_id": tenant_id,
                "limit": options.top_k,
                "min_score": options.min_score,
            }

            logger.info(f"Invoking RAG Retriever: {self.function_name}")
            response = self.client.invoke(
                FunctionName=self.function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )

            response_payload = json.loads(response["Payload"].read())

            # Check for function error
            if "FunctionError" in response or "errorMessage" in response_payload:
                logger.error(f"RAG Retriever error: {response_payload}")
                return []

            # Parse API Gateway-style response if present
            if "statusCode" in response_payload:
                if response_payload["statusCode"] != 200:
                    logger.error(f"RAG Retriever returned status {response_payload['statusCode']}")
                    return []
                body = response_payload.get("body", "{}")
                if isinstance(body, str):
                    response_payload = json.loads(body)
                else:
                    response_payload = body

            # Parse results - rag-retriever returns "documents" not "results"
            results_data = response_payload.get("documents", [])
            documents = []
            for item in results_data:
                try:
                    documents.append(SourceDocument(**item))
                except Exception as e:
                    logger.warning(f"Failed to parse source document: {e}")

            logger.info(f"RAG retrieved {len(documents)} documents")
            return documents

        except Exception:
            logger.exception("Failed to invoke RAG Retriever (proceeding without context)")
            return []


class BedrockHandlerClient:
    """Client for invoking the Bedrock Handler Lambda function."""

    def __init__(self, function_name: str, lambda_client: Any = None) -> None:
        self.function_name = function_name
        self.client = lambda_client or boto3.client("lambda")

    @tracer.capture_method
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(ClientError),
        reraise=True,
    )
    def generate_response(
        self,
        message: str,
        context: list[str],
        conversation_id: str | None,
        tenant_id: str,
    ) -> dict[str, Any]:
        """
        Generate a response using the Bedrock Handler.
        Retries on ClientErrors (throttling, timeouts).
        """

        if conversation_id is None:
            conversation_id = f"conv-{uuid4().hex[:12]}"

        payload = {
            "user_message": message,
            "rag_context": context,
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
        }

        logger.info(f"Invoking Bedrock Handler: {self.function_name}")
        response = self.client.invoke(
            FunctionName=self.function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        response_payload = json.loads(response["Payload"].read())

        # Handle Lambda function errors
        if "FunctionError" in response or "errorMessage" in response_payload:
            error_msg = response_payload.get("errorMessage", "Unknown Bedrock error")
            logger.error(f"Bedrock Handler failed: {error_msg}")
            raise RuntimeError(f"Bedrock generation failed: {error_msg}")

        # Parse API Gateway-style response if present
        if "statusCode" in response_payload:
            if response_payload["statusCode"] != 200:
                raise RuntimeError(
                    f"Bedrock Handler returned status {response_payload['statusCode']}"
                )
            # Parse the stringified body
            body = response_payload.get("body", "{}")
            if isinstance(body, str):
                response_payload = json.loads(body)
            else:
                response_payload = body

        return cast(dict[str, Any], response_payload)


class ResponseValidatorClient:
    """Client for invoking the Response Validator Lambda function."""

    def __init__(self, function_name: str, lambda_client: Any = None) -> None:
        self.function_name = function_name
        self.client = lambda_client or boto3.client("lambda")
        self.enabled = bool(function_name)

    @tracer.capture_method
    def validate(
        self,
        response_text: str,
        user_message: str,
        conversation_id: str,
        tenant_id: str,
        intent: str | None = None,
        intent_confidence: float | None = None,
        urgency: str | None = None,
        previous_intents: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Validate an AI-generated response.

        Returns validation result with validated_response, is_valid, action, and metadata.
        On failure, returns a pass-through result to avoid blocking responses.
        """
        if not self.enabled:
            logger.debug("Response validation disabled (no function name configured)")
            return self._create_passthrough_result(response_text)

        try:
            payload: dict[str, Any] = {
                "response_text": response_text,
                "user_message": user_message,
                "conversation_id": conversation_id,
                "tenant_id": tenant_id,
            }

            if intent:
                payload["intent"] = intent
            if intent_confidence is not None:
                payload["intent_confidence"] = intent_confidence
            if urgency:
                payload["urgency"] = urgency
            if previous_intents:
                payload["previous_intents"] = previous_intents

            logger.info(f"Invoking Response Validator: {self.function_name}")
            start_time = time.perf_counter()

            response = self.client.invoke(
                FunctionName=self.function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"Response Validator completed in {duration_ms:.2f}ms")

            response_payload = json.loads(response["Payload"].read())

            # Check for function error
            if "FunctionError" in response or "errorMessage" in response_payload:
                logger.error(f"Response Validator error: {response_payload}")
                return self._create_passthrough_result(response_text, error=True)

            # Parse API Gateway-style response if present
            if "statusCode" in response_payload:
                if response_payload["statusCode"] != 200:
                    logger.error(
                        f"Response Validator returned status {response_payload['statusCode']}"
                    )
                    return self._create_passthrough_result(response_text, error=True)
                body = response_payload.get("body", {})
                if isinstance(body, str):
                    response_payload = json.loads(body)
                else:
                    response_payload = body

            return cast(dict[str, Any], response_payload)

        except Exception:
            logger.exception("Failed to invoke Response Validator (proceeding with original)")
            return self._create_passthrough_result(response_text, error=True)

    def _create_passthrough_result(self, response_text: str, error: bool = False) -> dict[str, Any]:
        """Create a pass-through result when validation is skipped or fails."""
        return {
            "is_valid": True,
            "action": "PASS",
            "validated_response": response_text,
            "original_response": response_text,
            "was_modified": False,
            "validation_skipped": True,
            "validation_error": error,
            "metadata": {
                "validation_time_ms": 0,
                "rules_evaluated": 0,
                "fallback_used": False,
            },
        }


class EscalationRouterClient:
    """Client for invoking the Escalation Router Lambda function.

    Routes escalated conversations to human agents when the escalation
    threshold is exceeded.
    """

    def __init__(self, function_name: str, lambda_client: Any = None) -> None:
        self.function_name = function_name
        self.client = lambda_client or boto3.client("lambda")
        self.enabled = bool(function_name)

    @tracer.capture_method
    def route_escalation(
        self,
        conversation_id: str,
        tenant_id: str,
        user_id: str | None,
        escalation_data: dict[str, Any],
        sentiment_data: dict[str, Any] | None,
        last_user_message: str,
        last_ai_response: str | None,
        message_count: int = 1,
        intent: str | None = None,
        intent_confidence: float | None = None,
        urgency: str | None = None,
        previous_intents: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Route an escalated conversation to human agents.

        Args:
            conversation_id: Conversation identifier.
            tenant_id: Tenant identifier.
            user_id: Optional user identifier.
            escalation_data: Escalation result from Response Validator.
            sentiment_data: Sentiment result from Response Validator.
            last_user_message: The user's message that triggered escalation.
            last_ai_response: The AI's response (may be modified).
            message_count: Number of messages in conversation.
            intent: Detected intent.
            intent_confidence: Intent confidence score.
            urgency: Urgency level (low, medium, high, critical).
            previous_intents: List of previous intents in conversation.
            metadata: Additional metadata.

        Returns:
            Escalation routing result with escalation_id, priority, customer_message.
        """
        if not self.enabled:
            logger.debug("Escalation routing disabled (no function name configured)")
            return self._create_disabled_result()

        try:
            payload: dict[str, Any] = {
                "conversation_id": conversation_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "escalation": escalation_data,
                "sentiment": sentiment_data,
                "last_user_message": last_user_message,
                "last_ai_response": last_ai_response,
                "message_count": message_count,
                "intent": intent,
                "intent_confidence": intent_confidence,
                "urgency": urgency,
                "previous_intents": previous_intents or [],
                "metadata": metadata or {},
            }

            logger.info(
                f"Invoking Escalation Router: {self.function_name}",
                extra={
                    "conversation_id": conversation_id,
                    "escalation_score": escalation_data.get("score"),
                },
            )
            start_time = time.perf_counter()

            response = self.client.invoke(
                FunctionName=self.function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"Escalation Router completed in {duration_ms:.2f}ms")

            response_payload = json.loads(response["Payload"].read())

            # Check for function error
            if "FunctionError" in response or "errorMessage" in response_payload:
                logger.error(f"Escalation Router error: {response_payload}")
                metrics.add_metric(name="EscalationRoutingErrors", unit=MetricUnit.Count, value=1)
                return self._create_error_result(str(response_payload))

            # Parse API Gateway-style response if present
            if "statusCode" in response_payload:
                status_code = response_payload["statusCode"]
                body = response_payload.get("body", {})
                if isinstance(body, str):
                    body = json.loads(body)

                if status_code != 200:
                    logger.error(f"Escalation Router returned status {status_code}")
                    return self._create_error_result(f"Status {status_code}")

                response_payload = body

            # Track success metrics
            metrics.add_metric(name="EscalationsRouted", unit=MetricUnit.Count, value=1)

            logger.info(
                "Escalation routed successfully",
                extra={
                    "escalation_id": response_payload.get("escalation_id"),
                    "priority": response_payload.get("priority"),
                },
            )

            return cast(dict[str, Any], response_payload)

        except Exception as e:
            logger.exception("Failed to invoke Escalation Router")
            metrics.add_metric(name="EscalationRoutingErrors", unit=MetricUnit.Count, value=1)
            return self._create_error_result(str(e))

    def _create_disabled_result(self) -> dict[str, Any]:
        """Create result when escalation routing is disabled."""
        return {
            "success": False,
            "escalation_id": None,
            "priority": None,
            "customer_message": None,
            "routing_disabled": True,
        }

    def _create_error_result(self, error: str) -> dict[str, Any]:
        """Create result when escalation routing fails."""
        return {
            "success": False,
            "escalation_id": None,
            "priority": None,
            "customer_message": None,
            "routing_error": True,
            "error_message": error,
        }


class ChatOrchestrator:
    """Coordinator for the chat flow."""

    def __init__(
        self,
        rag_client: RAGRetrieverClient,
        bedrock_client: BedrockHandlerClient,
        validator_client: ResponseValidatorClient | None = None,
        escalation_client: EscalationRouterClient | None = None,
    ) -> None:
        self.rag_client = rag_client
        self.bedrock_client = bedrock_client
        self.validator_client = validator_client
        self.escalation_client = escalation_client

    @tracer.capture_method
    def process_request(self, request: ChatRequest) -> ChatResponse:
        """
        Orchestrate the request:
        RAG Retrieval -> Context Construction -> Bedrock Generation ->
        Response Validation -> Escalation Routing (if needed).
        """
        start_time = time.perf_counter()

        # 1. RAG Retrieval
        rag_start = time.perf_counter()
        sources: list[SourceDocument] = []
        rag_skipped = not request.use_rag

        if request.use_rag:
            sources = self.rag_client.retrieve(
                query=request.message,
                tenant_id=request.tenant_id,
                options=request.rag_options,
            )

        rag_duration_ms = (time.perf_counter() - rag_start) * 1000

        # 2. Context Construction
        context_strings = [doc.content for doc in sources]

        # 3. Bedrock Generation
        bedrock_start = time.perf_counter()

        try:
            bedrock_result = self.bedrock_client.generate_response(
                message=request.message,
                context=context_strings,
                conversation_id=request.conversation_id,
                tenant_id=request.tenant_id,
            )
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            raise

        bedrock_duration_ms = (time.perf_counter() - bedrock_start) * 1000

        # Extract response from Bedrock
        response_text = bedrock_result.get("response_text", "")
        model_used = bedrock_result.get("model_id", "unknown")
        conversation_id = bedrock_result.get("conversation_id", request.conversation_id)

        # 4. Response Validation (optional)
        validation_start = time.perf_counter()
        validation_result: dict[str, Any] | None = None
        validation_duration_ms: float | None = None
        escalation_routing_result: dict[str, Any] | None = None

        if request.validate_response and self.validator_client:
            validation_start = time.perf_counter()
            result = self.validator_client.validate(
                response_text=response_text,
                user_message=request.message,
                conversation_id=conversation_id or "unknown",
                tenant_id=request.tenant_id,
            )

            validation_duration_ms = (time.perf_counter() - validation_start) * 1000
            validation_result = result

            # Use validated response (may be modified or replaced with fallback)
            response_text = result.get("validated_response", response_text)

            logger.info(
                "Validation result",
                extra={
                    "is_valid": result.get("is_valid"),
                    "action": result.get("action"),
                    "was_modified": result.get("was_modified"),
                },
            )

            # 5. Escalation Routing (if needed)
            escalation_data = result.get("escalation")
            if escalation_data and escalation_data.get("needs_escalation"):
                escalation_routing_result = self._route_escalation(
                    request=request,
                    conversation_id=conversation_id or "unknown",
                    response_text=response_text,
                    validation_result=result,
                    rag_documents_used=len(sources),
                )

                # If escalation routing succeeded, append customer message to response
                if escalation_routing_result and escalation_routing_result.get("success"):
                    customer_message = escalation_routing_result.get("customer_message")
                    if customer_message:
                        response_text = f"{response_text}\n\n{customer_message}"

        total_duration_ms = (time.perf_counter() - start_time) * 1000

        # 6. Response Assembly
        return ChatResponse.create(
            conversation_id=conversation_id or "unknown",
            response_text=response_text,
            model=model_used,
            sources=sources,
            rag_documents_used=len(sources),
            rag_skipped=rag_skipped,
            rag_latency_ms=rag_duration_ms,
            bedrock_latency_ms=bedrock_duration_ms,
            validation_latency_ms=validation_duration_ms,
            total_latency_ms=total_duration_ms,
            validation_result=validation_result,
            escalation_routing_result=escalation_routing_result,
        )

    @tracer.capture_method
    def _route_escalation(
        self,
        request: ChatRequest,
        conversation_id: str,
        response_text: str,
        validation_result: dict[str, Any],
        rag_documents_used: int = 0,
    ) -> dict[str, Any] | None:
        """Route an escalated conversation to human agents.

        Args:
            request: Original chat request.
            conversation_id: Conversation identifier.
            response_text: The AI's response (possibly modified).
            validation_result: Full validation result with escalation data.
            rag_documents_used: Number of RAG documents used in the request.

        Returns:
            Escalation routing result or None if routing is disabled.
        """
        if not self.escalation_client or not self.escalation_client.enabled:
            logger.info("Escalation routing disabled, skipping")
            return None

        # Narrow type for the escalation client so the return value is typed correctly
        assert self.escalation_client is not None

        escalation_data = validation_result.get("escalation", {})
        sentiment_data = validation_result.get("sentiment")

        logger.info(
            "Routing escalation",
            extra={
                "conversation_id": conversation_id,
                "escalation_score": escalation_data.get("score"),
                "primary_reason": escalation_data.get("primary_reason"),
            },
        )

        return self.escalation_client.route_escalation(
            conversation_id=conversation_id,
            tenant_id=request.tenant_id,
            user_id=getattr(request, "user_id", None),
            escalation_data=escalation_data,
            sentiment_data=sentiment_data,
            last_user_message=request.message,
            last_ai_response=response_text,
            message_count=getattr(request, "message_count", 1),
            intent=validation_result.get("metadata", {}).get("intent"),
            intent_confidence=validation_result.get("metadata", {}).get("intent_confidence"),
            urgency=getattr(request, "urgency", None),
            previous_intents=getattr(request, "previous_intents", None),
            metadata={
                "rag_documents_used": rag_documents_used,
            },
        )
