"""Tests for handler module."""

from typing import Any
from unittest.mock import MagicMock, patch

from bedrock_client import BedrockModelError, BedrockThrottlingError
from shared.exceptions import DependencyError


class TestHandler:
    """Tests for Lambda handler function."""

    def test_handler_success(
        self,
        sample_bedrock_request: dict[str, Any],
        mock_bedrock_client_response: dict[str, Any],
        lambda_context: MagicMock,
    ) -> None:
        """Test successful handler invocation."""
        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.return_value = mock_bedrock_client_response

            # Import handler after patching
            from handler import handler

            result = handler(sample_bedrock_request, lambda_context)

        assert "conversation_id" in result
        assert result["conversation_id"] == "conv-123"
        assert "response_text" in result
        assert result["response_text"] == "Our return policy allows returns within 30 days."
        assert result["input_tokens"] == 150
        assert result["output_tokens"] == 25
        assert result["stop_reason"] == "end_turn"
        assert "timestamp" in result

    def test_handler_with_conversation_context(
        self,
        sample_bedrock_request_with_context: dict[str, Any],
        mock_bedrock_client_response: dict[str, Any],
        lambda_context: MagicMock,
    ) -> None:
        """Test handler with conversation history."""
        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.return_value = mock_bedrock_client_response

            from handler import handler

            result = handler(sample_bedrock_request_with_context, lambda_context)

        assert result["conversation_id"] == "conv-456"
        assert "response_text" in result

    def test_handler_with_rag_context(
        self,
        sample_bedrock_request_with_rag: dict[str, Any],
        mock_bedrock_client_response: dict[str, Any],
        lambda_context: MagicMock,
    ) -> None:
        """Test handler with RAG context."""
        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.return_value = mock_bedrock_client_response

            from handler import handler

            result = handler(sample_bedrock_request_with_rag, lambda_context)

        assert result["conversation_id"] == "conv-789"
        assert "response_text" in result

    def test_handler_validation_error_missing_conversation_id(
        self,
        lambda_context: MagicMock,
    ) -> None:
        """Test handler with missing required field."""
        invalid_request = {
            "user_message": "Hello",
            # Missing conversation_id
        }

        with patch("handler.bedrock_client"):
            from handler import handler

            result = handler(invalid_request, lambda_context)

        assert result["statusCode"] == 400
        assert "Validation error" in result["body"]

    def test_handler_validation_error_missing_user_message(
        self,
        lambda_context: MagicMock,
    ) -> None:
        """Test handler with missing user_message."""
        invalid_request = {
            "conversation_id": "conv-123",
            # Missing user_message
        }

        with patch("handler.bedrock_client"):
            from handler import handler

            result = handler(invalid_request, lambda_context)

        assert result["statusCode"] == 400
        assert "Validation error" in result["body"]

    def test_handler_validation_error_invalid_temperature(
        self,
        lambda_context: MagicMock,
    ) -> None:
        """Test handler with invalid temperature value."""
        invalid_request = {
            "conversation_id": "conv-123",
            "user_message": "Hello",
            "temperature": 2.0,  # Must be <= 1.0
        }

        with patch("handler.bedrock_client"):
            from handler import handler

            result = handler(invalid_request, lambda_context)

        assert result["statusCode"] == 400

    def test_handler_model_error(
        self,
        sample_bedrock_request: dict[str, Any],
        lambda_context: MagicMock,
    ) -> None:
        """Test handler with Bedrock model error."""
        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.side_effect = BedrockModelError("Invalid request")

            from handler import handler

            result = handler(sample_bedrock_request, lambda_context)

        assert result["statusCode"] == 400
        assert "Model error" in result["body"]

    def test_handler_throttling_error(
        self,
        sample_bedrock_request: dict[str, Any],
        lambda_context: MagicMock,
    ) -> None:
        """Test handler with throttling error."""
        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.side_effect = BedrockThrottlingError("Rate exceeded")

            from handler import handler

            result = handler(sample_bedrock_request, lambda_context)

        assert result["statusCode"] == 429
        assert "throttled" in result["body"].lower()

    def test_handler_dependency_error(
        self,
        sample_bedrock_request: dict[str, Any],
        lambda_context: MagicMock,
    ) -> None:
        """Test handler with dependency error."""
        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.side_effect = DependencyError("Bedrock unavailable")

            from handler import handler

            result = handler(sample_bedrock_request, lambda_context)

        assert result["statusCode"] == 502
        assert "Dependency error" in result["body"]

    def test_handler_unexpected_error(
        self,
        sample_bedrock_request: dict[str, Any],
        lambda_context: MagicMock,
    ) -> None:
        """Test handler with unexpected error."""
        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.side_effect = Exception("Unexpected")

            from handler import handler

            result = handler(sample_bedrock_request, lambda_context)

        assert result["statusCode"] == 500
        assert "Internal server error" in result["body"]


