"""Unit tests for Escalation Router service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from models import (
    EscalationPriority,
    EscalationRequest,
    EscalationRouterConfig,
)
from service import (
    EscalationRouterService,
    NotificationError,
    QueueError,
    create_escalation_router,
    create_escalation_router_from_env,
)

if TYPE_CHECKING:
    pass


class TestEscalationRouterServiceInit:
    """Tests for EscalationRouterService initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default config."""
        service = EscalationRouterService()

        assert service.config is not None
        assert service.config.enable_queue is True

    def test_init_with_custom_config(self, default_config: EscalationRouterConfig) -> None:
        """Test initialization with custom config."""
        service = EscalationRouterService(config=default_config)

        assert service.config.queue_url == default_config.queue_url

    def test_init_with_clients(
        self,
        default_config: EscalationRouterConfig,
        mock_sqs_client: MagicMock,
        mock_dynamodb_client: MagicMock,
    ) -> None:
        """Test initialization with injected clients."""
        service = EscalationRouterService(
            config=default_config,
            sqs_client=mock_sqs_client,
            dynamodb_client=mock_dynamodb_client,
        )

        assert service._sqs_client is mock_sqs_client
        assert service._dynamodb_client is mock_dynamodb_client


class TestEscalationRouterServiceLazyLoading:
    """Tests for lazy-loading of AWS clients."""

    def test_sqs_client_lazy_load(self, default_config: EscalationRouterConfig) -> None:
        """Test SQS client is lazy-loaded."""
        service = EscalationRouterService(config=default_config)

        assert service._sqs_client is None

        with patch("boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            client = service.sqs_client

            mock_boto.assert_called_once_with("sqs")
            assert client is not None

    def test_dynamodb_client_lazy_load(self, default_config: EscalationRouterConfig) -> None:
        """Test DynamoDB client is lazy-loaded."""
        service = EscalationRouterService(config=default_config)

        assert service._dynamodb_client is None

        with patch("boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            client = service.dynamodb_client

            mock_boto.assert_called_once_with("dynamodb")
            assert client is not None

    def test_sns_client_lazy_load(self, default_config: EscalationRouterConfig) -> None:
        """Test SNS client is lazy-loaded."""
        service = EscalationRouterService(config=default_config)

        assert service._sns_client is None

        with patch("boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            client = service.sns_client

            mock_boto.assert_called_once_with("sns")
            assert client is not None


class TestRouteEscalation:
    """Tests for route_escalation method."""

    def test_route_normal_priority(
        self,
        service_with_mocks: EscalationRouterService,
        request_normal_priority: EscalationRequest,
    ) -> None:
        """Test routing with NORMAL priority."""
        response = service_with_mocks.route_escalation(request_normal_priority)

        assert response.success is True
        assert response.priority == EscalationPriority.NORMAL
        assert response.escalation_id.startswith("esc-")

    def test_route_high_priority(
        self,
        service_with_mocks: EscalationRouterService,
        request_high_priority: EscalationRequest,
    ) -> None:
        """Test routing with HIGH priority."""
        response = service_with_mocks.route_escalation(request_high_priority)

        assert response.success is True
        assert response.priority == EscalationPriority.HIGH

    def test_route_critical_priority(
        self,
        service_with_mocks: EscalationRouterService,
        request_critical_priority: EscalationRequest,
    ) -> None:
        """Test routing with CRITICAL priority."""
        response = service_with_mocks.route_escalation(request_critical_priority)

        assert response.success is True
        assert response.priority == EscalationPriority.CRITICAL

    def test_route_calls_sqs(
        self,
        service_with_mocks: EscalationRouterService,
        request_normal_priority: EscalationRequest,
        mock_sqs_client: MagicMock,
    ) -> None:
        """Test that routing calls SQS send_message."""
        service_with_mocks.route_escalation(request_normal_priority)

        mock_sqs_client.send_message.assert_called_once()
        call_kwargs = mock_sqs_client.send_message.call_args.kwargs
        assert "MessageBody" in call_kwargs
        assert "MessageGroupId" in call_kwargs
        assert call_kwargs["MessageGroupId"] == "priority-normal"

    def test_route_calls_dynamodb(
        self,
        service_with_mocks: EscalationRouterService,
        request_normal_priority: EscalationRequest,
        mock_dynamodb_client: MagicMock,
    ) -> None:
        """Test that routing calls DynamoDB update_item."""
        service_with_mocks.route_escalation(request_normal_priority)

        mock_dynamodb_client.update_item.assert_called_once()

    def test_route_returns_queue_message_id(
        self,
        service_with_mocks: EscalationRouterService,
        request_normal_priority: EscalationRequest,
    ) -> None:
        """Test response includes SQS message ID."""
        response = service_with_mocks.route_escalation(request_normal_priority)

        assert response.queue_message_id == "sqs-msg-123456"

    def test_route_returns_customer_message(
        self,
        service_with_mocks: EscalationRouterService,
        request_normal_priority: EscalationRequest,
    ) -> None:
        """Test response includes customer-facing message."""
        response = service_with_mocks.route_escalation(request_normal_priority)

        assert response.customer_message is not None
        assert len(response.customer_message) > 0

    def test_route_returns_estimated_wait(
        self,
        service_with_mocks: EscalationRouterService,
        request_critical_priority: EscalationRequest,
    ) -> None:
        """Test response includes estimated wait time."""
        response = service_with_mocks.route_escalation(request_critical_priority)

        assert response.estimated_wait is not None
        assert "minute" in response.estimated_wait.lower()


class TestRouteEscalationWithSNS:
    """Tests for route_escalation with SNS notifications."""

    def test_route_with_sns_enabled(
        self,
        service_with_sns: EscalationRouterService,
        request_high_priority: EscalationRequest,
        mock_sns_client: MagicMock,
    ) -> None:
        """Test routing with SNS notifications enabled."""
        response = service_with_sns.route_escalation(request_high_priority)

        assert response.success is True
        assert response.notification_sent is True
        mock_sns_client.publish.assert_called_once()

    def test_sns_message_includes_priority(
        self,
        service_with_sns: EscalationRouterService,
        request_critical_priority: EscalationRequest,
        mock_sns_client: MagicMock,
    ) -> None:
        """Test SNS message includes priority in subject."""
        service_with_sns.route_escalation(request_critical_priority)

        call_kwargs = mock_sns_client.publish.call_args.kwargs
        assert "CRITICAL" in call_kwargs["Subject"]

    def test_sns_failure_doesnt_fail_request(
        self,
        config_with_sns: EscalationRouterConfig,
        mock_sqs_client: MagicMock,
        mock_dynamodb_client: MagicMock,
        request_high_priority: EscalationRequest,
    ) -> None:
        """Test SNS failure doesn't fail the overall request."""
        mock_sns_error = MagicMock()
        mock_sns_error.publish.side_effect = ClientError(
            {"Error": {"Code": "ServiceException", "Message": "SNS unavailable"}},
            "Publish",
        )

        service = EscalationRouterService(
            config=config_with_sns,
            sqs_client=mock_sqs_client,
            dynamodb_client=mock_dynamodb_client,
            sns_client=mock_sns_error,
        )

        response = service.route_escalation(request_high_priority)

        # Request should still succeed despite SNS failure
        assert response.success is True
        assert response.notification_sent is False


