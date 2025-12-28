"""Escalation scoring engine for response validation.

This module provides escalation scoring based on weighted factors
to determine when conversations should be routed to human agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from aws_lambda_powertools import Logger

from models import EscalationFactors, EscalationResult, SentimentResult

if TYPE_CHECKING:
    from sentiment_analyzer import ExplicitEscalationResult

logger = Logger(child=True)


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class EscalationScorerConfig:
    """Configuration for escalation scoring."""

    # Threshold for triggering escalation
    threshold: float = 0.70

    # Factor weights (must sum to 1.0)
    weight_explicit_intent: float = 0.35
    weight_negative_sentiment: float = 0.25
    weight_urgency: float = 0.20
    weight_repeated_question: float = 0.15
    weight_low_confidence: float = 0.05

    # Repeated question thresholds
    repeat_count_high: int = 2  # 3+ total asks = 1.0 score
    repeat_count_medium: int = 1  # 2 total asks = 0.5 score

    # Confidence threshold for "low confidence" factor
    low_confidence_threshold: float = 0.7

    def __post_init__(self) -> None:
        """Validate weights sum to 1.0."""
        total = (
            self.weight_explicit_intent
            + self.weight_negative_sentiment
            + self.weight_urgency
            + self.weight_repeated_question
            + self.weight_low_confidence
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Factor weights must sum to 1.0, got {total}")


# =============================================================================
# Urgency Mapping
# =============================================================================


URGENCY_SCORES: dict[str, float] = {
    "high": 1.0,
    "critical": 1.0,
    "medium": 0.5,
    "normal": 0.25,
    "low": 0.0,
}


def map_urgency_to_score(urgency: str | None) -> float:
    """Map urgency level string to numeric score.

    Args:
        urgency: Urgency level from intent classifier (high, medium, low, etc.)

    Returns:
        Float score between 0.0 and 1.0.
    """
    if not urgency:
        return 0.0
    return URGENCY_SCORES.get(urgency.lower(), 0.0)


# =============================================================================
# Escalation Scorer
# =============================================================================


class EscalationScorer:
    """Escalation scoring engine using weighted factors."""

    def __init__(self, config: EscalationScorerConfig | None = None) -> None:
        """Initialize the escalation scorer.

        Args:
            config: Scorer configuration. Uses defaults if not provided.
        """
        self.config = config or EscalationScorerConfig()

    def calculate_score(
        self,
        sentiment: SentimentResult | None = None,
        explicit_escalation: ExplicitEscalationResult | None = None,
        urgency: str | None = None,
        current_intent: str | None = None,
        previous_intents: list[str] | None = None,
        intent_confidence: float | None = None,
    ) -> EscalationResult:
        """Calculate escalation score from weighted factors.

        Args:
            sentiment: Sentiment analysis result from Comprehend.
            explicit_escalation: Explicit escalation detection result.
            urgency: Urgency level from intent classifier.
            current_intent: Current message intent.
            previous_intents: List of previous intents in conversation.
            intent_confidence: Confidence score from intent classifier.

        Returns:
            EscalationResult with score, threshold, and factor breakdown.
        """
        # Calculate individual factor scores
        explicit_intent_score = self._calculate_explicit_intent(explicit_escalation)
        negative_sentiment_score = self._calculate_negative_sentiment(sentiment)
        urgency_score = self._calculate_urgency(urgency)
        repeated_question_score = self._calculate_repeated_question(
            current_intent, previous_intents
        )
        low_confidence_score = self._calculate_low_confidence(intent_confidence)

        # Build factors model
        factors = EscalationFactors(
            explicit_intent=explicit_intent_score,
            negative_sentiment=negative_sentiment_score,
            urgency=urgency_score,
            repeated_question=repeated_question_score,
            low_confidence=low_confidence_score,
        )

        # Calculate weighted score using config weights
        weighted_score = (
            self.config.weight_explicit_intent * factors.explicit_intent
            + self.config.weight_negative_sentiment * factors.negative_sentiment
            + self.config.weight_urgency * factors.urgency
            + self.config.weight_repeated_question * factors.repeated_question
            + self.config.weight_low_confidence * factors.low_confidence
        )

        # Determine if escalation is needed
        needs_escalation = weighted_score >= self.config.threshold

        # Determine primary reason if escalating
        primary_reason = self._determine_primary_reason(factors) if needs_escalation else None

        result = EscalationResult(
            score=round(weighted_score, 4),
            needs_escalation=needs_escalation,
            threshold=self.config.threshold,
            factors=factors,
            primary_reason=primary_reason,
        )

        logger.info(
            "Escalation score calculated",
            extra={
                "score": result.score,
                "needs_escalation": result.needs_escalation,
                "threshold": result.threshold,
                "primary_reason": result.primary_reason,
                "factors": {
                    "explicit_intent": factors.explicit_intent,
                    "negative_sentiment": factors.negative_sentiment,
                    "urgency": factors.urgency,
                    "repeated_question": factors.repeated_question,
                    "low_confidence": factors.low_confidence,
                },
            },
        )

        return result

    def _calculate_explicit_intent(
        self, explicit_escalation: ExplicitEscalationResult | None
    ) -> float:
        """Calculate explicit escalation intent score.

        Args:
            explicit_escalation: Result from keyword pattern detection.

        Returns:
            1.0 if explicit escalation detected, else 0.0.
        """
        if explicit_escalation is None:
            return 0.0
        return 1.0 if explicit_escalation.detected else 0.0

    def _calculate_negative_sentiment(self, sentiment: SentimentResult | None) -> float:
        """Calculate negative sentiment score.

        Args:
            sentiment: Sentiment analysis result from Comprehend.

        Returns:
            Negative sentiment score (0.0-1.0) from Comprehend.
        """
        if sentiment is None:
            return 0.0
        return float(sentiment.scores.negative)

    def _calculate_urgency(self, urgency: str | None) -> float:
        """Calculate urgency score.

        Args:
            urgency: Urgency level string from intent classifier.

        Returns:
            Mapped urgency score (0.0-1.0).
        """
        return map_urgency_to_score(urgency)

    def _calculate_repeated_question(
        self,
        current_intent: str | None,
        previous_intents: list[str] | None,
    ) -> float:
        """Calculate repeated question score.

        Args:
            current_intent: Current message intent.
            previous_intents: List of previous intents in conversation.

        Returns:
            Score based on how many times this intent has been seen before.
        """
        if not current_intent or not previous_intents:
            return 0.0

        repeat_count = previous_intents.count(current_intent)

        if repeat_count >= self.config.repeat_count_high:
            return 1.0
        elif repeat_count >= self.config.repeat_count_medium:
            return 0.5
        return 0.0

    def _calculate_low_confidence(self, intent_confidence: float | None) -> float:
        """Calculate low confidence score.

        Args:
            intent_confidence: Confidence score from intent classifier (0.0-1.0).

        Returns:
            Inverted confidence score, higher when confidence is low.
        """
        if intent_confidence is None:
            return 0.0

        # Invert: low confidence = high score
        # Only trigger if below threshold
        if intent_confidence < self.config.low_confidence_threshold:
            return 1.0 - intent_confidence
        return 0.0

    def _determine_primary_reason(self, factors: EscalationFactors) -> str:
        """Determine the primary reason for escalation.

        Args:
            factors: Calculated escalation factors.

        Returns:
            Human-readable string describing primary escalation reason.
        """
        # Calculate weighted contributions
        contributions = {
            "Explicit escalation request": (
                self.config.weight_explicit_intent * factors.explicit_intent
            ),
            "Negative customer sentiment": (
                self.config.weight_negative_sentiment * factors.negative_sentiment
            ),
            "High urgency issue": self.config.weight_urgency * factors.urgency,
            "Repeated question": (self.config.weight_repeated_question * factors.repeated_question),
            "Low AI confidence": self.config.weight_low_confidence * factors.low_confidence,
        }

        # Find highest contributor
        return max(contributions, key=lambda k: contributions[k])


# =============================================================================
# Convenience Functions
# =============================================================================


def create_default_scorer() -> EscalationScorer:
    """Create an escalation scorer with default configuration."""
    return EscalationScorer()


def create_scorer_with_threshold(threshold: float) -> EscalationScorer:
    """Create an escalation scorer with custom threshold.

    Args:
        threshold: Escalation threshold (0.0-1.0).

    Returns:
        Configured EscalationScorer instance.
    """
    config = EscalationScorerConfig(threshold=threshold)
    return EscalationScorer(config=config)


def create_sensitive_scorer() -> EscalationScorer:
    """Create an escalation scorer with lower threshold for sensitive use cases.

    This scorer triggers escalation more easily (threshold=0.50).
    """
    config = EscalationScorerConfig(threshold=0.50)
    return EscalationScorer(config=config)


def create_conservative_scorer() -> EscalationScorer:
    """Create an escalation scorer with higher threshold.

    This scorer only triggers escalation for clear cases (threshold=0.85).
    """
    config = EscalationScorerConfig(threshold=0.85)
    return EscalationScorer(config=config)
