"""Sentiment analysis service for response validation.

This module provides sentiment analysis using Amazon Comprehend and
explicit escalation intent detection using keyword patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import boto3
from aws_lambda_powertools import Logger
from botocore.config import Config
from botocore.exceptions import ClientError

from models import Sentiment, SentimentResult, SentimentScores

if TYPE_CHECKING:
    from mypy_boto3_comprehend import ComprehendClient

logger = Logger(child=True)


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class SentimentAnalyzerConfig:
    """Configuration for sentiment analysis."""

    # Comprehend settings
    language_code: str = "en"
    min_text_length: int = 5
    max_text_length: int = 5000

    # Explicit escalation detection
    detect_explicit_escalation: bool = True

    # Behavior settings
    fail_open: bool = True  # Return neutral sentiment on errors


@dataclass(frozen=True)
class ExplicitEscalationResult:
    """Result of explicit escalation intent detection."""

    detected: bool
    matched_pattern: str | None = None
    matched_text: str | None = None


# =============================================================================
# Escalation Patterns
# =============================================================================


@dataclass
class EscalationPattern:
    """Configuration for an escalation detection pattern."""

    pattern: str
    description: str
    compiled: re.Pattern[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Compile the regex pattern."""
        object.__setattr__(self, "compiled", re.compile(self.pattern, re.IGNORECASE | re.MULTILINE))


DEFAULT_ESCALATION_PATTERNS: list[EscalationPattern] = [
    EscalationPattern(
        pattern=r"\b(speak|talk)\s+(to|with)\s+(a\s+)?(human|person|agent|representative|someone|real\s+person)\b",
        description="Request to speak with human",
    ),
    EscalationPattern(
        pattern=r"\b(need|want|get|give)\s+(me\s+)?(a\s+)?(human|person|agent|representative|manager|supervisor)\b",
        description="Request for human agent",
    ),
    EscalationPattern(
        pattern=r"\b(transfer|connect|escalate|redirect)\s+(me\s+)?(to)?\s*(a\s+)?(human|person|agent|someone|support)?\b",
        description="Transfer request",
    ),
    EscalationPattern(
        pattern=r"\breal\s+person\b",
        description="Real person request",
    ),
    EscalationPattern(
        pattern=r"\bhuman\s+(help|support|assistance|agent)\b",
        description="Human help request",
    ),
    EscalationPattern(
        pattern=r"\bthis\s+(isn'?t|is\s*n'?t|is\s+not)\s+(helping|working|useful)\b",
        description="Frustration with bot",
    ),
    EscalationPattern(
        pattern=r"\b(useless|worthless|stupid|dumb|terrible|awful)\s+(bot|ai|assistant|chatbot)\b",
        description="Negative bot sentiment",
    ),
    EscalationPattern(
        pattern=r"\bstop\s+(talking\s+to|with)\s+(a\s+)?(bot|ai|machine|computer)\b",
        description="Stop talking to bot",
    ),
    EscalationPattern(
        pattern=r"\bi\s+(don'?t|do\s*n'?t)\s+want\s+(to\s+)?(talk|speak)\s+(to|with)\s+(a\s+)?(bot|ai|machine)\b",
        description="Don't want to talk to bot",
    ),
    EscalationPattern(
        pattern=r"\blet\s+me\s+(talk|speak)\s+(to|with)\s+(a\s+)?(human|person|someone)\b",
        description="Let me talk to human",
    ),
]


# =============================================================================
# Sentiment Analyzer Service
# =============================================================================


