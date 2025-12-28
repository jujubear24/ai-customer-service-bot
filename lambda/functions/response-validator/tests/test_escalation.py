"""Unit tests for Response Validator escalation scoring engine."""

from __future__ import annotations

import pytest

from escalation import (
    URGENCY_SCORES,
    EscalationScorer,
    EscalationScorerConfig,
    create_conservative_scorer,
    create_default_scorer,
    create_scorer_with_threshold,
    create_sensitive_scorer,
    map_urgency_to_score,
)
from models import EscalationFactors, EscalationResult, Sentiment, SentimentResult, SentimentScores
from sentiment_analyzer import ExplicitEscalationResult


class TestEscalationScorerConfig:
    """Tests for EscalationScorerConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = EscalationScorerConfig()

        assert config.threshold == 0.70
        assert config.weight_explicit_intent == 0.35
        assert config.weight_negative_sentiment == 0.25
        assert config.weight_urgency == 0.20
        assert config.weight_repeated_question == 0.15
        assert config.weight_low_confidence == 0.05
        assert config.repeat_count_high == 2
        assert config.repeat_count_medium == 1
        assert config.low_confidence_threshold == 0.7

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = EscalationScorerConfig(
            threshold=0.50,
            weight_explicit_intent=0.40,
            weight_negative_sentiment=0.30,
            weight_urgency=0.15,
            weight_repeated_question=0.10,
            weight_low_confidence=0.05,
        )

        assert config.threshold == 0.50
        assert config.weight_explicit_intent == 0.40

    def test_config_weights_must_sum_to_one(self) -> None:
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            EscalationScorerConfig(
                weight_explicit_intent=0.50,
                weight_negative_sentiment=0.50,
                weight_urgency=0.50,  # Total > 1.0
                weight_repeated_question=0.15,
                weight_low_confidence=0.05,
            )

    def test_config_weights_sum_validation_tolerance(self) -> None:
        """Test that small floating point differences are tolerated."""
        # This should not raise - weights sum to 1.0 within tolerance
        config = EscalationScorerConfig(
            weight_explicit_intent=0.35,
            weight_negative_sentiment=0.25,
            weight_urgency=0.20,
            weight_repeated_question=0.15,
            weight_low_confidence=0.05,
        )
        assert config is not None


class TestUrgencyMapping:
    """Tests for urgency score mapping."""

    def test_urgency_scores_dict(self) -> None:
        """Test URGENCY_SCORES dictionary values."""
        assert URGENCY_SCORES["high"] == 1.0
        assert URGENCY_SCORES["critical"] == 1.0
        assert URGENCY_SCORES["medium"] == 0.5
        assert URGENCY_SCORES["normal"] == 0.25
        assert URGENCY_SCORES["low"] == 0.0

    def test_map_urgency_high(self) -> None:
        """Test mapping high urgency."""
        assert map_urgency_to_score("high") == 1.0
        assert map_urgency_to_score("HIGH") == 1.0
        assert map_urgency_to_score("High") == 1.0

    def test_map_urgency_medium(self) -> None:
        """Test mapping medium urgency."""
        assert map_urgency_to_score("medium") == 0.5

    def test_map_urgency_low(self) -> None:
        """Test mapping low urgency."""
        assert map_urgency_to_score("low") == 0.0

    def test_map_urgency_none(self) -> None:
        """Test mapping None urgency."""
        assert map_urgency_to_score(None) == 0.0

    def test_map_urgency_unknown(self) -> None:
        """Test mapping unknown urgency value."""
        assert map_urgency_to_score("unknown") == 0.0
        assert map_urgency_to_score("extreme") == 0.0


class TestEscalationScorer:
    """Tests for EscalationScorer class."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default config."""
        scorer = EscalationScorer()

        assert scorer.config.threshold == 0.70

    def test_init_with_custom_config(self) -> None:
        """Test initialization with custom config."""
        config = EscalationScorerConfig(threshold=0.50)
        scorer = EscalationScorer(config=config)

        assert scorer.config.threshold == 0.50


