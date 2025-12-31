"""Context Builder Lambda handler with Step Functions compatibility.

Retrieves conversation history and builds context for Bedrock.
Supports both Step Functions and API Gateway invocations.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from shared.exceptions import DynamoDBError, NonRetryableError, RetryableError, ValidationError
from shared.sf_adapter import StepFunctionsAdapter, is_retryable_boto_error
from shared.types import ConversationContext, MessageContext

# =============================================================================
# Initialize
# =============================================================================

logger = Logger(service="context-builder")
tracer = Tracer(service="context-builder")
metrics = Metrics()

# Environment variables
TABLE_NAME = os.environ.get("TABLE_NAME", "")
MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", "10"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "8000"))

# AWS clients
dynamodb = boto3.resource("dynamodb")


# =============================================================================
# Request/Response Models
# =============================================================================


class ContextBuilderRequest(BaseModel):
    """Request model for context building."""

    conversation_id: str = Field(..., min_length=1, description="Conversation ID")
    include_system_prompt: bool = Field(default=True, description="Include system prompt tokens")
    max_messages: int | None = Field(
        default=None, ge=1, le=100, description="Max messages override"
    )
    max_tokens: int | None = Field(
        default=None, ge=100, le=32000, description="Max tokens override"
    )


class ContextBuilderResponse(BaseModel):
    """Response model for context building."""

    conversation_id: str = Field(..., description="Conversation ID")
    context: ConversationContext = Field(..., description="Built conversation context")
    timestamp: str = Field(..., description="ISO timestamp")


# =============================================================================
# Context Builder Logic
# =============================================================================


class ContextBuilder:
    """Build conversation context from DynamoDB."""

    def __init__(self, table_name: str, max_messages: int, max_tokens: int) -> None:
        """Initialize context builder."""
        self.table = dynamodb.Table(table_name)
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.tokens_per_message_estimate = 100

    @tracer.capture_method
    def get_conversation_metadata(self, conversation_id: str) -> dict[str, Any] | None:
        """Retrieve conversation metadata."""
        try:
            response = self.table.get_item(Key={"pk": f"CONV#{conversation_id}", "sk": "METADATA"})
            item = response.get("Item")
            return dict(item) if item else None
        except ClientError as e:
            if is_retryable_boto_error(e):
                raise RetryableError(
                    message=f"DynamoDB temporarily unavailable: {e}",
                    details={"conversation_id": conversation_id},
                ) from e
            raise DynamoDBError(
                message=f"Failed to get conversation metadata: {e}",
                table_name=TABLE_NAME,
                operation="get_item",
            ) from e

    @tracer.capture_method
    def get_conversation_messages(
        self, conversation_id: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve conversation messages in chronological order."""
        try:
            query_params: dict[str, Any] = {
                "KeyConditionExpression": "pk = :pk AND begins_with(sk, :sk_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": f"CONV#{conversation_id}",
                    ":sk_prefix": "MSG#",
                },
                "ScanIndexForward": False,
            }

            if limit:
                query_params["Limit"] = limit

            response = self.table.query(**query_params)
            messages = response.get("Items", [])
            return list(reversed(messages))

        except ClientError as e:
            if is_retryable_boto_error(e):
                raise RetryableError(
                    message=f"DynamoDB temporarily unavailable: {e}",
                    details={"conversation_id": conversation_id},
                ) from e
            raise DynamoDBError(
                message=f"Failed to get conversation messages: {e}",
                table_name=TABLE_NAME,
                operation="query",
            ) from e

    @tracer.capture_method
    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total tokens in messages."""
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        return total_chars // 4

    @tracer.capture_method
    def build_context(
        self,
        conversation_id: str,
        include_system_prompt: bool = True,
        max_messages: int | None = None,
        max_tokens: int | None = None,
    ) -> ConversationContext:
        """Build conversation context with token management."""
        effective_max_messages = max_messages or self.max_messages
        effective_max_tokens = max_tokens or self.max_tokens

        # Get conversation metadata
        metadata = self.get_conversation_metadata(conversation_id)

        if not metadata:
            logger.warning(
                "Conversation not found, creating new context",
                extra={"conversation_id": conversation_id},
            )
            return ConversationContext(
                conversation_id=conversation_id,
                messages=[],
                total_messages=0,
                estimated_tokens=0,
                is_truncated=False,
                status="ACTIVE",
            )

        # Get recent messages
        messages = self.get_conversation_messages(
            conversation_id,
            limit=effective_max_messages * 2,
        )

        # Build message contexts
        message_contexts: list[MessageContext] = []
        estimated_tokens = 0

        # Reserve tokens for system prompt if needed
        available_tokens = effective_max_tokens
        if include_system_prompt:
            available_tokens -= 500

        # Add messages until token limit
        is_truncated = False
        for msg in messages:
            msg_tokens = self.estimate_tokens([msg])

            if estimated_tokens + msg_tokens > available_tokens:
                is_truncated = True
                logger.info(
                    "Context truncated due to token limit",
                    extra={
                        "conversation_id": conversation_id,
                        "messages_included": len(message_contexts),
                        "total_messages": len(messages),
                    },
                )
                break

            message_contexts.append(
                MessageContext(
                    message_id=msg["message_id"],
                    role=msg["role"],
                    content=msg["content"],
                    timestamp=msg["timestamp"],
                    intent=msg.get("intent"),
                    entities=msg.get("entities"),
                    sentiment=msg.get("sentiment"),
                )
            )
            estimated_tokens += msg_tokens

        # Build final context
        context = ConversationContext(
            conversation_id=conversation_id,
            user_id=metadata.get("user_id"),
            messages=message_contexts,
            total_messages=len(message_contexts),
            estimated_tokens=estimated_tokens,
            is_truncated=is_truncated,
            status=metadata.get("status", "ACTIVE"),
            last_intent=metadata.get("last_intent"),
            sentiment_score=metadata.get("sentiment_score"),
        )

        metrics.add_metric(
            name="MessagesRetrieved", unit=MetricUnit.Count, value=len(message_contexts)
        )
        metrics.add_metric(name="EstimatedTokens", unit=MetricUnit.Count, value=estimated_tokens)
        metrics.add_metric(
            name="ContextTruncated", unit=MetricUnit.Count, value=1 if is_truncated else 0
        )

        return context


# Initialize context builder (lazy to handle missing TABLE_NAME in tests)
_context_builder: ContextBuilder | None = None


def get_context_builder() -> ContextBuilder:
    """Get or create context builder instance."""
    global _context_builder
    if _context_builder is None:
        if not TABLE_NAME:
            raise NonRetryableError(
                message="TABLE_NAME environment variable not set",
                error_code="CONFIGURATION_ERROR",
            )
        _context_builder = ContextBuilder(
            table_name=TABLE_NAME,
            max_messages=MAX_MESSAGES,
            max_tokens=MAX_TOKENS,
        )
    return _context_builder


# =============================================================================
# Handler
# =============================================================================


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for context building.

    Step Functions Input:
        {
            "conversation_id": "conv-123",
            "include_system_prompt": true
        }

    Step Functions Output:
        {
            "conversation_id": "conv-123",
            "context": {
                "conversation_id": "conv-123",
                "messages": [...],
                "total_messages": 5,
                "estimated_tokens": 450,
                "is_truncated": false
            },
            "timestamp": "2025-01-15T10:30:00Z"
        }
    """
    adapter = StepFunctionsAdapter(event)
    logger.append_keys(invocation_source=adapter.source.value)

    try:
        # Parse and validate request
        request = adapter.parse_model(ContextBuilderRequest)

        logger.info(
            "Building context",
            extra={
                "conversation_id": request.conversation_id,
                "include_system_prompt": request.include_system_prompt,
            },
        )

        # Build context
        context_builder = get_context_builder()
        conversation_context = context_builder.build_context(
            conversation_id=request.conversation_id,
            include_system_prompt=request.include_system_prompt,
            max_messages=request.max_messages,
            max_tokens=request.max_tokens,
        )

        # Create response
        response = ContextBuilderResponse(
            conversation_id=request.conversation_id,
            context=conversation_context,
            timestamp=datetime.utcnow().isoformat(),
        )

        metrics.add_metric(name="ContextBuilt", unit=MetricUnit.Count, value=1)

        return adapter.success_response(response)

    except ValidationError as e:
        logger.warning("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="ValidationErrors", unit=MetricUnit.Count, value=1)
        return adapter.error_response(e, status_code=400)

    except RetryableError as e:
        logger.warning("Retryable error", extra={"error": str(e)})
        metrics.add_metric(name="RetryableErrors", unit=MetricUnit.Count, value=1)
        return adapter.error_response(e, status_code=503)

    except (DynamoDBError, NonRetryableError) as e:
        logger.error("Non-retryable error", extra={"error": str(e)})
        metrics.add_metric(name="DependencyErrors", unit=MetricUnit.Count, value=1)
        return adapter.error_response(e, status_code=502)

    except Exception as e:
        logger.exception("Unexpected error")
        metrics.add_metric(name="UnexpectedErrors", unit=MetricUnit.Count, value=1)
        error = NonRetryableError(
            message=f"Context building failed: {str(e)}",
            details={"original_error": type(e).__name__},
        )
        return adapter.error_response(error, status_code=500)


# Default response for fail-open behavior
DEFAULT_CONTEXT_RESPONSE: dict[str, Any] = {
    "conversation_id": None,
    "context": {
        "conversation_id": None,
        "messages": [],
        "total_messages": 0,
        "estimated_tokens": 0,
        "is_truncated": False,
        "status": "ACTIVE",
    },
    "timestamp": None,
    "_default_used": True,
}
