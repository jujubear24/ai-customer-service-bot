"""Response Validator request and response models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Enums
# =============================================================================


class Sentiment(str, Enum):
    """Sentiment classification from Amazon Comprehend."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"


class PIIType(str, Enum):
    """PII entity types detected by Comprehend and custom patterns."""

    # Comprehend standard types
    SSN = "SSN"
    CREDIT_DEBIT_NUMBER = "CREDIT_DEBIT_NUMBER"
    BANK_ACCOUNT_NUMBER = "BANK_ACCOUNT_NUMBER"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    ADDRESS = "ADDRESS"
    DATE_TIME = "DATE_TIME"
    DRIVER_ID = "DRIVER_ID"
    PASSPORT_NUMBER = "PASSPORT_NUMBER"
    NAME = "NAME"
    AGE = "AGE"

    # Custom business types
    ORDER_ID = "ORDER_ID"
    ACCOUNT_CODE = "ACCOUNT_CODE"
    CUSTOMER_REF = "CUSTOMER_REF"


class PIIAction(str, Enum):
    """Action to take when PII is detected."""

    BLOCK = "BLOCK"
    REDACT = "REDACT"
    WARN = "WARN"
    ALLOW = "ALLOW"


class RuleSeverity(str, Enum):
    """Severity level for business rule violations."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ValidationAction(str, Enum):
    """Action taken by the validator."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    MODIFY = "MODIFY"
    WARN = "WARN"


# =============================================================================
# Request Models
# =============================================================================


class ValidationOptions(BaseModel):
    """Configuration options for validation checks."""

    check_pii: bool = Field(default=True, description="Enable PII detection")
    check_profanity: bool = Field(default=True, description="Enable profanity detection")
    check_business_rules: bool = Field(default=True, description="Enable business rules")
    analyze_sentiment: bool = Field(default=True, description="Enable sentiment analysis")
    calculate_escalation: bool = Field(default=True, description="Calculate escalation score")
    redact_pii: bool = Field(default=True, description="Redact PII instead of blocking")