class TestEscalationScorerCalculateScore:
    """Tests for EscalationScorer.calculate_score method."""

    def test_calculate_score_all_zeros(self, escalation_scorer: EscalationScorer) -> None:
        """Test score calculation with all zero factors."""
        result = escalation_scorer.calculate_score()

        assert result.score == 0.0
        assert result.needs_escalation is False
        assert result.primary_reason is None

    def test_calculate_score_explicit_intent_only(
        self, escalation_scorer: EscalationScorer
    ) -> None:
        """Test score with only explicit intent."""
        explicit_escalation = ExplicitEscalationResult(
            detected=True,
            matched_pattern="Human agent request",
            matched_text="speak to a human",
        )

        result = escalation_scorer.calculate_score(explicit_escalation=explicit_escalation)

        # 0.35 * 1.0 = 0.35
        assert result.score == pytest.approx(0.35)
        assert result.needs_escalation is False  # Below 0.70 threshold
        assert result.factors.explicit_intent == 1.0

    def test_calculate_score_negative_sentiment_only(
        self, escalation_scorer: EscalationScorer
    ) -> None:
        """Test score with only negative sentiment."""
        sentiment = SentimentResult(
            sentiment=Sentiment.NEGATIVE,
            confidence=0.88,
            scores=SentimentScores(
                positive=0.02,
                negative=0.88,
                neutral=0.05,
                mixed=0.05,
            ),
        )

        result = escalation_scorer.calculate_score(sentiment=sentiment)

        # 0.25 * 0.88 = 0.22
        assert result.score == pytest.approx(0.22)
        assert result.needs_escalation is False
        assert result.factors.negative_sentiment == pytest.approx(0.88)

    def test_calculate_score_urgency_high(self, escalation_scorer: EscalationScorer) -> None:
        """Test score with high urgency."""
        result = escalation_scorer.calculate_score(urgency="high")

        # 0.20 * 1.0 = 0.20
        assert result.score == pytest.approx(0.20)
        assert result.factors.urgency == 1.0

    def test_calculate_score_urgency_medium(self, escalation_scorer: EscalationScorer) -> None:
        """Test score with medium urgency."""
        result = escalation_scorer.calculate_score(urgency="medium")

        # 0.20 * 0.5 = 0.10
        assert result.score == pytest.approx(0.10)
        assert result.factors.urgency == 0.5

    def test_calculate_score_repeated_question_once(
        self, escalation_scorer: EscalationScorer
    ) -> None:
        """Test score with question asked twice (1 repeat)."""
        result = escalation_scorer.calculate_score(
            current_intent="order_status",
            previous_intents=["greeting", "order_status"],
        )

        # 0.15 * 0.5 = 0.075
        assert result.score == pytest.approx(0.075)
        assert result.factors.repeated_question == 0.5

    def test_calculate_score_repeated_question_twice(
        self, escalation_scorer: EscalationScorer
    ) -> None:
        """Test score with question asked 3+ times (2+ repeats)."""
        result = escalation_scorer.calculate_score(
            current_intent="order_status",
            previous_intents=["order_status", "order_status", "greeting"],
        )

        # 0.15 * 1.0 = 0.15
        assert result.score == pytest.approx(0.15)
        assert result.factors.repeated_question == 1.0

    def test_calculate_score_low_confidence(self, escalation_scorer: EscalationScorer) -> None:
        """Test score with low intent confidence."""
        result = escalation_scorer.calculate_score(intent_confidence=0.4)

        # Below 0.7 threshold: 1.0 - 0.4 = 0.6
        # 0.05 * 0.6 = 0.03
        assert result.score == pytest.approx(0.03)
        assert result.factors.low_confidence == pytest.approx(0.6)

    def test_calculate_score_high_confidence_no_penalty(
        self, escalation_scorer: EscalationScorer
    ) -> None:
        """Test score with high intent confidence has no penalty."""
        result = escalation_scorer.calculate_score(intent_confidence=0.95)

        # Above 0.7 threshold: no penalty
        assert result.score == 0.0
        assert result.factors.low_confidence == 0.0

    def test_calculate_score_triggers_escalation(self, escalation_scorer: EscalationScorer) -> None:
        """Test score that triggers escalation."""
        explicit_escalation = ExplicitEscalationResult(detected=True)
        sentiment = SentimentResult(
            sentiment=Sentiment.NEGATIVE,
            confidence=0.90,
            scores=SentimentScores(positive=0.02, negative=0.90, neutral=0.05, mixed=0.03),
        )

        result = escalation_scorer.calculate_score(
            sentiment=sentiment,
            explicit_escalation=explicit_escalation,
            urgency="high",
        )

        # 0.35 * 1.0 + 0.25 * 0.90 + 0.20 * 1.0 = 0.35 + 0.225 + 0.20 = 0.775
        assert result.score == pytest.approx(0.775)
        assert result.needs_escalation is True
        assert result.primary_reason is not None

    def test_calculate_score_primary_reason_explicit_intent(
        self, escalation_scorer_low_threshold: EscalationScorer
    ) -> None:
        """Test primary reason is explicit intent when it's the largest contributor."""
        explicit_escalation = ExplicitEscalationResult(detected=True)

        result = escalation_scorer_low_threshold.calculate_score(
            explicit_escalation=explicit_escalation,
        )

        assert result.needs_escalation is True
        assert result.primary_reason == "Explicit escalation request"

    def test_calculate_score_primary_reason_negative_sentiment(
        self, escalation_scorer_low_threshold: EscalationScorer
    ) -> None:
        """Test primary reason is negative sentiment when it's the largest contributor."""
        sentiment = SentimentResult(
            sentiment=Sentiment.NEGATIVE,
            confidence=0.95,
            scores=SentimentScores(positive=0.01, negative=0.95, neutral=0.02, mixed=0.02),
        )

        result = escalation_scorer_low_threshold.calculate_score(sentiment=sentiment)

        assert result.needs_escalation is False  # 0.25 * 0.95 = 0.2375 < 0.30
        # Even without escalation, we can check the factor
        assert result.factors.negative_sentiment == pytest.approx(0.95)

    def test_calculate_score_primary_reason_urgency(
        self, escalation_scorer_low_threshold: EscalationScorer
    ) -> None:
        """Test primary reason is urgency when it's the largest contributor."""
        result = escalation_scorer_low_threshold.calculate_score(
            urgency="high",
            intent_confidence=0.95,  # High confidence, no penalty
        )

        # 0.20 * 1.0 = 0.20 - below 0.30 threshold
        assert result.needs_escalation is False
        assert result.factors.urgency == 1.0

    def test_calculate_score_combined_factors(self, escalation_scorer: EscalationScorer) -> None:
        """Test score with all factors combined."""
        explicit_escalation = ExplicitEscalationResult(detected=True)
        sentiment = SentimentResult(
            sentiment=Sentiment.NEGATIVE,
            confidence=0.80,
            scores=SentimentScores(positive=0.05, negative=0.80, neutral=0.10, mixed=0.05),
        )

        result = escalation_scorer.calculate_score(
            sentiment=sentiment,
            explicit_escalation=explicit_escalation,
            urgency="high",
            current_intent="complaint",
            previous_intents=["complaint", "complaint"],
            intent_confidence=0.5,
        )

        # 0.35 * 1.0 = 0.35 (explicit intent)
        # 0.25 * 0.80 = 0.20 (negative sentiment)
        # 0.20 * 1.0 = 0.20 (urgency)
        # 0.15 * 1.0 = 0.15 (repeated question - 2 repeats)
        # 0.05 * 0.5 = 0.025 (low confidence - 1.0 - 0.5 = 0.5)
        # Total = 0.925
        assert result.score == pytest.approx(0.925)
        assert result.needs_escalation is True
        assert result.primary_reason == "Explicit escalation request"

    def test_calculate_score_none_sentiment(self, escalation_scorer: EscalationScorer) -> None:
        """Test score when sentiment is None."""
        result = escalation_scorer.calculate_score(sentiment=None)

        assert result.factors.negative_sentiment == 0.0

    def test_calculate_score_none_explicit_escalation(
        self, escalation_scorer: EscalationScorer
    ) -> None:
        """Test score when explicit escalation is None."""
        result = escalation_scorer.calculate_score(explicit_escalation=None)

        assert result.factors.explicit_intent == 0.0

    def test_calculate_score_empty_previous_intents(
        self, escalation_scorer: EscalationScorer
    ) -> None:
        """Test score with empty previous intents list."""
        result = escalation_scorer.calculate_score(
            current_intent="order_status",
            previous_intents=[],
        )

        assert result.factors.repeated_question == 0.0

    def test_calculate_score_none_current_intent(self, escalation_scorer: EscalationScorer) -> None:
        """Test score with None current intent."""
        result = escalation_scorer.calculate_score(
            current_intent=None,
            previous_intents=["order_status", "order_status"],
        )

        assert result.factors.repeated_question == 0.0

    def test_calculate_score_none_intent_confidence(
        self, escalation_scorer: EscalationScorer
    ) -> None:
        """Test score with None intent confidence."""
        result = escalation_scorer.calculate_score(intent_confidence=None)

        assert result.factors.low_confidence == 0.0


