"""Pytest fixtures for Escalation Router tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from models import (
    EscalationData,
    EscalationFactors,
    EscalationRequest,
    EscalationRouterConfig,
    SentimentData,
)
from service import EscalationRouterService

# =============================================================================
# Environment Setup
# =============================================================================


@pytest.fixture(autouse=True)
def set_powertools_env() -> None:
    """Set required Powertools environment variables for all tests."""
    os.environ["POWERTOOLS_METRICS_NAMESPACE"] = "TestEscalationRouter"
    os.environ["POWERTOOLS_SERVICE_NAME"] = "escalation-router-test"
    os.environ["ESCALATION_QUEUE_URL"] = (
        "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo"
    )
    os.environ["DYNAMODB_TABLE_NAME"] = "test-conversations"
    os.environ["ENABLE_SNS_NOTIFICATIONS"] = "false"


# =============================================================================
# Factor Fixtures
# =============================================================================


@pytest.fixture
def default_factors() -> EscalationFactors:
    """Create default escalation factors."""
    return EscalationFactors(
        explicit_intent=0.0,
        negative_sentiment=0.0,
        urgency=0.0,
        repeated_question=0.0,
        low_confidence=0.0,
    )


@pytest.fixture
def high_explicit_intent_factors() -> EscalationFactors:
    """Create factors with high explicit intent (human request)."""
    return EscalationFactors(
        explicit_intent=1.0,
        negative_sentiment=0.3,
        urgency=0.5,
        repeated_question=0.0,
        low_confidence=0.0,
    )


@pytest.fixture
def high_frustration_factors() -> EscalationFactors:
    """Create factors indicating high customer frustration."""
    return EscalationFactors(
        explicit_intent=0.0,
        negative_sentiment=0.9,
        urgency=0.8,
        repeated_question=0.7,
        low_confidence=0.2,
    )


@pytest.fixture
def critical_factors() -> EscalationFactors:
    """Create factors for critical priority escalation."""
    return EscalationFactors(
        explicit_intent=1.0,
        negative_sentiment=0.9,
        urgency=0.9,
        repeated_question=0.5,
        low_confidence=0.3,
    )


# =============================================================================
# Escalation Data Fixtures
# =============================================================================


@pytest.fixture
def escalation_data_normal(default_factors: EscalationFactors) -> EscalationData:
    """Create escalation data for NORMAL priority."""
    return EscalationData(
        score=0.72,
        needs_escalation=True,
        threshold=0.70,
        factors=default_factors,
        primary_reason="threshold_exceeded",
    )


@pytest.fixture
def escalation_data_high(high_explicit_intent_factors: EscalationFactors) -> EscalationData:
    """Create escalation data for HIGH priority."""
    return EscalationData(
        score=0.85,
        needs_escalation=True,
        threshold=0.70,
        factors=high_explicit_intent_factors,
        primary_reason="explicit_intent",
    )


@pytest.fixture
def escalation_data_critical(critical_factors: EscalationFactors) -> EscalationData:
    """Create escalation data for CRITICAL priority."""
    return EscalationData(
        score=0.95,
        needs_escalation=True,
        threshold=0.70,
        factors=critical_factors,
        primary_reason="explicit_intent",
    )


@pytest.fixture
def escalation_data_no_escalation(default_factors: EscalationFactors) -> EscalationData:
    """Create escalation data where escalation is not needed."""
    return EscalationData(
        score=0.45,
        needs_escalation=False,
        threshold=0.70,
        factors=default_factors,
        primary_reason=None,
    )


# =============================================================================
# Sentiment Data Fixtures
# =============================================================================


@pytest.fixture
def sentiment_negative() -> SentimentData:
    """Create negative sentiment data."""
    return SentimentData(
        sentiment="NEGATIVE",
        confidence=0.88,
        negative_score=0.88,
    )


@pytest.fixture
def sentiment_neutral() -> SentimentData:
    """Create neutral sentiment data."""
    return SentimentData(
        sentiment="NEUTRAL",
        confidence=0.75,
        negative_score=0.10,
    )


@pytest.fixture
def sentiment_positive() -> SentimentData:
    """Create positive sentiment data."""
    return SentimentData(
        sentiment="POSITIVE",
        confidence=0.92,
        negative_score=0.05,
    )


# =============================================================================
# Request Fixtures
# =============================================================================


@pytest.fixture
def request_normal_priority(
    escalation_data_normal: EscalationData,
    sentiment_neutral: SentimentData,
) -> EscalationRequest:
    """Create a request that should route with NORMAL priority."""
    return EscalationRequest(
        conversation_id="conv-normal-001",
        tenant_id="tenant-001",
        user_id="user-123",
        escalation=escalation_data_normal,
        sentiment=sentiment_neutral,
        last_user_message="I'd like to speak with someone about my account.",
        message_count=3,
        intent="account_inquiry",
        intent_confidence=0.85,
    )


@pytest.fixture
def request_high_priority(
    escalation_data_high: EscalationData,
    sentiment_negative: SentimentData,
) -> EscalationRequest:
    """Create a request that should route with HIGH priority."""
    return EscalationRequest(
        conversation_id="conv-high-002",
        tenant_id="tenant-001",
        user_id="user-456",
        escalation=escalation_data_high,
        sentiment=sentiment_negative,
        last_user_message="Transfer me to a human agent now!",
        last_ai_response="I understand you'd like to speak with someone.",
        message_count=5,
        intent="escalation",
        intent_confidence=0.95,
        urgency="high",
        previous_intents=["complaint", "complaint"],
    )


@pytest.fixture
def request_critical_priority(
    escalation_data_critical: EscalationData,
    sentiment_negative: SentimentData,
) -> EscalationRequest:
    """Create a request that should route with CRITICAL priority."""
    return EscalationRequest(
        conversation_id="conv-critical-003",
        tenant_id="tenant-001",
        user_id="user-789",
        escalation=escalation_data_critical,
        sentiment=sentiment_negative,
        last_user_message="This is ridiculous! I demand to speak to a manager immediately!",
        last_ai_response="I sincerely apologize for the frustration.",
        message_count=8,
        intent="escalation",
        intent_confidence=0.98,
        urgency="critical",
        previous_intents=["complaint", "complaint", "escalation", "escalation"],
        metadata={"vip_customer": True},
    )


@pytest.fixture
def request_minimal(escalation_data_normal: EscalationData) -> EscalationRequest:
    """Create a minimal escalation request."""
    return EscalationRequest(
        conversation_id="conv-minimal",
        tenant_id="tenant-001",
        escalation=escalation_data_normal,
        last_user_message="Help me please.",
    )


# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture
def default_config() -> EscalationRouterConfig:
    """Create default service configuration."""
    return EscalationRouterConfig(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo",
        enable_queue=True,
        table_name="test-conversations",
        enable_dynamodb_update=True,
        enable_sns_notifications=False,
    )


@pytest.fixture
def config_with_sns() -> EscalationRouterConfig:
    """Create configuration with SNS enabled."""
    return EscalationRouterConfig(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo",
        enable_queue=True,
        sns_topic_arn="arn:aws:sns:us-east-1:123456789:test-topic",
        enable_sns_notifications=True,
        table_name="test-conversations",
        enable_dynamodb_update=True,
    )


@pytest.fixture
def config_queue_only() -> EscalationRouterConfig:
    """Create configuration with only queue enabled."""
    return EscalationRouterConfig(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo",
        enable_queue=True,
        enable_dynamodb_update=False,
        enable_sns_notifications=False,
    )


@pytest.fixture
def config_custom_thresholds() -> EscalationRouterConfig:
    """Create configuration with custom priority thresholds."""
    return EscalationRouterConfig(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo",
        critical_threshold=0.95,
        high_threshold=0.85,
    )


# =============================================================================
# Mock Client Fixtures
# =============================================================================


@pytest.fixture
def mock_sqs_client() -> MagicMock:
    """Create a mock SQS client."""
    client = MagicMock()
    client.send_message.return_value = {
        "MessageId": "sqs-msg-123456",
        "SequenceNumber": "123456789",
    }
    return client


@pytest.fixture
def mock_dynamodb_client() -> MagicMock:
    """Create a mock DynamoDB client."""
    client = MagicMock()
    client.update_item.return_value = {}
    return client


@pytest.fixture
def mock_sns_client() -> MagicMock:
    """Create a mock SNS client."""
    client = MagicMock()
    client.publish.return_value = {
        "MessageId": "sns-msg-789012",
    }
    return client


@pytest.fixture
def mock_sqs_error() -> MagicMock:
    """Create a mock SQS client that raises an error."""
    from botocore.exceptions import ClientError

    client = MagicMock()
    client.send_message.side_effect = ClientError(
        {"Error": {"Code": "ServiceException", "Message": "Service unavailable"}},
        "SendMessage",
    )
    return client


@pytest.fixture
def mock_dynamodb_error() -> MagicMock:
    """Create a mock DynamoDB client that raises an error."""
    from botocore.exceptions import ClientError

    client = MagicMock()
    client.update_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Condition failed"}},
        "UpdateItem",
    )
    return client


# =============================================================================
# Service Fixtures
# =============================================================================


@pytest.fixture
def service_with_mocks(
    default_config: EscalationRouterConfig,
    mock_sqs_client: MagicMock,
    mock_dynamodb_client: MagicMock,
    mock_sns_client: MagicMock,
) -> EscalationRouterService:
    """Create service with all mock clients."""
    return EscalationRouterService(
        config=default_config,
        sqs_client=mock_sqs_client,
        dynamodb_client=mock_dynamodb_client,
        sns_client=mock_sns_client,
    )


@pytest.fixture
def service_with_sns(
    config_with_sns: EscalationRouterConfig,
    mock_sqs_client: MagicMock,
    mock_dynamodb_client: MagicMock,
    mock_sns_client: MagicMock,
) -> EscalationRouterService:
    """Create service with SNS enabled and mock clients."""
    return EscalationRouterService(
        config=config_with_sns,
        sqs_client=mock_sqs_client,
        dynamodb_client=mock_dynamodb_client,
        sns_client=mock_sns_client,
    )


@pytest.fixture
def service_queue_only(
    config_queue_only: EscalationRouterConfig,
    mock_sqs_client: MagicMock,
) -> EscalationRouterService:
    """Create service with only queue enabled."""
    return EscalationRouterService(
        config=config_queue_only,
        sqs_client=mock_sqs_client,
    )