class ValidationRequest(BaseModel):
    """Request model for response validation."""

    response_text: str = Field(
        ..., min_length=1, max_length=10000, description="AI response to validate"
    )
    user_message: str = Field(
        ..., min_length=1, max_length=2000, description="Original user message"
    )
    conversation_id: str = Field(..., min_length=1, max_length=100, description="Conversation ID")
    tenant_id: str = Field(..., min_length=1, max_length=100, description="Tenant identifier")

    # Intent metadata
    intent: str | None = Field(default=None, description="Classified intent")
    intent_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Intent confidence"
    )
    urgency: str | None = Field(default=None, description="Urgency level: low, medium, high")

    # Context for escalation
    message_count: int = Field(default=1, ge=1, description="Messages in conversation")
    previous_intents: list[str] = Field(default_factory=list, description="Previous intents")

    # Options
    options: ValidationOptions = Field(default_factory=ValidationOptions)

    @field_validator("response_text", "user_message")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Strip whitespace and validate non-empty."""
        v = v.strip()
        if not v:
            raise ValueError("Field cannot be empty")
        return v

    @field_validator("tenant_id", "conversation_id")
    @classmethod
    def validate_id_fields(cls, v: str) -> str:
        """Strip whitespace and validate non-empty."""
        v = v.strip()
        if not v:
            raise ValueError("ID field cannot be empty")
        return v


# =============================================================================
# Result Models
# =============================================================================


class PIIDetection(BaseModel):
    """Details of a detected PII entity."""

    pii_type: PIIType = Field(..., description="Type of PII detected")
    text: str = Field(..., description="Detected text (may be masked)")
    start_offset: int = Field(..., ge=0, description="Start character offset")
    end_offset: int = Field(..., ge=0, description="End character offset")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence")
    source: str = Field(..., description="Detection source: comprehend or regex")
    action: PIIAction = Field(..., description="Action taken")
    redacted_text: str | None = Field(default=None, description="Masked text if redacted")


class PIICheckResult(BaseModel):
    """Result of PII detection check."""

    passed: bool = Field(..., description="True if no blocking PII found")
    detections: list[PIIDetection] = Field(default_factory=list, description="All detections")
    blocked_types: list[PIIType] = Field(
        default_factory=list, description="Types that caused blocking"
    )
    redacted_count: int = Field(default=0, ge=0, description="Number of redacted entities")


class ProfanityCheckResult(BaseModel):
    """Result of profanity check."""

    passed: bool = Field(..., description="True if no profanity detected")
    detected_terms: list[str] = Field(default_factory=list, description="Masked detected terms")
    severity: RuleSeverity | None = Field(default=None, description="Severity if detected")


class LengthCheckResult(BaseModel):
    """Result of response length validation."""

    passed: bool = Field(..., description="True if length within limits")
    char_count: int = Field(..., ge=0, description="Character count")
    min_length: int = Field(default=20, description="Minimum allowed")
    max_length: int = Field(default=2000, description="Maximum allowed")
    was_truncated: bool = Field(default=False, description="True if truncated")


class BusinessRuleViolation(BaseModel):
    """Details of a business rule violation."""

    rule_id: str = Field(..., description="Rule identifier")
    rule_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Violation description")
    severity: RuleSeverity = Field(..., description="Violation severity")
    action_taken: ValidationAction = Field(..., description="Action taken")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class BusinessRulesResult(BaseModel):
    """Result of business rules validation."""

    passed: bool = Field(..., description="True if no blocking violations")
    violations: list[BusinessRuleViolation] = Field(
        default_factory=list, description="All violations"
    )
    rules_evaluated: int = Field(default=0, ge=0, description="Rules evaluated")
    disclaimer_added: bool = Field(default=False, description="True if disclaimer appended")


class SentimentScores(BaseModel):
    """Detailed sentiment scores from Comprehend."""

    positive: float = Field(..., ge=0.0, le=1.0)
    negative: float = Field(..., ge=0.0, le=1.0)
    neutral: float = Field(..., ge=0.0, le=1.0)
    mixed: float = Field(..., ge=0.0, le=1.0)


class SentimentResult(BaseModel):
    """Result of sentiment analysis."""

    sentiment: Sentiment = Field(..., description="Dominant sentiment")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    scores: SentimentScores = Field(..., description="Detailed scores")

    @classmethod
    def from_comprehend(
        cls,
        sentiment: str,
        scores: dict[str, float],
    ) -> "SentimentResult":
        """Create from Comprehend API response."""
        sentiment_enum = Sentiment(sentiment)
        sentiment_scores = SentimentScores(
            positive=scores.get("Positive", 0.0),
            negative=scores.get("Negative", 0.0),
            neutral=scores.get("Neutral", 0.0),
            mixed=scores.get("Mixed", 0.0),
        )
        confidence = getattr(sentiment_scores, sentiment_enum.value.lower())
        return cls(
            sentiment=sentiment_enum,
            confidence=confidence,
            scores=sentiment_scores,
        )


class EscalationFactors(BaseModel):
    """Breakdown of factors contributing to escalation score."""

    explicit_intent: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Escalation intent score"
    )
    negative_sentiment: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Negative sentiment score"
    )
    urgency: float = Field(default=0.0, ge=0.0, le=1.0, description="Urgency score")
    repeated_question: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Repeated question score"
    )
    low_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Low AI confidence score"
    )


class EscalationResult(BaseModel):
    """Result of escalation scoring."""

    score: float = Field(..., ge=0.0, le=1.0, description="Composite escalation score")
    needs_escalation: bool = Field(..., description="True if score >= threshold")
    threshold: float = Field(default=0.70, ge=0.0, le=1.0, description="Escalation threshold")
    factors: EscalationFactors = Field(..., description="Factor breakdown")
    primary_reason: str | None = Field(default=None, description="Primary escalation reason")

    @classmethod
    def calculate(
        cls,
        factors: EscalationFactors,
        threshold: float = 0.70,
    ) -> "EscalationResult":
        """Calculate escalation score from weighted factors."""
        # Weights from ADR-012
        score = (
            0.35 * factors.explicit_intent
            + 0.25 * factors.negative_sentiment
            + 0.20 * factors.urgency
            + 0.15 * factors.repeated_question
            + 0.05 * factors.low_confidence
        )

        # Determine primary reason
        primary_reason = None
        if score >= threshold:
            factor_contributions = {
                "Explicit escalation request": 0.35 * factors.explicit_intent,
                "Negative sentiment": 0.25 * factors.negative_sentiment,
                "High urgency": 0.20 * factors.urgency,
                "Repeated question": 0.15 * factors.repeated_question,
                "Low AI confidence": 0.05 * factors.low_confidence,
            }
            primary_reason = max(factor_contributions, key=lambda k: factor_contributions[k])

        return cls(
            score=round(score, 4),
            needs_escalation=score >= threshold,
            threshold=threshold,
            factors=factors,
            primary_reason=primary_reason,
        )


class ValidationResults(BaseModel):
    """Aggregated results from all validation checks."""

    profanity: ProfanityCheckResult | None = Field(default=None, description="Profanity check")
    pii: PIICheckResult | None = Field(default=None, description="PII detection")
    length: LengthCheckResult | None = Field(default=None, description="Length validation")
    business_rules: BusinessRulesResult | None = Field(default=None, description="Business rules")


class ValidationMetadata(BaseModel):
    """Metadata about the validation process."""

    validation_time_ms: float = Field(..., ge=0.0, description="Validation time in ms")
    rules_evaluated: int = Field(default=0, ge=0, description="Rules evaluated")
    fallback_used: bool = Field(default=False, description="True if fallback used")
    fallback_reason: str | None = Field(default=None, description="Reason for fallback")
    comprehend_calls: int = Field(default=0, ge=0, description="Comprehend API calls")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(), description="ISO timestamp"
    )


# =============================================================================
# Response Models
# =============================================================================


class ValidationResponse(BaseModel):
    """Response model for response validation."""

    is_valid: bool = Field(..., description="True if passed all critical checks")
    action: ValidationAction = Field(..., description="Overall action taken")
    validated_response: str = Field(..., description="Validated response to return")
    original_response: str = Field(..., description="Original unmodified response")
    validation_results: ValidationResults = Field(..., description="Individual check results")
    sentiment: SentimentResult | None = Field(default=None, description="Sentiment analysis")
    escalation: EscalationResult | None = Field(default=None, description="Escalation scoring")
    metadata: ValidationMetadata = Field(..., description="Validation metadata")

    @classmethod
    def create(
        cls,
        original_response: str,
        validated_response: str,
        is_valid: bool,
        action: ValidationAction,
        validation_results: ValidationResults,
        validation_time_ms: float,
        sentiment: SentimentResult | None = None,
        escalation: EscalationResult | None = None,
        rules_evaluated: int = 0,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
        comprehend_calls: int = 0,
    ) -> "ValidationResponse":
        """Factory method to create a ValidationResponse."""
        return cls(
            is_valid=is_valid,
            action=action,
            validated_response=validated_response,
            original_response=original_response,
            validation_results=validation_results,
            sentiment=sentiment,
            escalation=escalation,
            metadata=ValidationMetadata(
                validation_time_ms=validation_time_ms,
                rules_evaluated=rules_evaluated,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                comprehend_calls=comprehend_calls,
            ),
        )


class ValidationError(BaseModel):
    """Error response model."""

    error_type: str = Field(..., description="Error type identifier")
    message: str = Field(..., description="Human-readable error message")
    retryable: bool = Field(default=False, description="Whether request can be retried")
    conversation_id: str | None = Field(default=None, description="Conversation ID if available")
    details: dict[str, Any] | None = Field(default=None, description="Error details")
