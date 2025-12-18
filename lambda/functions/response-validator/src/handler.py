"""Lambda handler for Response Validator.

This module provides the Lambda entry point for validating AI-generated responses.
It handles request parsing, validation, and error handling.
"""

from __future__ import annotations

import json
import os
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import ValidationError as PydanticValidationError

from models import (
    ValidationAction,
    ValidationError,
    ValidationMetadata,
    ValidationRequest,
    ValidationResponse,
    ValidationResults,
)
from service import ResponseValidatorService, ValidationServiceConfig

# =============================================================================
# Powertools Setup
# =============================================================================

logger = Logger()
tracer = Tracer()
metrics = Metrics()


# =============================================================================
# Service Initialization
# =============================================================================


def _create_service() -> ResponseValidatorService:
    """Create validation service from environment configuration."""
    config = ValidationServiceConfig(
        enable_pii_detection=os.getenv("ENABLE_PII_DETECTION", "true").lower() == "true",
        enable_profanity_check=os.getenv("ENABLE_PROFANITY_CHECK", "true").lower() == "true",
        enable_business_rules=os.getenv("ENABLE_BUSINESS_RULES", "true").lower() == "true",
        enable_length_check=os.getenv("ENABLE_LENGTH_CHECK", "true").lower() == "true",
        min_response_length=int(os.getenv("MIN_RESPONSE_LENGTH", "20")),
        max_response_length=int(os.getenv("MAX_RESPONSE_LENGTH", "2000")),
        truncate_long_responses=os.getenv("TRUNCATE_LONG_RESPONSES", "true").lower() == "true",
        stop_on_critical_failure=os.getenv("STOP_ON_CRITICAL_FAILURE", "true").lower() == "true",
        use_fallback_on_block=os.getenv("USE_FALLBACK_ON_BLOCK", "true").lower() == "true",
        redact_pii_in_response=os.getenv("REDACT_PII_IN_RESPONSE", "true").lower() == "true",
    )

    return ResponseValidatorService(config=config)


# Lazy-loaded service instance
_service: ResponseValidatorService | None = None


def get_service() -> ResponseValidatorService:
    """Get or create the validation service singleton."""
    global _service
    if _service is None:
        _service = _create_service()
    return _service


# =============================================================================
# Request Parsing
# =============================================================================


def _parse_request(event: dict[str, Any]) -> ValidationRequest:
    """Parse and validate the incoming Lambda event.

    Args:
        event: Lambda event payload (direct invocation format).

    Returns:
        Validated ValidationRequest.

    Raises:
        ValueError: If the event cannot be parsed.
    """
    # Handle direct invocation (dict payload)
    if isinstance(event, dict):
        # Check if body is a JSON string (API Gateway format)
        if "body" in event and isinstance(event["body"], str):
            try:
                body = json.loads(event["body"])
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in request body: {e}") from e
        elif "body" in event and isinstance(event["body"], dict):
            body = event["body"]
        else:
            # Direct invocation with payload as event
            body = event

        return ValidationRequest.model_validate(body)

    raise ValueError(f"Unexpected event type: {type(event)}")


# =============================================================================
# Response Building
# =============================================================================


def _build_success_response(response: ValidationResponse) -> dict[str, Any]:
    """Build successful Lambda response."""
    return {
        "statusCode": 200,
        "body": response.model_dump(mode="json"),
    }


def _build_error_response(
    error: ValidationError,
    status_code: int = 400,
) -> dict[str, Any]:
    """Build error Lambda response."""
    return {
        "statusCode": status_code,
        "body": error.model_dump(mode="json"),
    }


def _build_validation_error_response(
    error: PydanticValidationError,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Build response for Pydantic validation errors."""
    error_details = []
    for err in error.errors():
        error_details.append(
            {
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
            }
        )

    validation_error = ValidationError(
        error_type="ValidationError",
        message="Request validation failed",
        retryable=False,
        conversation_id=conversation_id,
        details={"errors": error_details},
    )

    return _build_error_response(validation_error, status_code=400)


def _build_internal_error_response(
    error: Exception,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Build response for internal errors."""
    validation_error = ValidationError(
        error_type="InternalError",
        message="An internal error occurred during validation",
        retryable=True,
        conversation_id=conversation_id,
        details={"error": str(error)} if os.getenv("DEBUG", "false").lower() == "true" else None,
    )

    return _build_error_response(validation_error, status_code=500)


def _build_fallback_validation_response(
    original_response: str,
    error_message: str,
) -> ValidationResponse:
    """Build a fallback ValidationResponse when validation itself fails.

    This ensures the caller always gets a usable response, even if validation
    encountered an error.
    """
    return ValidationResponse(
        is_valid=True,  # Pass through on validation failure
        action=ValidationAction.WARN,
        validated_response=original_response,
        original_response=original_response,
        validation_results=ValidationResults(),
        sentiment=None,
        escalation=None,
        metadata=ValidationMetadata(
            validation_time_ms=0.0,
            rules_evaluated=0,
            fallback_used=False,
            fallback_reason=f"validation_error: {error_message}",
            comprehend_calls=0,
        ),
    )


# =============================================================================
# Lambda Handler
# =============================================================================


@logger.inject_lambda_context(correlation_id_path=correlation_paths.LAMBDA_FUNCTION_URL)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda entry point for response validation.

    Args:
        event: Lambda event containing validation request.
        context: Lambda context.

    Returns:
        Dict with statusCode and body containing ValidationResponse or ValidationError.
    """
    conversation_id: str | None = None

    try:
        # Parse and validate request
        logger.debug("Parsing request", extra={"event_keys": list(event.keys())})
        request = _parse_request(event)
        conversation_id = request.conversation_id

        logger.info(
            "Processing validation request",
            extra={
                "conversation_id": conversation_id,
                "tenant_id": request.tenant_id,
                "response_length": len(request.response_text),
            },
        )

        # Get service and validate
        service = get_service()
        response = service.validate(request)

        logger.info(
            "Validation complete",
            extra={
                "conversation_id": conversation_id,
                "is_valid": response.is_valid,
                "action": response.action.value,
                "validation_time_ms": response.metadata.validation_time_ms,
            },
        )

        return _build_success_response(response)

    except PydanticValidationError as e:
        logger.warning(
            "Request validation failed",
            extra={
                "conversation_id": conversation_id,
                "error_count": len(e.errors()),
            },
        )
        return _build_validation_error_response(e, conversation_id)

    except ValueError as e:
        logger.warning(
            "Invalid request",
            extra={
                "conversation_id": conversation_id,
                "error": str(e),
            },
        )
        error = ValidationError(
            error_type="InvalidRequest",
            message=str(e),
            retryable=False,
            conversation_id=conversation_id,
        )
        return _build_error_response(error, status_code=400)

    except Exception as e:
        logger.exception(
            "Unexpected error during validation",
            extra={"conversation_id": conversation_id},
        )

        # In production, we might want to fail open and return the original response
        # rather than blocking the entire flow
        fail_open = os.getenv("FAIL_OPEN_ON_ERROR", "false").lower() == "true"

        if fail_open and "response_text" in event:
            logger.warning(
                "Failing open - returning original response",
                extra={"conversation_id": conversation_id},
            )
            fallback_response = _build_fallback_validation_response(
                original_response=event.get("response_text", ""),
                error_message=str(e),
            )
            return _build_success_response(fallback_response)

        return _build_internal_error_response(e, conversation_id)
