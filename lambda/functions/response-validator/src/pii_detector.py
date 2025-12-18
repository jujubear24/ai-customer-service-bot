"""PII detection service for response validation.

This module provides hybrid PII detection using Amazon Comprehend for standard
PII types and custom regex patterns for business-specific identifiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import boto3
from aws_lambda_powertools import Logger
from botocore.config import Config
from botocore.exceptions import ClientError

from models import (
    PIIAction,
    PIICheckResult,
    PIIDetection,
    PIIType,
)

if TYPE_CHECKING:
    from mypy_boto3_comprehend import ComprehendClient

logger = Logger(child=True)


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class PIIDetectorConfig:
    """Configuration for PII detection."""

    # Comprehend settings
    use_comprehend: bool = True
    comprehend_language: str = "en"
    min_confidence: float = 0.8

    # Action mappings for different PII types
    # Critical PII - always block
    block_types: frozenset[PIIType] = frozenset(
        {
            PIIType.SSN,
            PIIType.CREDIT_DEBIT_NUMBER,
            PIIType.BANK_ACCOUNT_NUMBER,
            PIIType.PASSPORT_NUMBER,
        }
    )

    # Sensitive PII - redact by default
    redact_types: frozenset[PIIType] = frozenset(
        {
            PIIType.PHONE,
            PIIType.EMAIL,
            PIIType.ADDRESS,
            PIIType.DRIVER_ID,
            PIIType.DATE_TIME,
        }
    )

    # Low-risk PII - warn only
    warn_types: frozenset[PIIType] = frozenset(
        {
            PIIType.NAME,
            PIIType.AGE,
        }
    )

    # Business identifiers - allow but log
    allow_types: frozenset[PIIType] = frozenset(
        {
            PIIType.ORDER_ID,
            PIIType.ACCOUNT_CODE,
            PIIType.CUSTOMER_REF,
        }
    )

    # Redaction settings
    redaction_char: str = "*"
    redaction_placeholder: str = "[REDACTED]"
    use_placeholder: bool = False  # If False, use character masking


@dataclass
class CustomPattern:
    """Configuration for a custom regex pattern."""

    pii_type: PIIType
    pattern: str
    description: str
    compiled: re.Pattern = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Compile the regex pattern."""
        self.compiled = re.compile(self.pattern, re.IGNORECASE)


# =============================================================================
# Default Custom Patterns
# =============================================================================


DEFAULT_CUSTOM_PATTERNS: list[CustomPattern] = [
    CustomPattern(
        pii_type=PIIType.ORDER_ID,
        pattern=r"\b(?:ORD[-_]?)?[A-Z]{2,4}[-_]?\d{4,10}\b",
        description="Order ID pattern (e.g., ORD-ABC12345, ABC-12345)",
    ),
    CustomPattern(
        pii_type=PIIType.ACCOUNT_CODE,
        pattern=r"\b(?:ACC|ACCT)[-_]?\d{6,12}\b",
        description="Account code pattern (e.g., ACC-123456, ACCT123456)",
    ),
    CustomPattern(
        pii_type=PIIType.CUSTOMER_REF,
        pattern=r"\b(?:CUST|CID|REF)[-_]?[A-Z0-9]{6,15}\b",
        description="Customer reference pattern (e.g., CUST-ABC123, CID123456)",
    ),
    # Additional SSN pattern for edge cases Comprehend might miss
    CustomPattern(
        pii_type=PIIType.SSN,
        pattern=r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
        description="Social Security Number pattern",
    ),
    # Credit card pattern for additional coverage
    CustomPattern(
        pii_type=PIIType.CREDIT_DEBIT_NUMBER,
        pattern=r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        description="Credit card number pattern",
    ),
]


# =============================================================================
# Comprehend PII Type Mapping
# =============================================================================


