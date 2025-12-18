"""Validation service layer for response validation.

This module provides the main service that orchestrates PII detection,
business rules validation, and generates fallback responses when needed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit

from models import (
    BusinessRulesResult,
    LengthCheckResult,
    PIICheckResult,
    ProfanityCheckResult,
    ValidationAction,
    ValidationRequest,
    ValidationResponse,
    ValidationResults,
)
from pii_detector import PIIDetector, PIIDetectorConfig
from rules import (
    BusinessRule,
    ProfanityRule,
    ResponseLengthRule,
    RulesEngine,
    TopicRestrictionRule,
)

if TYPE_CHECKING:
    from rules import RuleResult

logger = Logger(child=True)
tracer = Tracer()
metrics = Metrics()


# =============================================================================
# Fallback Responses
# =============================================================================


@dataclass(frozen=True)
class FallbackResponses:
    """Pre-defined fallback responses for different failure scenarios."""

    default: str = (
        "I apologize, but I'm unable to provide a response to that at the moment. "
        "Please let me know if you have another question, or I can connect you "
        "with a support agent."
    )

    pii_blocked: str = (
        "I apologize, but I cannot include certain sensitive information in my "
        "response for security reasons. Please contact our support team directly "
        "for assistance with account-specific details."
    )

    profanity_blocked: str = (
        "I apologize, but I'm unable to provide that response. "
        "Let me know how else I can help you today."
    )

    content_blocked: str = (
        "I'm not able to respond to that particular request. "
        "Is there something else I can assist you with?"
    )

    too_short: str = (
        "I apologize, but I wasn't able to generate a complete response. "
        "Could you please rephrase your question or provide more details?"
    )


FALLBACK = FallbackResponses()


# =============================================================================
# Service Configuration
# =============================================================================


@dataclass
class ValidationServiceConfig:
    """Configuration for the validation service."""

    # Feature flags
    enable_pii_detection: bool = True
    enable_profanity_check: bool = True
    enable_business_rules: bool = True
    enable_length_check: bool = True

    # PII settings
    pii_config: PIIDetectorConfig | None = None
    redact_pii_in_response: bool = True

    # Length settings
    min_response_length: int = 20
    max_response_length: int = 2000
    truncate_long_responses: bool = True

    # Behavior settings
    stop_on_critical_failure: bool = True
    use_fallback_on_block: bool = True


# =============================================================================
# Validation Service
# =============================================================================


class ResponseValidatorService:
    """Main service for validating AI-generated responses."""

    def __init__(
        self,
        config: ValidationServiceConfig | None = None,
        pii_detector: PIIDetector | None = None,
        rules_engine: RulesEngine | None = None,
    ) -> None:
        """Initialize the validation service.

        Args:
            config: Service configuration. Uses defaults if not provided.
            pii_detector: PII detector instance. Created if not provided.
            rules_engine: Rules engine instance. Created if not provided.
        """
        self.config = config or ValidationServiceConfig()
        self._pii_detector = pii_detector
        self._rules_engine = rules_engine

    @property
    def pii_detector(self) -> PIIDetector:
        """Lazy-load PII detector."""
        if self._pii_detector is None:
            self._pii_detector = PIIDetector(config=self.config.pii_config)
        return self._pii_detector

    @property
    def rules_engine(self) -> RulesEngine:
        """Lazy-load rules engine with configured rules."""
        if self._rules_engine is None:
            rules: list[BusinessRule] = []

            if self.config.enable_profanity_check:
                rules.append(ProfanityRule())

            if self.config.enable_length_check:
                from rules import LengthRuleConfig

                length_config = LengthRuleConfig(
                    min_length=self.config.min_response_length,
                    max_length=self.config.max_response_length,
                    truncate_if_exceeded=self.config.truncate_long_responses,
                )
                rules.append(ResponseLengthRule(config=length_config))

            if self.config.enable_business_rules:
                rules.append(TopicRestrictionRule())

            self._rules_engine = RulesEngine(rules=rules)

        return self._rules_engine

    @tracer.capture_method
    def validate(self, request: ValidationRequest) -> ValidationResponse:
        """Validate an AI-generated response.

        Args:
            request: The validation request containing response and context.

        Returns:
            ValidationResponse with validation results and possibly modified response.
        """
        start_time = time.perf_counter()
        comprehend_calls = 0

        logger.info(
            "Starting response validation",
            extra={
                "conversation_id": request.conversation_id,
                "tenant_id": request.tenant_id,
                "response_length": len(request.response_text),
                "options": request.options.model_dump(),
            },
        )

        # Track the current response text (may be modified)
        current_response = request.response_text
        original_response = request.response_text

        # Initialize results
        pii_result: PIICheckResult | None = None
        profanity_result: ProfanityCheckResult | None = None
        length_result: LengthCheckResult | None = None
        business_rules_result: BusinessRulesResult | None = None

        # Track overall status
        is_valid = True
        action = ValidationAction.PASS
        fallback_used = False
        fallback_reason: str | None = None
        rules_evaluated = 0

        # =================================================================
        # Step 1: PII Detection
        # =================================================================
        if request.options.check_pii and self.config.enable_pii_detection:
            pii_result = self._check_pii(current_response)
            comprehend_calls += 1

            if not pii_result.passed:
                logger.warning(
                    "PII check failed - blocking response",
                    extra={
                        "blocked_types": [t.value for t in pii_result.blocked_types],
                        "conversation_id": request.conversation_id,
                    },
                )
                is_valid = False
                action = ValidationAction.BLOCK
                fallback_reason = "pii_blocked"

                if self.config.use_fallback_on_block:
                    current_response = FALLBACK.pii_blocked
                    fallback_used = True

                # If stopping on critical failure, return early
                if self.config.stop_on_critical_failure:
                    return self._build_response(
                        original_response=original_response,
                        validated_response=current_response,
                        is_valid=is_valid,
                        action=action,
                        pii_result=pii_result,
                        profanity_result=profanity_result,
                        length_result=length_result,
                        business_rules_result=business_rules_result,
                        start_time=start_time,
                        rules_evaluated=rules_evaluated,
                        fallback_used=fallback_used,
                        fallback_reason=fallback_reason,
                        comprehend_calls=comprehend_calls,
                    )

            elif pii_result.redacted_count > 0 and self.config.redact_pii_in_response:
                # Redact PII from response
                current_response = self.pii_detector.redact(current_response, pii_result.detections)
                if action == ValidationAction.PASS:
                    action = ValidationAction.MODIFY

                logger.info(
                    "PII redacted from response",
                    extra={
                        "redacted_count": pii_result.redacted_count,
                        "conversation_id": request.conversation_id,
                    },
                )

        # =================================================================
        # Step 2: Business Rules (includes profanity and length)
        # =================================================================
        if request.options.check_business_rules or request.options.check_profanity:
            current_response, rule_results = self.rules_engine.evaluate(
                current_response,
                request,
                stop_on_block=self.config.stop_on_critical_failure,
            )
            rules_evaluated = len(rule_results)

            # Extract specific results
            profanity_result, length_result, business_rules_result = self._extract_rule_results(
                rule_results
            )

            # Check for blocking failures
            blocking_result = self._find_blocking_result(rule_results)
            if blocking_result is not None:
                is_valid = False
                action = ValidationAction.BLOCK

                fallback_reason = self._determine_fallback_reason(blocking_result)
                if self.config.use_fallback_on_block:
                    current_response = self._get_fallback_response(fallback_reason)
                    fallback_used = True

                logger.warning(
                    "Business rule blocked response",
                    extra={
                        "rule_id": blocking_result.rule_id,
                        "rule_name": blocking_result.rule_name,
                        "conversation_id": request.conversation_id,
                    },
                )

            # Check for modifications
            elif current_response != original_response and action == ValidationAction.PASS:
                action = ValidationAction.MODIFY

        # =================================================================
        # Step 3: Build and return response
        # =================================================================
        validation_response = self._build_response(
            original_response=original_response,
            validated_response=current_response,
            is_valid=is_valid,
            action=action,
            pii_result=pii_result,
            profanity_result=profanity_result,
            length_result=length_result,
            business_rules_result=business_rules_result,
            start_time=start_time,
            rules_evaluated=rules_evaluated,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            comprehend_calls=comprehend_calls,
        )

        # Emit metrics
        self._emit_metrics(validation_response, request)

        logger.info(
            "Response validation complete",
            extra={
                "is_valid": validation_response.is_valid,
                "action": validation_response.action.value,
                "validation_time_ms": validation_response.metadata.validation_time_ms,
                "fallback_used": fallback_used,
                "conversation_id": request.conversation_id,
            },
        )

        return validation_response

    @tracer.capture_method
    def _check_pii(self, text: str) -> PIICheckResult:
        """Run PII detection on text."""
        return self.pii_detector.detect(text)

    def _extract_rule_results(
        self,
        rule_results: list[RuleResult],
    ) -> tuple[ProfanityCheckResult | None, LengthCheckResult | None, BusinessRulesResult | None]:
        """Extract typed results from generic rule results."""
        profanity_result: ProfanityCheckResult | None = None
        length_result: LengthCheckResult | None = None

        for result in rule_results:
            if result.rule_id == "PROFANITY_001":
                profanity_rule = self._get_rule_by_id("PROFANITY_001")
                if profanity_rule and isinstance(profanity_rule, ProfanityRule):
                    profanity_result = profanity_rule.to_profanity_result(result)

            elif result.rule_id == "LENGTH_001":
                length_rule = self._get_rule_by_id("LENGTH_001")
                if length_rule and isinstance(length_rule, ResponseLengthRule):
                    length_result = length_rule.to_length_result("", result)

        # Build business rules result from all results
        business_rules_result = self.rules_engine.to_business_rules_result(
            rule_results,
            disclaimer_added=any(r.metadata.get("disclaimer_added", False) for r in rule_results),
        )

        return profanity_result, length_result, business_rules_result

    def _get_rule_by_id(self, rule_id: str) -> object | None:
        """Get a rule instance by ID."""
        for rule in self.rules_engine.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def _find_blocking_result(self, rule_results: list[RuleResult]) -> RuleResult | None:
        """Find the first rule result that blocked the response."""
        for result in rule_results:
            if not result.passed and result.action == ValidationAction.BLOCK:
                return result
        return None

    def _determine_fallback_reason(self, result: RuleResult) -> str:
        """Determine the fallback reason based on rule result."""
        if result.rule_id == "PROFANITY_001":
            return "profanity_blocked"
        elif result.rule_id == "LENGTH_001":
            if "too short" in (result.message or "").lower():
                return "too_short"
            return "content_blocked"
        return "content_blocked"

    def _get_fallback_response(self, reason: str) -> str:
        """Get the appropriate fallback response for a reason."""
        fallback_map = {
            "pii_blocked": FALLBACK.pii_blocked,
            "profanity_blocked": FALLBACK.profanity_blocked,
            "too_short": FALLBACK.too_short,
            "content_blocked": FALLBACK.content_blocked,
        }
        return fallback_map.get(reason, FALLBACK.default)

    def _build_response(
        self,
        original_response: str,
        validated_response: str,
        is_valid: bool,
        action: ValidationAction,
        pii_result: PIICheckResult | None,
        profanity_result: ProfanityCheckResult | None,
        length_result: LengthCheckResult | None,
        business_rules_result: BusinessRulesResult | None,
        start_time: float,
        rules_evaluated: int,
        fallback_used: bool,
        fallback_reason: str | None,
        comprehend_calls: int,
    ) -> ValidationResponse:
        """Build the validation response object."""
        validation_time_ms = (time.perf_counter() - start_time) * 1000

        validation_results = ValidationResults(
            pii=pii_result,
            profanity=profanity_result,
            length=length_result,
            business_rules=business_rules_result,
        )

        return ValidationResponse.create(
            original_response=original_response,
            validated_response=validated_response,
            is_valid=is_valid,
            action=action,
            validation_results=validation_results,
            validation_time_ms=validation_time_ms,
            rules_evaluated=rules_evaluated,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            comprehend_calls=comprehend_calls,
        )

    def _emit_metrics(
        self,
        response: ValidationResponse,
        request: ValidationRequest,
    ) -> None:
        """Emit CloudWatch metrics for validation."""
        # Validation outcome
        metrics.add_metric(
            name="ValidationRequests",
            unit=MetricUnit.Count,
            value=1,
        )

        if response.is_valid:
            metrics.add_metric(
                name="ValidationPassed",
                unit=MetricUnit.Count,
                value=1,
            )
        else:
            metrics.add_metric(
                name="ValidationFailed",
                unit=MetricUnit.Count,
                value=1,
            )

        # Action taken
        metrics.add_metric(
            name=f"ValidationAction_{response.action.value}",
            unit=MetricUnit.Count,
            value=1,
        )

        # Latency
        metrics.add_metric(
            name="ValidationLatency",
            unit=MetricUnit.Milliseconds,
            value=response.metadata.validation_time_ms,
        )

        # PII detections
        if response.validation_results.pii:
            pii_count = len(response.validation_results.pii.detections)
            if pii_count > 0:
                metrics.add_metric(
                    name="PIIDetections",
                    unit=MetricUnit.Count,
                    value=pii_count,
                )

        # Fallback usage
        if response.metadata.fallback_used:
            metrics.add_metric(
                name="FallbackResponseUsed",
                unit=MetricUnit.Count,
                value=1,
            )

        # Add dimensions
        metrics.add_dimension(name="TenantId", value=request.tenant_id)


# =============================================================================
# Convenience Functions
# =============================================================================


def create_default_service() -> ResponseValidatorService:
    """Create a validation service with default configuration."""
    return ResponseValidatorService()


def create_strict_service() -> ResponseValidatorService:
    """Create a validation service with strict configuration."""
    from pii_detector import create_strict_detector

    config = ValidationServiceConfig(
        min_response_length=50,
        max_response_length=1500,
        truncate_long_responses=False,
        stop_on_critical_failure=True,
    )

    return ResponseValidatorService(
        config=config,
        pii_detector=create_strict_detector(),
    )


def create_permissive_service() -> ResponseValidatorService:
    """Create a validation service with permissive configuration."""
    from pii_detector import create_permissive_detector

    config = ValidationServiceConfig(
        min_response_length=10,
        max_response_length=3000,
        truncate_long_responses=True,
        stop_on_critical_failure=False,
        use_fallback_on_block=False,
    )

    return ResponseValidatorService(
        config=config,
        pii_detector=create_permissive_detector(),
    )
