"""Lambda handler for Escalation Router.

This Lambda routes escalated conversations to human agents via SQS FIFO queue,
updates conversation status in DynamoDB, and optionally sends SNS notifications.
"""

from __future__ import annotations

import os
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import ValidationError

from models import (
    EscalationData,
    EscalationFactors,
    EscalationRequest,
    SentimentData,
)
from service import EscalationRouterService, create_escalation_router_from_env

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()

# Lazy-loaded service instance
_service: EscalationRouterService | None = None


def get_service() -> EscalationRouterService:
    """Get or create the escalation router service.

    Returns:
        Configured EscalationRouterService instance.
    """
    global _service
    if _service is None:
        _service = create_escalation_router_from_env()
    return _service


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for escalation routing.

    Args:
        event: Lambda event containing escalation request data.
        context: Lambda context.

    Returns:
        Response dict with escalation routing results.

    Event Format (from Chat Orchestrator):
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
                    "negative_sentiment": 0.75,
                    "urgency": 1.0,
                    "repeated_question": 0.5,
                    "low_confidence": 0.0
                },
                "primary_reason": "Explicit escalation request"
            },
            "sentiment": {
                "sentiment": "NEGATIVE",
                "confidence": 0.88,
                "negative_score": 0.88
            },
            "last_user_message": "I want to speak to a manager!",
            "message_count": 5,
            "intent": "complaint",
            "urgency": "high"
        }

    Response Format:
        {
            "statusCode": 200,
            "body": {
                "success": true,
                "escalation_id": "esc-abc123",
                "priority": "HIGH",
                "customer_message": "I understand your concern...",
                "estimated_wait": "< 5 minutes"
            }
        }
    """
    logger.info("Processing escalation request", extra={"event_keys": list(event.keys())})

    try:
        # Parse and validate request
        request = _parse_request(event)

        # Validate escalation is actually needed
        if not request.escalation.needs_escalation:
            logger.warning(
                "Received request with needs_escalation=False",
                extra={"conversation_id": request.conversation_id},
            )
            return _build_response(
                status_code=200,
                body={
                    "success": False,
                    "error": "Escalation not required",
                    "escalation_id": None,
                },
            )

        # Route the escalation
        service = get_service()
        result = service.route_escalation(request)

        logger.info(
            "Escalation routed successfully",
            extra={
                "escalation_id": result.escalation_id,
                "priority": result.priority.value,
                "conversation_id": request.conversation_id,
            },
        )

        return _build_response(
            status_code=200,
            body={
                "success": result.success,
                "escalation_id": result.escalation_id,
                "priority": result.priority.value,
                "queue_message_id": result.queue_message_id,
                "notification_sent": result.notification_sent,
                "customer_message": result.customer_message,
                "estimated_wait": result.estimated_wait,
                "processed_at": result.processed_at.isoformat(),
            },
        )

    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        metrics.add_metric(name="ValidationErrors", unit="Count", value=1)
        return _build_response(
            status_code=400,
            body={
                "success": False,
                "error": "Invalid request format",
                "details": e.errors(),
            },
        )

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        metrics.add_metric(name="UnexpectedErrors", unit="Count", value=1)

        # Check if we should fail open
        fail_open = os.environ.get("FAIL_OPEN_ON_ERROR", "false").lower() == "true"

        if fail_open:
            logger.warning("Failing open - returning success despite error")
            return _build_response(
                status_code=200,
                body={
                    "success": True,
                    "escalation_id": None,
                    "error": "Escalation routing failed, but continuing",
                    "fail_open": True,
                },
            )

        return _build_response(
            status_code=500,
            body={
                "success": False,
                "error": str(e),
            },
        )


def _parse_request(event: dict[str, Any]) -> EscalationRequest:
    """Parse and validate the incoming event.

    Args:
        event: Raw Lambda event.

    Returns:
        Validated EscalationRequest.

    Raises:
        ValidationError: If event doesn't match expected schema.
    """
    # Handle both direct invocation and API Gateway formats
    body = event.get("body", event)
    if isinstance(body, str):
        import json

        body = json.loads(body)

    # Build escalation factors
    factors_data = body.get("escalation", {}).get("factors", {})
    factors = EscalationFactors(
        explicit_intent=factors_data.get("explicit_intent", 0.0),
        negative_sentiment=factors_data.get("negative_sentiment", 0.0),
        urgency=factors_data.get("urgency", 0.0),
        repeated_question=factors_data.get("repeated_question", 0.0),
        low_confidence=factors_data.get("low_confidence", 0.0),
    )

    # Build escalation data
    escalation_data = body.get("escalation", {})
    escalation = EscalationData(
        score=escalation_data.get("score", 0.0),
        needs_escalation=escalation_data.get("needs_escalation", False),
        threshold=escalation_data.get("threshold", 0.70),
        factors=factors,
        primary_reason=escalation_data.get("primary_reason"),
    )

    # Build sentiment data (optional)
    sentiment = None
    sentiment_data = body.get("sentiment")
    if sentiment_data:
        sentiment = SentimentData(
            sentiment=sentiment_data.get("sentiment", "NEUTRAL"),
            confidence=sentiment_data.get("confidence", 0.0),
            negative_score=sentiment_data.get("negative_score", 0.0),
        )

    # Build the request
    return EscalationRequest(
        conversation_id=body["conversation_id"],
        tenant_id=body["tenant_id"],
        user_id=body.get("user_id"),
        message_id=body.get("message_id"),
        escalation=escalation,
        sentiment=sentiment,
        last_user_message=body["last_user_message"],
        last_ai_response=body.get("last_ai_response"),
        message_count=body.get("message_count", 1),
        intent=body.get("intent"),
        intent_confidence=body.get("intent_confidence"),
        urgency=body.get("urgency"),
        previous_intents=body.get("previous_intents", []),
        metadata=body.get("metadata", {}),
    )


def _build_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build a Lambda response.

    Args:
        status_code: HTTP status code.
        body: Response body.

    Returns:
        Lambda response dict.
    """
    import json

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": json.dumps(body, default=str),
    }
