"""Unit tests for response-validator handler."""

import json
from unittest.mock import Mock, patch

import pytest

from shared.exceptions import ValidationError
from src.handler import lambda_handler, process_event, validate_event


@pytest.fixture
def lambda_context() -> Mock:
    """Create mock Lambda context."""
    context = Mock()
    context.function_name = "response-validator"
    context.function_version = "$LATEST"
    context.invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:response-validator"
    )
    context.memory_limit_in_mb = 128
    context.aws_request_id = "test-request-id"
    context.log_group_name = "/aws/lambda/response-validator"
    context.log_stream_name = "2024/01/01/[$LATEST]test"
    context.get_remaining_time_in_millis = Mock(return_value=30000)
    return context


@pytest.fixture
def sample_event() -> dict:
    """Create sample Lambda event."""
    return {
        "body": json.dumps({"test": "data"}),
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
        assert body["message"] == "Success"
        assert "correlation_id" in body

    def test_lambda_handler_validation_error(self, lambda_context: Mock) -> None:
        """Test lambda handler with validation error."""
        event = {}

        response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "ValidationError"

    def test_lambda_handler_unexpected_error(
        self, sample_event: dict, lambda_context: Mock
    ) -> None:
        """Test lambda handler with unexpected error."""
        with patch("src.handler.process_event", side_effect=Exception("Unexpected")):
            response = lambda_handler(sample_event, lambda_context)

            assert response["statusCode"] == 500
            body = json.loads(response["body"])
            assert body["error"] == "InternalServerError"


class TestValidateEvent:
    """Test cases for validate_event function."""

    def test_validate_event_success(self, sample_event: dict) -> None:
        """Test successful event validation."""
        # Should not raise any exception
        validate_event(sample_event)

    def test_validate_event_empty(self) -> None:
        """Test validation with empty event."""
        with pytest.raises(ValidationError):
            validate_event({})


class TestProcessEvent:
    """Test cases for process_event function."""

    def test_process_event_success(self, sample_event: dict, lambda_context: Mock) -> None:
        """Test successful event processing."""
        result = process_event(sample_event, lambda_context)

        assert "function" in result
        assert result["function"] == "response-validator"
        assert "request_id" in result
