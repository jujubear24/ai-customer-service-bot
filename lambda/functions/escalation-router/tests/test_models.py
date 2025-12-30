"""Unit tests for Escalation Router models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import (
    DynamoDBEscalationUpdate,
    EscalationData,
    EscalationFactors,
    EscalationMessage,
    EscalationPriority,
    EscalationRequest,
    EscalationResponse,
    EscalationRouterConfig,
    SentimentData,
)


class TestEscalationPriority:
    """Tests for EscalationPriority enum."""

    def test_priority_values(self) -> None:
        """Test priority enum values."""
        assert EscalationPriority.CRITICAL.value == "CRITICAL"
        assert EscalationPriority.HIGH.value == "HIGH"
        assert EscalationPriority.NORMAL.value == "NORMAL"

    def test_priority_is_string(self) -> None:
        """Test priority can be used as string via .value."""
        assert EscalationPriority.CRITICAL.value == "CRITICAL"
        assert EscalationPriority.HIGH.value == "HIGH"


class TestEscalationFactors:
    """Tests for EscalationFactors model."""

    def test_default_values(self) -> None:
        """Test default factor values."""
        factors = EscalationFactors()

        assert factors.explicit_intent == 0.0
        assert factors.negative_sentiment == 0.0
        assert factors.urgency == 0.0
        assert factors.repeated_question == 0.0
        assert factors.low_confidence == 0.0

    def test_custom_values(self) -> None:
        """Test custom factor values."""
        factors = EscalationFactors(
            explicit_intent=0.8,
            negative_sentiment=0.6,
            urgency=0.7,
            repeated_question=0.3,
            low_confidence=0.1,
        )

        assert factors.explicit_intent == 0.8
        assert factors.negative_sentiment == 0.6

    def test_validation_min_max(self) -> None:
        """Test factor validation boundaries."""
        # Valid at boundaries
        factors = EscalationFactors(explicit_intent=0.0, negative_sentiment=1.0)
        assert factors.explicit_intent == 0.0
        assert factors.negative_sentiment == 1.0

    def test_validation_exceeds_max(self) -> None:
        """Test validation rejects values > 1.0."""
        with pytest.raises(ValidationError):
            EscalationFactors(explicit_intent=1.5)

    def test_validation_below_min(self) -> None:
        """Test validation rejects values < 0.0."""
        with pytest.raises(ValidationError):
            EscalationFactors(negative_sentiment=-0.1)


class TestEscalationData:
    """Tests for EscalationData model."""

    def test_valid_escalation_data(self, default_factors: EscalationFactors) -> None:
        """Test creating valid escalation data."""
        data = EscalationData(
            score=0.85,
            needs_escalation=True,
            threshold=0.70,
            factors=default_factors,
            primary_reason="explicit_intent",
        )

        assert data.score == 0.85
        assert data.needs_escalation is True
        assert data.primary_reason == "explicit_intent"

    def test_default_threshold(self, default_factors: EscalationFactors) -> None:
        """Test default threshold value."""
        data = EscalationData(
            score=0.75,
            needs_escalation=True,
            factors=default_factors,
        )

        assert data.threshold == 0.70

    def test_optional_primary_reason(self, default_factors: EscalationFactors) -> None:
        """Test primary_reason is optional."""
        data = EscalationData(
            score=0.50,
            needs_escalation=False,
            factors=default_factors,
        )

        assert data.primary_reason is None


class TestSentimentData:
    """Tests for SentimentData model."""

    def test_valid_sentiment(self) -> None:
        """Test creating valid sentiment data."""
        data = SentimentData(
            sentiment="NEGATIVE",
            confidence=0.88,
            negative_score=0.85,
        )

        assert data.sentiment == "NEGATIVE"
        assert data.confidence == 0.88

    def test_default_negative_score(self) -> None:
        """Test default negative score."""
        data = SentimentData(
            sentiment="POSITIVE",
            confidence=0.90,
        )

        assert data.negative_score == 0.0


class TestEscalationRequest:
    """Tests for EscalationRequest model."""

    def test_valid_request(self, escalation_data_normal: EscalationData) -> None:
        """Test creating a valid escalation request."""
        request = EscalationRequest(
            conversation_id="conv-123",
            tenant_id="tenant-001",
            escalation=escalation_data_normal,
            last_user_message="I need help with my account.",
        )

        assert request.conversation_id == "conv-123"
        assert request.tenant_id == "tenant-001"
        assert request.escalation.score == 0.72

    def test_full_request(
        self,
        escalation_data_high: EscalationData,
        sentiment_negative: SentimentData,
    ) -> None:
        """Test creating a fully populated request."""
        request = EscalationRequest(
            conversation_id="conv-456",
            tenant_id="tenant-002",
            user_id="user-789",
            message_id="msg-001",
            escalation=escalation_data_high,
            sentiment=sentiment_negative,
            last_user_message="Transfer me now!",
            last_ai_response="I understand your concern.",
            message_count=5,
            intent="escalation",
            intent_confidence=0.95,
            urgency="high",
            previous_intents=["complaint", "complaint"],
            metadata={"vip": True},
        )

        assert request.user_id == "user-789"
        assert request.message_count == 5
        assert request.urgency == "high"
        assert len(request.previous_intents) == 2
        assert request.metadata["vip"] is True

    def test_default_values(self, escalation_data_normal: EscalationData) -> None:
        """Test default values for optional fields."""
        request = EscalationRequest(
            conversation_id="conv-123",
            tenant_id="tenant-001",
            escalation=escalation_data_normal,
            last_user_message="Help please.",
        )

        assert request.user_id is None
        assert request.message_count == 1
        assert request.previous_intents == []
        assert request.metadata == {}

    def test_empty_conversation_id_rejected(self, escalation_data_normal: EscalationData) -> None:
        """Test empty conversation_id is rejected."""
        with pytest.raises(ValidationError):
            EscalationRequest(
                conversation_id="",
                tenant_id="tenant-001",
                escalation=escalation_data_normal,
                last_user_message="Help",
            )

    def test_empty_tenant_id_rejected(self, escalation_data_normal: EscalationData) -> None:
        """Test empty tenant_id is rejected."""
        with pytest.raises(ValidationError):
            EscalationRequest(
                conversation_id="conv-123",
                tenant_id="",
                escalation=escalation_data_normal,
                last_user_message="Help",
            )


class TestEscalationMessage:
    """Tests for EscalationMessage model."""

    def test_valid_message(self, high_explicit_intent_factors: EscalationFactors) -> None:
        """Test creating a valid escalation message."""
        message = EscalationMessage(
            escalation_id="esc-abc123",
            conversation_id="conv-456",
            tenant_id="tenant-001",
            priority=EscalationPriority.HIGH,
            escalation_score=0.85,
            factors=high_explicit_intent_factors,
            last_user_message="Transfer me to a human!",
        )

        assert message.escalation_id == "esc-abc123"
        assert message.priority == EscalationPriority.HIGH

    def test_to_sqs_message_format(self, default_factors: EscalationFactors) -> None:
        """Test SQS message format generation."""
        message = EscalationMessage(
            escalation_id="esc-test-123",
            conversation_id="conv-789",
            tenant_id="tenant-001",
            priority=EscalationPriority.CRITICAL,
            escalation_score=0.95,
            factors=default_factors,
            last_user_message="Urgent help needed!",
        )

        sqs_msg = message.to_sqs_message()

        assert "MessageBody" in sqs_msg
        assert "MessageGroupId" in sqs_msg
        assert "MessageDeduplicationId" in sqs_msg

    def test_to_sqs_message_group_id_critical(self, default_factors: EscalationFactors) -> None:
        """Test CRITICAL priority message group ID."""
        message = EscalationMessage(
            escalation_id="esc-critical",
            conversation_id="conv-001",
            tenant_id="tenant-001",
            priority=EscalationPriority.CRITICAL,
            escalation_score=0.95,
            factors=default_factors,
            last_user_message="Help!",
        )

        sqs_msg = message.to_sqs_message()
        assert sqs_msg["MessageGroupId"] == "priority-critical"

    def test_to_sqs_message_group_id_high(self, default_factors: EscalationFactors) -> None:
        """Test HIGH priority message group ID."""
        message = EscalationMessage(
            escalation_id="esc-high",
            conversation_id="conv-001",
            tenant_id="tenant-001",
            priority=EscalationPriority.HIGH,
            escalation_score=0.85,
            factors=default_factors,
            last_user_message="Help!",
        )

        sqs_msg = message.to_sqs_message()
        assert sqs_msg["MessageGroupId"] == "priority-high"

    def test_to_sqs_message_group_id_normal(self, default_factors: EscalationFactors) -> None:
        """Test NORMAL priority message group ID."""
        message = EscalationMessage(
            escalation_id="esc-normal",
            conversation_id="conv-001",
            tenant_id="tenant-001",
            priority=EscalationPriority.NORMAL,
            escalation_score=0.72,
            factors=default_factors,
            last_user_message="Help!",
        )

        sqs_msg = message.to_sqs_message()
        assert sqs_msg["MessageGroupId"] == "priority-normal"

    def test_to_sqs_deduplication_id(self, default_factors: EscalationFactors) -> None:
        """Test deduplication ID is escalation_id."""
        message = EscalationMessage(
            escalation_id="esc-unique-abc",
            conversation_id="conv-001",
            tenant_id="tenant-001",
            priority=EscalationPriority.NORMAL,
            escalation_score=0.72,
            factors=default_factors,
            last_user_message="Help!",
        )

        sqs_msg = message.to_sqs_message()
        assert sqs_msg["MessageDeduplicationId"] == "esc-unique-abc"


class TestDynamoDBEscalationUpdate:
    """Tests for DynamoDBEscalationUpdate model."""

    def test_valid_update(self) -> None:
        """Test creating a valid DynamoDB update."""
        update = DynamoDBEscalationUpdate(
            conversation_id="conv-123",
            escalation_id="esc-456",
            escalation_score=0.85,
            escalation_reason="explicit_intent",
            escalation_priority=EscalationPriority.HIGH,
        )

        assert update.status == "ESCALATED"
        assert update.gsi2_pk == "STATUS#ESCALATED"
        assert update.conversation_id in update.gsi2_sk

    def test_gsi2_sk_format(self) -> None:
        """Test GSI2 sort key format includes timestamp and conversation_id."""
        update = DynamoDBEscalationUpdate(
            conversation_id="conv-abc",
            escalation_id="esc-xyz",
            escalation_score=0.90,
            escalation_reason="frustration",
            escalation_priority=EscalationPriority.CRITICAL,
        )

        # Format: {timestamp}#{conversation_id}
        assert "#conv-abc" in update.gsi2_sk
        # Should contain ISO timestamp
        assert "T" in update.gsi2_sk  # ISO format includes T

    def test_to_update_expression_structure(self) -> None:
        """Test update expression has correct structure."""
        update = DynamoDBEscalationUpdate(
            conversation_id="conv-123",
            escalation_id="esc-456",
            escalation_score=0.85,
            escalation_reason="test",
            escalation_priority=EscalationPriority.HIGH,
        )

        expr = update.to_update_expression()

        assert "UpdateExpression" in expr
        assert "ExpressionAttributeNames" in expr
        assert "ExpressionAttributeValues" in expr

    def test_to_update_expression_values(self) -> None:
        """Test update expression contains correct values."""
        update = DynamoDBEscalationUpdate(
            conversation_id="conv-123",
            escalation_id="esc-789",
            escalation_score=0.92,
            escalation_reason="explicit_intent",
            escalation_priority=EscalationPriority.CRITICAL,
        )

        expr = update.to_update_expression()
        values = expr["ExpressionAttributeValues"]

        assert values[":status"] == "ESCALATED"
        assert values[":esc_id"] == "esc-789"
        assert values[":esc_priority"] == "CRITICAL"


class TestEscalationResponse:
    """Tests for EscalationResponse model."""

    def test_successful_response(self) -> None:
        """Test creating a successful response."""
        response = EscalationResponse(
            success=True,
            escalation_id="esc-success-123",
            priority=EscalationPriority.HIGH,
            queue_message_id="sqs-msg-456",
        )

        assert response.success is True
        assert response.escalation_id == "esc-success-123"
        assert response.queue_message_id == "sqs-msg-456"

    def test_default_customer_message(self) -> None:
        """Test default customer message is set."""
        response = EscalationResponse(
            success=True,
            escalation_id="esc-test",
            priority=EscalationPriority.NORMAL,
        )

        assert "escalated" in response.customer_message.lower()
        assert "human agent" in response.customer_message.lower()

    def test_default_estimated_wait(self) -> None:
        """Test default estimated wait time."""
        response = EscalationResponse(
            success=True,
            escalation_id="esc-test",
            priority=EscalationPriority.NORMAL,
        )

        assert response.estimated_wait == "< 5 minutes"


class TestEscalationRouterConfig:
    """Tests for EscalationRouterConfig model."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = EscalationRouterConfig()

        assert config.enable_queue is True
        assert config.enable_sns_notifications is False
        assert config.enable_dynamodb_update is True
        assert config.critical_threshold == 0.90
        assert config.high_threshold == 0.80

    def test_custom_thresholds(self) -> None:
        """Test custom threshold configuration."""
        config = EscalationRouterConfig(
            critical_threshold=0.95,
            high_threshold=0.85,
        )

        assert config.critical_threshold == 0.95
        assert config.high_threshold == 0.85

    def test_determine_priority_critical(self) -> None:
        """Test priority determination for CRITICAL."""
        config = EscalationRouterConfig()

        assert config.determine_priority(0.95) == EscalationPriority.CRITICAL
        assert config.determine_priority(0.90) == EscalationPriority.CRITICAL
        assert config.determine_priority(1.0) == EscalationPriority.CRITICAL

    def test_determine_priority_high(self) -> None:
        """Test priority determination for HIGH."""
        config = EscalationRouterConfig()

        assert config.determine_priority(0.85) == EscalationPriority.HIGH
        assert config.determine_priority(0.80) == EscalationPriority.HIGH
        assert config.determine_priority(0.89) == EscalationPriority.HIGH

    def test_determine_priority_normal(self) -> None:
        """Test priority determination for NORMAL."""
        config = EscalationRouterConfig()

        assert config.determine_priority(0.75) == EscalationPriority.NORMAL
        assert config.determine_priority(0.70) == EscalationPriority.NORMAL
        assert config.determine_priority(0.79) == EscalationPriority.NORMAL

    def test_determine_priority_below_normal_still_normal(self) -> None:
        """Test scores below normal threshold still return NORMAL."""
        config = EscalationRouterConfig()

        # Even if score is below threshold, if it's being routed, it's NORMAL
        assert config.determine_priority(0.50) == EscalationPriority.NORMAL
        assert config.determine_priority(0.0) == EscalationPriority.NORMAL

    def test_determine_priority_custom_thresholds(self) -> None:
        """Test priority with custom thresholds."""
        config = EscalationRouterConfig(
            critical_threshold=0.95,
            high_threshold=0.85,
        )

        # With custom thresholds
        assert config.determine_priority(0.90) == EscalationPriority.HIGH
        assert config.determine_priority(0.95) == EscalationPriority.CRITICAL
        assert config.determine_priority(0.80) == EscalationPriority.NORMAL

    def test_get_customer_message_critical(self) -> None:
        """Test customer message for CRITICAL priority."""
        config = EscalationRouterConfig()

        message = config.get_customer_message(EscalationPriority.CRITICAL)

        assert "apologize" in message.lower()
        assert "senior" in message.lower() or "top priority" in message.lower()

    def test_get_customer_message_high(self) -> None:
        """Test customer message for HIGH priority."""
        config = EscalationRouterConfig()

        message = config.get_customer_message(EscalationPriority.HIGH)

        assert "concern" in message.lower()
        assert "human agent" in message.lower()

    def test_get_customer_message_normal(self) -> None:
        """Test customer message for NORMAL priority."""
        config = EscalationRouterConfig()

        message = config.get_customer_message(EscalationPriority.NORMAL)

        assert "escalated" in message.lower()

    def test_custom_customer_messages(self) -> None:
        """Test custom customer messages."""
        config = EscalationRouterConfig(
            customer_messages={
                "CRITICAL": "Custom critical message",
                "HIGH": "Custom high message",
                "NORMAL": "Custom normal message",
            }
        )

        assert config.get_customer_message(EscalationPriority.CRITICAL) == "Custom critical message"
        assert config.get_customer_message(EscalationPriority.HIGH) == "Custom high message"