class TestRouteEscalationErrors:
    """Tests for error handling in route_escalation."""

    def test_sqs_error_raises_queue_error(
        self,
        default_config: EscalationRouterConfig,
        mock_sqs_error: MagicMock,
        mock_dynamodb_client: MagicMock,
        request_normal_priority: EscalationRequest,
    ) -> None:
        """Test SQS error raises QueueError."""
        service = EscalationRouterService(
            config=default_config,
            sqs_client=mock_sqs_error,
            dynamodb_client=mock_dynamodb_client,
        )

        with pytest.raises(QueueError):
            service.route_escalation(request_normal_priority)

    def test_dynamodb_error_continues(
        self,
        default_config: EscalationRouterConfig,
        mock_sqs_client: MagicMock,
        mock_dynamodb_error: MagicMock,
        request_normal_priority: EscalationRequest,
    ) -> None:
        """Test DynamoDB error doesn't fail the request."""
        service = EscalationRouterService(
            config=default_config,
            sqs_client=mock_sqs_client,
            dynamodb_client=mock_dynamodb_error,
        )

        # Should succeed even with DynamoDB error
        response = service.route_escalation(request_normal_priority)

        assert response.success is True
        # Error message should be captured
        assert response.error_message is not None
        assert "DynamoDB" in response.error_message

    def test_queue_disabled_skips_sqs(
        self,
        mock_sqs_client: MagicMock,
        request_normal_priority: EscalationRequest,
    ) -> None:
        """Test queue disabled skips SQS call."""
        config = EscalationRouterConfig(
            queue_url="https://sqs.example.com/queue.fifo",
            enable_queue=False,
            enable_dynamodb_update=False,
        )
        service = EscalationRouterService(
            config=config,
            sqs_client=mock_sqs_client,
        )

        response = service.route_escalation(request_normal_priority)

        assert response.success is True
        mock_sqs_client.send_message.assert_not_called()


