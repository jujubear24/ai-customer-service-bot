"""Pytest fixtures for Response Validator tests."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest

from escalation import EscalationScorer, EscalationScorerConfig
from models import (
    EscalationFactors,
    PIIAction,
    PIICheckResult,
    PIIDetection,
    PIIType,
    Sentiment,
    SentimentResult,
    SentimentScores,
    ValidationRequest,
)
from pii_detector import PIIDetector, PIIDetectorConfig
from rules import (
    LengthRuleConfig,
    ProfanityRule,
    ResponseLengthRule,
    RulesEngine,
    TopicRestrictionRule,
)
from sentiment_analyzer import SentimentAnalyzer, SentimentAnalyzerConfig
from service import ResponseValidatorService, ValidationServiceConfig

# =============================================================================
# Environment Setup - Autouse fixture for Powertools
# =============================================================================


@pytest.fixture(autouse=True)
def set_powertools_env() -> None:
    """Set required Powertools environment variables for all tests."""
    os.environ["POWERTOOLS_METRICS_NAMESPACE"] = "TestResponseValidator"
    os.environ["POWERTOOLS_SERVICE_NAME"] = "response-validator-test"


# =============================================================================
# Request Fixtures
# =============================================================================


@pytest.fixture
def sample_request() -> ValidationRequest:
    """Create a sample validation request."""
    return ValidationRequest(
        response_text="Here is how to reset your password. Go to settings and click reset.",
        user_message="How do I reset my password?",
        conversation_id="conv-12345",
        tenant_id="test-tenant",
        intent="question",
        intent_confidence=0.92,
        urgency="low",
        message_count=1,
    )


@pytest.fixture
def request_with_escalation_intent() -> ValidationRequest:
    """Create a request indicating escalation intent."""
    return ValidationRequest(
        response_text="I understand your frustration. Let me help you.",
        user_message="I want to speak to a manager right now!",
        conversation_id="conv-escalate",
        tenant_id="test-tenant",
        intent="escalation",
        intent_confidence=0.95,
        urgency="high",
        message_count=5,
        previous_intents=["complaint", "complaint", "escalation"],
    )


@pytest.fixture
def request_minimal() -> ValidationRequest:
    """Create a minimal validation request."""
    return ValidationRequest(
        response_text="Hello!",
        user_message="Hi",
        conversation_id="conv-minimal",
        tenant_id="test-tenant",
    )


@pytest.fixture
def request_with_pii_response() -> ValidationRequest:
    """Create a request with PII in the response."""
    return ValidationRequest(
        response_text="Your SSN is 123-45-6789 and your card is 4111-1111-1111-1111.",
        user_message="What are my account details?",
        conversation_id="conv-pii",
        tenant_id="test-tenant",
    )


@pytest.fixture
def request_with_profanity() -> ValidationRequest:
    """Create a request with profanity in the response."""
    return ValidationRequest(
        response_text="That's a damn good question, let me help you.",
        user_message="Can you help me?",
        conversation_id="conv-profanity",
        tenant_id="test-tenant",
    )


@pytest.fixture
def request_with_long_response() -> ValidationRequest:
    """Create a request with a very long response."""
    long_text = "This is a detailed response. " * 100  # ~3000 chars
    return ValidationRequest(
        response_text=long_text,
        user_message="Tell me everything",
        conversation_id="conv-long",
        tenant_id="test-tenant",
    )


@pytest.fixture
def request_with_short_response() -> ValidationRequest:
    """Create a request with a too-short response."""
    return ValidationRequest(
        response_text="OK",
        user_message="Help me",
        conversation_id="conv-short",
        tenant_id="test-tenant",
    )


@pytest.fixture
def request_with_medical_content() -> ValidationRequest:
    """Create a request with medical advice content."""
    return ValidationRequest(
        response_text=(
            "Based on your symptoms, you should take this medication. "
            "The recommended dosage is 500mg twice daily. "
            "You should see a doctor if symptoms persist."
        ),
        user_message="What should I do about my headache?",
        conversation_id="conv-medical",
        tenant_id="test-tenant",
    )


# =============================================================================
# Model Fixtures
# =============================================================================


@pytest.fixture
def sample_pii_detection() -> PIIDetection:
    """Create a sample PII detection."""
    return PIIDetection(
        pii_type=PIIType.SSN,
        text="12*****89",
        start_offset=12,
        end_offset=23,
        confidence=0.95,
        source="comprehend",
        action=PIIAction.BLOCK,
    )


@pytest.fixture
def sample_pii_check_result_passed() -> PIICheckResult:
    """Create a passing PII check result."""
    return PIICheckResult(
        passed=True,
        detections=[],
        blocked_types=[],
        redacted_count=0,
    )


@pytest.fixture
def sample_pii_check_result_failed(sample_pii_detection: PIIDetection) -> PIICheckResult:
    """Create a failing PII check result."""
    return PIICheckResult(
        passed=False,
        detections=[sample_pii_detection],
        blocked_types=[PIIType.SSN],
        redacted_count=0,
    )


@pytest.fixture
def sample_sentiment_result() -> SentimentResult:
    """Create a sample sentiment result."""
    return SentimentResult(
        sentiment=Sentiment.NEUTRAL,
        confidence=0.85,
        scores=SentimentScores(
            positive=0.10,
            negative=0.05,
            neutral=0.85,
            mixed=0.00,
        ),
    )


@pytest.fixture
def sample_escalation_factors() -> EscalationFactors:
    """Create sample escalation factors."""
    return EscalationFactors(
        explicit_intent=0.0,
        negative_sentiment=0.2,
        urgency=0.0,
        repeated_question=0.0,
        low_confidence=0.1,
    )


@pytest.fixture
def high_escalation_factors() -> EscalationFactors:
    """Create escalation factors that trigger escalation."""
    return EscalationFactors(
        explicit_intent=1.0,
        negative_sentiment=0.8,
        urgency=1.0,
        repeated_question=0.5,
        low_confidence=0.3,
    )


# =============================================================================
# Service & Component Fixtures
# =============================================================================


@pytest.fixture
def pii_detector_config() -> PIIDetectorConfig:
    """Create a PII detector configuration."""
    return PIIDetectorConfig(
        use_comprehend=False,  # Disable for unit tests
        min_confidence=0.8,
    )


@pytest.fixture
def pii_detector(pii_detector_config: PIIDetectorConfig) -> PIIDetector:
    """Create a PII detector with Comprehend disabled."""
    return PIIDetector(config=pii_detector_config)


@pytest.fixture
def profanity_rule() -> ProfanityRule:
    """Create a profanity rule."""
    return ProfanityRule()


@pytest.fixture
def length_rule() -> ResponseLengthRule:
    """Create a response length rule."""
    return ResponseLengthRule()


@pytest.fixture
def length_rule_strict() -> ResponseLengthRule:
    """Create a strict response length rule."""
    config = LengthRuleConfig(
        min_length=50,
        max_length=500,
        truncate_if_exceeded=False,
    )
    return ResponseLengthRule(config=config)


@pytest.fixture
def topic_rule() -> TopicRestrictionRule:
    """Create a topic restriction rule."""
    return TopicRestrictionRule()


@pytest.fixture
def rules_engine() -> RulesEngine:
    """Create a rules engine with default rules."""
    return RulesEngine()


@pytest.fixture
def rules_engine_profanity_only() -> RulesEngine:
    """Create a rules engine with only profanity rule."""
    return RulesEngine(rules=[ProfanityRule()])


@pytest.fixture
def validation_service_config() -> ValidationServiceConfig:
    """Create a validation service configuration."""
    return ValidationServiceConfig(
        enable_pii_detection=True,
        enable_profanity_check=True,
        enable_business_rules=True,
        enable_length_check=True,
    )


@pytest.fixture
def validation_service_no_pii() -> ValidationServiceConfig:
    """Create a validation service config with PII disabled."""
    return ValidationServiceConfig(
        enable_pii_detection=False,
        enable_profanity_check=True,
        enable_business_rules=True,
        enable_length_check=True,
    )


@pytest.fixture
def validation_service(
    validation_service_config: ValidationServiceConfig,
    pii_detector: PIIDetector,
) -> ResponseValidatorService:
    """Create a validation service with mocked PII detector."""
    return ResponseValidatorService(
        config=validation_service_config,
        pii_detector=pii_detector,
    )


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_comprehend_client() -> MagicMock:
    """Create a mock Comprehend client."""
    client = MagicMock()
    client.detect_pii_entities.return_value = {
        "Entities": [],
    }
    return client


@pytest.fixture
def mock_comprehend_with_pii() -> MagicMock:
    """Create a mock Comprehend client that returns PII."""
    client = MagicMock()
    client.detect_pii_entities.return_value = {
        "Entities": [
            {
                "Type": "SSN",
                "Score": 0.95,
                "BeginOffset": 12,
                "EndOffset": 23,
            },
            {
                "Type": "CREDIT_DEBIT_NUMBER",
                "Score": 0.98,
                "BeginOffset": 45,
                "EndOffset": 64,
            },
        ],
    }
    return client


@pytest.fixture
def mock_lambda_context() -> MagicMock:
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "response-validator"
    context.memory_limit_in_mb = 512
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789:function:response-validator"
    context.aws_request_id = "test-request-id-12345"
    context.get_remaining_time_in_millis.return_value = 30000
    return context


# =============================================================================
# Comprehend Sentiment Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_comprehend_sentiment_positive() -> MagicMock:
    """Create a mock Comprehend client that returns positive sentiment."""
    mock = MagicMock()
    mock.detect_sentiment.return_value = {
        "Sentiment": "POSITIVE",
        "SentimentScore": {
            "Positive": 0.95,
            "Negative": 0.01,
            "Neutral": 0.03,
            "Mixed": 0.01,
        },
    }
    return mock


@pytest.fixture
def mock_comprehend_sentiment_negative() -> MagicMock:
    """Create a mock Comprehend client that returns negative sentiment."""
    mock = MagicMock()
    mock.detect_sentiment.return_value = {
        "Sentiment": "NEGATIVE",
        "SentimentScore": {
            "Positive": 0.02,
            "Negative": 0.88,
            "Neutral": 0.05,
            "Mixed": 0.05,
        },
    }
    return mock


@pytest.fixture
def mock_comprehend_sentiment_neutral() -> MagicMock:
    """Create a mock Comprehend client that returns neutral sentiment."""
    mock = MagicMock()
    mock.detect_sentiment.return_value = {
        "Sentiment": "NEUTRAL",
        "SentimentScore": {
            "Positive": 0.03,
            "Negative": 0.02,
            "Neutral": 0.92,
            "Mixed": 0.03,
        },
    }
    return mock


@pytest.fixture
def mock_comprehend_sentiment_mixed() -> MagicMock:
    """Create a mock Comprehend client that returns mixed sentiment."""
    mock = MagicMock()
    mock.detect_sentiment.return_value = {
        "Sentiment": "MIXED",
        "SentimentScore": {
            "Positive": 0.35,
            "Negative": 0.30,
            "Neutral": 0.10,
            "Mixed": 0.25,
        },
    }
    return mock


# =============================================================================
# Sentiment Analyzer Fixtures
# =============================================================================


@pytest.fixture
def sentiment_analyzer(mock_comprehend_sentiment_neutral: MagicMock) -> SentimentAnalyzer:
    """Create a sentiment analyzer with mocked Comprehend client."""
    return SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_neutral)


@pytest.fixture
def sentiment_analyzer_no_comprehend() -> SentimentAnalyzer:
    """Create a sentiment analyzer without Comprehend (for escalation pattern testing)."""
    config = SentimentAnalyzerConfig(fail_open=True)
    return SentimentAnalyzer(config=config)


# =============================================================================
# Escalation Scorer Fixtures
# =============================================================================


@pytest.fixture
def escalation_scorer() -> EscalationScorer:
    """Create an escalation scorer with default config."""
    return EscalationScorer()


@pytest.fixture
def escalation_scorer_low_threshold() -> EscalationScorer:
    """Create an escalation scorer with low threshold for testing."""
    config = EscalationScorerConfig(threshold=0.30)
    return EscalationScorer(config=config)


@pytest.fixture
def escalation_scorer_high_threshold() -> EscalationScorer:
    """Create an escalation scorer with high threshold for testing."""
    config = EscalationScorerConfig(threshold=0.90)
    return EscalationScorer(config=config)


# =============================================================================
# Full Validation Service Fixture (with sentiment & escalation)
# =============================================================================


@pytest.fixture
def validation_service_full(
    pii_detector: PIIDetector,
    mock_comprehend_sentiment_neutral: MagicMock,
) -> ResponseValidatorService:
    """Create a validation service with all features enabled including sentiment."""
    sentiment_analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_neutral)

    config = ValidationServiceConfig(
        enable_pii_detection=True,
        enable_profanity_check=True,
        enable_business_rules=True,
        enable_length_check=True,
        enable_sentiment_analysis=True,
        enable_escalation_scoring=True,
    )

    return ResponseValidatorService(
        config=config,
        pii_detector=pii_detector,
        sentiment_analyzer=sentiment_analyzer,
    )


# =============================================================================
# Lambda Event Fixtures
# =============================================================================


@pytest.fixture
def lambda_event_direct(sample_request: ValidationRequest) -> dict[str, Any]:
    """Create a direct invocation Lambda event."""
    return sample_request.model_dump()


@pytest.fixture
def lambda_event_api_gateway(sample_request: ValidationRequest) -> dict[str, Any]:
    """Create an API Gateway format Lambda event."""
    import json

    return {
        "body": json.dumps(sample_request.model_dump()),
        "headers": {"Content-Type": "application/json"},
        "httpMethod": "POST",
        "path": "/validate",
    }


@pytest.fixture
def lambda_event_invalid() -> dict[str, Any]:
    """Create an invalid Lambda event."""
    return {
        "response_text": "",  # Empty - will fail validation
        "user_message": "test",
        "conversation_id": "conv-123",
        "tenant_id": "test",
    }


@pytest.fixture
def lambda_event_malformed_json() -> dict[str, Any]:
    """Create a Lambda event with malformed JSON body."""
    return {
        "body": "{ invalid json }",
    }
