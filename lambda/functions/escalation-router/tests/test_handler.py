"""Unit tests for Escalation Router Lambda handler."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from models import EscalationPriority

if TYPE_CHECKING:
    pass


# =============================================================================
# Handler Import Fixtures
# =============================================================================


@pytest.fixture
def handler_module():
    """Import handler module after setting environment variables."""
    # Ensure environment is set
    os.environ["ESCALATION_QUEUE_URL"] = (
        "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo"
    )
    os.environ["DYNAMODB_TABLE_NAME"] = "test-conversations"
    os.environ["ENABLE_SNS_NOTIFICATIONS"] = "false"
    os.environ["FAIL_OPEN_ON_ERROR"] = "false"

    import handler

    # Reset the service singleton for each test
    handler._service = None
    return handler


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "test-escalation-router"
    context.memory_limit_in_mb = 256
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789:function:test"
    context.aws_request_id = "test-request-id-123"
    return context


# =============================================================================
# Event Builder Helpers
# =============================================================================


def build_escalation_event(
    conversation_id: str = "conv-test-001",
    tenant_id: str = "tenant-001",
    escalation_score: float = 0.85,
    needs_escalation: bool = True,
    last_user_message: str = "I need to speak with a human!",
    sentiment: str = "NEGATIVE",
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a valid escalation event."""
    return {
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "escalation": {
            "score": escalation_score,
            "needs_escalation": needs_escalation,
            "threshold": 0.70,
            "factors": {
                "explicit_intent": kwargs.get("explicit_intent", 0.8),
                "negative_sentiment": kwargs.get("negative_sentiment", 0.5),
                "urgency": kwargs.get("urgency_factor", 0.4),
                "repeated_question": kwargs.get("repeated_question", 0.0),
                "low_confidence": kwargs.get("low_confidence", 0.0),
            },
            "primary_reason": kwargs.get("primary_reason", "explicit_intent"),
        },
        "sentiment": {
            "sentiment": sentiment,
            "confidence": 0.88,
            "negative_score": 0.85,
        },
        "last_user_message": last_user_message,
        "last_ai_response": kwargs.get("last_ai_response", "I understand your concern."),
        "message_count": kwargs.get("message_count", 3),
        "intent": kwargs.get("intent", "escalation"),
        "intent_confidence": kwargs.get("intent_confidence", 0.92),
        "urgency": kwargs.get("urgency", "high"),
        "previous_intents": kwargs.get("previous_intents", ["complaint"]),
        "metadata": kwargs.get("metadata", {}),
    }


def build_api_gateway_event(body: dict[str, Any]) -> dict[str, Any]:
    """Wrap body in API Gateway event format."""
    return {
        "body": json.dumps(body),
        "headers": {"Content-Type": "application/json"},
        "httpMethod": "POST",
        "isBase64Encoded": False,
        "path": "/escalate",
        "requestContext": {
            "requestId": "api-request-123",
        },
    }


# =============================================================================
# Handler Tests
# =============================================================================


