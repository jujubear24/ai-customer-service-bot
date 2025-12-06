"""Shared test fixtures for Bedrock Handler tests."""

import json
import os
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Add src directory to Python path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Set environment variables before importing modules
os.environ["POWERTOOLS_SERVICE_NAME"] = "bedrock-handler"
os.environ["POWERTOOLS_METRICS_NAMESPACE"] = "AICustomerService"
os.environ["POWERTOOLS_LOG_LEVEL"] = "DEBUG"
os.environ["BEDROCK_MODEL_ID"] = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
os.environ["MAX_TOKENS"] = "1024"
os.environ["TEMPERATURE"] = "0.7"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def sample_bedrock_request() -> dict[str, Any]:
    """Create a sample BedrockRequest as dict."""
    return {
        "conversation_id": "conv-123",
        "user_message": "What is your return policy?",
        "intent": "question",
        "entities": {"topic": "returns"},
        "max_tokens": 1024,
        "temperature": 0.7,
        "top_p": 0.9,
    }


@pytest.fixture
def sample_bedrock_request_with_context() -> dict[str, Any]:
    """Create a BedrockRequest with conversation context."""
    return {
        "conversation_id": "conv-456",
        "user_message": "Can you tell me more about that?",
        "conversation_context": {
            "conversation_id": "conv-456",
            "user_id": "user-789",
            "messages": [
                {
                    "message_id": "msg-001",
                    "role": "USER",
                    "content": "What shipping options do you have?",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
                {
                    "message_id": "msg-002",
                    "role": "ASSISTANT",
                    "content": "We offer standard (5-7 days) and express (2-3 days) shipping.",
                    "timestamp": "2025-01-15T10:00:05Z",
                },
            ],
            "total_messages": 2,
            "estimated_tokens": 50,
            "is_truncated": False,
            "status": "ACTIVE",
        },
        "intent": "question",
        "max_tokens": 1024,
        "temperature": 0.7,
        "top_p": 0.9,
    }


@pytest.fixture
def sample_bedrock_request_with_rag() -> dict[str, Any]:
    """Create a BedrockRequest with RAG context."""
    return {
        "conversation_id": "conv-789",
        "user_message": "How do I return a damaged item?",
        "intent": "question",
        "rag_context": [
            "Return Policy: Items can be returned within 30 days of purchase.",
            "Damaged Items: Contact support immediately for damaged item returns.",
        ],
        "max_tokens": 1024,
        "temperature": 0.7,
        "top_p": 0.9,
    }


@pytest.fixture
def mock_bedrock_response() -> dict[str, Any]:
    """Create a mock Bedrock API response."""
    return {
        "content": [{"type": "text", "text": "Our return policy allows returns within 30 days."}],
        "usage": {"input_tokens": 150, "output_tokens": 25},
        "stop_reason": "end_turn",
    }


@pytest.fixture
def mock_bedrock_client_response() -> dict[str, Any]:
    """Create a mock response from BedrockClient.invoke_model()."""
    return {
        "response_text": "Our return policy allows returns within 30 days.",
        "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "input_tokens": 150,
        "output_tokens": 25,
        "latency_ms": 523,
        "stop_reason": "end_turn",
        "request_id": "req-abc-123",
    }


@pytest.fixture
def mock_boto3_bedrock_client(
    mock_bedrock_response: dict[str, Any],
) -> Generator[MagicMock, None, None]:
    """Mock boto3 Bedrock runtime client."""
    with patch("bedrock_client.boto3.client") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance

        # Mock invoke_model response
        mock_response = {
            "body": MagicMock(),
            "ResponseMetadata": {"RequestId": "req-abc-123"},
        }
        mock_response["body"].read.return_value = json.dumps(mock_bedrock_response).encode()
        mock_instance.invoke_model.return_value = mock_response

        yield mock_instance


@pytest.fixture
def lambda_context() -> MagicMock:
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "bedrock-handler"
    context.memory_limit_in_mb = 512
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789:function:bedrock-handler"
    context.aws_request_id = "test-request-id"
    context.get_remaining_time_in_millis.return_value = 30000
    return context
