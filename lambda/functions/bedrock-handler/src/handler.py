"""Bedrock Handler Lambda with Step Functions compatibility.

Invokes Amazon Bedrock Claude models to generate AI responses.
Properly handles throttling for Step Functions retry logic.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from bedrock_client import BedrockClient, BedrockClientError, BedrockModelError
from prompt_builder import build_messages_payload, build_system_prompt
from shared.exceptions import (
    BedrockError,
    NonRetryableError,
    ThrottlingError,
    ValidationError,
)
from shared.sf_adapter import StepFunctionsAdapter
from shared.types import BedrockRequest, BedrockResponse

# =============================================================================
# Initialize
# =============================================================================

logger = Logger(service="bedrock-handler")
tracer = Tracer(service="bedrock-handler")
metrics = Metrics()

# Environment variables
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
DEFAULT_MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))
DEFAULT_TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.7"))

# Initialize Bedrock client
bedrock_client = BedrockClient(model_id=MODEL_ID)


# =============================================================================
# Processing Logic
# =============================================================================


@tracer.capture_method
def process_request(request: BedrockRequest) -> BedrockResponse:
    """Process a Bedrock request and return response.

    Args:
        request: Validated BedrockRequest.

    Returns:
        BedrockResponse with AI-generated content.

    Raises:
        ThrottlingError: If Bedrock is throttling (Step Functions will retry).
        BedrockError: For non-retryable Bedrock failures.
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


# =============================================================================
# Handler
# =============================================================================


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for Bedrock invocation.

    Step Functions Input:
        {
            "conversation_id": "conv-123",
            "user_message": "How do I reset my password?",
            "rag_context": ["To reset your password..."],
            "intent": "password_reset",
            "max_tokens": 1024
        }

    Step Functions Output:
        {
            "conversation_id": "conv-123",
            "response_text": "I can help you reset your password...",
            "model_id": "anthropic.claude-3-sonnet",
            "input_tokens": 256,
            "output_tokens": 150,
            "latency_ms": 1250,
            "stop_reason": "end_turn",
            "timestamp": "2025-01-15T10:30:00Z"
        }

    Step Functions Error Handling:
        - ThrottlingError: Caught by Retry block, will retry with backoff
        - BedrockError: Caught by Catch block, routes to error response state
    """
    adapter = StepFunctionsAdapter(event)
    logger.append_keys(invocation_source=adapter.source.value)

    try:
        # Parse and validate request
        request = adapter.parse_model(BedrockRequest)

        logger.info(
            "Processing Bedrock request",
            extra={
                "conversation_id": request.conversation_id,
                "message_length": len(request.user_message),
                "has_rag_context": request.rag_context is not None,
            },
        )

        # Process request
        response = process_request(request)

        return adapter.success_response(response)

    except ValidationError as e:
        logger.warning("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="BedrockValidationErrors", unit=MetricUnit.Count, value=1)
        return adapter.error_response(e, status_code=400)

    except BedrockModelError as e:
        # Model-level errors (bad request, content policy, etc.) - not retryable
        logger.error("Model error", extra={"error": str(e)})
        metrics.add_metric(name="BedrockModelErrors", unit=MetricUnit.Count, value=1)
        model_error = BedrockError(
            message=f"Model error: {str(e)}",
            model_id=MODEL_ID,
            details={"error_type": "model_error"},
        )
        return adapter.error_response(model_error, status_code=400)

    except BedrockClientError as e:
        # Client-level errors - check if throttling
        error_str = str(e).lower()
        if "throttl" in error_str or "too many requests" in error_str or "rate" in error_str:
            logger.warning("Bedrock throttled", extra={"error": str(e)})
            metrics.add_metric(name="BedrockThrottles", unit=MetricUnit.Count, value=1)
            # Raise ThrottlingError for Step Functions to retry
            throttle_error = ThrottlingError(
                message=f"Bedrock throttled: {str(e)}",
                service="bedrock",
                retry_after_seconds=5,
            )
            return adapter.error_response(throttle_error, status_code=429)
        else:
            logger.error("Bedrock client error", extra={"error": str(e)})
            metrics.add_metric(name="BedrockClientErrors", unit=MetricUnit.Count, value=1)
            client_error = BedrockError(
                message=f"Bedrock client error: {str(e)}",
                model_id=MODEL_ID,
            )
            return adapter.error_response(client_error, status_code=502)

    except Exception as e:
        logger.exception("Unexpected error")
        metrics.add_metric(name="BedrockUnexpectedErrors", unit=MetricUnit.Count, value=1)
        unexpected_error = NonRetryableError(
            message=f"Bedrock invocation failed: {str(e)}",
            details={"original_error": type(e).__name__},
        )
        return adapter.error_response(unexpected_error, status_code=500)


# =============================================================================
# Default Error Response for Step Functions
# =============================================================================

# This is returned by the BedrockErrorResponse state in Step Functions
# when Bedrock fails and we want to give the user a friendly message
BEDROCK_ERROR_MESSAGE = (
    "I apologize, but I'm having trouble processing your request right now. "
    "Please try again in a moment, or let me know if you'd like to speak "
    "with a human agent."
)
