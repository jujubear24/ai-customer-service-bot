"""Unit tests for Response Validator models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import (
    EscalationFactors,
    EscalationResult,
    LengthCheckResult,
    PIIAction,
    PIICheckResult,
    PIIDetection,
    PIIType,
    ProfanityCheckResult,
    Sentiment,
    SentimentResult,
    ValidationAction,
    ValidationOptions,
    ValidationRequest,
    ValidationResponse,
    ValidationResults,
)
from models import (
    ValidationError as ValidationErrorModel,
)


class TestValidationRequest:
    """Tests for ValidationRequest model."""

    def test_valid_request(self) -> None:
        """Test creating a valid request."""
        request = ValidationRequest(
            response_text="This is a valid response.",
            user_message="What is the answer?",
            conversation_id="conv-123",
            tenant_id="tenant-456",
        )

        assert request.response_text == "This is a valid response."
        assert request.user_message == "What is the answer?"
        assert request.conversation_id == "conv-123"
        assert request.tenant_id == "tenant-456"

    def test_request_with_all_fields(self) -> None:
        """Test creating a request with all optional fields."""
        request = ValidationRequest(
            response_text="Response text here.",
            user_message="User message here.",
            conversation_id="conv-123",
            tenant_id="tenant-456",
            intent="question",
            intent_confidence=0.95,
            urgency="high",
            message_count=5,
            previous_intents=["greeting", "question"],
            options=ValidationOptions(check_pii=False),
        )

        assert request.intent == "question"
        assert request.intent_confidence == 0.95
        assert request.urgency == "high"
        assert request.message_count == 5
        assert request.previous_intents == ["greeting", "question"]
        assert request.options.check_pii is False

    def test_request_strips_whitespace(self) -> None:
        """Test that whitespace is stripped from text fields."""
        request = ValidationRequest(
            response_text="  Response with spaces  ",
            user_message="  Message with spaces  ",
            conversation_id="  conv-123  ",
            tenant_id="  tenant-456  ",
        )

        assert request.response_text == "Response with spaces"
        assert request.user_message == "Message with spaces"
        assert request.conversation_id == "conv-123"
        assert request.tenant_id == "tenant-456"

    def test_request_empty_response_text_fails(self) -> None:
        """Test that empty response_text fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ValidationRequest(
                response_text="",
                user_message="Valid message",
                conversation_id="conv-123",
                tenant_id="tenant-456",
            )

        assert "response_text" in str(exc_info.value)

    def test_request_whitespace_only_response_fails(self) -> None:
        """Test that whitespace-only response fails validation."""
        with pytest.raises(ValidationError):
            ValidationRequest(
                response_text="   ",
                user_message="Valid message",
                conversation_id="conv-123",
                tenant_id="tenant-456",
            )

    def test_request_empty_tenant_fails(self) -> None:
        """Test that empty tenant_id fails validation."""
        with pytest.raises(ValidationError):
            ValidationRequest(
                response_text="Valid response",
                user_message="Valid message",
                conversation_id="conv-123",
                tenant_id="",
            )

    def test_request_confidence_bounds(self) -> None:
        """Test intent_confidence bounds validation."""
        # Valid bounds
        request = ValidationRequest(
            response_text="Response",
            user_message="Message",
            conversation_id="conv-123",
            tenant_id="tenant-456",
            intent_confidence=0.0,
        )
        assert request.intent_confidence == 0.0

        request = ValidationRequest(
            response_text="Response",
            user_message="Message",
            conversation_id="conv-123",
            tenant_id="tenant-456",
            intent_confidence=1.0,
        )
        assert request.intent_confidence == 1.0

        # Invalid bounds
        with pytest.raises(ValidationError):
            ValidationRequest(
                response_text="Response",
                user_message="Message",
                conversation_id="conv-123",
                tenant_id="tenant-456",
                intent_confidence=1.5,
            )

    def test_request_defaults(self) -> None:
        """Test default values are applied."""
        request = ValidationRequest(
            response_text="Response",
            user_message="Message",
            conversation_id="conv-123",
            tenant_id="tenant-456",
        )

        assert request.intent is None
        assert request.intent_confidence is None
        assert request.urgency is None
        assert request.message_count == 1
        assert request.previous_intents == []
        assert request.options.check_pii is True