class TestRouteEscalationQueueOnly:
    """Tests for queue-only configuration."""

    def test_queue_only_skips_dynamodb(
        self,
        service_queue_only: EscalationRouterService,
        request_normal_priority: EscalationRequest,
    ) -> None:
        """Test queue-only config skips DynamoDB update."""
        response = service_queue_only.route_escalation(request_normal_priority)

        assert response.success is True
        # DynamoDB client should never be accessed
        assert service_queue_only._dynamodb_client is None


class TestGenerateEscalationId:
    """Tests for _generate_escalation_id method."""

    def test_generates_unique_ids(self, service_with_mocks: EscalationRouterService) -> None:
        """Test escalation IDs are unique."""
        id1 = service_with_mocks._generate_escalation_id()
        id2 = service_with_mocks._generate_escalation_id()

        assert id1 != id2

    def test_id_format(self, service_with_mocks: EscalationRouterService) -> None:
        """Test escalation ID format."""
        esc_id = service_with_mocks._generate_escalation_id()

        assert esc_id.startswith("esc-")
        assert len(esc_id) == 16  # "esc-" + 12 hex chars


class TestBuildEscalationMessage:
    """Tests for _build_escalation_message method."""

    def test_message_contains_required_fields(
        self,
        service_with_mocks: EscalationRouterService,
        request_high_priority: EscalationRequest,
    ) -> None:
        """Test message contains all required fields."""
        message = service_with_mocks._build_escalation_message(
            request=request_high_priority,
            escalation_id="esc-test-123",
            priority=EscalationPriority.HIGH,
        )

        assert message.escalation_id == "esc-test-123"
        assert message.conversation_id == request_high_priority.conversation_id
        assert message.tenant_id == request_high_priority.tenant_id
        assert message.priority == EscalationPriority.HIGH
        assert message.escalation_score == request_high_priority.escalation.score

    def test_message_includes_sentiment(
        self,
        service_with_mocks: EscalationRouterService,
        request_high_priority: EscalationRequest,
    ) -> None:
        """Test message includes sentiment when present."""
        message = service_with_mocks._build_escalation_message(
            request=request_high_priority,
            escalation_id="esc-test",
            priority=EscalationPriority.HIGH,
        )

        assert message.sentiment == "NEGATIVE"

    def test_message_includes_metadata(
        self,
        service_with_mocks: EscalationRouterService,
        request_critical_priority: EscalationRequest,
    ) -> None:
        """Test message includes metadata."""
        message = service_with_mocks._build_escalation_message(
            request=request_critical_priority,
            escalation_id="esc-meta",
            priority=EscalationPriority.CRITICAL,
        )

        assert "vip_customer" in message.metadata


class TestSendToQueue:
    """Tests for _send_to_queue method."""

    def test_send_to_queue_success(
        self,
        service_with_mocks: EscalationRouterService,
        request_normal_priority: EscalationRequest,
        mock_sqs_client: MagicMock,
    ) -> None:
        """Test successful queue send."""
        message = service_with_mocks._build_escalation_message(
            request=request_normal_priority,
            escalation_id="esc-queue-test",
            priority=EscalationPriority.NORMAL,
        )

        msg_id = service_with_mocks._send_to_queue(message)

        assert msg_id == "sqs-msg-123456"
        mock_sqs_client.send_message.assert_called_once()

    def test_send_to_queue_no_url_raises_error(
        self,
        mock_sqs_client: MagicMock,
        default_factors,
    ) -> None:
        """Test missing queue URL raises QueueError."""
        from models import EscalationMessage

        config = EscalationRouterConfig(queue_url="")
        service = EscalationRouterService(config=config, sqs_client=mock_sqs_client)

        message = EscalationMessage(
            escalation_id="esc-test",
            conversation_id="conv-test",
            tenant_id="tenant-test",
            priority=EscalationPriority.NORMAL,
            escalation_score=0.75,
            factors=default_factors,
            last_user_message="Test",
        )

        with pytest.raises(QueueError) as exc_info:
            service._send_to_queue(message)

        assert "not configured" in str(exc_info.value)


