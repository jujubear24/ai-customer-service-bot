"""Chat Orchestrator service layer with RAG, Bedrock, and Response Validation clients."""

import json
import time
from typing import Any, cast
from uuid import uuid4

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.exceptions import ClientError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from models import ChatRequest, ChatResponse, RAGOptions, SourceDocument

logger = Logger(child=True)
tracer = Tracer()


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


class ChatOrchestrator:
    """Coordinator for the chat flow."""

    def __init__(
        self,
        rag_client: RAGRetrieverClient,
        bedrock_client: BedrockHandlerClient,
        validator_client: ResponseValidatorClient | None = None,
    ) -> None:
        self.rag_client = rag_client
        self.bedrock_client = bedrock_client
        self.validator_client = validator_client

    @tracer.capture_method
    def process_request(self, request: ChatRequest) -> ChatResponse:
        """
        Orchestrate the request:
        RAG Retrieval -> Context Construction -> Bedrock Generation -> Response Validation.
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

        total_duration_ms = (time.perf_counter() - start_time) * 1000

        # 5. Response Assembly
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
        )
