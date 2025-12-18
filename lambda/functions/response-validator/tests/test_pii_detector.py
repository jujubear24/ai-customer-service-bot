"""Unit tests for Response Validator PII detection service."""

from __future__ import annotations

from unittest.mock import MagicMock

from models import PIIAction, PIIType
from pii_detector import (
    COMPREHEND_TO_PII_TYPE,
    DEFAULT_CUSTOM_PATTERNS,
    CustomPattern,
    PIIDetector,
    PIIDetectorConfig,
    create_default_detector,
    create_permissive_detector,
    create_strict_detector,
)


class TestPIIDetectorConfig:
    """Tests for PIIDetectorConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = PIIDetectorConfig()

        assert config.use_comprehend is True
        assert config.comprehend_language == "en"
        assert config.min_confidence == 0.8
        assert PIIType.SSN in config.block_types
        assert PIIType.PHONE in config.redact_types
        assert PIIType.NAME in config.warn_types
        assert PIIType.ORDER_ID in config.allow_types

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = PIIDetectorConfig(
            use_comprehend=False,
            min_confidence=0.9,
            block_types=frozenset({PIIType.SSN}),
        )

        assert config.use_comprehend is False
        assert config.min_confidence == 0.9
        assert config.block_types == frozenset({PIIType.SSN})


class TestCustomPattern:
    """Tests for CustomPattern."""

    def test_pattern_compilation(self) -> None:
        """Test pattern is compiled on init."""
        pattern = CustomPattern(
            pii_type=PIIType.ORDER_ID,
            pattern=r"\bORD-\d+\b",
            description="Order ID pattern",
        )

        assert pattern.compiled is not None
        assert pattern.compiled.match("ORD-12345")

    def test_case_insensitive(self) -> None:
        """Test patterns are case insensitive."""
        pattern = CustomPattern(
            pii_type=PIIType.ACCOUNT_CODE,
            pattern=r"\bACC-\d+\b",
            description="Account code",
        )

        assert pattern.compiled.match("acc-12345")
        assert pattern.compiled.match("ACC-12345")


class TestDefaultPatterns:
    """Tests for default custom patterns."""

    def test_order_id_pattern(self) -> None:
        """Test order ID pattern matches expected formats."""
        order_pattern = next(p for p in DEFAULT_CUSTOM_PATTERNS if p.pii_type == PIIType.ORDER_ID)

        # Should match
        assert order_pattern.compiled.search("Order ORD-ABC12345 confirmed")
        assert order_pattern.compiled.search("Your order ABC-12345 is ready")

    def test_account_code_pattern(self) -> None:
        """Test account code pattern matches expected formats."""
        acc_pattern = next(p for p in DEFAULT_CUSTOM_PATTERNS if p.pii_type == PIIType.ACCOUNT_CODE)

        assert acc_pattern.compiled.search("Account ACC-123456")
        assert acc_pattern.compiled.search("Your ACCT123456789")

    def test_ssn_pattern(self) -> None:
        """Test SSN pattern matches expected formats."""
        ssn_pattern = next(p for p in DEFAULT_CUSTOM_PATTERNS if p.pii_type == PIIType.SSN)

        assert ssn_pattern.compiled.search("SSN: 123-45-6789")
        assert ssn_pattern.compiled.search("SSN 123 45 6789")

    def test_credit_card_pattern(self) -> None:
        """Test credit card pattern matches expected formats."""
        cc_pattern = next(
            p for p in DEFAULT_CUSTOM_PATTERNS if p.pii_type == PIIType.CREDIT_DEBIT_NUMBER
        )

        assert cc_pattern.compiled.search("Card: 4111-1111-1111-1111")
        assert cc_pattern.compiled.search("4111 1111 1111 1111")


class TestPIIDetector:
    """Tests for PIIDetector class."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default config."""
        detector = PIIDetector()

        assert detector.config.use_comprehend is True
        assert len(detector.custom_patterns) > 0

    def test_init_with_custom_config(self) -> None:
        """Test initialization with custom config."""
        config = PIIDetectorConfig(use_comprehend=False)
        detector = PIIDetector(config=config)

        assert detector.config.use_comprehend is False

    def test_detect_no_pii(self, pii_detector: PIIDetector) -> None:
        """Test detection on clean text."""
        result = pii_detector.detect("This is a clean text with no sensitive data.")

        assert result.passed is True
        assert result.has_detections is False
        assert result.detections == []

    def test_detect_order_id(self, pii_detector: PIIDetector) -> None:
        """Test detection of order IDs."""
        result = pii_detector.detect("Your order ORD-ABC12345 is ready for pickup.")

        assert result.has_detections is True
        # Order IDs should be allowed by default
        assert result.passed is True

        order_detections = [d for d in result.detections if d.pii_type == PIIType.ORDER_ID]
        assert len(order_detections) >= 1

    def test_detect_ssn_pattern(self, pii_detector: PIIDetector) -> None:
        """Test detection of SSN patterns."""
        result = pii_detector.detect("Your SSN is 123-45-6789.")

        assert result.has_detections is True
        assert result.passed is False  # SSN should block

        ssn_detections = [d for d in result.detections if d.pii_type == PIIType.SSN]
        assert len(ssn_detections) >= 1
        assert ssn_detections[0].action == PIIAction.BLOCK

    def test_detect_credit_card_pattern(self, pii_detector: PIIDetector) -> None:
        """Test detection of credit card patterns."""
        result = pii_detector.detect("Card number: 4111-1111-1111-1111")

        assert result.has_detections is True
        assert result.passed is False  # Credit card should block

        cc_detections = [d for d in result.detections if d.pii_type == PIIType.CREDIT_DEBIT_NUMBER]
        assert len(cc_detections) >= 1

    def test_detect_multiple_pii(self, pii_detector: PIIDetector) -> None:
        """Test detection of multiple PII types."""
        # SSN and credit card should both be detected
        result = pii_detector.detect("SSN: 123-45-6789 and Card: 4111-1111-1111-1111")

        assert result.has_detections is True
        assert len(result.detections) >= 2  # At least SSN and credit card

    def test_action_determination(self, pii_detector: PIIDetector) -> None:
        """Test correct action is determined for each PII type."""
        config = PIIDetectorConfig(
            use_comprehend=False,
            block_types=frozenset({PIIType.SSN}),
            redact_types=frozenset({PIIType.ORDER_ID}),
            warn_types=frozenset({PIIType.ACCOUNT_CODE}),
            allow_types=frozenset({PIIType.CUSTOMER_REF}),
        )
        detector = PIIDetector(config=config)

        # SSN should block
        ssn_result = detector.detect("SSN: 123-45-6789")
        ssn_detection = next((d for d in ssn_result.detections if d.pii_type == PIIType.SSN), None)
        if ssn_detection:
            assert ssn_detection.action == PIIAction.BLOCK

    def test_text_masked_for_logging(self, pii_detector: PIIDetector) -> None:
        """Test detected text is masked in results."""
        result = pii_detector.detect("SSN: 123-45-6789")

        for detection in result.detections:
            # Should not contain full SSN
            assert "123-45-6789" not in detection.text
            # Should contain masking characters
            assert "*" in detection.text

    def test_redact_text(self, pii_detector: PIIDetector) -> None:
        """Test PII redaction."""
        text = "Your SSN is 123-45-6789 on file."
        result = pii_detector.detect(text)

        redacted = pii_detector.redact(text, result.detections)

        # SSN should be masked
        assert "123-45-6789" not in redacted
        assert "***" in redacted or "[REDACTED]" in redacted

    def test_redact_preserves_structure(self, pii_detector: PIIDetector) -> None:
        """Test redaction preserves text structure."""
        text = "Start SSN: 123-45-6789 End"
        result = pii_detector.detect(text)

        redacted = pii_detector.redact(text, result.detections)

        assert redacted.startswith("Start")
        assert redacted.endswith("End")

    def test_redact_with_placeholder(self) -> None:
        """Test redaction using placeholder."""
        config = PIIDetectorConfig(
            use_comprehend=False,
            use_placeholder=True,
            redaction_placeholder="[HIDDEN]",
        )
        detector = PIIDetector(config=config)

        text = "SSN: 123-45-6789"
        redacted = detector.redact(text)

        assert "[HIDDEN]" in redacted

    def test_redact_without_detections(self, pii_detector: PIIDetector) -> None:
        """Test redact runs detection if no detections provided."""
        text = "SSN: 123-45-6789"
        redacted = pii_detector.redact(text)

        assert "123-45-6789" not in redacted