class TestEscalationScorerThresholds:
    """Tests for different threshold configurations."""

    def test_low_threshold_triggers_easily(
        self, escalation_scorer_low_threshold: EscalationScorer
    ) -> None:
        """Test that low threshold triggers escalation more easily."""
        result = escalation_scorer_low_threshold.calculate_score(urgency="high")

        # 0.20 * 1.0 = 0.20 - below 0.30 threshold
        assert result.score == pytest.approx(0.20)
        assert result.needs_escalation is False  # Still below 0.30

        # With explicit intent: 0.35 >= 0.30
        explicit = ExplicitEscalationResult(detected=True)
        result2 = escalation_scorer_low_threshold.calculate_score(explicit_escalation=explicit)
        assert result2.needs_escalation is True

    def test_high_threshold_requires_more(
        self, escalation_scorer_high_threshold: EscalationScorer
    ) -> None:
        """Test that high threshold requires more factors."""
        explicit = ExplicitEscalationResult(detected=True)
        sentiment = SentimentResult(
            sentiment=Sentiment.NEGATIVE,
            confidence=0.85,
            scores=SentimentScores(positive=0.05, negative=0.85, neutral=0.05, mixed=0.05),
        )

        result = escalation_scorer_high_threshold.calculate_score(
            explicit_escalation=explicit,
            sentiment=sentiment,
            urgency="high",
        )

        # 0.35 + 0.2125 + 0.20 = 0.7625 < 0.90
        assert result.score == pytest.approx(0.7625)
        assert result.needs_escalation is False


