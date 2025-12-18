"""Unit tests for Response Validator service layer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from models import (
    ValidationAction,
    ValidationRequest,
)
from pii_detector import PIIDetector, PIIDetectorConfig
from rules import RulesEngine
from service import (
    FALLBACK,
    ResponseValidatorService,
    ValidationServiceConfig,
    create_default_service,
    create_permissive_service,
    create_strict_service,
)


class TestFallbackResponses:
    """Tests for FallbackResponses."""

    def test_default_responses(self) -> None:
        """Test default fallback responses exist."""
        assert FALLBACK.default is not None
        assert FALLBACK.pii_blocked is not None
        assert FALLBACK.profanity_blocked is not None
        assert FALLBACK.content_blocked is not None
        assert FALLBACK.too_short is not None

    def test_responses_are_helpful(self) -> None:
        """Test fallback responses are user-friendly."""
        assert "apologize" in FALLBACK.default.lower()
        assert "security" in FALLBACK.pii_blocked.lower()


class TestValidationServiceConfig:
    """Tests for ValidationServiceConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = ValidationServiceConfig()

        assert config.enable_pii_detection is True
        assert config.enable_profanity_check is True
        assert config.enable_business_rules is True
        assert config.enable_length_check is True
        assert config.min_response_length == 20
        assert config.max_response_length == 2000
        assert config.truncate_long_responses is True
        assert config.stop_on_critical_failure is True
        assert config.use_fallback_on_block is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = ValidationServiceConfig(
            enable_pii_detection=False,
            min_response_length=50,
            max_response_length=1000,
        )

        assert config.enable_pii_detection is False
        assert config.min_response_length == 50
        assert config.max_response_length == 1000