class TestValidationOptions:
    """Tests for ValidationOptions model."""

    def test_default_options(self) -> None:
        """Test default options values."""
        options = ValidationOptions()

        assert options.check_pii is True
        assert options.check_profanity is True
        assert options.check_business_rules is True
        assert options.analyze_sentiment is True
        assert options.calculate_escalation is True
        assert options.redact_pii is True

    def test_custom_options(self) -> None:
        """Test custom options values."""
        options = ValidationOptions(
            check_pii=False,
            check_profanity=False,
            analyze_sentiment=False,
        )

        assert options.check_pii is False
        assert options.check_profanity is False
        assert options.analyze_sentiment is False
        assert options.check_business_rules is True  # Still default


class TestPIIDetection:
    """Tests for PIIDetection model."""

    def test_pii_detection_creation(self) -> None:
        """Test creating a PII detection."""
        detection = PIIDetection(
            pii_type=PIIType.SSN,
            text="12*****89",
            start_offset=0,
            end_offset=11,
            confidence=0.95,
            source="comprehend",
            action=PIIAction.BLOCK,
        )

        assert detection.pii_type == PIIType.SSN
        assert detection.confidence == 0.95
        assert detection.action == PIIAction.BLOCK
        assert detection.redacted_text is None

    def test_pii_detection_with_redaction(self) -> None:
        """Test PII detection with redacted text."""
        detection = PIIDetection(
            pii_type=PIIType.PHONE,
            text="55*****00",
            start_offset=10,
            end_offset=22,
            confidence=0.88,
            source="regex",
            action=PIIAction.REDACT,
            redacted_text="************",
        )

        assert detection.action == PIIAction.REDACT
        assert detection.redacted_text == "************"


class TestPIICheckResult:
    """Tests for PIICheckResult model."""

    def test_passed_result(self) -> None:
        """Test a passing PII check result."""
        result = PIICheckResult(
            passed=True,
            detections=[],
            blocked_types=[],
            redacted_count=0,
        )

        assert result.passed is True
        assert result.has_detections is False
        assert result.critical_pii_found is False

    def test_failed_result_with_detections(self) -> None:
        """Test a failing PII check result."""
        detection = PIIDetection(
            pii_type=PIIType.SSN,
            text="***",
            start_offset=0,
            end_offset=11,
            confidence=0.95,
            source="comprehend",
            action=PIIAction.BLOCK,
        )

        result = PIICheckResult(
            passed=False,
            detections=[detection],
            blocked_types=[PIIType.SSN],
            redacted_count=0,
        )

        assert result.passed is False
        assert result.has_detections is True
        assert result.critical_pii_found is True

    def test_critical_pii_types(self) -> None:
        """Test critical_pii_found property with different types."""
        # Non-critical PII
        detection = PIIDetection(
            pii_type=PIIType.NAME,
            text="***",
            start_offset=0,
            end_offset=5,
            confidence=0.9,
            source="comprehend",
            action=PIIAction.WARN,
        )

        result = PIICheckResult(
            passed=True,
            detections=[detection],
            blocked_types=[],
            redacted_count=0,
        )

        assert result.has_detections is True
        assert result.critical_pii_found is False

        # Credit card - critical
        cc_detection = PIIDetection(
            pii_type=PIIType.CREDIT_DEBIT_NUMBER,
            text="***",
            start_offset=0,
            end_offset=16,
            confidence=0.98,
            source="comprehend",
            action=PIIAction.BLOCK,
        )

        result_critical = PIICheckResult(
            passed=False,
            detections=[cc_detection],
            blocked_types=[PIIType.CREDIT_DEBIT_NUMBER],
            redacted_count=0,
        )

        assert result_critical.critical_pii_found is True


