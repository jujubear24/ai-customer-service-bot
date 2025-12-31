"""Escalation Router Lambda handler with Step Functions compatibility.

Routes escalated conversations to human agents via SQS FIFO queue.
Updates conversation status in DynamoDB and optionally sends SNS notifications.
Supports both Step Functions and API Gateway invocations.
"""

from __future__ import annotations

import os
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from models import (
    EscalationData,
    EscalationFactors,
    EscalationRequest,
    SentimentData,
)
from service import EscalationRouterService, QueueError, create_escalation_router_from_env
from shared.exceptions import (
    NonRetryableError,
    RetryableError,
    ValidationError,
)
from shared.sf_adapter import StepFunctionsAdapter

# =============================================================================
# Initialize
# =============================================================================

logger = Logger(service="escalation-router")
tracer = Tracer(service="escalation-router")
metrics = Metrics()

# Lazy-loaded service instance
_service: EscalationRouterService | None = None


def get_service() -> EscalationRouterService:
    """Get or create the escalation router service."""
    global _service
    if _service is None:
        _service = create_escalation_router_from_env()
    return _service


# =============================================================================
# Request Parsing
# =============================================================================


def _parse_escalation_request(payload: dict[str, Any]) -> EscalationRequest:
    """Parse and validate the escalation request from payload.

    Args:
        payload: Request payload (already extracted by adapter).

    Returns:
        Validated EscalationRequest.

    Raises:
        ValidationError: If required fields are missing or invalid.
    """
    # Validate required fields
    if "escalation" not in payload:
        raise ValidationError(
            message="Missing required field: escalation",
            field="escalation",
        )

    if "conversation_id" not in payload:
        raise ValidationError(
            message="Missing required field: conversation_id",
            field="conversation_id",
        )

    if "tenant_id" not in payload:
        raise ValidationError(
            message="Missing required field: tenant_id",
            field="tenant_id",
        )

    if "last_user_message" not in payload:
        raise ValidationError(
            message="Missing required field: last_user_message",
            field="last_user_message",
        )

    # Build escalation factors
    factors_data = payload.get("escalation", {}).get("factors", {})
    factors = EscalationFactors(
        explicit_intent=factors_data.get("explicit_intent", 0.0),
        negative_sentiment=factors_data.get("negative_sentiment", 0.0),
        urgency=factors_data.get("urgency", 0.0),
        repeated_question=factors_data.get("repeated_question", 0.0),
        low_confidence=factors_data.get("low_confidence", 0.0),
    )

    # Build escalation data
    escalation_data = payload.get("escalation", {})
    escalation = EscalationData(
        score=escalation_data.get("score", 0.0),
        needs_escalation=escalation_data.get("needs_escalation", False),
        threshold=escalation_data.get("threshold", 0.70),
        factors=factors,
        primary_reason=escalation_data.get("primary_reason"),
    )

    # Build sentiment data (optional)
    sentiment = None
    sentiment_data = payload.get("sentiment")
    if sentiment_data:
        sentiment = SentimentData(
            sentiment=sentiment_data.get("sentiment", "NEUTRAL"),
            confidence=sentiment_data.get("confidence", 0.0),
            negative_score=sentiment_data.get("negative_score", 0.0),
        )

    # Build the request
    return EscalationRequest(
        conversation_id=payload["conversation_id"],
        tenant_id=payload["tenant_id"],
        user_id=payload.get("user_id"),
        message_id=payload.get("message_id"),
        escalation=escalation,
        sentiment=sentiment,
        last_user_message=payload["last_user_message"],
        last_ai_response=payload.get("last_ai_response"),
        message_count=payload.get("message_count", 1),
        intent=payload.get("intent"),
        intent_confidence=payload.get("intent_confidence"),
        urgency=payload.get("urgency"),
        previous_intents=payload.get("previous_intents", []),
        metadata=payload.get("metadata", {}),
    )


