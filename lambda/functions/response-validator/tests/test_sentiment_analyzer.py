"""Unit tests for Response Validator sentiment analyzer service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from models import Sentiment, SentimentResult
from sentiment_analyzer import (
    DEFAULT_ESCALATION_PATTERNS,
    EscalationPattern,
    ExplicitEscalationResult,
    SentimentAnalyzer,
    SentimentAnalyzerConfig,
    create_analyzer_without_escalation,
    create_default_analyzer,
)


class TestSentimentAnalyzerConfig:
    """Tests for SentimentAnalyzerConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = SentimentAnalyzerConfig()

        assert config.language_code == "en"
        assert config.min_text_length == 5
        assert config.max_text_length == 5000
        assert config.detect_explicit_escalation is True
        assert config.fail_open is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = SentimentAnalyzerConfig(
            language_code="es",
            min_text_length=10,
            max_text_length=1000,
            detect_explicit_escalation=False,
            fail_open=False,
        )

        assert config.language_code == "es"
        assert config.min_text_length == 10
        assert config.max_text_length == 1000
        assert config.detect_explicit_escalation is False
        assert config.fail_open is False


class TestEscalationPattern:
    """Tests for EscalationPattern."""

    def test_pattern_compilation(self) -> None:
        """Test pattern is compiled on init."""
        pattern = EscalationPattern(
            pattern=r"\bhelp\b",
            description="Help request",
        )

        assert pattern.compiled is not None
        assert pattern.compiled.search("I need help")

    def test_case_insensitive(self) -> None:
        """Test patterns are case insensitive."""
        pattern = EscalationPattern(
            pattern=r"\bhuman\s+agent\b",
            description="Human agent request",
        )

        assert pattern.compiled.search("I want a HUMAN AGENT")
        assert pattern.compiled.search("human agent please")
        assert pattern.compiled.search("Human Agent")


class TestDefaultEscalationPatterns:
    """Tests for default escalation patterns."""

    def test_speak_to_human_patterns(self) -> None:
        """Test 'speak to human' pattern variants."""
        texts = [
            "I want to speak to a human",
            "Can I talk with a person",
            "Let me speak to someone",
            "I need to talk to a representative",
            "speak to a real person please",
        ]

        for text in texts:
            matched = any(p.compiled.search(text) for p in DEFAULT_ESCALATION_PATTERNS)
            assert matched, f"Pattern should match: {text}"

    def test_transfer_request_patterns(self) -> None:
        """Test transfer request pattern variants."""
        texts = [
            "Transfer me to a human",
            "Please connect me to support",
            "Escalate this issue",
            "Can you transfer me",
        ]

        for text in texts:
            matched = any(p.compiled.search(text) for p in DEFAULT_ESCALATION_PATTERNS)
            assert matched, f"Pattern should match: {text}"

    def test_frustration_patterns(self) -> None:
        """Test frustration pattern variants."""
        texts = [
            "This isn't helping",
            "This is not helping at all",
            "useless bot",
            "stupid AI",
            "this terrible chatbot",
        ]

        for text in texts:
            matched = any(p.compiled.search(text) for p in DEFAULT_ESCALATION_PATTERNS)
            assert matched, f"Pattern should match: {text}"

    def test_non_escalation_text(self) -> None:
        """Test normal text doesn't trigger escalation."""
        texts = [
            "Thank you for your help",
            "What are your store hours?",
            "I want to return a product",
            "How do I reset my password?",
            "The weather is nice today",
        ]

        for text in texts:
            matched = any(p.compiled.search(text) for p in DEFAULT_ESCALATION_PATTERNS)
            assert not matched, f"Pattern should NOT match: {text}"


class TestSentimentAnalyzer:
    """Tests for SentimentAnalyzer class."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default config."""
        analyzer = SentimentAnalyzer()

        assert analyzer.config.language_code == "en"
        assert len(analyzer.escalation_patterns) > 0

    def test_init_with_custom_config(self) -> None:
        """Test initialization with custom config."""
        config = SentimentAnalyzerConfig(language_code="fr")
        analyzer = SentimentAnalyzer(config=config)

        assert analyzer.config.language_code == "fr"

    def test_init_with_custom_patterns(self) -> None:
        """Test initialization with custom escalation patterns."""
        custom_patterns = [
            EscalationPattern(
                pattern=r"\bcustom\b",
                description="Custom pattern",
            ),
        ]
        analyzer = SentimentAnalyzer(escalation_patterns=custom_patterns)

        assert len(analyzer.escalation_patterns) == 1
        assert analyzer.escalation_patterns[0].description == "Custom pattern"


