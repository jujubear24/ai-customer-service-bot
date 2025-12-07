"""Tests for bedrock_client module."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from bedrock_client import (
    BedrockClient,
    BedrockModelError,
    BedrockThrottlingError,
)
from shared.exceptions import DependencyError


class TestBedrockClientInit:
    """Tests for BedrockClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Test client initialization with default values."""
        with patch("bedrock_client.boto3.client"):
            client = BedrockClient()

        assert client.model_id == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        assert client.region == "us-east-1"

    def test_init_with_custom_values(self) -> None:
        """Test client initialization with custom values."""
        with patch("bedrock_client.boto3.client"):
            client = BedrockClient(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                region="us-west-2",
            )

        assert client.model_id == "us.anthropic.claude-sonnet-4-20250514-v1:0"
        assert client.region == "us-west-2"


class TestBedrockClientInvokeModel:
    """Tests for BedrockClient.invoke_model method."""

    def test_invoke_model_success(
        self,
        mock_boto3_bedrock_client: MagicMock,
        mock_bedrock_response: dict[str, Any],
    ) -> None:
        """Test successful model invocation."""
        with patch("bedrock_client.boto3.client", return_value=mock_boto3_bedrock_client):
            client = BedrockClient()
            result = client.invoke_model(
                messages=[{"role": "user", "content": "Hello"}],
                system_prompt="You are a helpful assistant.",
                max_tokens=1024,
                temperature=0.7,
            )

        assert result["response_text"] == "Our return policy allows returns within 30 days."
        assert result["input_tokens"] == 150
        assert result["output_tokens"] == 25
        assert result["stop_reason"] == "end_turn"
        assert result["request_id"] == "req-abc-123"
        assert "latency_ms" in result
        assert result["latency_ms"] >= 0

    def test_invoke_model_request_body(
        self,
        mock_boto3_bedrock_client: MagicMock,
    ) -> None:
        """Test that request body is correctly formatted with top_p."""
        with patch("bedrock_client.boto3.client", return_value=mock_boto3_bedrock_client):
            client = BedrockClient()
            client.invoke_model(
                messages=[{"role": "user", "content": "Test message"}],
                system_prompt="System prompt",
                max_tokens=512,
                temperature=None,  # Disable temperature to use top_p
                top_p=0.8,
            )

        # Verify invoke_model was called with correct parameters
        call_args = mock_boto3_bedrock_client.invoke_model.call_args
        body = json.loads(call_args.kwargs["body"])

        assert body["anthropic_version"] == "bedrock-2023-05-31"
        assert body["max_tokens"] == 512
        assert body["top_p"] == 0.8
        assert "temperature" not in body  # Should not be present when top_p is used
        assert body["system"] == "System prompt"
        assert body["messages"] == [{"role": "user", "content": "Test message"}]

    def test_invoke_model_throttling_error(self) -> None:
        """Test that throttling errors raise BedrockThrottlingError."""
        mock_client = MagicMock()
        error_response = {
            "Error": {
                "Code": "ThrottlingException",
                "Message": "Rate exceeded",
            }
        }
        mock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        with patch("bedrock_client.boto3.client", return_value=mock_client):
            client = BedrockClient()

            # Retry logic will retry 3 times, so we need to expect the final exception
            with pytest.raises(BedrockThrottlingError) as exc_info:
                client.invoke_model(
                    messages=[{"role": "user", "content": "Hello"}],
                    system_prompt="Test",
                )

            assert "throttled" in str(exc_info.value).lower()

    def test_invoke_model_service_unavailable_error(self) -> None:
        """Test that service unavailable errors raise BedrockThrottlingError."""
        mock_client = MagicMock()
        error_response = {
            "Error": {
                "Code": "ServiceUnavailableException",
                "Message": "Service temporarily unavailable",
            }
        }
        mock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        with patch("bedrock_client.boto3.client", return_value=mock_client):
            client = BedrockClient()

            with pytest.raises(BedrockThrottlingError):
                client.invoke_model(
                    messages=[{"role": "user", "content": "Hello"}],
                    system_prompt="Test",
                )

    def test_invoke_model_timeout_error(self) -> None:
        """Test that timeout errors raise BedrockThrottlingError (retryable)."""
        mock_client = MagicMock()
        error_response = {
            "Error": {
                "Code": "ModelTimeoutException",
                "Message": "Model timed out",
            }
        }
        mock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        with patch("bedrock_client.boto3.client", return_value=mock_client):
            client = BedrockClient()

            with pytest.raises(BedrockThrottlingError) as exc_info:
                client.invoke_model(
                    messages=[{"role": "user", "content": "Hello"}],
                    system_prompt="Test",
                )

            assert "timeout" in str(exc_info.value).lower()

    def test_invoke_model_validation_error(self) -> None:
        """Test that validation errors raise BedrockModelError (not retried)."""
        mock_client = MagicMock()
        error_response = {
            "Error": {
                "Code": "ValidationException",
                "Message": "Invalid request body",
            }
        }
        mock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        with patch("bedrock_client.boto3.client", return_value=mock_client):
            client = BedrockClient()

            with pytest.raises(BedrockModelError) as exc_info:
                client.invoke_model(
                    messages=[{"role": "user", "content": "Hello"}],
                    system_prompt="Test",
                )

            assert "Invalid request" in str(exc_info.value)

    def test_invoke_model_access_denied_error(self) -> None:
        """Test that access denied errors raise BedrockModelError."""
        mock_client = MagicMock()
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized",
            }
        }
        mock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        with patch("bedrock_client.boto3.client", return_value=mock_client):
            client = BedrockClient()

            with pytest.raises(BedrockModelError) as exc_info:
                client.invoke_model(
                    messages=[{"role": "user", "content": "Hello"}],
                    system_prompt="Test",
                )

            assert "Access denied" in str(exc_info.value)

    def test_invoke_model_generic_error(self) -> None:
        """Test that generic errors raise DependencyError."""
        mock_client = MagicMock()
        error_response = {
            "Error": {
                "Code": "InternalServerError",
                "Message": "Something went wrong",
            }
        }
        mock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        with patch("bedrock_client.boto3.client", return_value=mock_client):
            client = BedrockClient()

            with pytest.raises(DependencyError):
                client.invoke_model(
                    messages=[{"role": "user", "content": "Hello"}],
                    system_prompt="Test",
                )

    def test_invoke_model_unexpected_error(self) -> None:
        """Test that unexpected errors raise DependencyError."""
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = Exception("Unexpected error")

        with patch("bedrock_client.boto3.client", return_value=mock_client):
            client = BedrockClient()

            with pytest.raises(DependencyError) as exc_info:
                client.invoke_model(
                    messages=[{"role": "user", "content": "Hello"}],
                    system_prompt="Test",
                )

            assert "Unexpected" in str(exc_info.value)


class TestBedrockClientRetryBehavior:
    """Tests for retry behavior."""

    def test_retry_succeeds_after_throttle(self) -> None:
        """Test that retries succeed after transient throttling."""
        mock_client = MagicMock()

        # First call fails with throttling, second succeeds
        error_response = {
            "Error": {
                "Code": "ThrottlingException",
                "Message": "Rate exceeded",
            }
        }
        success_response = {
            "body": MagicMock(),
            "ResponseMetadata": {"RequestId": "req-123"},
        }
        success_response["body"].read.return_value = json.dumps(
            {
                "content": [{"text": "Success"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "stop_reason": "end_turn",
            }
        ).encode()

        mock_client.invoke_model.side_effect = [
            ClientError(error_response, "InvokeModel"),
            success_response,
        ]

        with patch("bedrock_client.boto3.client", return_value=mock_client):
            client = BedrockClient()
            result = client.invoke_model(
                messages=[{"role": "user", "content": "Hello"}],
                system_prompt="Test",
            )

        assert result["response_text"] == "Success"
        assert mock_client.invoke_model.call_count == 2

    def test_max_retries_exceeded(self) -> None:
        """Test that max retries are respected."""
        mock_client = MagicMock()
        error_response = {
            "Error": {
                "Code": "ThrottlingException",
                "Message": "Rate exceeded",
            }
        }
        mock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        with patch("bedrock_client.boto3.client", return_value=mock_client):
            client = BedrockClient()

            with pytest.raises(BedrockThrottlingError):
                client.invoke_model(
                    messages=[{"role": "user", "content": "Hello"}],
                    system_prompt="Test",
                )

        # Should have tried 3 times (initial + 2 retries)
        assert mock_client.invoke_model.call_count == 3


class TestIsRetryableError:
    """Tests for _is_retryable_error method."""

    def test_throttling_is_retryable(self) -> None:
        """Test that throttling errors are retryable."""
        with patch("bedrock_client.boto3.client"):
            client = BedrockClient()

        error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Test"}},
            "InvokeModel",
        )
        assert client._is_retryable_error(error) is True

    def test_service_unavailable_is_retryable(self) -> None:
        """Test that service unavailable errors are retryable."""
        with patch("bedrock_client.boto3.client"):
            client = BedrockClient()

        error = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "Test"}},
            "InvokeModel",
        )
        assert client._is_retryable_error(error) is True

    def test_validation_not_retryable(self) -> None:
        """Test that validation errors are not retryable."""
        with patch("bedrock_client.boto3.client"):
            client = BedrockClient()

        error = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Test"}},
            "InvokeModel",
        )
        assert client._is_retryable_error(error) is False

    def test_access_denied_not_retryable(self) -> None:
        """Test that access denied errors are not retryable."""
        with patch("bedrock_client.boto3.client"):
            client = BedrockClient()

        error = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Test"}},
            "InvokeModel",
        )
        assert client._is_retryable_error(error) is False
