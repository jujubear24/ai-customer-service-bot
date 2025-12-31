"""Response Validator Lambda handler with Step Functions compatibility.

Validates AI-generated responses for PII, profanity, and business rules.
Analyzes sentiment and calculates escalation scores.
Supports both Step Functions and API Gateway invocations.
"""

from __future__ import annotations

import os
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from models import (
    ValidationAction,
    ValidationMetadata,
    ValidationRequest,
    ValidationResponse,
    ValidationResults,
)
from service import ResponseValidatorService, ValidationServiceConfig
from shared.exceptions import NonRetryableError, ValidationError
from shared.sf_adapter import StepFunctionsAdapter

# =============================================================================
# Initialize
# =============================================================================

logger = Logger(service="response-validator")
tracer = Tracer(service="response-validator")
metrics = Metrics()


# =============================================================================
# Service Initialization
# =============================================================================


def _create_service() -> ResponseValidatorService:
    """Create validation service from environment configuration."""
    config = ValidationServiceConfig(
        # Feature flags
        enable_pii_detection=os.getenv("ENABLE_PII_DETECTION", "true").lower() == "true",
        enable_profanity_check=os.getenv("ENABLE_PROFANITY_CHECK", "true").lower() == "true",
        enable_business_rules=os.getenv("ENABLE_BUSINESS_RULES", "true").lower() == "true",
        enable_length_check=os.getenv("ENABLE_LENGTH_CHECK", "true").lower() == "true",
        enable_sentiment_analysis=os.getenv("ENABLE_SENTIMENT_ANALYSIS", "true").lower() == "true",
        enable_escalation_scoring=os.getenv("ENABLE_ESCALATION_SCORING", "true").lower() == "true",
        # Length settings
        min_response_length=int(os.getenv("MIN_RESPONSE_LENGTH", "20")),
        max_response_length=int(os.getenv("MAX_RESPONSE_LENGTH", "2000")),
        truncate_long_responses=os.getenv("TRUNCATE_LONG_RESPONSES", "true").lower() == "true",
        # Escalation settings
        escalation_threshold=float(os.getenv("ESCALATION_THRESHOLD", "0.70")),
        # Behavior settings
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
# Fallback Response Builder
# =============================================================================


def _build_fallback_validation_response(
    original_response: str,
    error_message: str,
) -> ValidationResponse:
    """Build a fallback ValidationResponse when validation itself fails.

    This ensures the caller always gets a usable response, even if validation
    encountered an error. Fail-open design.
    """
    return ValidationResponse(
        is_valid=True,
        action=ValidationAction.WARN,
        validated_response=original_response,
        original_response=original_response,
        validation_results=ValidationResults(),
        sentiment=None,
        escalation=None,
        metadata=ValidationMetadata(
            validation_time_ms=0.0,
            rules_evaluated=0,
            fallback_used=True,
            fallback_reason=f"validation_error: {error_message}",
            comprehend_calls=0,
        ),
    )


# =============================================================================
# Handler
# =============================================================================


@logger.inject_lambda_context(correlation_id_path=correlation_paths.LAMBDA_FUNCTION_URL)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for response validation.

    Step Functions Input:
        {
            "response_text": "I can help you reset your password...",
            "user_message": "How do I reset my password?",
            "conversation_id": "conv-123",
            "tenant_id": "tenant-456",
            "intent": "password_reset",
            "intent_confidence": 0.92
        }

    Step Functions Output:
        {
            "is_valid": true,
            "action": "PASS",
            "validated_response": "I can help you reset your password...",
            "original_response": "I can help you reset your password...",
            "validation_results": {...},
            "sentiment": {
                "sentiment": "NEUTRAL",
                "confidence": 0.85,
                "scores": {...}
            },
            "escalation": {
                "score": 0.25,
                "needs_escalation": false,
                "threshold": 0.70,
                "factors": {...}
            },
            "metadata": {...}
        }
    """
    adapter = StepFunctionsAdapter(event)
    logger.append_keys(invocation_source=adapter.source.value)

    conversation_id: str | None = None

    try:
        # Parse and validate request
        request = adapter.parse_model(ValidationRequest)
        conversation_id = request.conversation_id

        logger.info(
            "Processing validation request",
            extra={
                "conversation_id": conversation_id,
                "tenant_id": request.tenant_id,
                "response_length": len(request.response_text),
                "sentiment_enabled": request.options.analyze_sentiment,
                "escalation_enabled": request.options.calculate_escalation,
            },
        )

        # Get service and validate
        service = get_service()
        response = service.validate(request)

        # Record metrics
        metrics.add_metric(name="ValidationRequests", unit=MetricUnit.Count, value=1)

        if response.is_valid:
            metrics.add_metric(name="ValidationPassed", unit=MetricUnit.Count, value=1)
        else:
            metrics.add_metric(name="ValidationFailed", unit=MetricUnit.Count, value=1)

        metrics.add_metric(
            name=f"ValidationAction_{response.action.value}",
            unit=MetricUnit.Count,
            value=1,
        )

        if response.needs_escalation:
            metrics.add_metric(name="EscalationTriggered", unit=MetricUnit.Count, value=1)

        logger.info(
            "Validation complete",
            extra={
                "conversation_id": conversation_id,
                "is_valid": response.is_valid,
                "action": response.action.value,
                "validation_time_ms": response.metadata.validation_time_ms,
                "needs_escalation": response.needs_escalation,
                "sentiment": response.sentiment.sentiment.value if response.sentiment else None,
            },
        )

        return adapter.success_response(response)

    except ValidationError as e:
        logger.warning(
            "Request validation failed",
            extra={"conversation_id": conversation_id, "error": str(e)},
        )
        metrics.add_metric(name="RequestValidationErrors", unit=MetricUnit.Count, value=1)
        return adapter.error_response(e, status_code=400)

    except Exception as e:
        logger.exception("Unexpected error during validation")
        metrics.add_metric(name="UnexpectedErrors", unit=MetricUnit.Count, value=1)

        # Check if we should fail open
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
            return adapter.success_response(fallback_response)

        error = NonRetryableError(
            message=f"Validation failed: {str(e)}",
            details={
                "original_error": type(e).__name__,
                "conversation_id": conversation_id,
            },
        )
        return adapter.error_response(error, status_code=500)


# Default response for fail-open behavior
DEFAULT_VALIDATION_RESPONSE: dict[str, Any] = {
    "is_valid": True,
    "action": "PASS",
    "validated_response": "",
    "original_response": "",
    "validation_results": {},
    "sentiment": None,
    "escalation": None,
    "metadata": {
        "validation_time_ms": 0.0,
        "rules_evaluated": 0,
        "fallback_used": True,
        "fallback_reason": "step_functions_fallback",
        "comprehend_calls": 0,
    },
    "_default_used": True,
}