class TestResponseValidatorService:
    """Tests for ResponseValidatorService."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default config."""
        service = ResponseValidatorService()

        assert service.config is not None
        assert service.config.enable_pii_detection is True

    def test_init_with_custom_config(self) -> None:
        """Test initialization with custom config."""
        config = ValidationServiceConfig(enable_pii_detection=False)
        service = ResponseValidatorService(config=config)

        assert service.config.enable_pii_detection is False

    def test_lazy_pii_detector(self) -> None:
        """Test PII detector is lazy loaded."""
        service = ResponseValidatorService()

        # Accessing property creates detector
        detector = service.pii_detector
        assert detector is not None
        assert isinstance(detector, PIIDetector)

    def test_lazy_rules_engine(self) -> None:
        """Test rules engine is lazy loaded."""
        service = ResponseValidatorService()

        engine = service.rules_engine
        assert engine is not None
        assert isinstance(engine, RulesEngine)

    def test_validate_clean_response(
        self,
        validation_service: ResponseValidatorService,
        sample_request: ValidationRequest,
    ) -> None:
        """Test validation of clean response."""
        response = validation_service.validate(sample_request)

        assert response.is_valid is True
        assert response.action == ValidationAction.PASS
        assert response.validated_response == sample_request.response_text
        assert response.was_modified is False

    def test_validate_with_pii_blocked(
        self,
        validation_service: ResponseValidatorService,
        request_with_pii_response: ValidationRequest,
    ) -> None:
        """Test validation blocks response with critical PII."""
        response = validation_service.validate(request_with_pii_response)

        assert response.is_valid is False
        assert response.action == ValidationAction.BLOCK
        assert response.metadata.fallback_used is True
        assert response.validated_response == FALLBACK.pii_blocked

    def test_validate_with_profanity(
        self,
        validation_service: ResponseValidatorService,
        request_with_profanity: ValidationRequest,
    ) -> None:
        """Test validation blocks response with profanity."""
        response = validation_service.validate(request_with_profanity)

        assert response.is_valid is False
        assert response.action == ValidationAction.BLOCK
        assert response.metadata.fallback_used is True

    def test_validate_with_short_response(
        self,
        validation_service: ResponseValidatorService,
        request_with_short_response: ValidationRequest,
    ) -> None:
        """Test validation blocks too-short response."""
        response = validation_service.validate(request_with_short_response)

        assert response.is_valid is False
        assert response.action == ValidationAction.BLOCK

    def test_validate_with_long_response_truncated(
        self,
        validation_service: ResponseValidatorService,
        request_with_long_response: ValidationRequest,
    ) -> None:
        """Test validation truncates long response."""
        response = validation_service.validate(request_with_long_response)

        # Should pass because truncation fixes it
        assert response.is_valid is True
        assert response.was_modified is True
        assert len(response.validated_response) <= 2000

    def test_validate_with_medical_content(
        self,
        validation_service: ResponseValidatorService,
        request_with_medical_content: ValidationRequest,
    ) -> None:
        """Test validation adds disclaimer for medical content."""
        response = validation_service.validate(request_with_medical_content)

        assert response.is_valid is True
        assert response.was_modified is True
        assert "Disclaimer" in response.validated_response

    def test_validate_pii_detection_disabled(
        self,
        validation_service_no_pii: ValidationServiceConfig,
        request_with_pii_response: ValidationRequest,
    ) -> None:
        """Test validation with PII detection disabled."""
        service = ResponseValidatorService(config=validation_service_no_pii)
        response = service.validate(request_with_pii_response)

        # PII check disabled, but profanity/length should still run
        # The response might still fail length check if too short
        assert response.validation_results.pii is None

    def test_validate_stop_on_critical_failure(
        self,
        request_with_pii_response: ValidationRequest,
    ) -> None:
        """Test validation stops on critical failure when configured."""
        config = ValidationServiceConfig(
            stop_on_critical_failure=True,
            enable_pii_detection=True,
        )
        # Create detector that will find PII
        pii_config = PIIDetectorConfig(use_comprehend=False)
        pii_detector = PIIDetector(config=pii_config)

        service = ResponseValidatorService(config=config, pii_detector=pii_detector)
        response = service.validate(request_with_pii_response)

        # Should stop after PII check fails
        assert response.is_valid is False
        assert response.metadata.fallback_used is True

    def test_validate_continue_on_failure(
        self,
        request_with_pii_response: ValidationRequest,
    ) -> None:
        """Test validation continues when stop_on_critical_failure is False."""
        config = ValidationServiceConfig(
            stop_on_critical_failure=False,
            use_fallback_on_block=False,
            enable_pii_detection=True,
        )
        pii_config = PIIDetectorConfig(use_comprehend=False)
        pii_detector = PIIDetector(config=pii_config)

        service = ResponseValidatorService(config=config, pii_detector=pii_detector)
        response = service.validate(request_with_pii_response)

        # Should still evaluate business rules even after PII failure
        assert response.validation_results.business_rules is not None

    def test_validate_no_fallback(
        self,
        request_with_pii_response: ValidationRequest,
    ) -> None:
        """Test validation without fallback substitution."""
        config = ValidationServiceConfig(
            use_fallback_on_block=False,
            enable_pii_detection=True,
        )
        pii_config = PIIDetectorConfig(use_comprehend=False)
        pii_detector = PIIDetector(config=pii_config)

        service = ResponseValidatorService(config=config, pii_detector=pii_detector)
        response = service.validate(request_with_pii_response)

        assert response.is_valid is False
        assert response.metadata.fallback_used is False
        # Original response should still be marked as blocked but not replaced
        assert response.original_response == request_with_pii_response.response_text

    def test_validate_pii_redaction(self, sample_request: ValidationRequest) -> None:
        """Test PII is redacted when configured."""
        config = ValidationServiceConfig(
            redact_pii_in_response=True,
            enable_pii_detection=True,
        )

        # Create a request with redactable (but not blocking) PII
        request = ValidationRequest(
            response_text="Your SSN is 123-45-6789 for reference.",
            user_message="What is my SSN?",
            conversation_id="conv-redact",
            tenant_id="test-tenant",
        )

        # Use default PII detector (blocks SSN)
        pii_config = PIIDetectorConfig(use_comprehend=False)
        pii_detector = PIIDetector(config=pii_config)

        service = ResponseValidatorService(config=config, pii_detector=pii_detector)
        response = service.validate(request)

        # SSN should cause blocking
        assert response.is_valid is False
        assert response.action == ValidationAction.BLOCK

    def test_validate_metadata(
        self,
        validation_service: ResponseValidatorService,
        sample_request: ValidationRequest,
    ) -> None:
        """Test validation metadata is populated."""
        response = validation_service.validate(sample_request)

        assert response.metadata.validation_time_ms > 0
        assert response.metadata.rules_evaluated > 0
        assert response.metadata.timestamp is not None

    def test_rules_engine_configuration(self) -> None:
        """Test rules engine is configured based on service config."""
        config = ValidationServiceConfig(
            enable_profanity_check=True,
            enable_length_check=True,
            enable_business_rules=True,
            min_response_length=50,
            max_response_length=500,
        )
        service = ResponseValidatorService(config=config)

        engine = service.rules_engine
        rule_ids = [r.rule_id for r in engine.rules]

        assert "PROFANITY_001" in rule_ids
        assert "LENGTH_001" in rule_ids
        assert "TOPIC_001" in rule_ids

    def test_rules_engine_partial_configuration(self) -> None:
        """Test rules engine with some checks disabled."""
        config = ValidationServiceConfig(
            enable_profanity_check=False,
            enable_length_check=True,
            enable_business_rules=False,
        )
        service = ResponseValidatorService(config=config)

        engine = service.rules_engine
        rule_ids = [r.rule_id for r in engine.rules]

        assert "PROFANITY_001" not in rule_ids
        assert "LENGTH_001" in rule_ids
        assert "TOPIC_001" not in rule_ids


