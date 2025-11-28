"""
Tests for Context Builder Lambda.
"""

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from moto import mock_aws

from src.handler import ContextBuilder, handler


@pytest.fixture
def aws_credentials() -> None:
    """Mock AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def dynamodb_table(aws_credentials: None) -> Any:
    """Create mock DynamoDB table."""
    with mock_aws():
        import boto3

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-conversations",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield table


@pytest.fixture
def lambda_context() -> MagicMock:
    """Mock Lambda context."""
    context = MagicMock()
    context.function_name = "context-builder"
    context.function_version = "$LATEST"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:context-builder"
    context.memory_limit_in_mb = 128
    context.aws_request_id = "test-request-id"
    return context


@pytest.fixture
def sample_conversation(dynamodb_table: Any) -> dict[str, Any]:
    """Create sample conversation in DynamoDB."""
    conversation_id = "conv-123"
    user_id = "user-456"

    # Add conversation metadata
    dynamodb_table.put_item(
        Item={
            "pk": f"CONV#{conversation_id}",
            "sk": "METADATA",
            "entity_type": "CONVERSATION",
            "conversation_id": conversation_id,
            "user_id": user_id,
            "status": "ACTIVE",
            "created_at": "2025-01-01T10:00:00",
            "updated_at": "2025-01-01T10:05:00",
            "message_count": 3,
            "last_intent": "question",
            "sentiment_score": 0.7,
            "gsi1_pk": f"USER#{user_id}",
            "gsi1_sk": "CONV#2025-01-01T10:00:00",
            "gsi2_pk": "STATUS#ACTIVE",
            "gsi2_sk": "2025-01-01T10:05:00",
        }
    )

    # Add messages
    messages = [
        {
            "pk": f"CONV#{conversation_id}",
            "sk": "MSG#2025-01-01T10:00:00#msg-1",
            "entity_type": "MESSAGE",
            "conversation_id": conversation_id,
            "message_id": "msg-1",
            "role": "USER",
            "content": "Hello, I need help",
            "timestamp": "2025-01-01T10:00:00",
            "intent": "greeting",
            "sentiment": "neutral",
        },
        {
            "pk": f"CONV#{conversation_id}",
            "sk": "MSG#2025-01-01T10:02:00#msg-2",
            "entity_type": "MESSAGE",
            "conversation_id": conversation_id,
            "message_id": "msg-2",
            "role": "ASSISTANT",
            "content": "Hello! How can I help you today?",
            "timestamp": "2025-01-01T10:02:00",
        },
        {
            "pk": f"CONV#{conversation_id}",
            "sk": "MSG#2025-01-01T10:05:00#msg-3",
            "entity_type": "MESSAGE",
            "conversation_id": conversation_id,
            "message_id": "msg-3",
            "role": "USER",
            "content": "Where is my order #12345?",
            "timestamp": "2025-01-01T10:05:00",
            "intent": "question",
            "entities": {"order_id": "12345"},
            "sentiment": "concerned",
        },
    ]

    for msg in messages:
        dynamodb_table.put_item(Item=msg)

    return {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "messages": messages,
    }


class TestContextBuilder:
    """Test ContextBuilder class."""

    def test_get_conversation_metadata(
        self, dynamodb_table: Any, sample_conversation: dict[str, Any]
    ) -> None:
        """Test retrieving conversation metadata."""
        builder = ContextBuilder(table_name="test-conversations", max_messages=10, max_tokens=8000)

        metadata = builder.get_conversation_metadata(sample_conversation["conversation_id"])

        assert metadata is not None
        assert metadata["conversation_id"] == sample_conversation["conversation_id"]
        assert metadata["user_id"] == sample_conversation["user_id"]
        assert metadata["status"] == "ACTIVE"
        assert metadata["message_count"] == 3

    def test_get_conversation_metadata_not_found(self, dynamodb_table: Any) -> None:
        """Test getting metadata for non-existent conversation."""
        builder = ContextBuilder(table_name="test-conversations", max_messages=10, max_tokens=8000)

        metadata = builder.get_conversation_metadata("non-existent")
        assert metadata is None

    def test_get_conversation_messages(
        self, dynamodb_table: Any, sample_conversation: dict[str, Any]
    ) -> None:
        """Test retrieving conversation messages."""
        builder = ContextBuilder(table_name="test-conversations", max_messages=10, max_tokens=8000)

        messages = builder.get_conversation_messages(sample_conversation["conversation_id"])

        assert len(messages) == 3
        # Should be in chronological order (oldest first)
        assert messages[0]["message_id"] == "msg-1"
        assert messages[1]["message_id"] == "msg-2"
        assert messages[2]["message_id"] == "msg-3"

    def test_get_conversation_messages_with_limit(
        self, dynamodb_table: Any, sample_conversation: dict[str, Any]
    ) -> None:
        """Test retrieving messages with limit."""
        builder = ContextBuilder(table_name="test-conversations", max_messages=10, max_tokens=8000)

        messages = builder.get_conversation_messages(
            sample_conversation["conversation_id"], limit=2
        )

        assert len(messages) == 2

    def test_estimate_tokens(self, dynamodb_table: Any) -> None:
        """Test token estimation."""
        builder = ContextBuilder(table_name="test-conversations", max_messages=10, max_tokens=8000)

        messages = [
            {"content": "Hello"},  # ~1 token
            {"content": "This is a longer message with more content"},  # ~10 tokens
        ]

        tokens = builder.estimate_tokens(messages)
        assert tokens > 0
        assert tokens < 50  # Should be reasonable

    def test_build_context(self, dynamodb_table: Any, sample_conversation: dict[str, Any]) -> None:
        """Test building full context."""
        builder = ContextBuilder(table_name="test-conversations", max_messages=10, max_tokens=8000)

        context = builder.build_context(sample_conversation["conversation_id"])

        assert context.conversation_id == sample_conversation["conversation_id"]
        assert context.user_id == sample_conversation["user_id"]
        assert context.total_messages == 3
        assert len(context.messages) == 3
        assert context.estimated_tokens > 0
        assert not context.is_truncated
        assert context.status == "ACTIVE"
        assert context.last_intent == "question"

    def test_build_context_truncation(
        self, dynamodb_table: Any, sample_conversation: dict[str, Any]
    ) -> None:
        """Test context truncation with token limit."""
        # Set very low token limit to force truncation
        builder = ContextBuilder(table_name="test-conversations", max_messages=10, max_tokens=50)

        context = builder.build_context(sample_conversation["conversation_id"])

        assert context.is_truncated
        assert context.total_messages < 3  # Some messages should be excluded

    def test_build_context_new_conversation(self, dynamodb_table: Any) -> None:
        """Test building context for new conversation."""
        builder = ContextBuilder(table_name="test-conversations", max_messages=10, max_tokens=8000)

        context = builder.build_context("new-conversation-id")

        assert context.conversation_id == "new-conversation-id"
        assert context.total_messages == 0
        assert len(context.messages) == 0
        assert not context.is_truncated


class TestHandler:
    """Test Lambda handler."""

    @patch.dict(
        os.environ,
        {
            "TABLE_NAME": "test-conversations",
            "MAX_MESSAGES": "10",
            "MAX_TOKENS": "8000",
        },
    )
    def test_handler_success(
        self, dynamodb_table: Any, sample_conversation: dict[str, Any], lambda_context: MagicMock
    ) -> None:
        """Test successful handler invocation."""
        event = {
            "conversation_id": sample_conversation["conversation_id"],
            "include_system_prompt": True,
        }

        response = handler(event, lambda_context)

        assert "conversation_id" in response
        assert response["conversation_id"] == sample_conversation["conversation_id"]
        assert "context" in response
        assert "timestamp" in response

        context = response["context"]
        assert context["total_messages"] == 3
        assert len(context["messages"]) == 3

    @patch.dict(
        os.environ,
        {
            "TABLE_NAME": "test-conversations",
            "MAX_MESSAGES": "10",
            "MAX_TOKENS": "8000",
        },
    )
    def test_handler_validation_error(self, dynamodb_table: Any, lambda_context: MagicMock) -> None:
        """Test handler with invalid request."""
        event = {}  # Missing conversation_id

        response = handler(event, lambda_context)

        assert response["statusCode"] == 400
        assert "error" in json.loads(response["body"])

    @patch.dict(
        os.environ,
        {
            "TABLE_NAME": "test-conversations",
            "MAX_MESSAGES": "10",
            "MAX_TOKENS": "8000",
        },
    )
    def test_handler_new_conversation(self, dynamodb_table: Any, lambda_context: MagicMock) -> None:
        """Test handler with new conversation."""
        event = {
            "conversation_id": "new-conversation",
            "include_system_prompt": False,
        }

        response = handler(event, lambda_context)

        assert "conversation_id" in response
        assert response["conversation_id"] == "new-conversation"
        assert response["context"]["total_messages"] == 0
