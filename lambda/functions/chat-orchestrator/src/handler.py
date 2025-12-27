"""Chat Orchestrator Lambda handler."""

import json
import os
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import ValidationError

from models import ChatRequest
from service import (
    BedrockHandlerClient,
    ChatOrchestrator,
    RAGRetrieverClient,
    ResponseValidatorClient,
)

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="ChatBot")

# Initialize Services (Global scope for Cold Start optimization)
RAG_FUNCTION_NAME = os.getenv("RAG_FUNCTION_NAME", "")
BEDROCK_FUNCTION_NAME = os.getenv("BEDROCK_FUNCTION_NAME", "")
RESPONSE_VALIDATOR_FUNCTION_NAME = os.getenv("RESPONSE_VALIDATOR_FUNCTION_NAME", "")

# Initialize clients
rag_client = RAGRetrieverClient(function_name=RAG_FUNCTION_NAME)
bedrock_client = BedrockHandlerClient(function_name=BEDROCK_FUNCTION_NAME)
validator_client = ResponseValidatorClient(function_name=RESPONSE_VALIDATOR_FUNCTION_NAME)

# Initialize orchestrator with all clients
orchestrator = ChatOrchestrator(
    rag_client=rag_client,
    bedrock_client=bedrock_client,
    validator_client=validator_client,
)


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

        # 3. Process Request (includes RAG, Bedrock, and Validation)
        response = orchestrator.process_request(chat_request)

        # 4. Add metrics for validation
        if response.metadata.validation:
            metrics.add_metric(
                name="ResponseValidated",
                unit="Count",
                value=1,
            )
            if not response.metadata.validation.is_valid:
                metrics.add_metric(
                    name="ResponseBlocked",
                    unit="Count",
                    value=1,
                )
            if response.metadata.validation.was_modified:
                metrics.add_metric(
                    name="ResponseModified",
                    unit="Count",
                    value=1,
                )

        # 5. Return Success
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