class TestProcessRequest:
    """Tests for process_request function."""

    def test_process_request_builds_correct_messages(
        self,
        sample_bedrock_request: dict[str, Any],
        mock_bedrock_client_response: dict[str, Any],
    ) -> None:
        """Test that process_request builds correct message payload."""
        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.return_value = mock_bedrock_client_response

            from handler import process_request
            from shared.types import BedrockRequest

            request = BedrockRequest.model_validate(sample_bedrock_request)
            process_request(request)

        # Verify invoke_model was called
        mock_client.invoke_model.assert_called_once()
        call_args = mock_client.invoke_model.call_args

        # Verify messages contain user message
        messages = call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "return policy" in messages[0]["content"]

        # Verify system prompt was passed
        assert "system_prompt" in call_args.kwargs
        assert len(call_args.kwargs["system_prompt"]) > 0

    def test_process_request_uses_custom_parameters(
        self,
        mock_bedrock_client_response: dict[str, Any],
    ) -> None:
        """Test that process_request uses custom inference parameters."""
        custom_request = {
            "conversation_id": "conv-123",
            "user_message": "Hello",
            "max_tokens": 512,
            "temperature": 0.5,
            "top_p": 0.8,
        }

        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.return_value = mock_bedrock_client_response

            from handler import process_request
            from shared.types import BedrockRequest

            request = BedrockRequest.model_validate(custom_request)
            process_request(request)

        call_args = mock_client.invoke_model.call_args
        assert call_args.kwargs["max_tokens"] == 512
        assert call_args.kwargs["temperature"] == 0.5
        assert call_args.kwargs["top_p"] == 0.8

    def test_process_request_with_system_prompt_override(
        self,
        mock_bedrock_client_response: dict[str, Any],
    ) -> None:
        """Test that system_prompt_override is applied."""
        request_with_override = {
            "conversation_id": "conv-123",
            "user_message": "Hello",
            "system_prompt_override": "Always respond in Spanish.",
        }

        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.return_value = mock_bedrock_client_response

            from handler import process_request
            from shared.types import BedrockRequest

            request = BedrockRequest.model_validate(request_with_override)
            process_request(request)

        call_args = mock_client.invoke_model.call_args
        system_prompt = call_args.kwargs["system_prompt"]
        assert "Always respond in Spanish" in system_prompt

    def test_process_request_returns_bedrock_response(
        self,
        sample_bedrock_request: dict[str, Any],
        mock_bedrock_client_response: dict[str, Any],
    ) -> None:
        """Test that process_request returns valid BedrockResponse."""
        with patch("handler.bedrock_client") as mock_client:
            mock_client.invoke_model.return_value = mock_bedrock_client_response

            from handler import process_request
            from shared.types import BedrockRequest, BedrockResponse

            request = BedrockRequest.model_validate(sample_bedrock_request)
            result = process_request(request)

        assert isinstance(result, BedrockResponse)
        assert result.conversation_id == "conv-123"
        assert result.response_text == "Our return policy allows returns within 30 days."
        assert result.model_id == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        assert result.input_tokens == 150
        assert result.output_tokens == 25
        assert result.latency_ms == 523
        assert result.stop_reason == "end_turn"