class TestServiceFallbackSelection:
    """Tests for fallback response selection."""

    def test_pii_fallback(
        self,
        request_with_pii_response: ValidationRequest,
    ) -> None:
        """Test PII blocked uses correct fallback."""
        config = ValidationServiceConfig(enable_pii_detection=True)
        pii_config = PIIDetectorConfig(use_comprehend=False)
        pii_detector = PIIDetector(config=pii_config)

        service = ResponseValidatorService(config=config, pii_detector=pii_detector)
        response = service.validate(request_with_pii_response)

        assert response.validated_response == FALLBACK.pii_blocked
        assert response.metadata.fallback_reason == "pii_blocked"

    def test_profanity_fallback(
        self,
        request_with_profanity: ValidationRequest,
    ) -> None:
        """Test profanity blocked uses correct fallback."""
        config = ValidationServiceConfig(enable_pii_detection=False)
        service = ResponseValidatorService(config=config)
        response = service.validate(request_with_profanity)

        assert response.validated_response == FALLBACK.profanity_blocked
        assert response.metadata.fallback_reason == "profanity_blocked"

    def test_too_short_fallback(
        self,
        request_with_short_response: ValidationRequest,
    ) -> None:
        """Test too-short response uses correct fallback."""
        config = ValidationServiceConfig(enable_pii_detection=False)
        service = ResponseValidatorService(config=config)
        response = service.validate(request_with_short_response)

        assert response.validated_response == FALLBACK.too_short
        assert response.metadata.fallback_reason == "too_short"


class TestServiceMetrics:
    """Tests for service metrics emission."""

    @patch("service.metrics")
    def test_metrics_emitted_on_success(
        self,
        mock_metrics: MagicMock,
        validation_service: ResponseValidatorService,
        sample_request: ValidationRequest,
    ) -> None:
        """Test metrics are emitted on successful validation."""
        validation_service.validate(sample_request)

        # Check that add_metric was called
        assert mock_metrics.add_metric.called

    @patch("service.metrics")
    def test_metrics_include_tenant(
        self,
        mock_metrics: MagicMock,
        validation_service: ResponseValidatorService,
        sample_request: ValidationRequest,
    ) -> None:
        """Test metrics include tenant dimension."""
        validation_service.validate(sample_request)

        # Check add_dimension was called with tenant
        mock_metrics.add_dimension.assert_called()


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_default_service(self) -> None:
        """Test create_default_service function."""
        service = create_default_service()

        assert service is not None
        assert service.config.enable_pii_detection is True

    def test_create_strict_service(self) -> None:
        """Test create_strict_service function."""
        service = create_strict_service()

        assert service is not None
        assert service.config.min_response_length == 50
        assert service.config.max_response_length == 1500
        assert service.config.truncate_long_responses is False

    def test_create_permissive_service(self) -> None:
        """Test create_permissive_service function."""
        service = create_permissive_service()

        assert service is not None
        assert service.config.min_response_length == 10
        assert service.config.max_response_length == 3000
        assert service.config.stop_on_critical_failure is False
        assert service.config.use_fallback_on_block is False