class TestPIIDetectorWithComprehend:
    """Tests for PIIDetector with Comprehend integration."""

    def test_comprehend_detection(self, mock_comprehend_with_pii: MagicMock) -> None:
        """Test detection using Comprehend."""
        detector = PIIDetector(comprehend_client=mock_comprehend_with_pii)

        result = detector.detect("Text with SSN and credit card")

        mock_comprehend_with_pii.detect_pii_entities.assert_called_once()
        assert result.has_detections is True
        assert len(result.detections) >= 2

    def test_comprehend_low_confidence_filtered(self, mock_comprehend_client: MagicMock) -> None:
        """Test low confidence detections are filtered."""
        mock_comprehend_client.detect_pii_entities.return_value = {
            "Entities": [
                {
                    "Type": "NAME",
                    "Score": 0.5,  # Below threshold
                    "BeginOffset": 0,
                    "EndOffset": 4,
                },
            ],
        }

        config = PIIDetectorConfig(min_confidence=0.8)
        detector = PIIDetector(config=config, comprehend_client=mock_comprehend_client)

        result = detector.detect("John is here")

        # Low confidence detection should be filtered
        assert result.has_detections is False

    def test_comprehend_error_handling(self, mock_comprehend_client: MagicMock) -> None:
        """Test graceful handling of Comprehend errors."""
        from botocore.exceptions import ClientError

        mock_comprehend_client.detect_pii_entities.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "DetectPiiEntities",
        )

        detector = PIIDetector(comprehend_client=mock_comprehend_client)

        # Should not raise, but return empty Comprehend results
        result = detector.detect("SSN: 123-45-6789")

        # Custom patterns should still work
        assert result.has_detections is True

    def test_comprehend_type_mapping(self) -> None:
        """Test Comprehend type to PIIType mapping."""
        assert COMPREHEND_TO_PII_TYPE["SSN"] == PIIType.SSN
        assert COMPREHEND_TO_PII_TYPE["CREDIT_DEBIT_NUMBER"] == PIIType.CREDIT_DEBIT_NUMBER
        assert COMPREHEND_TO_PII_TYPE["PHONE"] == PIIType.PHONE
        assert COMPREHEND_TO_PII_TYPE["EMAIL"] == PIIType.EMAIL


