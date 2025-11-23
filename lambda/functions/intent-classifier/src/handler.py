"""Main handler for intent-classifier Lambda function."""

from typing import TYPE_CHECKING, Any

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from shared.config import Config
from shared.exceptions import LambdaError, ValidationError
from shared.metrics import MetricUnit, metrics
from shared.types import LambdaResponse
from shared.utils import format_response, get_correlation_id, parse_json_body

# Import classifier from same directory (not from src package)
if TYPE_CHECKING:
    from src.classifier import classify_intent
else:
    try:
        from classifier import classify_intent
    except ImportError:
        # Fallback for local testing where src is a package
        from src.classifier import classify_intent

# Initialize
config = Config.from_env()
logger = Logger(service="intent-classifier")
tracer = Tracer(service="intent-classifier")


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> LambdaResponse:
    """
    Main Lambda handler function for intent classification.

    Expected input (API Gateway):
    {
        "body": {
            "message": "I need to speak to a manager",
            "conversation_history": []  // Optional
        }
    }

    Returns:
        Response with classified intent, confidence, and entities
    """
    correlation_id = get_correlation_id(event)

    logger.info(
        "Processing intent classification request", extra={"correlation_id": correlation_id}
    )

    # Add custom metric
    metrics.add_metric(name="FunctionInvocation", unit=MetricUnit.Count, value=1)

    try:
        # Parse and validate input
        body = parse_json_body(event.get("body"))
        message, conversation_history = validate_and_extract_input(body)

        # Classify intent
        classification = classify_intent(message, conversation_history)

        logger.info(
            "Successfully classified intent",
            extra={
                "correlation_id": correlation_id,
                "intent": classification.intent,
                "confidence": classification.confidence,
            },
        )

        metrics.add_metric(name="SuccessfulClassification", unit=MetricUnit.Count, value=1)
        metrics.add_metric(
            name=f"Intent_{classification.intent}",
            unit=MetricUnit.Count,
            value=1,
        )

        return format_response(
            200,
            {
                "message": "Intent classified successfully",
                "classification": classification.model_dump(),
                "correlation_id": correlation_id,
            },
        )

    except ValidationError as e:
        logger.warning(f"Validation error: {str(e)}", exc_info=True)
        metrics.add_metric(name="ValidationError", unit=MetricUnit.Count, value=1)

        return format_response(
            400,
            {
                "error": "ValidationError",
                "message": str(e),
                "correlation_id": correlation_id,
            },
        )

    except LambdaError as e:
        logger.error(f"Lambda error: {str(e)}", exc_info=True)
        metrics.add_metric(name="LambdaError", unit=MetricUnit.Count, value=1)

        return format_response(
            500,
            {
                "error": type(e).__name__,
                "message": str(e),
                "correlation_id": correlation_id,
            },
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        metrics.add_metric(name="UnexpectedError", unit=MetricUnit.Count, value=1)

        return format_response(
            500,
            {
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id,
            },
        )


@tracer.capture_method
def validate_and_extract_input(body: dict[str, Any]) -> tuple[str, list[dict[str, Any]] | None]:
    """
    Validate incoming request body and extract required fields.

    Args:
        body: Parsed request body

    Returns:
        Tuple of (message, conversation_history)

    Raises:
        ValidationError: If validation fails
    """
    if not body:
        raise ValidationError("Request body cannot be empty")

    # Extract and validate message
    message = body.get("message", "").strip()
    if not message:
        raise ValidationError("'message' field is required and cannot be empty")

    if len(message) > 2000:
        raise ValidationError("'message' exceeds maximum length of 2000 characters")

    # Extract optional conversation history
    conversation_history = body.get("conversation_history")
    if conversation_history is not None:
        if not isinstance(conversation_history, list):
            raise ValidationError("'conversation_history' must be an array")

        if len(conversation_history) > 50:
            raise ValidationError("'conversation_history' exceeds maximum of 50 messages")

    logger.debug(
        f"Validated input - message length: {len(message)}, "
        f"history length: {len(conversation_history) if conversation_history else 0}"
    )

    return message, conversation_history