class TestSentimentResult:
    """Tests for SentimentResult model."""

    def test_from_comprehend_factory(self) -> None:
        """Test creating from Comprehend response."""
        result = SentimentResult.from_comprehend(
            sentiment="POSITIVE",
            scores={
                "Positive": 0.85,
                "Negative": 0.05,
                "Neutral": 0.08,
                "Mixed": 0.02,
            },
        )

        assert result.sentiment == Sentiment.POSITIVE
        assert result.confidence == 0.85
        assert result.scores.positive == 0.85
        assert result.scores.negative == 0.05

    def test_from_comprehend_negative(self) -> None:
        """Test creating negative sentiment from Comprehend."""
        result = SentimentResult.from_comprehend(
            sentiment="NEGATIVE",
            scores={
                "Positive": 0.05,
                "Negative": 0.90,
                "Neutral": 0.03,
                "Mixed": 0.02,
            },
        )

        assert result.sentiment == Sentiment.NEGATIVE
        assert result.confidence == 0.90


class TestEscalationFactors:
    """Tests for EscalationFactors model."""

    def test_weighted_score_calculation(self) -> None:
        """Test weighted score property."""
        factors = EscalationFactors(
            explicit_intent=1.0,
            negative_sentiment=0.0,
            urgency=0.0,
            repeated_question=0.0,
            low_confidence=0.0,
        )

        # 0.35 * 1.0 = 0.35
        assert factors.weighted_score == pytest.approx(0.35)

    def test_weighted_score_multiple_factors(self) -> None:
        """Test weighted score with multiple factors."""
        factors = EscalationFactors(
            explicit_intent=1.0,  # 0.35
            negative_sentiment=1.0,  # 0.25
            urgency=1.0,  # 0.20
            repeated_question=1.0,  # 0.15
            low_confidence=1.0,  # 0.05
        )

        # All weights sum to 1.0
        assert factors.weighted_score == pytest.approx(1.0)

    def test_dominant_factor(self) -> None:
        """Test dominant factor property."""
        factors = EscalationFactors(
            explicit_intent=1.0,
            negative_sentiment=0.5,
            urgency=0.3,
            repeated_question=0.0,
            low_confidence=0.0,
        )

        assert factors.dominant_factor == "explicit_intent"

    def test_dominant_factor_zero_scores(self) -> None:
        """Test dominant factor when all scores are zero."""
        factors = EscalationFactors()

        assert factors.dominant_factor is None


class TestEscalationResult:
    """Tests for EscalationResult model."""

    def test_calculate_below_threshold(self) -> None:
        """Test calculation below escalation threshold."""
        factors = EscalationFactors(
            explicit_intent=0.0,
            negative_sentiment=0.5,
            urgency=0.0,
            repeated_question=0.0,
            low_confidence=0.0,
        )

        result = EscalationResult.calculate(factors, threshold=0.70)

        assert result.score == pytest.approx(0.125)  # 0.25 * 0.5
        assert result.needs_escalation is False
        assert result.primary_reason is None

    def test_calculate_above_threshold(self) -> None:
        """Test calculation above escalation threshold."""
        factors = EscalationFactors(
            explicit_intent=1.0,
            negative_sentiment=0.8,
            urgency=1.0,
            repeated_question=0.5,
            low_confidence=0.0,
        )

        result = EscalationResult.calculate(factors, threshold=0.70)

        assert result.needs_escalation is True
        assert result.primary_reason is not None
        assert "escalation" in result.primary_reason.lower()