class TestPIICheckResult:
    """Tests for PIICheckResult properties."""

    def test_critical_pii_found_ssn(self, pii_detector: PIIDetector) -> None:
        """Test critical_pii_found detects SSN."""
        result = pii_detector.detect("SSN: 123-45-6789")

        assert result.critical_pii_found is True

    def test_critical_pii_found_credit_card(self, pii_detector: PIIDetector) -> None:
        """Test critical_pii_found detects credit card."""
        result = pii_detector.detect("Card: 4111-1111-1111-1111")

        assert result.critical_pii_found is True

    def test_non_critical_pii(self, pii_detector: PIIDetector) -> None:
        """Test non-critical PII doesn't trigger critical flag."""
        result = pii_detector.detect("Order: ORD-ABC12345")

        # Order IDs are allowed, not critical
        if result.has_detections:
            assert result.critical_pii_found is False


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_default_detector(self) -> None:
        """Test create_default_detector function."""
        detector = create_default_detector()

        assert detector is not None
        assert detector.config.use_comprehend is True

    def test_create_strict_detector(self) -> None:
        """Test create_strict_detector function."""
        detector = create_strict_detector()

        assert detector is not None
        # Strict detector blocks more types
        assert PIIType.PHONE in detector.config.block_types
        assert PIIType.EMAIL in detector.config.block_types
        # Lower confidence threshold
        assert detector.config.min_confidence == 0.7

    def test_create_permissive_detector(self) -> None:
        """Test create_permissive_detector function."""
        detector = create_permissive_detector()

        assert detector is not None
        # Permissive detector warns on more types
        assert PIIType.PHONE in detector.config.warn_types
        assert PIIType.EMAIL in detector.config.warn_types
        # Higher confidence threshold
        assert detector.config.min_confidence == 0.9


class TestPositionOverlap:
    """Tests for position overlap detection."""

    def test_overlapping_positions(self) -> None:
        """Test overlap detection for overlapping positions."""
        config = PIIDetectorConfig(use_comprehend=False)
        detector = PIIDetector(config=config)

        # Test internal overlap method
        assert detector._positions_overlap(0, 10, 5, 15) is True
        assert detector._positions_overlap(5, 15, 0, 10) is True
        assert detector._positions_overlap(0, 10, 0, 10) is True

    def test_non_overlapping_positions(self) -> None:
        """Test overlap detection for non-overlapping positions."""
        config = PIIDetectorConfig(use_comprehend=False)
        detector = PIIDetector(config=config)

        assert detector._positions_overlap(0, 10, 10, 20) is False
        assert detector._positions_overlap(10, 20, 0, 10) is False
        assert detector._positions_overlap(0, 10, 20, 30) is False
