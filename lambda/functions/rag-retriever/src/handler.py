"""
RAG Retriever Lambda Handler.

Entry point for retrieving documents from Amazon Bedrock Knowledge Base.
Integrates with the Bedrock Handler Lambda via the rag_context field.

Environment Variables:
    KNOWLEDGE_BASE_ID: ID of the Bedrock Knowledge Base
    LOG_LEVEL: Logging level (default: INFO)
    POWERTOOLS_SERVICE_NAME: Service name for logging
"""

from __future__ import annotations

import os
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import ValidationError

from models import RetrievalError, RetrievalRequest, RetrievalResponse
from service import (
    KnowledgeBaseNotFoundError,
    RetrievalService,
    RetrievalServiceError,
    ThrottlingError,
)

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()

# Configuration
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Lazy-initialized service
_service: RetrievalService | None = None


def get_service() -> RetrievalService:
    """Get or create the retrieval service (singleton pattern)."""
    global _service
    if _service is None:
        if not KNOWLEDGE_BASE_ID:
            raise ValueError("KNOWLEDGE_BASE_ID environment variable not set")
        _service = RetrievalService(
            knowledge_base_id=KNOWLEDGE_BASE_ID,
            region=AWS_REGION,
        )
    return _service


def create_error_response(
    status_code: int,
    error: RetrievalError,
) -> dict[str, Any]:
    """Create a standardized error response."""
    return {
        "statusCode": status_code,
        "body": error.model_dump_json(),
        "headers": {
            "Content-Type": "application/json",
        },
    }


def create_success_response(response: RetrievalResponse) -> dict[str, Any]:
    """Create a standardized success response."""
    return {
        "statusCode": 200,
        "body": response.model_dump_json(),
        "headers": {
            "Content-Type": "application/json",
        },
    }


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """
    Lambda handler for RAG retrieval.

    Accepts a retrieval request and returns matching documents from
    the Bedrock Knowledge Base.

    Args:
        event: Lambda event containing retrieval request
        context: Lambda context

    Returns:
        API Gateway-style response with retrieval results or error
    """
    logger.info("Processing retrieval request", event_keys=list(event.keys()))

    try:
        # Parse and validate request
        request = _parse_request(event)
        logger.info(
            "Request validated",
            tenant_id=request.tenant_id,
            query_length=len(request.query),
            top_k=request.top_k,
        )

        # Add correlation IDs to logger
        logger.append_keys(
            tenant_id=request.tenant_id,
            conversation_id=request.conversation_id,
        )

        # Perform retrieval
        service = get_service()
        response = service.retrieve(request)

        # Record metrics
        _record_metrics(response)

        logger.info(
            "Retrieval successful",
            documents_returned=len(response.documents),
            average_score=round(response.average_score, 3),
            retrieval_time_ms=round(response.retrieval_time_ms, 2),
        )

        return create_success_response(response)

    except ValidationError as e:
        logger.warning("Validation error", errors=e.errors())
        metrics.add_metric(name="ValidationErrors", unit=MetricUnit.Count, value=1)
        return create_error_response(
            400,
            RetrievalError(
                error_type="VALIDATION_ERROR",
                message="Invalid request format",
                details={"validation_errors": e.errors()},
                retryable=False,
            ),
        )

    except KnowledgeBaseNotFoundError as e:
        logger.error("Knowledge base not found", error=str(e))
        metrics.add_metric(name="KnowledgeBaseNotFound", unit=MetricUnit.Count, value=1)
        return create_error_response(
            404,
            RetrievalError(
                error_type=e.error_type,
                message=str(e),
                retryable=False,
            ),
        )

    except ThrottlingError as e:
        logger.warning("Request throttled after retries", error=str(e))
        metrics.add_metric(name="ThrottlingErrors", unit=MetricUnit.Count, value=1)
        return create_error_response(
            429,
            RetrievalError(
                error_type=e.error_type,
                message=str(e),
                retryable=True,
            ),
        )

    except RetrievalServiceError as e:
        logger.error(
            "Retrieval service error",
            error=str(e),
            error_type=e.error_type,
            details=e.details,
        )
        metrics.add_metric(name="ServiceErrors", unit=MetricUnit.Count, value=1)
        return create_error_response(
            500,
            RetrievalError(
                error_type=e.error_type,
                message=str(e),
                details=e.details,
                retryable=e.retryable,
            ),
        )

    except ValueError as e:
        logger.error("Configuration error", error=str(e))
        metrics.add_metric(name="ConfigurationErrors", unit=MetricUnit.Count, value=1)
        return create_error_response(
            500,
            RetrievalError(
                error_type="CONFIGURATION_ERROR",
                message=str(e),
                retryable=False,
            ),
        )

    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        metrics.add_metric(name="UnexpectedErrors", unit=MetricUnit.Count, value=1)
        return create_error_response(
            500,
            RetrievalError(
                error_type="INTERNAL_ERROR",
                message="An unexpected error occurred",
                retryable=True,
            ),
        )


def _parse_request(event: dict[str, Any]) -> RetrievalRequest:
    """
    Parse the retrieval request from the Lambda event.

    Supports both direct invocation and API Gateway events.
    """
    # Check if this is an API Gateway event
    if "body" in event and isinstance(event.get("body"), str):
        import json

        body = json.loads(event["body"])
    elif "body" in event and isinstance(event.get("body"), dict):
        body = event["body"]
    else:
        # Direct invocation - event IS the request
        body = event

    return RetrievalRequest.model_validate(body)


def _record_metrics(response: RetrievalResponse) -> None:
    """Record CloudWatch metrics for the retrieval."""
    metrics.add_metric(
        name="DocumentsRetrieved",
        unit=MetricUnit.Count,
        value=len(response.documents),
    )
    metrics.add_metric(
        name="RetrievalLatency",
        unit=MetricUnit.Milliseconds,
        value=response.retrieval_time_ms,
    )

    if response.has_results:
        metrics.add_metric(
            name="AverageRelevanceScore",
            unit=MetricUnit.NoUnit,
            value=response.average_score,
        )
    else:
        metrics.add_metric(
            name="NoResultsReturned",
            unit=MetricUnit.Count,
            value=1,
        )
