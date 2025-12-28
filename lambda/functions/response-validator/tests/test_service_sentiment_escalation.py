"""Unit tests for Response Validator service - Sentiment & Escalation integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from escalation import EscalationScorer, EscalationScorerConfig
from models import (
    Sentiment,
    SentimentResult,
    ValidationAction,
    ValidationOptions,
    ValidationRequest,
)
from pii_detector import PIIDetector
from sentiment_analyzer import SentimentAnalyzer
from service import ResponseValidatorService, ValidationServiceConfig


class TestValidationServiceConfigSentimentEscalation:
    """Tests for ValidationServiceConfig sentiment and escalation settings."""

    def test_default_config_enables_sentiment(self) -> None:
        """Test default config has sentiment analysis enabled."""
        config = ValidationServiceConfig()

        assert config.enable_sentiment_analysis is True

    def test_default_config_enables_escalation(self) -> None:
        """Test default config has escalation scoring enabled."""
        config = ValidationServiceConfig()

        assert config.enable_escalation_scoring is True

    def test_default_escalation_threshold(self) -> None:
        """Test default escalation threshold is 0.70."""
        config = ValidationServiceConfig()

        assert config.escalation_threshold == 0.70

    def test_custom_escalation_threshold(self) -> None:
        """Test custom escalation threshold."""
        config = ValidationServiceConfig(escalation_threshold=0.50)

        assert config.escalation_threshold == 0.50

    def test_disable_sentiment_analysis(self) -> None:
        """Test disabling sentiment analysis."""
        config = ValidationServiceConfig(enable_sentiment_analysis=False)

        assert config.enable_sentiment_analysis is False

    def test_disable_escalation_scoring(self) -> None:
        """Test disabling escalation scoring."""
        config = ValidationServiceConfig(enable_escalation_scoring=False)

        assert config.enable_escalation_scoring is False


class TestValidationServiceSentimentAnalysis:
    """Tests for sentiment analysis in ValidationService."""

    def test_service_has_sentiment_analyzer(
        self, validation_service_full: ResponseValidatorService
    ) -> None:
        """Test service has sentiment analyzer property."""
        assert validation_service_full.sentiment_analyzer is not None
        assert isinstance(validation_service_full.sentiment_analyzer, SentimentAnalyzer)

    def test_service_lazy_loads_sentiment_analyzer(self) -> None:
        """Test sentiment analyzer is lazy-loaded."""
        config = ValidationServiceConfig(enable_sentiment_analysis=True)
        service = ResponseValidatorService(config=config)

        # Access the property to trigger lazy loading
        analyzer = service.sentiment_analyzer

        assert analyzer is not None
        assert isinstance(analyzer, SentimentAnalyzer)

    def test_validate_includes_sentiment_result(
        self,
        validation_service_full: ResponseValidatorService,
        sample_request: ValidationRequest,
    ) -> None:
        """Test validation response includes sentiment result."""
        response = validation_service_full.validate(sample_request)

        assert response.sentiment is not None
        assert isinstance(response.sentiment, SentimentResult)
        assert response.sentiment.sentiment in Sentiment

    def test_validate_sentiment_disabled_via_config(
        self,
        pii_detector: PIIDetector,
        sample_request: ValidationRequest,
    ) -> None:
        """Test sentiment is None when disabled in service config."""
        config = ValidationServiceConfig(
            enable_pii_detection=True,
            enable_sentiment_analysis=False,
            enable_escalation_scoring=False,
        )
        service = ResponseValidatorService(config=config, pii_detector=pii_detector)

        response = service.validate(sample_request)

        assert response.sentiment is None

    def test_validate_sentiment_disabled_via_request_options(
        self,
        validation_service_full: ResponseValidatorService,
    ) -> None:
        """Test sentiment is None when disabled in request options."""
        request = ValidationRequest(
            response_text="This is a test response that should pass validation.",
            user_message="What is the answer?",
            conversation_id="conv-123",
            tenant_id="test-tenant",
            options=ValidationOptions(
                analyze_sentiment=False,
                calculate_escalation=False,
            ),
        )

        response = validation_service_full.validate(request)

        assert response.sentiment is None

    def test_validate_analyzes_user_message_not_response(
        self,
        pii_detector: PIIDetector,
        mock_comprehend_sentiment_negative: MagicMock,
    ) -> None:
        """Test that sentiment analysis is performed on user message."""
        sentiment_analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_negative)
        config = ValidationServiceConfig(
            enable_pii_detection=True,
            enable_sentiment_analysis=True,
            enable_escalation_scoring=True,
        )
        service = ResponseValidatorService(
            config=config,
            pii_detector=pii_detector,
            sentiment_analyzer=sentiment_analyzer,
        )

        request = ValidationRequest(
            response_text="Here is your answer with helpful information.",
            user_message="I am very frustrated with this terrible service!",
            conversation_id="conv-123",
            tenant_id="test-tenant",
        )

        response = service.validate(request)

        # Should detect negative sentiment from user message
        assert response.sentiment is not None
        assert response.sentiment.sentiment == Sentiment.NEGATIVE

    def test_validate_sentiment_error_fails_open(
        self,
        pii_detector: PIIDetector,
    ) -> None:
        """Test that sentiment analysis errors fail open."""
        # Create analyzer that will raise an exception
        mock_analyzer = MagicMock(spec=SentimentAnalyzer)
        mock_analyzer.analyze_with_escalation.side_effect = Exception("Comprehend error")

        config = ValidationServiceConfig(
            enable_pii_detection=True,
            enable_sentiment_analysis=True,
            enable_escalation_scoring=True,
        )
        service = ResponseValidatorService(
            config=config,
            pii_detector=pii_detector,
            sentiment_analyzer=mock_analyzer,
        )

        request = ValidationRequest(
            response_text="This is a valid response text for testing.",
            user_message="Test message",
            conversation_id="conv-123",
            tenant_id="test-tenant",
        )

        # Should not raise, should fail open
        response = service.validate(request)

        assert response.is_valid is True
        assert response.sentiment is None


class TestValidationServiceEscalationScoring:
    """Tests for escalation scoring in ValidationService."""

    def test_service_has_escalation_scorer(
        self, validation_service_full: ResponseValidatorService
    ) -> None:
        """Test service has escalation scorer property."""
        assert validation_service_full.escalation_scorer is not None
        assert isinstance(validation_service_full.escalation_scorer, EscalationScorer)

    def test_service_lazy_loads_escalation_scorer(self) -> None:
        """Test escalation scorer is lazy-loaded."""
        config = ValidationServiceConfig(enable_escalation_scoring=True)
        service = ResponseValidatorService(config=config)

        scorer = service.escalation_scorer

        assert scorer is not None
        assert isinstance(scorer, EscalationScorer)

    def test_service_uses_config_threshold(self) -> None:
        """Test escalation scorer uses threshold from config."""
        config = ValidationServiceConfig(
            enable_escalation_scoring=True,
            escalation_threshold=0.50,
        )
        service = ResponseValidatorService(config=config)

        assert service.escalation_scorer.config.threshold == 0.50

    def test_validate_includes_escalation_result(
        self,
        validation_service_full: ResponseValidatorService,
        sample_request: ValidationRequest,
    ) -> None:
        """Test validation response includes escalation result."""
        response = validation_service_full.validate(sample_request)

        assert response.escalation is not None
        assert hasattr(response.escalation, "score")
        assert hasattr(response.escalation, "needs_escalation")
        assert hasattr(response.escalation, "factors")

    def test_validate_escalation_disabled_via_config(
        self,
        pii_detector: PIIDetector,
        sample_request: ValidationRequest,
    ) -> None:
        """Test escalation is None when disabled in service config."""
        config = ValidationServiceConfig(
            enable_pii_detection=True,
            enable_sentiment_analysis=False,
            enable_escalation_scoring=False,
        )
        service = ResponseValidatorService(config=config, pii_detector=pii_detector)

        response = service.validate(sample_request)

        assert response.escalation is None

    def test_validate_escalation_disabled_via_request_options(
        self,
        validation_service_full: ResponseValidatorService,
    ) -> None:
        """Test escalation is None when disabled in request options."""
        request = ValidationRequest(
            response_text="This is a test response that should pass validation.",
            user_message="What is the answer?",
            conversation_id="conv-123",
            tenant_id="test-tenant",
            options=ValidationOptions(
                analyze_sentiment=False,
                calculate_escalation=False,
            ),
        )

        response = validation_service_full.validate(request)

        assert response.escalation is None

    def test_validate_escalation_uses_request_context(
        self,
        pii_detector: PIIDetector,
        mock_comprehend_sentiment_neutral: MagicMock,
    ) -> None:
        """Test escalation uses intent, urgency, and previous_intents from request."""
        sentiment_analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_neutral)
        config = ValidationServiceConfig(
            enable_pii_detection=True,
            enable_sentiment_analysis=True,
            enable_escalation_scoring=True,
        )
        service = ResponseValidatorService(
            config=config,
            pii_detector=pii_detector,
            sentiment_analyzer=sentiment_analyzer,
        )

        request = ValidationRequest(
            response_text="I understand your concern. Let me help.",
            user_message="Why isn't this working?",
            conversation_id="conv-123",
            tenant_id="test-tenant",
            intent="complaint",
            intent_confidence=0.85,
            urgency="high",
            message_count=5,
            previous_intents=["complaint", "complaint"],
        )

        response = service.validate(request)

        assert response.escalation is not None
        # High urgency should contribute to score
        assert response.escalation.factors.urgency == 1.0
        # Repeated complaint intent should contribute
        assert response.escalation.factors.repeated_question == 1.0

    def test_validate_needs_escalation_property(
        self,
        pii_detector: PIIDetector,
        mock_comprehend_sentiment_negative: MagicMock,
    ) -> None:
        """Test needs_escalation property on ValidationResponse."""
        sentiment_analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_negative)
        # Use low threshold to trigger escalation
        escalation_config = EscalationScorerConfig(threshold=0.30)
        escalation_scorer = EscalationScorer(config=escalation_config)

        config = ValidationServiceConfig(
            enable_pii_detection=True,
            enable_sentiment_analysis=True,
            enable_escalation_scoring=True,
        )
        service = ResponseValidatorService(
            config=config,
            pii_detector=pii_detector,
            sentiment_analyzer=sentiment_analyzer,
            escalation_scorer=escalation_scorer,
        )

        request = ValidationRequest(
            response_text="I apologize for the inconvenience.",
            user_message="I want to speak to a human agent right now!",
            conversation_id="conv-123",
            tenant_id="test-tenant",
            urgency="high",
        )

        response = service.validate(request)

        # Should trigger escalation due to explicit intent + negative sentiment + high urgency
        assert response.needs_escalation is True
        assert response.escalation is not None
        assert response.escalation.needs_escalation is True


class TestValidationServiceExplicitEscalation:
    """Tests for explicit escalation detection in validation flow."""

    def test_explicit_escalation_detected(
        self,
        pii_detector: PIIDetector,
        mock_comprehend_sentiment_neutral: MagicMock,
    ) -> None:
        """Test that explicit escalation phrases are detected."""
        sentiment_analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_neutral)
        escalation_config = EscalationScorerConfig(threshold=0.30)
        escalation_scorer = EscalationScorer(config=escalation_config)

        config = ValidationServiceConfig(
            enable_pii_detection=True,
            enable_sentiment_analysis=True,
            enable_escalation_scoring=True,
        )
        service = ResponseValidatorService(
            config=config,
            pii_detector=pii_detector,
            sentiment_analyzer=sentiment_analyzer,
            escalation_scorer=escalation_scorer,
        )

        request = ValidationRequest(
            response_text="I understand. Let me help you.",
            user_message="Transfer me to a human please",
            conversation_id="conv-123",
            tenant_id="test-tenant",
        )

        response = service.validate(request)

        assert response.escalation is not None
        assert response.escalation.factors.explicit_intent == 1.0

    def test_no_explicit_escalation_in_normal_message(
        self,
        validation_service_full: ResponseValidatorService,
    ) -> None:
        """Test that normal messages don't trigger explicit escalation."""
        request = ValidationRequest(
            response_text="Here is the information you requested.",
            user_message="What are your store hours?",
            conversation_id="conv-123",
            tenant_id="test-tenant",
        )

        response = validation_service_full.validate(request)

        assert response.escalation is not None
        assert response.escalation.factors.explicit_intent == 0.0