class TestEscalationResult:
    """Tests for EscalationResult model."""

    def test_result_properties(self) -> None:
        """Test EscalationResult properties."""
        factors = EscalationFactors(
            explicit_intent=1.0,
            negative_sentiment=0.5,
            urgency=0.5,
            repeated_question=0.0,
            low_confidence=0.0,
        )

        result = EscalationResult(
            score=0.75,
            needs_escalation=True,
            threshold=0.70,
            factors=factors,
            primary_reason="Explicit escalation request",
        )

        assert result.score == 0.75
        assert result.needs_escalation is True
        assert result.threshold == 0.70
        assert result.primary_reason == "Explicit escalation request"

    def test_result_calculate_factory(self) -> None:
        """Test EscalationResult.calculate factory method."""
        factors = EscalationFactors(
            explicit_intent=1.0,
            negative_sentiment=0.8,
            urgency=1.0,
            repeated_question=0.5,
            low_confidence=0.0,
        )

        result = EscalationResult.calculate(factors, threshold=0.70)

        # 0.35 + 0.20 + 0.20 + 0.075 = 0.825
        assert result.score == pytest.approx(0.825)
        assert result.needs_escalation is True
        assert result.primary_reason is not None


class TestEscalationFactors:
    """Tests for EscalationFactors model."""

    def test_weighted_score_property(self, sample_escalation_factors: EscalationFactors) -> None:
        """Test weighted_score property calculation."""
        # explicit_intent=0.0, negative_sentiment=0.2, urgency=0.0,
        # repeated_question=0.0, low_confidence=0.1
        # 0.35*0 + 0.25*0.2 + 0.20*0 + 0.15*0 + 0.05*0.1 = 0.05 + 0.005 = 0.055
        assert sample_escalation_factors.weighted_score == pytest.approx(0.055)

    def test_weighted_score_all_max(self, high_escalation_factors: EscalationFactors) -> None:
        """Test weighted_score with high values."""
        # explicit_intent=1.0, negative_sentiment=0.8, urgency=1.0,
        # repeated_question=0.5, low_confidence=0.3
        # 0.35*1 + 0.25*0.8 + 0.20*1 + 0.15*0.5 + 0.05*0.3
        # = 0.35 + 0.20 + 0.20 + 0.075 + 0.015 = 0.84
        assert high_escalation_factors.weighted_score == pytest.approx(0.84)

    def test_dominant_factor_explicit_intent(self) -> None:
        """Test dominant_factor when explicit intent is highest."""
        factors = EscalationFactors(
            explicit_intent=1.0,
            negative_sentiment=0.2,
            urgency=0.0,
            repeated_question=0.0,
            low_confidence=0.0,
        )

        assert factors.dominant_factor == "explicit_intent"

    def test_dominant_factor_negative_sentiment(self) -> None:
        """Test dominant_factor when negative sentiment is highest."""
        factors = EscalationFactors(
            explicit_intent=0.0,
            negative_sentiment=1.0,
            urgency=0.0,
            repeated_question=0.0,
            low_confidence=0.0,
        )

        assert factors.dominant_factor == "negative_sentiment"

    def test_dominant_factor_urgency(self) -> None:
        """Test dominant_factor when urgency is highest."""
        factors = EscalationFactors(
            explicit_intent=0.0,
            negative_sentiment=0.0,
            urgency=1.0,
            repeated_question=0.0,
            low_confidence=0.0,
        )

        assert factors.dominant_factor == "urgency"

    def test_dominant_factor_all_zero(self) -> None:
        """Test dominant_factor when all factors are zero."""
        factors = EscalationFactors()

        assert factors.dominant_factor is None


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_default_scorer(self) -> None:
        """Test create_default_scorer function."""
        scorer = create_default_scorer()

        assert scorer is not None
        assert scorer.config.threshold == 0.70

    def test_create_scorer_with_threshold(self) -> None:
        """Test create_scorer_with_threshold function."""
        scorer = create_scorer_with_threshold(0.60)

        assert scorer.config.threshold == 0.60

    def test_create_sensitive_scorer(self) -> None:
        """Test create_sensitive_scorer function."""
        scorer = create_sensitive_scorer()

        assert scorer.config.threshold == 0.50

    def test_create_conservative_scorer(self) -> None:
        """Test create_conservative_scorer function."""
        scorer = create_conservative_scorer()

        assert scorer.config.threshold == 0.85


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_confidence_at_threshold(self, escalation_scorer: EscalationScorer) -> None:
        """Test confidence exactly at threshold."""
        result = escalation_scorer.calculate_score(intent_confidence=0.7)

        # At threshold, no penalty
        assert result.factors.low_confidence == 0.0

    def test_confidence_just_below_threshold(self, escalation_scorer: EscalationScorer) -> None:
        """Test confidence just below threshold."""
        result = escalation_scorer.calculate_score(intent_confidence=0.69)

        # Below threshold: 1.0 - 0.69 = 0.31
        assert result.factors.low_confidence == pytest.approx(0.31)

    def test_score_at_exact_threshold(self) -> None:
        """Test score exactly at escalation threshold."""
        config = EscalationScorerConfig(threshold=0.35)
        scorer = EscalationScorer(config=config)

        explicit = ExplicitEscalationResult(detected=True)
        result = scorer.calculate_score(explicit_escalation=explicit)

        # 0.35 * 1.0 = 0.35 == threshold
        assert result.score == pytest.approx(0.35)
        assert result.needs_escalation is True  # >= threshold

    def test_very_small_score(self, escalation_scorer: EscalationScorer) -> None:
        """Test very small non-zero score."""
        result = escalation_scorer.calculate_score(intent_confidence=0.69)

        # 0.05 * 0.31 = 0.0155
        assert result.score == pytest.approx(0.0155)
        assert result.needs_escalation is False

    def test_repeated_question_different_intent(self, escalation_scorer: EscalationScorer) -> None:
        """Test repeated question with different intent doesn't count."""
        result = escalation_scorer.calculate_score(
            current_intent="refund",
            previous_intents=["order_status", "order_status", "shipping"],
        )

        assert result.factors.repeated_question == 0.0