# =============================================================================
# Handler
# =============================================================================


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for escalation routing.

    Step Functions Input:
        {
            "conversation_id": "conv-123",
            "tenant_id": "tenant-456",
            "user_id": "user-789",
            "escalation": {
                "score": 0.85,
                "needs_escalation": true,
                "threshold": 0.70,
                "factors": {
                    "explicit_intent": 1.0,
                    "negative_sentiment": 0.75
                },
                "primary_reason": "Explicit escalation request"
            },
            "sentiment": {
                "sentiment": "NEGATIVE",
                "confidence": 0.88
            },
            "last_user_message": "I want to speak to a manager!"
        }

    Step Functions Output:
        {
            "success": true,
            "escalation_id": "esc-abc123",
            "priority": "HIGH",
            "queue_message_id": "msg-xyz",
            "notification_sent": false,
            "customer_message": "I understand your concern...",
            "estimated_wait": "< 5 minutes",
            "processed_at": "2025-01-15T10:30:00Z"
        }
    """
    adapter = StepFunctionsAdapter(event)
    logger.append_keys(invocation_source=adapter.source.value)

    try:
        # Parse and validate request
        payload = adapter.get_payload()
        request = _parse_escalation_request(payload)

        logger.info(
            "Processing escalation request",
            extra={
                "conversation_id": request.conversation_id,
                "escalation_score": request.escalation.score,
                "needs_escalation": request.escalation.needs_escalation,
            },
        )

        # Validate escalation is actually needed
        if not request.escalation.needs_escalation:
            logger.warning(
                "Received request with needs_escalation=False",
                extra={"conversation_id": request.conversation_id},
            )
            return adapter.success_response(
                {
                    "success": False,
                    "error": "Escalation not required",
                    "escalation_id": None,
                    "priority": None,
                }
            )

        # Route the escalation
        service = get_service()
        result = service.route_escalation(request)

        # Record metrics
        metrics.add_metric(name="EscalationsRouted", unit=MetricUnit.Count, value=1)
        metrics.add_metric(
            name=f"EscalationPriority_{result.priority.value}",
            unit=MetricUnit.Count,
            value=1,
        )

        logger.info(
            "Escalation routed successfully",
            extra={
                "escalation_id": result.escalation_id,
                "priority": result.priority.value,
                "conversation_id": request.conversation_id,
            },
        )

        return adapter.success_response(
            {
                "success": result.success,
                "escalation_id": result.escalation_id,
                "priority": result.priority.value,
                "queue_message_id": result.queue_message_id,
                "notification_sent": result.notification_sent,
                "customer_message": result.customer_message,
                "estimated_wait": result.estimated_wait,
                "processed_at": result.processed_at.isoformat(),
                "error_message": result.error_message,
            }
        )

    except ValidationError as e:
        logger.warning("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="ValidationErrors", unit=MetricUnit.Count, value=1)
        return adapter.error_response(e, status_code=400)

    except QueueError as e:
        # Queue errors are critical but potentially retryable
        logger.error("Queue error", extra={"error": str(e)})
        metrics.add_metric(name="QueueErrors", unit=MetricUnit.Count, value=1)
        queue_error = RetryableError(
            message=f"Failed to send to escalation queue: {str(e)}",
            error_code="QUEUE_ERROR",
            retry_after_seconds=5,
        )
        return adapter.error_response(queue_error, status_code=503)

    except Exception as e:
        logger.exception("Unexpected error")
        metrics.add_metric(name="UnexpectedErrors", unit=MetricUnit.Count, value=1)

        # Check if we should fail open
        fail_open = os.environ.get("FAIL_OPEN_ON_ERROR", "false").lower() == "true"

        if fail_open:
            logger.warning("Failing open - returning success despite error")
            return adapter.success_response(
                {
                    "success": True,
                    "escalation_id": None,
                    "priority": None,
                    "error": "Escalation routing failed, but continuing",
                    "fail_open": True,
                }
            )

        unexpected_error = NonRetryableError(
            message=f"Escalation routing failed: {str(e)}",
            details={"original_error": type(e).__name__},
        )
        return adapter.error_response(unexpected_error, status_code=500)


# Default response for fail-open behavior
DEFAULT_ESCALATION_RESPONSE: dict[str, Any] = {
    "success": True,
    "escalation_id": None,
    "priority": None,
    "queue_message_id": None,
    "notification_sent": False,
    "customer_message": None,
    "estimated_wait": None,
    "fail_open": True,
    "_default_used": True,
}