class TestValidationServiceCombinedFlow:
    """Tests for combined validation flow with all features."""

    def test_full_validation_flow_pass(
        self,
        validation_service_full: ResponseValidatorService,
        sample_request: ValidationRequest,
    ) -> None:
        """Test full validation flow that passes all checks."""
        response = validation_service_full.validate(sample_request)

        assert response.is_valid is True
        assert response.action == ValidationAction.PASS
        assert response.sentiment is not None
        assert response.escalation is not None
        assert response.metadata.comprehend_calls >= 1

    def test_full_validation_flow_with_pii_block(
        self,
        validation_service_full: ResponseValidatorService,
        request_with_pii_response: ValidationRequest,
    ) -> None:
        """Test validation flow where PII blocks but sentiment/escalation still run."""
        # Note: With stop_on_critical_failure=True, sentiment may not run after PII block
        response = validation_service_full.validate(request_with_pii_response)

        assert response.is_valid is False
        assert response.action == ValidationAction.BLOCK

    def test_validation_metadata_tracks_comprehend_calls(
        self,
        validation_service_full: ResponseValidatorService,
        sample_request: ValidationRequest,
    ) -> None:
        """Test that comprehend_calls metadata is tracked."""
        response = validation_service_full.validate(sample_request)

        # Should have at least 1 call for sentiment (PII uses regex only in test)
        assert response.metadata.comprehend_calls >= 1

    def test_validation_response_properties(
        self,
        pii_detector: PIIDetector,
        mock_comprehend_sentiment_negative: MagicMock,
    ) -> None:
        """Test ValidationResponse convenience properties."""
        sentiment_analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_negative)
        escalation_config = EscalationScorerConfig(threshold=0.20)
        escalation_scorer = EscalationScorer(config=escalation_config)

        config = ValidationServiceConfig(
            enable_pii_detection=True,
            enable_sentiment_analysis=True,
            enable_escalation_scoring=True,
        )
        service = ResponseValidatorService(
            config=config,
            pii_detector=pii_detector,
            sentiment_analyzer=sentiment_analyzer,
            escalation_scorer=escalation_scorer,
        )

        request = ValidationRequest(
            response_text="I apologize for the frustration you're experiencing.",
            user_message="This is terrible! Let me speak to a manager!",
            conversation_id="conv-123",
            tenant_id="test-tenant",
            urgency="high",
        )

        response = service.validate(request)

        # Test convenience properties
        assert response.needs_escalation is True
        assert response.was_modified is False  # Response wasn't changed
        assert response.has_warnings is False  # Action is PASS, not WARN


