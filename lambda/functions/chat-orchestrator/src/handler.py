import json
import os
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import ValidationError

from models import ChatRequest
from service import BedrockHandlerClient, ChatOrchestrator, RAGRetrieverClient

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="ChatBot")

# Initialize Services (Global scope for Cold Start optimization)
RAG_FUNCTION_NAME = os.getenv("RAG_FUNCTION_NAME", "")
BEDROCK_FUNCTION_NAME = os.getenv("BEDROCK_FUNCTION_NAME", "")

# We initialize these lazily or with default checks in a real scenario,
# but here we assume env vars are set or defaults are handled by the clients.
rag_client = RAGRetrieverClient(function_name=RAG_FUNCTION_NAME)
bedrock_client = BedrockHandlerClient(function_name=BEDROCK_FUNCTION_NAME)
orchestrator = ChatOrchestrator(rag_client=rag_client, bedrock_client=bedrock_client)


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """
    Lambda entry point for the Chat Orchestrator.
    Handles API Gateway Proxy events.
    """
    try:
        # 1. Parse Request Body
        body = event.get("body")
        if not body:
            logger.warning("Received empty request body")
            return _build_response(400, {"error": "Missing request body"})

        if isinstance(body, str):
            try:
                body_data = json.loads(body)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in request body")
                return _build_response(400, {"error": "Invalid JSON format"})
        else:
            body_data = body

        # 2. Validate Input
        try:
            chat_request = ChatRequest(**body_data)
        except ValidationError as e:
            logger.warning(f"Validation failed: {e.errors()}")
            return _build_response(400, {"error": "Validation Error", "details": e.errors()})

        # 3. Process Request
        response = orchestrator.process_request(chat_request)

        # 4. Return Success
        # Use model_dump(mode='json') to handle nested Pydantic models serialization
        return _build_response(200, response.model_dump(mode="json"))

    except Exception as e:
        logger.exception("Internal Server Error")
        return _build_response(500, {"error": "Internal Server Error", "message": str(e)})


def _build_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Helper to build API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",  # Adjust for production CORS
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(body),
    }
