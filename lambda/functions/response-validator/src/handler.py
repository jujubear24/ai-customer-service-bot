"""Main handler for response-validator Lambda function."""

import json
from typing import Any

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from shared.config import Config
from shared.exceptions import LambdaError, ValidationError
from shared.metrics import MetricUnit, metrics
from shared.types import LambdaResponse
from shared.utils import format_response, get_correlation_id

# Initialize
config = Config.from_env()
logger = Logger(service="response-validator")
tracer = Tracer(service="response-validator")


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> LambdaResponse:
    """
    Main Lambda handler function.

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        Response dictionary with statusCode, headers, and body
    """
    correlation_id = get_correlation_id(event)

    logger.info("Processing event for response-validator", extra={"correlation_id": correlation_id})

    # Add custom metric
    metrics.add_metric(name="FunctionInvocation", unit=MetricUnit.Count, value=1)

    try:
        # Validate input
        validate_event(event)

        # Process event
        result = process_event(event, context)

        logger.info("Successfully processed event", extra={"correlation_id": correlation_id})

        metrics.add_metric(name="SuccessfulProcessing", unit=MetricUnit.Count, value=1)

        return format_response(
            200,
            {
                "message": "Success",
                "data": result,
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
def validate_event(event: dict[str, Any]) -> None:
    """
    Validate incoming event.

    Args:
        event: Lambda event object

    Raises:
        ValidationError: If event is invalid
    """
    # TODO: Implement validation logic specific to response-validator
    if not event:
        raise ValidationError("Event cannot be empty")


@tracer.capture_method
def process_event(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """
    Process the incoming event.

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        Processed result dictionary
    """
    # TODO: Implement your business logic here
    logger.debug(f"Processing event: {json.dumps(event)}")

    return {
        "function": "response-validator",
        "request_id": context.aws_request_id if hasattr(context, "aws_request_id") else None,
        "remaining_time_ms": context.get_remaining_time_in_millis()
        if hasattr(context, "get_remaining_time_in_millis")
        else None,
    }
