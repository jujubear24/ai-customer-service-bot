"""RAG Retriever Lambda handler with Step Functions compatibility.

Retrieves documents from Amazon Bedrock Knowledge Base.
Supports both Step Functions and API Gateway invocations.
"""

from __future__ import annotations

import os
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from models import RetrievalRequest
from service import (
    KnowledgeBaseNotFoundError,
    RetrievalService,
    RetrievalServiceError,
)
from service import (
    ThrottlingError as ServiceThrottlingError,
)
from shared.exceptions import (
    NonRetryableError,
    ThrottlingError,
    ValidationError,
)
from shared.sf_adapter import StepFunctionsAdapter

# =============================================================================
# Initialize
# =============================================================================

logger = Logger(service="rag-retriever")
tracer = Tracer(service="rag-retriever")
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
            raise NonRetryableError(
                message="KNOWLEDGE_BASE_ID environment variable not set",
                error_code="CONFIGURATION_ERROR",
            )
        _service = RetrievalService(
            knowledge_base_id=KNOWLEDGE_BASE_ID,
            region=AWS_REGION,
        )
    return _service


# =============================================================================
# Handler
# =============================================================================


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for RAG retrieval.

    Step Functions Input:
        {
            "query": "How do I reset my password?",
            "tenant_id": "tenant-456",
            "conversation_id": "conv-123",
            "top_k": 5,
            "min_score": 0.5
        }

    Step Functions Output:
        {
            "documents": [
                {
                    "content": "To reset your password...",
                    "score": 0.89,
                    "source_name": "password-guide.pdf",
                    "source_uri": "s3://...",
                    "metadata": {}
                }
            ],
            "query": "How do I reset my password?",
            "total_found": 3,
            "retrieval_time_ms": 156.2
        }
    """
    adapter = StepFunctionsAdapter(event)
    logger.append_keys(invocation_source=adapter.source.value)

    try:
        # Parse and validate request
        request = adapter.parse_model(RetrievalRequest)

        logger.info(
            "Processing retrieval request",
            extra={
                "tenant_id": request.tenant_id,
                "conversation_id": request.conversation_id,
                "query_length": len(request.query),
                "top_k": request.top_k,
            },
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
            metrics.add_metric(name="NoResultsReturned", unit=MetricUnit.Count, value=1)

        logger.info(
            "Retrieval successful",
            extra={
                "documents_returned": len(response.documents),
                "average_score": round(response.average_score, 3),
                "retrieval_time_ms": round(response.retrieval_time_ms, 2),
            },
        )

        return adapter.success_response(response)

    except ValidationError as e:
        logger.warning("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="ValidationErrors", unit=MetricUnit.Count, value=1)
        return adapter.error_response(e, status_code=400)

    except KnowledgeBaseNotFoundError as e:
        logger.error("Knowledge base not found", extra={"error": str(e)})
        metrics.add_metric(name="KnowledgeBaseNotFound", unit=MetricUnit.Count, value=1)
        not_found_error = NonRetryableError(
            message=str(e),
            error_code="KNOWLEDGE_BASE_NOT_FOUND",
        )
        return adapter.error_response(not_found_error, status_code=404)

    except ServiceThrottlingError as e:
        logger.warning("Request throttled", extra={"error": str(e)})
        metrics.add_metric(name="ThrottlingErrors", unit=MetricUnit.Count, value=1)
        # Convert to shared ThrottlingError for Step Functions
        throttle_error = ThrottlingError(
            message=str(e),
            service="bedrock-agent-runtime",
            retry_after_seconds=5,
        )
        return adapter.error_response(throttle_error, status_code=429)

    except RetrievalServiceError as e:
        logger.error(
            "Retrieval service error",
            extra={
                "error": str(e),
                "error_type": e.error_type,
                "retryable": e.retryable,
            },
        )
        metrics.add_metric(name="ServiceErrors", unit=MetricUnit.Count, value=1)

        if e.retryable:
            from shared.exceptions import RetryableError

            retry_error = RetryableError(
                message=str(e),
                error_code=e.error_type,
                details=e.details,
            )
            return adapter.error_response(retry_error, status_code=503)
        else:
            service_error = NonRetryableError(
                message=str(e),
                error_code=e.error_type,
                details=e.details,
            )
            return adapter.error_response(service_error, status_code=500)

    except Exception as e:
        logger.exception("Unexpected error")
        metrics.add_metric(name="UnexpectedErrors", unit=MetricUnit.Count, value=1)
        unexpected_error = NonRetryableError(
            message=f"Retrieval failed: {str(e)}",
            details={"original_error": type(e).__name__},
        )
        return adapter.error_response(unexpected_error, status_code=500)


# Default response for fail-open behavior
DEFAULT_RAG_RESPONSE: dict[str, Any] = {
    "documents": [],
    "query": "",
    "total_found": 0,
    "retrieval_time_ms": 0.0,
    "_default_used": True,
}
