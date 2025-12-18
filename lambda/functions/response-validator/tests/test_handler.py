"""Unit tests for Response Validator Lambda handler."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from models import ValidationAction, ValidationRequest


class TestLambdaHandler:
    """Tests for lambda_handler function."""

    @patch("handler.get_service")
    def test_handler_success(
        self,
        mock_get_service: MagicMock,
        lambda_event_direct: dict[str, Any],
        mock_lambda_context: MagicMock,
    ) -> None:
        """Test successful handler invocation."""
        from handler import lambda_handler
        from models import ValidationMetadata, ValidationResponse, ValidationResults

        # Create mock response
        mock_response = ValidationResponse(
            is_valid=True,
            action=ValidationAction.PASS,
            validated_response="Test response",
            original_response="Test response",
            validation_results=ValidationResults(),
            sentiment=None,
            escalation=None,
            metadata=ValidationMetadata(
                validation_time_ms=100.0,
                rules_evaluated=3,
                fallback_used=False,
                comprehend_calls=0,
            ),
        )

        mock_service = MagicMock()
        mock_service.validate.return_value = mock_response
        mock_get_service.return_value = mock_service

        result = lambda_handler(lambda_event_direct, mock_lambda_context)

        assert result["statusCode"] == 200
        assert "body" in result
        assert result["body"]["is_valid"] is True

    @patch("handler.get_service")
    def test_handler_api_gateway_format(
        self,
        mock_get_service: MagicMock,
        lambda_event_api_gateway: dict[str, Any],
        mock_lambda_context: MagicMock,
    ) -> None:
        """Test handler with API Gateway event format."""
        from handler import lambda_handler
        from models import ValidationMetadata, ValidationResponse, ValidationResults

        mock_response = ValidationResponse(
            is_valid=True,
            action=ValidationAction.PASS,
            validated_response="Test response",
            original_response="Test response",
            validation_results=ValidationResults(),
            sentiment=None,
            escalation=None,
            metadata=ValidationMetadata(
                validation_time_ms=100.0,
                rules_evaluated=3,
                fallback_used=False,
                comprehend_calls=0,
            ),
        )

        mock_service = MagicMock()
        mock_service.validate.return_value = mock_response
        mock_get_service.return_value = mock_service

        result = lambda_handler(lambda_event_api_gateway, mock_lambda_context)

        assert result["statusCode"] == 200
        mock_service.validate.assert_called_once()

    def test_handler_validation_error(
        self,
        lambda_event_invalid: dict[str, Any],
        mock_lambda_context: MagicMock,
    ) -> None:
        """Test handler with invalid request."""
        from handler import lambda_handler

        result = lambda_handler(lambda_event_invalid, mock_lambda_context)

        assert result["statusCode"] == 400
        assert result["body"]["error_type"] == "ValidationError"
        assert result["body"]["retryable"] is False

    def test_handler_malformed_json(
        self,
        lambda_event_malformed_json: dict[str, Any],
        mock_lambda_context: MagicMock,
    ) -> None:
        """Test handler with malformed JSON body."""
        from handler import lambda_handler

        result = lambda_handler(lambda_event_malformed_json, mock_lambda_context)

        assert result["statusCode"] == 400
        assert result["body"]["error_type"] == "InvalidRequest"

    @patch.dict(os.environ, {"DEBUG": "true"})
    @patch("handler.get_service")
    def test_handler_internal_error(
        self,
        mock_get_service: MagicMock,
        lambda_event_direct: dict[str, Any],
        mock_lambda_context: MagicMock,
    ) -> None:
        """Test handler internal error handling."""
        from handler import lambda_handler

        mock_service = MagicMock()
        mock_service.validate.side_effect = Exception("Internal error")
        mock_get_service.return_value = mock_service

        result = lambda_handler(lambda_event_direct, mock_lambda_context)

        assert result["statusCode"] == 500
        assert result["body"]["error_type"] == "InternalError"
        assert result["body"]["retryable"] is True
        # Debug mode should include error details
        assert result["body"]["details"] is not None

    @patch.dict(os.environ, {"DEBUG": "false", "FAIL_OPEN_ON_ERROR": "true"})
    @patch("handler.get_service")
    def test_handler_fail_open(
        self,
        mock_get_service: MagicMock,
        mock_lambda_context: MagicMock,
    ) -> None:
        """Test handler fails open when configured."""
        from handler import lambda_handler

        mock_service = MagicMock()
        mock_service.validate.side_effect = Exception("Service error")
        mock_get_service.return_value = mock_service

        event = {
            "response_text": "Original response text",
            "user_message": "Test message",
            "conversation_id": "conv-123",
            "tenant_id": "test-tenant",
        }

        result = lambda_handler(event, mock_lambda_context)

        # Should return 200 with original response
        assert result["statusCode"] == 200
        assert result["body"]["validated_response"] == "Original response text"
        assert result["body"]["action"] == ValidationAction.WARN.value


class TestRequestParsing:
    """Tests for request parsing functions."""

    def test_parse_direct_invocation(self) -> None:
        """Test parsing direct invocation event."""
        from handler import _parse_request

        event = {
            "response_text": "Test response",
            "user_message": "Test message",
            "conversation_id": "conv-123",
            "tenant_id": "test-tenant",
        }

        request = _parse_request(event)

        assert request.response_text == "Test response"
        assert request.conversation_id == "conv-123"

    def test_parse_api_gateway_string_body(self) -> None:
        """Test parsing API Gateway event with string body."""
        from handler import _parse_request

        event = {
            "body": json.dumps(
                {
                    "response_text": "Test response",
                    "user_message": "Test message",
                    "conversation_id": "conv-123",
                    "tenant_id": "test-tenant",
                }
            ),
        }

        request = _parse_request(event)

        assert request.response_text == "Test response"

    def test_parse_api_gateway_dict_body(self) -> None:
        """Test parsing API Gateway event with dict body."""
        from handler import _parse_request

        event = {
            "body": {
                "response_text": "Test response",
                "user_message": "Test message",
                "conversation_id": "conv-123",
                "tenant_id": "test-tenant",
            },
        }

        request = _parse_request(event)

        assert request.response_text == "Test response"

    def test_parse_invalid_json(self) -> None:
        """Test parsing event with invalid JSON body."""
        from handler import _parse_request

        event = {"body": "{ invalid json }"}

        with pytest.raises(ValueError, match="Invalid JSON"):
            _parse_request(event)


class TestResponseBuilding:
    """Tests for response building functions."""

    def test_build_success_response(self) -> None:
        """Test building success response."""
        from handler import _build_success_response
        from models import ValidationMetadata, ValidationResponse, ValidationResults

        response = ValidationResponse(
            is_valid=True,
            action=ValidationAction.PASS,
            validated_response="Test",
            original_response="Test",
            validation_results=ValidationResults(),
            sentiment=None,
            escalation=None,
            metadata=ValidationMetadata(
                validation_time_ms=100.0,
                rules_evaluated=0,
                fallback_used=False,
                comprehend_calls=0,
            ),
        )

        result = _build_success_response(response)

        assert result["statusCode"] == 200
        assert result["body"]["is_valid"] is True

    def test_build_error_response(self) -> None:
        """Test building error response."""
        from handler import _build_error_response
        from models import ValidationError

        error = ValidationError(
            error_type="TestError",
            message="Test error message",
            retryable=False,
        )

        result = _build_error_response(error, status_code=400)

        assert result["statusCode"] == 400
        assert result["body"]["error_type"] == "TestError"

    def test_build_validation_error_response(self) -> None:
        """Test building Pydantic validation error response."""
        from pydantic import ValidationError

        from handler import _build_validation_error_response

        try:
            ValidationRequest(
                response_text="",
                user_message="test",
                conversation_id="conv",
                tenant_id="tenant",
            )
        except ValidationError as e:
            result = _build_validation_error_response(e, "conv-123")

            assert result["statusCode"] == 400
            assert result["body"]["error_type"] == "ValidationError"
            assert "errors" in result["body"]["details"]

    def test_build_fallback_validation_response(self) -> None:
        """Test building fallback validation response."""
        from handler import _build_fallback_validation_response

        response = _build_fallback_validation_response(
            original_response="Original text",
            error_message="Test error",
        )

        assert response.is_valid is True
        assert response.action == ValidationAction.WARN
        assert response.validated_response == "Original text"
        assert response.metadata.fallback_reason is not None
        assert "validation_error" in response.metadata.fallback_reason


class TestServiceInitialization:
    """Tests for service initialization."""

    @patch.dict(
        os.environ,
        {
            "ENABLE_PII_DETECTION": "false",
            "ENABLE_PROFANITY_CHECK": "true",
            "MIN_RESPONSE_LENGTH": "50",
            "MAX_RESPONSE_LENGTH": "1000",
        },
    )
    def test_create_service_from_env(self) -> None:
        """Test service is created from environment variables."""
        from handler import _create_service

        service = _create_service()

        assert service.config.enable_pii_detection is False
        assert service.config.enable_profanity_check is True
        assert service.config.min_response_length == 50
        assert service.config.max_response_length == 1000

    def test_create_service_defaults(self) -> None:
        """Test service uses defaults when env vars not set."""
        from handler import _create_service

        service = _create_service()

        # Default values
        assert service.config.min_response_length == 20

    def test_get_service_singleton(self) -> None:
        """Test get_service returns singleton."""
        import handler

        # Reset singleton
        handler._service = None

        service1 = handler.get_service()
        service2 = handler.get_service()

        assert service1 is service2

        # Clean up
        handler._service = None


class TestEnvironmentConfiguration:
    """Tests for environment-based configuration."""

    @patch.dict(
        os.environ,
        {
            "ENABLE_PII_DETECTION": "true",
            "ENABLE_PROFANITY_CHECK": "false",
            "ENABLE_BUSINESS_RULES": "true",
            "ENABLE_LENGTH_CHECK": "false",
            "TRUNCATE_LONG_RESPONSES": "false",
            "STOP_ON_CRITICAL_FAILURE": "false",
            "USE_FALLBACK_ON_BLOCK": "false",
            "REDACT_PII_IN_RESPONSE": "false",
            "MIN_RESPONSE_LENGTH": "100",
            "MAX_RESPONSE_LENGTH": "500",
        },
    )
    def test_all_env_vars(self) -> None:
        """Test all environment variables are respected."""
        from handler import _create_service

        service = _create_service()

        assert service.config.enable_pii_detection is True
        assert service.config.enable_profanity_check is False
        assert service.config.enable_business_rules is True
        assert service.config.enable_length_check is False
        assert service.config.truncate_long_responses is False
        assert service.config.stop_on_critical_failure is False
        assert service.config.use_fallback_on_block is False
        assert service.config.redact_pii_in_response is False
        assert service.config.min_response_length == 100
        assert service.config.max_response_length == 500