class TestSentimentAnalyzerAnalyze:
    """Tests for SentimentAnalyzer.analyze method."""

    def test_analyze_positive_sentiment(
        self, mock_comprehend_sentiment_positive: MagicMock
    ) -> None:
        """Test analyzing positive sentiment."""
        analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_positive)

        result = analyzer.analyze("I love this product! It's amazing!")

        assert result is not None
        assert result.sentiment == Sentiment.POSITIVE
        assert result.confidence == pytest.approx(0.95)
        assert result.scores.positive == pytest.approx(0.95)
        mock_comprehend_sentiment_positive.detect_sentiment.assert_called_once()

    def test_analyze_negative_sentiment(
        self, mock_comprehend_sentiment_negative: MagicMock
    ) -> None:
        """Test analyzing negative sentiment."""
        analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_negative)

        result = analyzer.analyze("This is terrible. I'm very frustrated.")

        assert result is not None
        assert result.sentiment == Sentiment.NEGATIVE
        assert result.confidence == pytest.approx(0.88)
        assert result.scores.negative == pytest.approx(0.88)

    def test_analyze_neutral_sentiment(self, mock_comprehend_sentiment_neutral: MagicMock) -> None:
        """Test analyzing neutral sentiment."""
        analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_neutral)

        result = analyzer.analyze("What are your store hours?")

        assert result is not None
        assert result.sentiment == Sentiment.NEUTRAL
        assert result.scores.neutral == pytest.approx(0.92)

    def test_analyze_mixed_sentiment(self, mock_comprehend_sentiment_mixed: MagicMock) -> None:
        """Test analyzing mixed sentiment."""
        analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_mixed)

        result = analyzer.analyze("The product is good but shipping was slow.")

        assert result is not None
        assert result.sentiment == Sentiment.MIXED

    def test_analyze_short_text_returns_neutral(self, mock_comprehend_client: MagicMock) -> None:
        """Test that very short text returns neutral without calling Comprehend."""
        analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_client)

        result = analyzer.analyze("Hi")

        assert result is not None
        assert result.sentiment == Sentiment.NEUTRAL
        assert result.confidence == 1.0
        mock_comprehend_client.detect_sentiment.assert_not_called()

    def test_analyze_truncates_long_text(
        self, mock_comprehend_sentiment_positive: MagicMock
    ) -> None:
        """Test that long text is truncated."""
        config = SentimentAnalyzerConfig(max_text_length=100)
        analyzer = SentimentAnalyzer(
            config=config, comprehend_client=mock_comprehend_sentiment_positive
        )

        long_text = "A" * 500
        analyzer.analyze(long_text)

        # Verify the text was truncated
        call_args = mock_comprehend_sentiment_positive.detect_sentiment.call_args
        assert len(call_args.kwargs["Text"]) == 100

    def test_analyze_comprehend_error_fail_open(self, mock_comprehend_client: MagicMock) -> None:
        """Test that Comprehend errors return None when fail_open is True."""
        mock_comprehend_client.detect_sentiment.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "DetectSentiment",
        )

        config = SentimentAnalyzerConfig(fail_open=True)
        analyzer = SentimentAnalyzer(config=config, comprehend_client=mock_comprehend_client)

        result = analyzer.analyze("Test message")

        assert result is None

    def test_analyze_comprehend_error_fail_closed(self, mock_comprehend_client: MagicMock) -> None:
        """Test that Comprehend errors raise when fail_open is False."""
        mock_comprehend_client.detect_sentiment.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "DetectSentiment",
        )

        config = SentimentAnalyzerConfig(fail_open=False)
        analyzer = SentimentAnalyzer(config=config, comprehend_client=mock_comprehend_client)

        with pytest.raises(ClientError):
            analyzer.analyze("Test message")


class TestSentimentAnalyzerExplicitEscalation:
    """Tests for SentimentAnalyzer.detect_explicit_escalation method."""

    def test_detect_explicit_escalation_found(self) -> None:
        """Test detecting explicit escalation request."""
        analyzer = SentimentAnalyzer()

        result = analyzer.detect_explicit_escalation("I want to speak to a human agent")

        assert result.detected is True
        assert result.matched_pattern is not None
        assert result.matched_text is not None

    def test_detect_explicit_escalation_not_found(self) -> None:
        """Test no escalation detected in normal text."""
        analyzer = SentimentAnalyzer()

        result = analyzer.detect_explicit_escalation("What is your return policy?")

        assert result.detected is False
        assert result.matched_pattern is None
        assert result.matched_text is None

    def test_detect_explicit_escalation_disabled(self) -> None:
        """Test escalation detection when disabled in config."""
        config = SentimentAnalyzerConfig(detect_explicit_escalation=False)
        analyzer = SentimentAnalyzer(config=config)

        result = analyzer.detect_explicit_escalation("I want to speak to a human")

        assert result.detected is False

    def test_detect_multiple_patterns_returns_first(self) -> None:
        """Test that first matching pattern is returned."""
        analyzer = SentimentAnalyzer()

        # Text with multiple potential matches
        result = analyzer.detect_explicit_escalation(
            "This useless bot isn't helping, let me speak to a human"
        )

        assert result.detected is True
        # Should match one of the patterns
        assert result.matched_pattern is not None