class TestValidationResults:
    """Tests for ValidationResults model."""

    def test_all_passed_empty(self) -> None:
        """Test all_passed with no checks."""
        results = ValidationResults()

        assert results.all_passed is True
        assert results.failed_checks == []

    def test_all_passed_with_passing_checks(self) -> None:
        """Test all_passed with all passing checks."""
        results = ValidationResults(
            profanity=ProfanityCheckResult(passed=True),
            pii=PIICheckResult(passed=True, detections=[], blocked_types=[], redacted_count=0),
            length=LengthCheckResult(passed=True, char_count=100),
        )

        assert results.all_passed is True
        assert results.failed_checks == []

    def test_all_passed_with_failures(self) -> None:
        """Test all_passed with some failures."""
        results = ValidationResults(
            profanity=ProfanityCheckResult(passed=False, detected_terms=["test"]),
            pii=PIICheckResult(passed=True, detections=[], blocked_types=[], redacted_count=0),
        )

        assert results.all_passed is False
        assert results.failed_checks == ["profanity"]

    def test_multiple_failures(self) -> None:
        """Test with multiple failed checks."""
        results = ValidationResults(
            profanity=ProfanityCheckResult(passed=False, detected_terms=["test"]),
            length=LengthCheckResult(passed=False, char_count=5, min_length=20, max_length=2000),
        )

        assert results.all_passed is False
        assert "profanity" in results.failed_checks
        assert "length" in results.failed_checks


class TestValidationResponse:
    """Tests for ValidationResponse model."""

    def test_create_factory(self) -> None:
        """Test the create factory method."""
        response = ValidationResponse.create(
            original_response="Original text",
            validated_response="Validated text",
            is_valid=True,
            action=ValidationAction.MODIFY,
            validation_results=ValidationResults(),
            validation_time_ms=150.5,
            rules_evaluated=3,
        )

        assert response.is_valid is True
        assert response.action == ValidationAction.MODIFY
        assert response.original_response == "Original text"
        assert response.validated_response == "Validated text"
        assert response.metadata.validation_time_ms == 150.5
        assert response.metadata.rules_evaluated == 3

    def test_was_modified_property(self) -> None:
        """Test was_modified property."""
        response_modified = ValidationResponse.create(
            original_response="Original",
            validated_response="Modified",
            is_valid=True,
            action=ValidationAction.MODIFY,
            validation_results=ValidationResults(),
            validation_time_ms=100.0,
        )

        assert response_modified.was_modified is True

        response_same = ValidationResponse.create(
            original_response="Same",
            validated_response="Same",
            is_valid=True,
            action=ValidationAction.PASS,
            validation_results=ValidationResults(),
            validation_time_ms=100.0,
        )

        assert response_same.was_modified is False

    def test_needs_escalation_property(self) -> None:
        """Test needs_escalation property."""
        factors = EscalationFactors(explicit_intent=1.0)
        escalation = EscalationResult.calculate(factors, threshold=0.30)

        response = ValidationResponse.create(
            original_response="Text",
            validated_response="Text",
            is_valid=True,
            action=ValidationAction.PASS,
            validation_results=ValidationResults(),
            validation_time_ms=100.0,
        )
        response = ValidationResponse(
            **response.model_dump(exclude={"escalation"}),
            escalation=escalation,
        )

        assert response.needs_escalation is True

    def test_has_warnings_property(self) -> None:
        """Test has_warnings property."""
        response_warn = ValidationResponse.create(
            original_response="Text",
            validated_response="Text",
            is_valid=True,
            action=ValidationAction.WARN,
            validation_results=ValidationResults(),
            validation_time_ms=100.0,
        )

        assert response_warn.has_warnings is True

        response_pass = ValidationResponse.create(
            original_response="Text",
            validated_response="Text",
            is_valid=True,
            action=ValidationAction.PASS,
            validation_results=ValidationResults(),
            validation_time_ms=100.0,
        )

        assert response_pass.has_warnings is False


class TestValidationErrorModel:
    """Tests for ValidationError model."""

    def test_error_creation(self) -> None:
        """Test creating a validation error."""
        error = ValidationErrorModel(
            error_type="TestError",
            message="This is a test error",
            retryable=True,
            conversation_id="conv-123",
            details={"key": "value"},
        )

        assert error.error_type == "TestError"
        assert error.message == "This is a test error"
        assert error.retryable is True
        assert error.conversation_id == "conv-123"
        assert error.details == {"key": "value"}

    def test_error_defaults(self) -> None:
        """Test error default values."""
        error = ValidationErrorModel(
            error_type="TestError",
            message="Error message",
        )

        assert error.retryable is False
        assert error.conversation_id is None
        assert error.details is None