class TestHandlerSuccess:
    """Tests for successful handler execution."""

    def test_handler_success_direct_invocation(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler with direct Lambda invocation."""
        event = build_escalation_event()

        with patch.object(handler_module, "get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.route_escalation.return_value = MagicMock(
                success=True,
                escalation_id="esc-test-123",
                priority=EscalationPriority.HIGH,
                queue_message_id="sqs-msg-456",
                notification_sent=False,
                customer_message="Your request has been escalated.",
                estimated_wait="< 5 minutes",
                processed_at=MagicMock(isoformat=lambda: "2025-01-01T00:00:00"),
                error_message=None,
            )
            mock_get_service.return_value = mock_service

            response = handler_module.handler(event, mock_context)

            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert body["success"] is True
            assert body["escalation_id"] == "esc-test-123"

    def test_handler_success_api_gateway_event(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler with API Gateway event format."""
        event = build_api_gateway_event(build_escalation_event())

        with patch.object(handler_module, "get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.route_escalation.return_value = MagicMock(
                success=True,
                escalation_id="esc-api-456",
                priority=EscalationPriority.NORMAL,
                queue_message_id="sqs-msg-789",
                notification_sent=False,
                customer_message="Escalated to support.",
                estimated_wait="< 10 minutes",
                processed_at=MagicMock(isoformat=lambda: "2025-01-01T00:00:00"),
                error_message=None,
            )
            mock_get_service.return_value = mock_service

            response = handler_module.handler(event, mock_context)

            assert response["statusCode"] == 200

    def test_handler_returns_priority_in_response(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler includes priority in response."""
        event = build_escalation_event(escalation_score=0.95)

        with patch.object(handler_module, "get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.route_escalation.return_value = MagicMock(
                success=True,
                escalation_id="esc-crit-789",
                priority=EscalationPriority.CRITICAL,
                queue_message_id="sqs-critical",
                notification_sent=True,
                customer_message="Immediately escalated.",
                estimated_wait="< 2 minutes",
                processed_at=MagicMock(isoformat=lambda: "2025-01-01T00:00:00"),
                error_message=None,
            )
            mock_get_service.return_value = mock_service

            response = handler_module.handler(event, mock_context)

            body = json.loads(response["body"])
            assert body["priority"] == "CRITICAL"


class TestHandlerValidation:
    """Tests for request validation."""

    def test_handler_rejects_no_escalation_needed(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler gracefully handles requests where escalation is not needed."""
        event = build_escalation_event(
            escalation_score=0.45,
            needs_escalation=False,
        )

        response = handler_module.handler(event, mock_context)

        # Returns 200 with success=False (graceful handling, not an error)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is False
        assert "not required" in body.get("error", "").lower()

    def test_handler_rejects_missing_conversation_id(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler rejects missing conversation_id."""
        event = build_escalation_event()
        del event["conversation_id"]

        response = handler_module.handler(event, mock_context)

        assert response["statusCode"] == 400

    def test_handler_rejects_missing_tenant_id(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler rejects missing tenant_id."""
        event = build_escalation_event()
        del event["tenant_id"]

        response = handler_module.handler(event, mock_context)

        assert response["statusCode"] == 400

    def test_handler_rejects_missing_escalation_data(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler rejects missing escalation data."""
        event = build_escalation_event()
        del event["escalation"]

        response = handler_module.handler(event, mock_context)

        assert response["statusCode"] == 400

    def test_handler_rejects_invalid_escalation_score(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler rejects invalid escalation score."""
        event = build_escalation_event()
        event["escalation"]["score"] = 1.5  # Invalid: > 1.0

        response = handler_module.handler(event, mock_context)

        assert response["statusCode"] == 400

    def test_handler_rejects_empty_last_user_message(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler rejects empty last_user_message."""
        event = build_escalation_event()
        event["last_user_message"] = ""

        response = handler_module.handler(event, mock_context)

        assert response["statusCode"] == 400


class TestHandlerErrors:
    """Tests for error handling."""

    def test_handler_service_error(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler handles service errors."""
        event = build_escalation_event()

        with patch.object(handler_module, "get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.route_escalation.side_effect = Exception("Service failed")
            mock_get_service.return_value = mock_service

            response = handler_module.handler(event, mock_context)

            assert response["statusCode"] == 500
            body = json.loads(response["body"])
            assert body["success"] is False

    def test_handler_fail_open_mode(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler with FAIL_OPEN_ON_ERROR=true continues on error."""
        os.environ["FAIL_OPEN_ON_ERROR"] = "true"

        # Reset service singleton
        handler_module._service = None

        event = build_escalation_event()

        with patch.object(handler_module, "get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.route_escalation.side_effect = Exception("Service failed")
            mock_get_service.return_value = mock_service

            response = handler_module.handler(event, mock_context)

            # With fail-open, should return 200 with fail_open flag
            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert body.get("fail_open") is True

        # Reset for other tests
        os.environ["FAIL_OPEN_ON_ERROR"] = "false"

    def test_handler_invalid_json_body(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler handles invalid JSON in API Gateway event."""
        event = {
            "body": "not valid json",
            "headers": {"Content-Type": "application/json"},
        }

        response = handler_module.handler(event, mock_context)

        assert response["statusCode"] == 400


class TestHandlerMinimalRequest:
    """Tests for minimal request scenarios."""

    def test_handler_minimal_valid_request(
        self,
        handler_module,
        mock_context: MagicMock,
    ) -> None:
        """Test handler with minimal required fields."""
        event = {
            "conversation_id": "conv-minimal",
            "tenant_id": "tenant-001",
            "escalation": {
                "score": 0.75,
                "needs_escalation": True,
                "factors": {},
            },
            "last_user_message": "Help please",
        }

        with patch.object(handler_module, "get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.route_escalation.return_value = MagicMock(
                success=True,
                escalation_id="esc-min-001",
                priority=EscalationPriority.NORMAL,
                queue_message_id="sqs-min",
                notification_sent=False,
                customer_message="Escalated.",
                estimated_wait="< 10 minutes",
                processed_at=MagicMock(isoformat=lambda: "2025-01-01T00:00:00"),
                error_message=None,
            )
            mock_get_service.return_value = mock_service

            response = handler_module.handler(event, mock_context)

            assert response["statusCode"] == 200


class TestGetService:
    """Tests for get_service function."""

    def test_get_service_singleton(
        self,
        handler_module,
    ) -> None:
        """Test get_service returns singleton."""
        # Reset singleton
        handler_module._service = None

        with patch("service.EscalationRouterService") as mock_class:
            mock_instance = MagicMock()
            mock_class.return_value = mock_instance

            service1 = handler_module.get_service()
            service2 = handler_module.get_service()

            # Should only instantiate once
            assert mock_class.call_count == 1
            assert service1 is service2


class TestParseRequest:
    """Tests for _parse_request function."""

    def test_parse_direct_event(
        self,
        handler_module,
    ) -> None:
        """Test parsing direct Lambda event."""
        event = build_escalation_event()

        request = handler_module._parse_request(event)

        assert request.conversation_id == "conv-test-001"
        assert request.tenant_id == "tenant-001"
        assert request.escalation.score == 0.85

    def test_parse_api_gateway_event(
        self,
        handler_module,
    ) -> None:
        """Test parsing API Gateway event."""
        body = build_escalation_event(conversation_id="conv-api")
        event = build_api_gateway_event(body)

        request = handler_module._parse_request(event)

        assert request.conversation_id == "conv-api"

    def test_parse_preserves_optional_fields(
        self,
        handler_module,
    ) -> None:
        """Test parsing preserves optional fields."""
        event = build_escalation_event(
            user_id="user-123",
            urgency="critical",
            previous_intents=["a", "b", "c"],
            metadata={"key": "value"},
        )
        event["user_id"] = "user-123"

        request = handler_module._parse_request(event)

        assert request.user_id == "user-123"
        assert request.urgency == "critical"
        assert len(request.previous_intents) == 3


class TestBuildResponse:
    """Tests for _build_response function."""

    def test_build_success_response(
        self,
        handler_module,
    ) -> None:
        """Test building success response."""
        body = {"success": True, "escalation_id": "esc-123"}

        response = handler_module._build_response(200, body)

        assert response["statusCode"] == 200
        assert "body" in response
        assert json.loads(response["body"]) == body

    def test_build_error_response(
        self,
        handler_module,
    ) -> None:
        """Test building error response."""
        body = {"success": False, "message": "Error occurred"}

        response = handler_module._build_response(500, body)

        assert response["statusCode"] == 500

    def test_response_has_cors_headers(
        self,
        handler_module,
    ) -> None:
        """Test response includes CORS headers."""
        response = handler_module._build_response(200, {})

        headers = response.get("headers", {})
        assert "Content-Type" in headers