class SentimentAnalyzer:
    """Sentiment analysis service using Amazon Comprehend."""

    def __init__(
        self,
        config: SentimentAnalyzerConfig | None = None,
        escalation_patterns: list[EscalationPattern] | None = None,
        comprehend_client: ComprehendClient | None = None,
    ) -> None:
        """Initialize the sentiment analyzer.

        Args:
            config: Analyzer configuration. Uses defaults if not provided.
            escalation_patterns: Custom escalation patterns. Uses defaults if not provided.
            comprehend_client: Boto3 Comprehend client. Created if not provided.
        """
        self.config = config or SentimentAnalyzerConfig()
        self.escalation_patterns = escalation_patterns or DEFAULT_ESCALATION_PATTERNS
        self._comprehend_client = comprehend_client

    @property
    def comprehend_client(self) -> ComprehendClient:
        """Lazy-load Comprehend client."""
        if self._comprehend_client is None:
            boto_config = Config(
                retries={"max_attempts": 3, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=30,
            )
            self._comprehend_client = boto3.client("comprehend", config=boto_config)
        return self._comprehend_client

    def analyze(self, text: str) -> SentimentResult | None:
        """Analyze sentiment of text using Amazon Comprehend.

        Args:
            text: Text to analyze (typically the user's message).

        Returns:
            SentimentResult with sentiment classification and scores,
            or None if analysis fails and fail_open is True.

        Raises:
            ClientError: If Comprehend API fails and fail_open is False.
        """
        # Validate text length
        if len(text.strip()) < self.config.min_text_length:
            logger.debug(
                "Text too short for sentiment analysis",
                extra={"text_length": len(text)},
            )
            return self._neutral_result()

        # Truncate if too long
        analysis_text = text[: self.config.max_text_length]

        try:
            response = self.comprehend_client.detect_sentiment(
                Text=analysis_text,
                LanguageCode=self.config.language_code,
            )

            sentiment = response.get("Sentiment", "NEUTRAL")
            scores = response.get("SentimentScore", {})

            result = SentimentResult.from_comprehend(
                sentiment=sentiment,
                scores={
                    "Positive": scores.get("Positive", 0.0),
                    "Negative": scores.get("Negative", 0.0),
                    "Neutral": scores.get("Neutral", 0.0),
                    "Mixed": scores.get("Mixed", 0.0),
                },
            )

            logger.info(
                "Sentiment analysis complete",
                extra={
                    "sentiment": result.sentiment.value,
                    "confidence": result.confidence,
                    "text_length": len(analysis_text),
                },
            )

            return result

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(
                "Comprehend DetectSentiment failed",
                extra={
                    "error_code": error_code,
                    "error_message": str(e),
                },
            )

            if self.config.fail_open:
                return None
            raise

    def detect_explicit_escalation(self, text: str) -> ExplicitEscalationResult:
        """Detect explicit escalation intent using keyword patterns.

        Args:
            text: Text to analyze (typically the user's message).

        Returns:
            ExplicitEscalationResult indicating if escalation was requested.
        """
        if not self.config.detect_explicit_escalation:
            return ExplicitEscalationResult(detected=False)

        for pattern in self.escalation_patterns:
            match = pattern.compiled.search(text)
            if match:
                logger.info(
                    "Explicit escalation detected",
                    extra={
                        "pattern_description": pattern.description,
                        "matched_text": match.group(),
                    },
                )
                return ExplicitEscalationResult(
                    detected=True,
                    matched_pattern=pattern.description,
                    matched_text=match.group(),
                )

        return ExplicitEscalationResult(detected=False)

    def analyze_with_escalation(
        self, text: str
    ) -> tuple[SentimentResult | None, ExplicitEscalationResult]:
        """Perform both sentiment analysis and explicit escalation detection.

        This is the recommended method for full analysis as it combines
        both checks in a single call.

        Args:
            text: Text to analyze (typically the user's message).

        Returns:
            Tuple of (SentimentResult or None, ExplicitEscalationResult).
        """
        sentiment = self.analyze(text)
        escalation = self.detect_explicit_escalation(text)

        return sentiment, escalation

    def _neutral_result(self) -> SentimentResult:
        """Create a neutral sentiment result for edge cases."""
        return SentimentResult(
            sentiment=Sentiment.NEUTRAL,
            confidence=1.0,
            scores=SentimentScores(
                positive=0.0,
                negative=0.0,
                neutral=1.0,
                mixed=0.0,
            ),
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def create_default_analyzer() -> SentimentAnalyzer:
    """Create a sentiment analyzer with default configuration."""
    return SentimentAnalyzer()


def create_analyzer_without_escalation() -> SentimentAnalyzer:
    """Create a sentiment analyzer without explicit escalation detection."""
    config = SentimentAnalyzerConfig(detect_explicit_escalation=False)
    return SentimentAnalyzer(config=config)