COMPREHEND_TO_PII_TYPE: dict[str, PIIType] = {
    "SSN": PIIType.SSN,
    "CREDIT_DEBIT_NUMBER": PIIType.CREDIT_DEBIT_NUMBER,
    "BANK_ACCOUNT_NUMBER": PIIType.BANK_ACCOUNT_NUMBER,
    "PHONE": PIIType.PHONE,
    "EMAIL": PIIType.EMAIL,
    "ADDRESS": PIIType.ADDRESS,
    "DATE_TIME": PIIType.DATE_TIME,
    "DRIVER_ID": PIIType.DRIVER_ID,
    "PASSPORT_NUMBER": PIIType.PASSPORT_NUMBER,
    "NAME": PIIType.NAME,
    "AGE": PIIType.AGE,
    # Additional Comprehend types mapped to our types
    "BANK_ROUTING": PIIType.BANK_ACCOUNT_NUMBER,
    "CREDIT_DEBIT_CVV": PIIType.CREDIT_DEBIT_NUMBER,
    "CREDIT_DEBIT_EXPIRY": PIIType.CREDIT_DEBIT_NUMBER,
    "PIN": PIIType.BANK_ACCOUNT_NUMBER,
    "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER": PIIType.SSN,
    "IP_ADDRESS": PIIType.ADDRESS,
    "MAC_ADDRESS": PIIType.ADDRESS,
    "URL": PIIType.ADDRESS,
    "AWS_ACCESS_KEY": PIIType.ACCOUNT_CODE,
    "AWS_SECRET_KEY": PIIType.ACCOUNT_CODE,
}


# =============================================================================
# PII Detector Service
# =============================================================================


