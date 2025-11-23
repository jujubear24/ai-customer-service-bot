"""Unit tests for intent-classifier handler."""

import json
from unittest.mock import Mock, patch

import pytest

from shared.exceptions import ValidationError
from src.handler import lambda_handler, validate_and_extract_input


@pytest.fixture
def lambda_context() -> Mock:
    """Create mock Lambda context."""
    context = Mock()
    context.function_name = "intent-classifier"
    context.function_version = "$LATEST"
    context.invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:intent-classifier"
    )
    context.memory_limit_in_mb = 128
    context.aws_request_id = "test-request-id"
    context.log_group_name = "/aws/lambda/intent-classifier"
    context.log_stream_name = "2024/01/01/[$LATEST]test"
    context.get_remaining_time_in_millis = Mock(return_value=30000)
    return context


@pytest.fixture
def sample_event() -> dict:
    """Create sample Lambda event from API Gateway."""
    return {
        "body": json.dumps({"message": "I need to speak to a manager"}),
        "headers": {"Content-Type": "application/json", "x-correlation-id": "test-correlation-id"},
        "requestContext": {"requestId": "test-request-id"},
    }


class TestLambdaHandler:
    """Test cases for lambda_handler function."""

    def test_lambda_handler_success(self, sample_event: dict, lambda_context: Mock) -> None:
        """Test successful lambda handler invocation."""
        response = lambda_handler(sample_event, lambda_context)

        assert response["statusCode"] == 200
        assert "body" in response

        body = json.loads(response["body"])
        assert body["message"] == "Intent classified successfully"
        assert "classification" in body
        assert body["classification"]["intent"] in [
            "escalation",
            "complaint",
            "request",
            "question",
            "greeting",
        ]
        assert "correlation_id" in body

    def test_lambda_handler_with_conversation_history(self, lambda_context: Mock) -> None:
        """Test handler with conversation history."""
        event = {
            "body": json.dumps(
                {
                    "message": "I need help with my order",
                    "conversation_history": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi! How can I help?"},
                    ],
                }
            ),
            "headers": {"Content-Type": "application/json"},
            "requestContext": {"requestId": "test-request-id"},
        }

        response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["classification"]["intent"] == "request"

    def test_lambda_handler_validation_error_empty_body(self, lambda_context: Mock) -> None:
        """Test lambda handler with empty body."""
        event = {
            "body": json.dumps({}),
            "headers": {"Content-Type": "application/json"},
            "requestContext": {"requestId": "test-request-id"},
        }

        response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "ValidationError"
        assert "required" in body["message"].lower() or "empty" in body["message"].lower()

    def test_lambda_handler_validation_error_missing_message(self, lambda_context: Mock) -> None:
        """Test lambda handler with missing message field."""
        event = {
            "body": json.dumps({"conversation_history": []}),
            "headers": {"Content-Type": "application/json"},
            "requestContext": {"requestId": "test-request-id"},
        }

        response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "ValidationError"

    def test_lambda_handler_validation_error_message_too_long(self, lambda_context: Mock) -> None:
        """Test lambda handler with message exceeding max length."""
        event = {
            "body": json.dumps({"message": "x" * 2001}),
            "headers": {"Content-Type": "application/json"},
            "requestContext": {"requestId": "test-request-id"},
        }

        response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "ValidationError"
        assert "2000" in body["message"]

    def test_lambda_handler_unexpected_error(
        self, sample_event: dict, lambda_context: Mock
    ) -> None:
        """Test lambda handler with unexpected error."""
        with patch("src.handler.classify_intent", side_effect=Exception("Unexpected error")):
            response = lambda_handler(sample_event, lambda_context)

            assert response["statusCode"] == 500
            body = json.loads(response["body"])
            assert body["error"] == "InternalServerError"

    def test_lambda_handler_different_intents(self, lambda_context: Mock) -> None:
        """Test classification of different intent types."""
        test_cases = [
            ("What are your business hours?", "question"),
            ("I have a complaint about my order", "complaint"),
            ("Can you help me cancel my subscription?", "request"),
            ("Hello there", "greeting"),
            ("I want to speak to your supervisor", "escalation"),
        ]

        for message, expected_intent in test_cases:
            event = {
                "body": json.dumps({"message": message}),
                "headers": {"Content-Type": "application/json"},
                "requestContext": {"requestId": "test-request-id"},
            }

            response = lambda_handler(event, lambda_context)
            assert response["statusCode"] == 200

            body = json.loads(response["body"])
            assert body["classification"]["intent"] == expected_intent


class TestValidateAndExtractInput:
    """Test cases for validate_and_extract_input function."""

    def test_validate_success(self) -> None:
        """Test successful validation."""
        body = {"message": "Hello, I need help"}
        message, history = validate_and_extract_input(body)

        assert message == "Hello, I need help"
        assert history is None

    def test_validate_with_history(self) -> None:
        """Test validation with conversation history."""
        body = {
            "message": "Follow up question",
            "conversation_history": [
                {"role": "user", "content": "Initial message"},
            ],
        }
        message, history = validate_and_extract_input(body)

        assert message == "Follow up question"
        assert history is not None
        assert len(history) == 1

    def test_validate_empty_body(self) -> None:
        """Test validation with empty body."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_and_extract_input({})

    def test_validate_empty_message(self) -> None:
        """Test validation with empty message."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_and_extract_input({"message": ""})

    def test_validate_message_too_long(self) -> None:
        """Test validation with message exceeding max length."""
        with pytest.raises(ValidationError, match="2000 characters"):
            validate_and_extract_input({"message": "x" * 2001})

    def test_validate_invalid_history_type(self) -> None:
        """Test validation with invalid conversation history type."""
        with pytest.raises(ValidationError, match="must be an array"):
            validate_and_extract_input(
                {
                    "message": "test",
                    "conversation_history": "not a list",
                }
            )

    def test_validate_history_too_long(self) -> None:
        """Test validation with conversation history exceeding max length."""
        with pytest.raises(ValidationError, match="50 messages"):
            validate_and_extract_input(
                {
                    "message": "test",
                    "conversation_history": [{"msg": f"message {i}"} for i in range(51)],
                }
            )

    def test_validate_strips_whitespace(self) -> None:
        """Test that validation strips whitespace from message."""
        body = {"message": "  Hello  "}
        message, _ = validate_and_extract_input(body)
        assert message == "Hello"