class TestSentimentAnalyzerCombined:
    """Tests for SentimentAnalyzer.analyze_with_escalation method."""

    def test_analyze_with_escalation_both_detected(
        self, mock_comprehend_sentiment_negative: MagicMock
    ) -> None:
        """Test combined analysis with both sentiment and escalation."""
        analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_negative)

        sentiment, escalation = analyzer.analyze_with_escalation(
            "This is terrible! I want to speak to a human!"
        )

        assert sentiment is not None
        assert sentiment.sentiment == Sentiment.NEGATIVE
        assert escalation.detected is True

    def test_analyze_with_escalation_sentiment_only(
        self, mock_comprehend_sentiment_negative: MagicMock
    ) -> None:
        """Test combined analysis with sentiment but no escalation."""
        analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_negative)

        sentiment, escalation = analyzer.analyze_with_escalation(
            "I'm frustrated with this product."
        )

        assert sentiment is not None
        assert sentiment.sentiment == Sentiment.NEGATIVE
        assert escalation.detected is False

    def test_analyze_with_escalation_escalation_only(
        self, mock_comprehend_sentiment_neutral: MagicMock
    ) -> None:
        """Test combined analysis with escalation but neutral sentiment."""
        analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_neutral)

        sentiment, escalation = analyzer.analyze_with_escalation(
            "Can you transfer me to a human please?"
        )

        assert sentiment is not None
        assert sentiment.sentiment == Sentiment.NEUTRAL
        assert escalation.detected is True

    def test_analyze_with_escalation_neither(
        self, mock_comprehend_sentiment_positive: MagicMock
    ) -> None:
        """Test combined analysis with neither escalation nor negative sentiment."""
        analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_positive)

        sentiment, escalation = analyzer.analyze_with_escalation("Thank you so much for your help!")

        assert sentiment is not None
        assert sentiment.sentiment == Sentiment.POSITIVE
        assert escalation.detected is False


class TestExplicitEscalationResult:
    """Tests for ExplicitEscalationResult model."""

    def test_not_detected(self) -> None:
        """Test result when escalation not detected."""
        result = ExplicitEscalationResult(detected=False)

        assert result.detected is False
        assert result.matched_pattern is None
        assert result.matched_text is None

    def test_detected_with_details(self) -> None:
        """Test result when escalation detected."""
        result = ExplicitEscalationResult(
            detected=True,
            matched_pattern="Human agent request",
            matched_text="speak to a human",
        )

        assert result.detected is True
        assert result.matched_pattern == "Human agent request"
        assert result.matched_text == "speak to a human"


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_default_analyzer(self) -> None:
        """Test create_default_analyzer function."""
        analyzer = create_default_analyzer()

        assert analyzer is not None
        assert analyzer.config.detect_explicit_escalation is True

    def test_create_analyzer_without_escalation(self) -> None:
        """Test create_analyzer_without_escalation function."""
        analyzer = create_analyzer_without_escalation()

        assert analyzer is not None
        assert analyzer.config.detect_explicit_escalation is False


class TestSentimentResultFromComprehend:
    """Tests for SentimentResult.from_comprehend factory."""

    def test_from_comprehend_positive(self) -> None:
        """Test creating from positive Comprehend response."""
        result = SentimentResult.from_comprehend(
            sentiment="POSITIVE",
            scores={
                "Positive": 0.92,
                "Negative": 0.02,
                "Neutral": 0.04,
                "Mixed": 0.02,
            },
        )

        assert result.sentiment == Sentiment.POSITIVE
        assert result.confidence == pytest.approx(0.92)
        assert result.scores.positive == pytest.approx(0.92)

    def test_from_comprehend_negative(self) -> None:
        """Test creating from negative Comprehend response."""
        result = SentimentResult.from_comprehend(
            sentiment="NEGATIVE",
            scores={
                "Positive": 0.05,
                "Negative": 0.85,
                "Neutral": 0.05,
                "Mixed": 0.05,
            },
        )

        assert result.sentiment == Sentiment.NEGATIVE
        assert result.confidence == pytest.approx(0.85)

    def test_from_comprehend_missing_scores(self) -> None:
        """Test creating with missing score values defaults to 0."""
        result = SentimentResult.from_comprehend(
            sentiment="NEUTRAL",
            scores={},
        )

        assert result.sentiment == Sentiment.NEUTRAL
        assert result.scores.positive == 0.0
        assert result.scores.negative == 0.0
        assert result.scores.neutral == 0.0
        assert result.scores.mixed == 0.0