class PIIDetector:
    """Hybrid PII detection service using Comprehend and custom patterns."""

    def __init__(
        self,
        config: PIIDetectorConfig | None = None,
        custom_patterns: list[CustomPattern] | None = None,
        comprehend_client: ComprehendClient | None = None,
    ) -> None:
        """Initialize the PII detector.

        Args:
            config: Detection configuration. Uses defaults if not provided.
            custom_patterns: Custom regex patterns. Uses defaults if not provided.
            comprehend_client: Boto3 Comprehend client. Created if not provided.
        """
        self.config = config or PIIDetectorConfig()
        self.custom_patterns = custom_patterns or DEFAULT_CUSTOM_PATTERNS
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

    def detect(self, text: str) -> PIICheckResult:
        """Detect PII in text using hybrid approach.

        Args:
            text: The text to scan for PII.

        Returns:
            PIICheckResult with all detections and actions taken.
        """
        all_detections: list[PIIDetection] = []

        # Run Comprehend detection if enabled
        if self.config.use_comprehend:
            comprehend_detections = self._detect_with_comprehend(text)
            all_detections.extend(comprehend_detections)

        # Run custom pattern detection
        custom_detections = self._detect_with_patterns(text)

        # Merge detections, avoiding duplicates based on position
        all_detections = self._merge_detections(all_detections, custom_detections)

        # Determine actions and check for blocking PII
        blocked_types: list[PIIType] = []
        redacted_count = 0
        passed = True

        for detection in all_detections:
            if detection.action == PIIAction.BLOCK:
                passed = False
                if detection.pii_type not in blocked_types:
                    blocked_types.append(detection.pii_type)
            elif detection.action == PIIAction.REDACT:
                redacted_count += 1

        return PIICheckResult(
            passed=passed,
            detections=all_detections,
            blocked_types=blocked_types,
            redacted_count=redacted_count,
        )

    def redact(self, text: str, detections: list[PIIDetection] | None = None) -> str:
        """Redact PII from text.

        Args:
            text: Original text to redact.
            detections: Pre-computed detections. If None, runs detection first.

        Returns:
            Text with PII redacted according to configuration.
        """
        if detections is None:
            result = self.detect(text)
            detections = result.detections

        # Filter to only redactable detections
        to_redact = [d for d in detections if d.action in (PIIAction.REDACT, PIIAction.BLOCK)]

        if not to_redact:
            return text

        # Sort by position (descending) to redact from end to start
        # This preserves correct offsets
        to_redact.sort(key=lambda d: d.start_offset, reverse=True)

        redacted_text = text
        for detection in to_redact:
            start = detection.start_offset
            end = detection.end_offset

            if self.config.use_placeholder:
                replacement = self.config.redaction_placeholder
            else:
                # Mask with redaction character, keeping same length
                original_length = end - start
                replacement = self.config.redaction_char * original_length

            redacted_text = redacted_text[:start] + replacement + redacted_text[end:]

        return redacted_text

    def _detect_with_comprehend(self, text: str) -> list[PIIDetection]:
        """Detect PII using Amazon Comprehend.

        Args:
            text: Text to analyze.

        Returns:
            List of PII detections from Comprehend.
        """
        detections: list[PIIDetection] = []

        try:
            response = self.comprehend_client.detect_pii_entities(
                Text=text,
                LanguageCode=self.config.comprehend_language,
            )

            for entity in response.get("Entities", []):
                confidence = entity.get("Score", 0.0)

                # Skip low-confidence detections
                if confidence < self.config.min_confidence:
                    continue

                comprehend_type = entity.get("Type", "")
                pii_type = COMPREHEND_TO_PII_TYPE.get(comprehend_type)

                if pii_type is None:
                    logger.debug(
                        "Unknown Comprehend PII type",
                        extra={"comprehend_type": comprehend_type},
                    )
                    continue

                start = entity.get("BeginOffset", 0)
                end = entity.get("EndOffset", 0)
                detected_text = text[start:end]

                action = self._determine_action(pii_type)

                detection = PIIDetection(
                    pii_type=pii_type,
                    text=self._mask_for_logging(detected_text),
                    start_offset=start,
                    end_offset=end,
                    confidence=confidence,
                    source="comprehend",
                    action=action,
                    redacted_text=(
                        self._create_redacted_text(detected_text)
                        if action == PIIAction.REDACT
                        else None
                    ),
                )
                detections.append(detection)

            logger.info(
                "Comprehend PII detection complete",
                extra={
                    "entities_found": len(detections),
                    "text_length": len(text),
                },
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(
                "Comprehend API error",
                extra={
                    "error_code": error_code,
                    "error_message": str(e),
                },
            )
            # Return empty list - fail open to allow custom patterns to run
            # In production, you might want to fail closed instead

        return detections

    def _detect_with_patterns(self, text: str) -> list[PIIDetection]:
        """Detect PII using custom regex patterns.

        Args:
            text: Text to analyze.

        Returns:
            List of PII detections from pattern matching.
        """
        detections: list[PIIDetection] = []

        for pattern in self.custom_patterns:
            for match in pattern.compiled.finditer(text):
                detected_text = match.group()
                start = match.start()
                end = match.end()

                action = self._determine_action(pattern.pii_type)

                detection = PIIDetection(
                    pii_type=pattern.pii_type,
                    text=self._mask_for_logging(detected_text),
                    start_offset=start,
                    end_offset=end,
                    confidence=0.95,  # High confidence for exact pattern match
                    source="regex",
                    action=action,
                    redacted_text=(
                        self._create_redacted_text(detected_text)
                        if action == PIIAction.REDACT
                        else None
                    ),
                )
                detections.append(detection)

        logger.debug(
            "Custom pattern detection complete",
            extra={"patterns_checked": len(self.custom_patterns), "matches_found": len(detections)},
        )

        return detections

    def _merge_detections(
        self,
        primary: list[PIIDetection],
        secondary: list[PIIDetection],
    ) -> list[PIIDetection]:
        """Merge detection lists, avoiding duplicates by position overlap.

        Primary detections (Comprehend) take precedence over secondary (regex)
        when positions overlap.

        Args:
            primary: Higher-priority detections.
            secondary: Lower-priority detections.

        Returns:
            Merged list without overlapping detections.
        """
        merged = list(primary)

        for sec_detection in secondary:
            # Check for overlap with any primary detection
            overlaps = any(
                self._positions_overlap(
                    sec_detection.start_offset,
                    sec_detection.end_offset,
                    pri.start_offset,
                    pri.end_offset,
                )
                for pri in primary
            )

            if not overlaps:
                merged.append(sec_detection)

        # Sort by position for consistent ordering
        merged.sort(key=lambda d: d.start_offset)

        return merged

    def _positions_overlap(
        self,
        start1: int,
        end1: int,
        start2: int,
        end2: int,
    ) -> bool:
        """Check if two text positions overlap."""
        return start1 < end2 and start2 < end1

    def _determine_action(self, pii_type: PIIType) -> PIIAction:
        """Determine the action for a PII type based on configuration."""
        if pii_type in self.config.block_types:
            return PIIAction.BLOCK
        if pii_type in self.config.redact_types:
            return PIIAction.REDACT
        if pii_type in self.config.warn_types:
            return PIIAction.WARN
        if pii_type in self.config.allow_types:
            return PIIAction.ALLOW
        # Default to WARN for unknown types
        return PIIAction.WARN

    def _mask_for_logging(self, text: str) -> str:
        """Mask sensitive text for safe logging.

        Shows first 2 and last 2 characters for debugging while hiding middle.
        """
        if len(text) <= 4:
            return "*" * len(text)
        return text[:2] + "*" * (len(text) - 4) + text[-2:]

    def _create_redacted_text(self, original: str) -> str:
        """Create redacted version of text."""
        if self.config.use_placeholder:
            return self.config.redaction_placeholder
        return self.config.redaction_char * len(original)


# =============================================================================
# Convenience Functions
# =============================================================================


def create_default_detector() -> PIIDetector:
    """Create a PII detector with default configuration."""
    return PIIDetector()


def create_strict_detector() -> PIIDetector:
    """Create a PII detector with strict configuration.

    All PII types except business identifiers will be blocked.
    """
    config = PIIDetectorConfig(
        block_types=frozenset(
            {
                PIIType.SSN,
                PIIType.CREDIT_DEBIT_NUMBER,
                PIIType.BANK_ACCOUNT_NUMBER,
                PIIType.PASSPORT_NUMBER,
                PIIType.PHONE,
                PIIType.EMAIL,
                PIIType.ADDRESS,
                PIIType.DRIVER_ID,
            }
        ),
        redact_types=frozenset(
            {
                PIIType.NAME,
                PIIType.AGE,
                PIIType.DATE_TIME,
            }
        ),
        warn_types=frozenset(),
        allow_types=frozenset(
            {
                PIIType.ORDER_ID,
                PIIType.ACCOUNT_CODE,
                PIIType.CUSTOMER_REF,
            }
        ),
        min_confidence=0.7,  # Lower threshold for stricter detection
    )
    return PIIDetector(config=config)


def create_permissive_detector() -> PIIDetector:
    """Create a PII detector with permissive configuration.

    Only critical financial PII will be blocked.
    """
    config = PIIDetectorConfig(
        block_types=frozenset(
            {
                PIIType.SSN,
                PIIType.CREDIT_DEBIT_NUMBER,
                PIIType.BANK_ACCOUNT_NUMBER,
            }
        ),
        redact_types=frozenset(
            {
                PIIType.PASSPORT_NUMBER,
                PIIType.DRIVER_ID,
            }
        ),
        warn_types=frozenset(
            {
                PIIType.PHONE,
                PIIType.EMAIL,
                PIIType.ADDRESS,
                PIIType.NAME,
                PIIType.AGE,
                PIIType.DATE_TIME,
            }
        ),
        allow_types=frozenset(
            {
                PIIType.ORDER_ID,
                PIIType.ACCOUNT_CODE,
                PIIType.CUSTOMER_REF,
            }
        ),
        min_confidence=0.9,  # Higher threshold for fewer false positives
    )
    return PIIDetector(config=config)