class TestUpdateConversationStatus:
    """Tests for _update_conversation_status method."""

    def test_update_calls_dynamodb(
        self,
        service_with_mocks: EscalationRouterService,
        request_normal_priority: EscalationRequest,
        mock_dynamodb_client: MagicMock,
    ) -> None:
        """Test status update calls DynamoDB."""
        service_with_mocks._update_conversation_status(
            request=request_normal_priority,
            escalation_id="esc-update-test",
            priority=EscalationPriority.NORMAL,
        )

        mock_dynamodb_client.update_item.assert_called_once()
        call_kwargs = mock_dynamodb_client.update_item.call_args.kwargs
        assert call_kwargs["TableName"] == "test-conversations"


class TestSendNotification:
    """Tests for _send_notification method."""

    def test_notification_not_sent_without_topic(
        self,
        service_with_mocks: EscalationRouterService,
        request_normal_priority: EscalationRequest,
        default_factors,
    ) -> None:
        """Test notification raises error without topic ARN."""
        from models import EscalationMessage

        message = EscalationMessage(
            escalation_id="esc-test",
            conversation_id="conv-test",
            tenant_id="tenant-test",
            priority=EscalationPriority.HIGH,
            escalation_score=0.85,
            factors=default_factors,
            last_user_message="Test",
        )

        with pytest.raises(NotificationError):
            service_with_mocks._send_notification(message, EscalationPriority.HIGH)


class TestGetEstimatedWait:
    """Tests for _get_estimated_wait method."""

    def test_critical_wait_time(self, service_with_mocks: EscalationRouterService) -> None:
        """Test CRITICAL priority wait time."""
        wait = service_with_mocks._get_estimated_wait(EscalationPriority.CRITICAL)
        assert "2 minute" in wait

    def test_high_wait_time(self, service_with_mocks: EscalationRouterService) -> None:
        """Test HIGH priority wait time."""
        wait = service_with_mocks._get_estimated_wait(EscalationPriority.HIGH)
        assert "5 minute" in wait

    def test_normal_wait_time(self, service_with_mocks: EscalationRouterService) -> None:
        """Test NORMAL priority wait time."""
        wait = service_with_mocks._get_estimated_wait(EscalationPriority.NORMAL)
        assert "10 minute" in wait


class TestConvenienceFunctions:
    """Tests for convenience factory functions."""

    def test_create_escalation_router(self) -> None:
        """Test create_escalation_router function."""
        service = create_escalation_router(
            queue_url="https://sqs.example.com/queue.fifo",
            table_name="test-table",
        )

        assert service.config.queue_url == "https://sqs.example.com/queue.fifo"
        assert service.config.table_name == "test-table"

    def test_create_escalation_router_with_sns(self) -> None:
        """Test create_escalation_router with SNS enabled."""
        service = create_escalation_router(
            queue_url="https://sqs.example.com/queue.fifo",
            sns_topic_arn="arn:aws:sns:us-east-1:123456789:topic",
            enable_sns=True,
        )

        assert service.config.enable_sns_notifications is True
        assert service.config.sns_topic_arn == "arn:aws:sns:us-east-1:123456789:topic"

    def test_create_escalation_router_from_env(self) -> None:
        """Test create_escalation_router_from_env function."""
        import os

        os.environ["ESCALATION_QUEUE_URL"] = "https://sqs.example.com/env-queue.fifo"
        os.environ["DYNAMODB_TABLE_NAME"] = "env-table"
        os.environ["ENABLE_SNS_NOTIFICATIONS"] = "false"
        os.environ["CRITICAL_THRESHOLD"] = "0.92"
        os.environ["HIGH_THRESHOLD"] = "0.82"

        service = create_escalation_router_from_env()

        assert service.config.queue_url == "https://sqs.example.com/env-queue.fifo"
        assert service.config.table_name == "env-table"
        assert service.config.critical_threshold == 0.92
        assert service.config.high_threshold == 0.82
