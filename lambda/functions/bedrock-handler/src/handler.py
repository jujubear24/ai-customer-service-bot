"""
Bedrock Handler Lambda Function.

Invokes Amazon Bedrock Claude models to generate AI responses.
Stateless design for Step Functions compatibility (ADR-009).
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import ValidationError

from bedrock_client import BedrockClient, BedrockClientError, BedrockModelError
from prompt_builder import build_messages_payload, build_system_prompt
from shared.exceptions import DependencyError
from shared.exceptions import ValidationError as CustomValidationError
from shared.types import BedrockRequest, BedrockResponse

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()

# Environment variables
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
DEFAULT_MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))
DEFAULT_TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.7"))

# Initialize Bedrock client
bedrock_client = BedrockClient(model_id=MODEL_ID)


@tracer.capture_method
def process_request(request: BedrockRequest) -> BedrockResponse:
    """Process a Bedrock request and return response.

    Args:
        request: Validated BedrockRequest.

    Returns:
        BedrockResponse with AI-generated content.
    """
    # Build system prompt
    system_prompt = build_system_prompt(
        include_guidelines=True,
        include_safety=True,
        custom_instructions=request.system_prompt_override,
    )

    # Build messages array
    messages = build_messages_payload(
        user_message=request.user_message,
        conversation_context=request.conversation_context,
        intent=request.intent,
        entities=request.entities,
        rag_context=request.rag_context,
    )

    # Log request details (without PII)
    logger.info(
        "Invoking Bedrock model",
        extra={
            "conversation_id": request.conversation_id,
            "model_id": MODEL_ID,
            "message_count": len(messages),
            "max_tokens": request.max_tokens,
            "has_rag_context": request.rag_context is not None,
        },
    )

    # Invoke model
    result = bedrock_client.invoke_model(
        messages=messages,
        system_prompt=system_prompt,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
    )

    # Record metrics
    metrics.add_metric(name="BedrockInvocations", unit=MetricUnit.Count, value=1)
    metrics.add_metric(
        name="BedrockInputTokens", unit=MetricUnit.Count, value=result["input_tokens"]
    )
    metrics.add_metric(
        name="BedrockOutputTokens", unit=MetricUnit.Count, value=result["output_tokens"]
    )
    metrics.add_metric(
        name="BedrockLatency", unit=MetricUnit.Milliseconds, value=result["latency_ms"]
    )

    # Build response
    response = BedrockResponse(
        conversation_id=request.conversation_id,
        response_text=result["response_text"],
        model_id=result["model_id"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        latency_ms=result["latency_ms"],
        stop_reason=result["stop_reason"],
        timestamp=datetime.now(UTC).isoformat(),
        request_id=result.get("request_id"),
    )

    logger.info(
        "Bedrock invocation successful",
        extra={
            "conversation_id": request.conversation_id,
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "latency_ms": result["latency_ms"],
            "stop_reason": result["stop_reason"],
        },
    )

    return response


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for Bedrock invocation.

    Args:
        event: Lambda event (BedrockRequest as dict).
        context: Lambda context.

    Returns:
        BedrockResponse as dict, or error response.
    """
    try:
        # Parse and validate request
        try:
            request = BedrockRequest.model_validate(event)
        except ValidationError as e:
            logger.error("Request validation failed", extra={"errors": e.errors()})
            raise CustomValidationError(f"Invalid request: {str(e)}") from e

        # Process request
        response = process_request(request)

        # Return response as dict
        return response.model_dump(mode="json")

    except CustomValidationError as e:
        logger.error("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="BedrockValidationErrors", unit=MetricUnit.Count, value=1)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Validation error", "details": str(e)}),
        }

    except BedrockModelError as e:
        logger.error("Model error", extra={"error": str(e)})
        metrics.add_metric(name="BedrockModelErrors", unit=MetricUnit.Count, value=1)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Model error", "details": str(e)}),
        }

    except BedrockClientError as e:
        logger.error("Bedrock client error", extra={"error": str(e)})
        metrics.add_metric(name="BedrockThrottles", unit=MetricUnit.Count, value=1)
        return {
            "statusCode": 429,
            "body": json.dumps({"error": "Service throttled", "details": str(e)}),
        }

    except DependencyError as e:
        logger.error("Dependency error", extra={"error": str(e)})
        metrics.add_metric(name="BedrockDependencyErrors", unit=MetricUnit.Count, value=1)
        return {
            "statusCode": 502,
            "body": json.dumps({"error": "Dependency error", "details": str(e)}),
        }

    except Exception:
        logger.exception("Unexpected error")
        metrics.add_metric(name="BedrockUnexpectedErrors", unit=MetricUnit.Count, value=1)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
        }