class TestValidationServiceMetrics:
    """Tests for metrics emission with sentiment and escalation."""

    def test_metrics_emitted_for_sentiment(
        self,
        validation_service_full: ResponseValidatorService,
        sample_request: ValidationRequest,
    ) -> None:
        """Test that sentiment metrics are emitted."""
        with patch("service.metrics") as mock_metrics:
            validation_service_full.validate(sample_request)

            # Check that sentiment-related metrics were added
            metric_names = [
                call[1]["name"]
                for call in mock_metrics.add_metric.call_args_list
                if "name" in call[1]
            ]

            assert "SentimentAnalysisRequests" in metric_names

    def test_metrics_emitted_for_escalation(
        self,
        pii_detector: PIIDetector,
        mock_comprehend_sentiment_negative: MagicMock,
    ) -> None:
        """Test that escalation metrics are emitted when triggered."""
        sentiment_analyzer = SentimentAnalyzer(comprehend_client=mock_comprehend_sentiment_negative)
        escalation_config = EscalationScorerConfig(threshold=0.20)
        escalation_scorer = EscalationScorer(config=escalation_config)

        config = ValidationServiceConfig(
            enable_pii_detection=True,
            enable_sentiment_analysis=True,
            enable_escalation_scoring=True,
        )
        service = ResponseValidatorService(
            config=config,
            pii_detector=pii_detector,
            sentiment_analyzer=sentiment_analyzer,
            escalation_scorer=escalation_scorer,
        )

        request = ValidationRequest(
            response_text="I understand your concern.",
            user_message="I want to speak to a human!",
            conversation_id="conv-123",
            tenant_id="test-tenant",
            urgency="high",
        )

        with patch("service.metrics") as mock_metrics:
            service.validate(request)

            metric_names = [
                call[1]["name"]
                for call in mock_metrics.add_metric.call_args_list
                if "name" in call[1]
            ]

            assert "EscalationTriggered" in metric_names


class TestValidationServiceConvenienceFunctions:
    """Tests for service convenience functions with sentiment/escalation."""

    def test_create_strict_service_low_escalation_threshold(self) -> None:
        """Test create_strict_service has lower escalation threshold."""
        from service import create_strict_service

        service = create_strict_service()

        assert service.config.escalation_threshold == 0.50

    def test_create_permissive_service_high_escalation_threshold(self) -> None:
        """Test create_permissive_service has higher escalation threshold."""
        from service import create_permissive_service

        service = create_permissive_service()

        assert service.config.escalation_threshold == 0.85
