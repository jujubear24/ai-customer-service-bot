import json
import time
from typing import Any, cast

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.exceptions import ClientError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from models import ChatRequest, ChatResponse, RAGOptions, SourceDocument

logger = Logger(child=True)
tracer = Tracer()


class RAGRetrieverClient:
    """Client for invoking the RAG Retriever Lambda function."""

    def __init__(self, function_name: str, lambda_client: Any = None):
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
            if "functionError" in response or "errorMessage" in response_payload:
                logger.error(f"RAG Retriever error: {response_payload}")
                return []

            # Parse results
            results_data = response_payload.get("results", [])
            documents = []
            for item in results_data:
                try:
                    documents.append(SourceDocument(**item))
                except Exception as e:
                    logger.warning(f"Failed to parse source document: {e}")

            return documents

        except Exception:
            logger.exception("Failed to invoke RAG Retriever (proceeding without context)")
            return []


class BedrockHandlerClient:
    """Client for invoking the Bedrock Handler Lambda function."""

    def __init__(self, function_name: str, lambda_client: Any = None):
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
        self, message: str, context: list[str], conversation_id: str | None, tenant_id: str
    ) -> dict[str, Any]:
        """
        Generate a response using the Bedrock Handler.
        Retries on ClientErrors (throttling, timeouts).
        """
        payload = {
            "message": message,
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

        # Handle Lambda function errors (4xx/5xx from the handler)
        if "functionError" in response or "errorMessage" in response_payload:
            error_msg = response_payload.get("errorMessage", "Unknown Bedrock error")
            logger.error(f"Bedrock Handler failed: {error_msg}")
            raise RuntimeError(f"Bedrock generation failed: {error_msg}")

        # Cast to dict[str, Any] to satisfy Mypy
        return cast(dict[str, Any], response_payload)


class ChatOrchestrator:
    """Coordinator for the chat flow."""

    def __init__(self, rag_client: RAGRetrieverClient, bedrock_client: BedrockHandlerClient):
        self.rag_client = rag_client
        self.bedrock_client = bedrock_client

    @tracer.capture_method
    def process_request(self, request: ChatRequest) -> ChatResponse:
        """
        Orchestrate the request: RAG Retrieval -> Context Construction -> Bedrock Generation.
        """
        start_time = time.perf_counter()

        # 1. RAG Retrieval
        rag_start = time.perf_counter()
        sources: list[SourceDocument] = []
        rag_skipped = not request.use_rag

        if request.use_rag:
            sources = self.rag_client.retrieve(
                query=request.message, tenant_id=request.tenant_id, options=request.rag_options
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
        total_duration_ms = (time.perf_counter() - start_time) * 1000

        # 4. Response Assembly
        response_text = bedrock_result.get("response", "")
        model_used = bedrock_result.get("model", "unknown")
        conversation_id = bedrock_result.get("conversation_id", request.conversation_id)

        return ChatResponse.create(
            conversation_id=conversation_id or "unknown",
            response_text=response_text,
            model=model_used,
            sources=sources,
            rag_documents_used=len(sources),
            rag_skipped=rag_skipped,
            rag_latency_ms=rag_duration_ms,
            bedrock_latency_ms=bedrock_duration_ms,
            total_latency_ms=total_duration_ms,
        )
