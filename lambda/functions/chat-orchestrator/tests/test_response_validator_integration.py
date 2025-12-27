"""Tests for Response Validator integration in Chat Orchestrator."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from models import ChatRequest, ValidationMetrics
from service import (
    BedrockHandlerClient,
    ChatOrchestrator,
    RAGRetrieverClient,
    ResponseValidatorClient,
)


class TestResponseValidatorClient:
    """Tests for ResponseValidatorClient."""

    def test_init_enabled(self) -> None:
        """Test client is enabled when function name is provided."""
        client = ResponseValidatorClient(function_name="test-validator")
        assert client.enabled is True

    def test_init_disabled(self) -> None:
        """Test client is disabled when function name is empty."""
        client = ResponseValidatorClient(function_name="")
        assert client.enabled is False

    def test_validate_disabled_returns_passthrough(self) -> None:
        """Test disabled client returns passthrough result."""
        client = ResponseValidatorClient(function_name="")

        result = client.validate(
            response_text="Test response",
            user_message="Test message",
            conversation_id="conv-123",
            tenant_id="tenant-456",
        )

        assert result["is_valid"] is True
        assert result["action"] == "PASS"
        assert result["validated_response"] == "Test response"
        assert result["validation_skipped"] is True

    def test_validate_success(self) -> None:
        """Test successful validation invocation."""
        mock_lambda = MagicMock()
        mock_lambda.invoke.return_value = {
            "Payload": MagicMock(
                read=lambda: json.dumps(
                    {
                        "statusCode": 200,
                        "body": json.dumps(
                            {
                                "is_valid": True,
                                "action": "PASS",
                                "validated_response": "Test response",
                                "original_response": "Test response",
                                "was_modified": False,
                                "metadata": {
                                    "validation_time_ms": 50.0,
                                    "rules_evaluated": 3,
                                    "fallback_used": False,
                                },
                            }
                        ),
                    }
                )
            )
        }

        client = ResponseValidatorClient(
            function_name="test-validator",
            lambda_client=mock_lambda,
        )

        result = client.validate(
            response_text="Test response",
            user_message="Test message",
            conversation_id="conv-123",
            tenant_id="tenant-456",
        )

        assert result["is_valid"] is True
        assert result["action"] == "PASS"
        mock_lambda.invoke.assert_called_once()

    def test_validate_with_modification(self) -> None:
        """Test validation that modifies the response."""
        mock_lambda = MagicMock()
        mock_lambda.invoke.return_value = {
            "Payload": MagicMock(
                read=lambda: json.dumps(
                    {
                        "statusCode": 200,
                        "body": json.dumps(
                            {
                                "is_valid": True,
                                "action": "MODIFY",
                                "validated_response": "Modified response with disclaimer.",
                                "original_response": "Original medical advice.",
                                "was_modified": True,
                                "metadata": {
                                    "validation_time_ms": 75.0,
                                    "rules_evaluated": 3,
                                    "fallback_used": False,
                                },
                            }
                        ),
                    }
                )
            )
        }

        client = ResponseValidatorClient(
            function_name="test-validator",
            lambda_client=mock_lambda,
        )

        result = client.validate(
            response_text="Original medical advice.",
            user_message="What medication should I take?",
            conversation_id="conv-123",
            tenant_id="tenant-456",
        )

        assert result["is_valid"] is True
        assert result["action"] == "MODIFY"
        assert result["validated_response"] == "Modified response with disclaimer."
        assert result["was_modified"] is True

    def test_validate_blocked_response(self) -> None:
        """Test validation that blocks the response."""
        mock_lambda = MagicMock()
        mock_lambda.invoke.return_value = {
            "Payload": MagicMock(
                read=lambda: json.dumps(
                    {
                        "statusCode": 200,
                        "body": json.dumps(
                            {
                                "is_valid": False,
                                "action": "BLOCK",
                                "validated_response": "I apologize, but I cannot provide that information.",
                                "original_response": "Your SSN is 123-45-6789.",
                                "was_modified": True,
                                "metadata": {
                                    "validation_time_ms": 100.0,
                                    "rules_evaluated": 3,
                                    "fallback_used": True,
                                    "fallback_reason": "pii_blocked",
                                },
                            }
                        ),
                    }
                )
            )
        }

        client = ResponseValidatorClient(
            function_name="test-validator",
            lambda_client=mock_lambda,
        )

        result = client.validate(
            response_text="Your SSN is 123-45-6789.",
            user_message="What is my SSN?",
            conversation_id="conv-123",
            tenant_id="tenant-456",
        )

        assert result["is_valid"] is False
        assert result["action"] == "BLOCK"
        assert result["metadata"]["fallback_used"] is True

    def test_validate_function_error(self) -> None:
        """Test handling of Lambda function error."""
        mock_lambda = MagicMock()
        mock_lambda.invoke.return_value = {
            "FunctionError": "Unhandled",
            "Payload": MagicMock(read=lambda: json.dumps({"errorMessage": "Internal error"})),
        }

        client = ResponseValidatorClient(
            function_name="test-validator",
            lambda_client=mock_lambda,
        )

        result = client.validate(
            response_text="Test response",
            user_message="Test message",
            conversation_id="conv-123",
            tenant_id="tenant-456",
        )

        # Should return passthrough on error
        assert result["is_valid"] is True
        assert result["validation_skipped"] is True
        assert result["validation_error"] is True

    def test_validate_exception(self) -> None:
        """Test handling of invocation exception."""
        mock_lambda = MagicMock()
        mock_lambda.invoke.side_effect = Exception("Network error")

        client = ResponseValidatorClient(
            function_name="test-validator",
            lambda_client=mock_lambda,
        )

        result = client.validate(
            response_text="Test response",
            user_message="Test message",
            conversation_id="conv-123",
            tenant_id="tenant-456",
        )

        # Should return passthrough on exception
        assert result["is_valid"] is True
        assert result["validation_skipped"] is True
        assert result["validation_error"] is True


class TestChatOrchestratorWithValidation:
    """Tests for ChatOrchestrator with Response Validator integration."""

    @pytest.fixture
    def mock_rag_client(self) -> MagicMock:
        """Create mock RAG client."""
        client = MagicMock(spec=RAGRetrieverClient)
        client.retrieve.return_value = []
        return client

    @pytest.fixture
    def mock_bedrock_client(self) -> MagicMock:
        """Create mock Bedrock client."""
        client = MagicMock(spec=BedrockHandlerClient)
        client.generate_response.return_value = {
            "response_text": "This is the AI response.",
            "model_id": "anthropic.claude-haiku",
            "conversation_id": "conv-123",
        }
        return client

    @pytest.fixture
    def mock_validator_client(self) -> MagicMock:
        """Create mock validator client."""
        client = MagicMock(spec=ResponseValidatorClient)
        client.enabled = True
        client.validate.return_value = {
            "is_valid": True,
            "action": "PASS",
            "validated_response": "This is the AI response.",
            "original_response": "This is the AI response.",
            "was_modified": False,
            "metadata": {
                "validation_time_ms": 50.0,
                "rules_evaluated": 3,
                "fallback_used": False,
            },
        }
        return client

    def test_orchestrator_with_validation_enabled(
        self,
        mock_rag_client: MagicMock,
        mock_bedrock_client: MagicMock,
        mock_validator_client: MagicMock,
    ) -> None:
        """Test orchestrator calls validator when enabled."""
        orchestrator = ChatOrchestrator(
            rag_client=mock_rag_client,
            bedrock_client=mock_bedrock_client,
            validator_client=mock_validator_client,
        )

        request = ChatRequest(
            message="Hello",
            tenant_id="tenant-123",
            validate_response=True,
        )

        response = orchestrator.process_request(request)

        # Verify validator was called
        mock_validator_client.validate.assert_called_once()

        # Verify response includes validation metadata
        assert response.metadata.validation is not None
        assert response.metadata.validation.is_valid is True
        assert response.metadata.validation.action == "PASS"

    def test_orchestrator_with_validation_disabled(
        self,
        mock_rag_client: MagicMock,
        mock_bedrock_client: MagicMock,
        mock_validator_client: MagicMock,
    ) -> None:
        """Test orchestrator skips validator when disabled in request."""
        orchestrator = ChatOrchestrator(
            rag_client=mock_rag_client,
            bedrock_client=mock_bedrock_client,
            validator_client=mock_validator_client,
        )

        request = ChatRequest(
            message="Hello",
            tenant_id="tenant-123",
            validate_response=False,  # Disabled
        )

        response = orchestrator.process_request(request)

        # Verify validator was NOT called
        mock_validator_client.validate.assert_not_called()

        # Verify no validation metadata
        assert response.metadata.validation is None

    def test_orchestrator_without_validator_client(
        self,
        mock_rag_client: MagicMock,
        mock_bedrock_client: MagicMock,
    ) -> None:
        """Test orchestrator works without validator client."""
        orchestrator = ChatOrchestrator(
            rag_client=mock_rag_client,
            bedrock_client=mock_bedrock_client,
            validator_client=None,  # No validator
        )

        request = ChatRequest(
            message="Hello",
            tenant_id="tenant-123",
            validate_response=True,
        )

        response = orchestrator.process_request(request)

        # Should still work, just no validation
        assert response.response == "This is the AI response."
        assert response.metadata.validation is None

    def test_orchestrator_uses_validated_response(
        self,
        mock_rag_client: MagicMock,
        mock_bedrock_client: MagicMock,
        mock_validator_client: MagicMock,
    ) -> None:
        """Test orchestrator uses validated (modified) response."""
        # Validator modifies the response
        mock_validator_client.validate.return_value = {
            "is_valid": True,
            "action": "MODIFY",
            "validated_response": "Modified response with disclaimer.",
            "original_response": "Original response.",
            "was_modified": True,
            "metadata": {
                "validation_time_ms": 50.0,
                "rules_evaluated": 3,
                "fallback_used": False,
            },
        }

        # Bedrock returns original
        mock_bedrock_client.generate_response.return_value = {
            "response_text": "Original response.",
            "model_id": "anthropic.claude-haiku",
            "conversation_id": "conv-123",
        }

        orchestrator = ChatOrchestrator(
            rag_client=mock_rag_client,
            bedrock_client=mock_bedrock_client,
            validator_client=mock_validator_client,
        )

        request = ChatRequest(
            message="Medical question",
            tenant_id="tenant-123",
            validate_response=True,
        )

        response = orchestrator.process_request(request)

        # Response should be the validated/modified one
        assert response.response == "Modified response with disclaimer."
        assert response.metadata.validation is not None
        assert response.metadata.validation.was_modified is True

    def test_orchestrator_latency_includes_validation(
        self,
        mock_rag_client: MagicMock,
        mock_bedrock_client: MagicMock,
        mock_validator_client: MagicMock,
    ) -> None:
        """Test latency metrics include validation time."""
        orchestrator = ChatOrchestrator(
            rag_client=mock_rag_client,
            bedrock_client=mock_bedrock_client,
            validator_client=mock_validator_client,
        )

        request = ChatRequest(
            message="Hello",
            tenant_id="tenant-123",
            validate_response=True,
        )

        response = orchestrator.process_request(request)

        # Verify validation latency is captured
        assert response.metadata.latency.validation_ms is not None
        assert response.metadata.latency.validation_ms >= 0


class TestChatRequestValidateResponseFlag:
    """Tests for validate_response flag in ChatRequest."""

    def test_default_validate_response_true(self) -> None:
        """Test validate_response defaults to True."""
        request = ChatRequest(
            message="Test",
            tenant_id="tenant-123",
        )
        assert request.validate_response is True

    def test_validate_response_can_be_disabled(self) -> None:
        """Test validate_response can be set to False."""
        request = ChatRequest(
            message="Test",
            tenant_id="tenant-123",
            validate_response=False,
        )
        assert request.validate_response is False


class TestValidationMetricsModel:
    """Tests for ValidationMetrics model."""

    def test_default_values(self) -> None:
        """Test default values for ValidationMetrics."""
        metrics = ValidationMetrics()

        assert metrics.is_valid is True
        assert metrics.action == "PASS"
        assert metrics.was_modified is False
        assert metrics.validation_skipped is False
        assert metrics.rules_evaluated == 0
        assert metrics.fallback_used is False
        assert metrics.fallback_reason is None

    def test_from_validation_result(self) -> None:
        """Test creating ValidationMetrics from validation result."""
        metrics = ValidationMetrics(
            is_valid=False,
            action="BLOCK",
            was_modified=True,
            validation_skipped=False,
            rules_evaluated=3,
            fallback_used=True,
            fallback_reason="pii_blocked",
        )

        assert metrics.is_valid is False
        assert metrics.action == "BLOCK"
        assert metrics.fallback_reason == "pii_blocked"
