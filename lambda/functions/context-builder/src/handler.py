"""
Context Builder Lambda Function.

Retrieves conversation history and builds context for Bedrock.
Handles context window management and relevance scoring.
"""

import json
import os
from datetime import datetime
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError
from pydantic import ValidationError

from shared.exceptions import DependencyError
from shared.exceptions import ValidationError as CustomValidationError
from shared.types import (
    ContextBuilderRequest,
    ContextBuilderResponse,
    ConversationContext,
    MessageContext,
)

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()

# Environment variables
TABLE_NAME = os.environ["TABLE_NAME"]
MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", "10"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "8000"))

# AWS clients
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


class ContextBuilder:
    """Build conversation context from DynamoDB."""

    def __init__(self, table_name: str, max_messages: int, max_tokens: int) -> None:
        """Initialize context builder."""
        self.table = dynamodb.Table(table_name)
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.tokens_per_message_estimate = 100  # Conservative estimate

    @tracer.capture_method
    def get_conversation_metadata(self, conversation_id: str) -> dict[str, Any] | None:
        """Retrieve conversation metadata."""
        try:
            response = self.table.get_item(Key={"pk": f"CONV#{conversation_id}", "sk": "METADATA"})
            item = response.get("Item")
            return item if item is None else dict(item)  # Cast to dict
        except ClientError as e:
            logger.error(
                "Failed to get conversation metadata",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )
            raise DependencyError(f"DynamoDB error: {str(e)}") from e

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
                "ScanIndexForward": False,  # Descending (newest first)
            }

            if limit:
                query_params["Limit"] = limit

            response = self.table.query(**query_params)
            messages = response.get("Items", [])

            # Reverse to get chronological order (oldest first)
            return list(reversed(messages))

        except ClientError as e:
            logger.error(
                "Failed to get conversation messages",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )
            raise DependencyError(f"DynamoDB error: {str(e)}") from e

    @tracer.capture_method
    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total tokens in messages."""
        # Simple estimation: ~4 chars per token
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        return total_chars // 4

    @tracer.capture_method
    def build_context(
        self, conversation_id: str, include_system_prompt: bool = True
    ) -> ConversationContext:
        """Build conversation context with token management."""
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
            limit=self.max_messages * 2,  # Get extras for truncation
        )

        # Build message contexts
        message_contexts: list[MessageContext] = []
        estimated_tokens = 0

        # Reserve tokens for system prompt if needed
        available_tokens = self.max_tokens
        if include_system_prompt:
            available_tokens -= 500  # Reserve for system prompt

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


# Initialize context builder
context_builder = ContextBuilder(
    table_name=TABLE_NAME, max_messages=MAX_MESSAGES, max_tokens=MAX_TOKENS
)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for context builder."""
    try:
        # Parse and validate request
        try:
            request = ContextBuilderRequest.model_validate(event)
        except ValidationError as e:
            logger.error("Request validation failed", extra={"errors": e.errors()})
            raise CustomValidationError(f"Invalid request: {str(e)}") from e

        logger.info(
            "Building context",
            extra={
                "conversation_id": request.conversation_id,
                "include_system_prompt": request.include_system_prompt,
            },
        )

        # Build context
        conversation_context = context_builder.build_context(
            conversation_id=request.conversation_id,
            include_system_prompt=request.include_system_prompt,
        )

        # Create response
        response = ContextBuilderResponse(
            conversation_id=request.conversation_id,
            context=conversation_context,
            timestamp=datetime.utcnow().isoformat(),
        )

        metrics.add_metric(name="ContextBuilt", unit=MetricUnit.Count, value=1)

        result: dict[str, Any] = json.loads(response.model_dump_json())
        return result

    except CustomValidationError as e:
        logger.error("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="ValidationError", unit=MetricUnit.Count, value=1)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Validation error", "details": str(e)}),
        }

    except DependencyError as e:
        logger.error("Dependency error", extra={"error": str(e)})
        metrics.add_metric(name="DependencyError", unit=MetricUnit.Count, value=1)
        return {
            "statusCode": 502,
            "body": json.dumps({"error": "Dependency error", "details": str(e)}),
        }

    except Exception:
        logger.exception("Unexpected error")
        metrics.add_metric(name="UnexpectedError", unit=MetricUnit.Count, value=1)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
        }
