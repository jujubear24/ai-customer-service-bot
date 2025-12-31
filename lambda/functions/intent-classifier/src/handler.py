"""Intent Classifier Lambda handler with Step Functions compatibility.

Supports both Step Functions and API Gateway invocations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import BaseModel, Field, field_validator

from shared.exceptions import NonRetryableError, ValidationError
from shared.sf_adapter import StepFunctionsAdapter

# Import classifier
if TYPE_CHECKING:
    from src.classifier import IntentClassifier
else:
    try:
        from classifier import IntentClassifier
    except ImportError:
        from src.classifier import IntentClassifier

# =============================================================================
# Initialize
# =============================================================================

logger = Logger(service="intent-classifier")
tracer = Tracer(service="intent-classifier")
metrics = Metrics()

# Initialize classifier once (reuse across invocations)
classifier = IntentClassifier()


# =============================================================================
# Request/Response Models
# =============================================================================


class IntentClassifierRequest(BaseModel):
    """Request model for intent classification."""

    message: str = Field(..., min_length=1, max_length=2000, description="User message to classify")
    conversation_id: str | None = Field(default=None, description="Conversation ID for correlation")
    conversation_history: list[dict[str, Any]] | None = Field(
        default=None, max_length=50, description="Optional conversation history"
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Strip whitespace and validate non-empty."""
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        return v


class IntentClassifierResponse(BaseModel):
    """Response model for intent classification."""

    intent: str = Field(..., description="Classified intent")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")
    entities: dict[str, Any] = Field(default_factory=dict, description="Extracted entities")
    requires_context: bool = Field(default=False, description="Whether context is needed")
    conversation_id: str | None = Field(default=None, description="Echoed conversation ID")


# =============================================================================
# Handler
# =============================================================================


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for intent classification.

    Step Functions Input:
        {
            "message": "I need to speak to a manager",
            "conversation_id": "conv-123"
        }

    Step Functions Output:
        {
            "intent": "escalation",
            "confidence": 0.95,
            "entities": {},
            "requires_context": false,
            "conversation_id": "conv-123"
        }
    """
    adapter = StepFunctionsAdapter(event)
    logger.append_keys(invocation_source=adapter.source.value)

    try:
        # Parse and validate request
        request = adapter.parse_model(IntentClassifierRequest)

        logger.info(
            "Processing intent classification",
            extra={
                "conversation_id": request.conversation_id,
                "message_length": len(request.message),
            },
        )

        # Classify intent
        classification = classifier.classify(request.message)

        # Build response
        response = IntentClassifierResponse(
            intent=classification.intent,
            confidence=classification.confidence,
            entities=classification.entities,
            requires_context=classification.requires_context,
            conversation_id=request.conversation_id,
        )

        # Record metrics
        metrics.add_metric(name="IntentClassified", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name=f"Intent_{classification.intent}", unit=MetricUnit.Count, value=1)

        logger.info(
            "Intent classified successfully",
            extra={
                "intent": classification.intent,
                "confidence": classification.confidence,
            },
        )

        return adapter.success_response(response)

    except ValidationError as e:
        logger.warning("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="ValidationErrors", unit=MetricUnit.Count, value=1)
        return adapter.error_response(e, status_code=400)

    except Exception as e:
        logger.exception("Unexpected error during classification")
        metrics.add_metric(name="ClassificationErrors", unit=MetricUnit.Count, value=1)
        error = NonRetryableError(
            message=f"Classification failed: {str(e)}",
            details={"original_error": type(e).__name__},
        )
        return adapter.error_response(error, status_code=500)


# Default response for fail-open behavior in Step Functions
DEFAULT_INTENT_RESPONSE: dict[str, Any] = {
    "intent": "general_inquiry",
    "confidence": 0.0,
    "entities": {},
    "requires_context": False,
    "conversation_id": None,
    "_default_used": True,
}
