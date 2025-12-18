"""Business rules engine for response validation.

This module provides a configurable rules engine that evaluates AI-generated
responses against business policies and content guidelines.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aws_lambda_powertools import Logger

from models import (
    BusinessRulesResult,
    BusinessRuleViolation,
    LengthCheckResult,
    ProfanityCheckResult,
    RuleSeverity,
    ValidationAction,
)

if TYPE_CHECKING:
    from models import ValidationRequest

logger = Logger(child=True)


# =============================================================================
# Rule Configuration
# =============================================================================


@dataclass(frozen=True)
class RuleConfig:
    """Configuration for a business rule."""

    enabled: bool = True
    severity: RuleSeverity = RuleSeverity.MEDIUM
    action: ValidationAction = ValidationAction.WARN


@dataclass(frozen=True)
class LengthRuleConfig(RuleConfig):
    """Configuration for response length rule."""

    min_length: int = 20
    max_length: int = 2000
    truncate_if_exceeded: bool = True


@dataclass(frozen=True)
class ProfanityRuleConfig(RuleConfig):
    """Configuration for profanity detection rule."""

    severity: RuleSeverity = RuleSeverity.CRITICAL
    action: ValidationAction = ValidationAction.BLOCK
    custom_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class TopicRestrictionConfig(RuleConfig):
    """Configuration for topic restriction rule."""

    restricted_topics: tuple[str, ...] = (
        "medical_advice",
        "legal_advice",
        "financial_advice",
    )
    add_disclaimer: bool = True


# =============================================================================
# Rule Results
# =============================================================================


@dataclass
class RuleResult:
    """Result of evaluating a single rule."""

    rule_id: str
    rule_name: str
    passed: bool
    severity: RuleSeverity
    action: ValidationAction
    message: str | None = None
    modified_response: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_violation(self) -> BusinessRuleViolation | None:
        """Convert to BusinessRuleViolation if rule failed."""
        if self.passed:
            return None
        return BusinessRuleViolation(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            description=self.message or f"Rule '{self.rule_name}' violated",
            severity=self.severity,
            action_taken=self.action,
            metadata=self.metadata,
        )


# =============================================================================
# Abstract Base Rule
# =============================================================================


class BusinessRule(ABC):
    """Abstract base class for business rules."""

    def __init__(self, config: RuleConfig | None = None) -> None:
        """Initialize rule with configuration."""
        self.config = config or RuleConfig()

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique identifier for the rule."""
        ...

    @property
    @abstractmethod
    def rule_name(self) -> str:
        """Human-readable name for the rule."""
        ...

    @property
    def priority(self) -> int:
        """Rule priority (lower = higher priority). Default: 100."""
        return 100

    @property
    def is_enabled(self) -> bool:
        """Check if rule is enabled."""
        return self.config.enabled

    @abstractmethod
    def evaluate(self, response_text: str, request: ValidationRequest) -> RuleResult:
        """Evaluate the rule against a response.

        Args:
            response_text: The AI-generated response to validate.
            request: The full validation request with context.

        Returns:
            RuleResult indicating pass/fail and any modifications.
        """
        ...


# =============================================================================
# Concrete Rules
# =============================================================================


class ResponseLengthRule(BusinessRule):
    """Validates response length is within acceptable bounds."""

    def __init__(self, config: LengthRuleConfig | None = None) -> None:
        """Initialize with length configuration."""
        self.config: LengthRuleConfig = config or LengthRuleConfig()

    @property
    def rule_id(self) -> str:
        return "LENGTH_001"

    @property
    def rule_name(self) -> str:
        return "Response Length Validation"

    @property
    def priority(self) -> int:
        return 10  # Run early

    def evaluate(self, response_text: str, request: ValidationRequest) -> RuleResult:
        """Check response length and optionally truncate."""
        char_count = len(response_text)
        min_len = self.config.min_length
        max_len = self.config.max_length

        # Too short
        if char_count < min_len:
            logger.warning(
                "Response too short",
                extra={
                    "char_count": char_count,
                    "min_length": min_len,
                    "conversation_id": request.conversation_id,
                },
            )
            return RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                passed=False,
                severity=RuleSeverity.HIGH,
                action=ValidationAction.BLOCK,
                message=f"Response too short ({char_count} chars, minimum {min_len})",
                metadata={"char_count": char_count, "min_length": min_len},
            )

        # Too long
        if char_count > max_len:
            if self.config.truncate_if_exceeded:
                # Truncate at last sentence boundary before max_length
                truncated = self._smart_truncate(response_text, max_len)
                logger.info(
                    "Response truncated",
                    extra={
                        "original_length": char_count,
                        "truncated_length": len(truncated),
                        "max_length": max_len,
                    },
                )
                return RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    passed=True,  # Pass because we fixed it
                    severity=RuleSeverity.LOW,
                    action=ValidationAction.MODIFY,
                    message=f"Response truncated from {char_count} to {len(truncated)} chars",
                    modified_response=truncated,
                    metadata={
                        "original_length": char_count,
                        "truncated_length": len(truncated),
                        "was_truncated": True,
                    },
                )
            else:
                return RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    passed=False,
                    severity=self.config.severity,
                    action=self.config.action,
                    message=f"Response too long ({char_count} chars, maximum {max_len})",
                    metadata={"char_count": char_count, "max_length": max_len},
                )

        # Within bounds
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=True,
            severity=RuleSeverity.LOW,
            action=ValidationAction.PASS,
            metadata={"char_count": char_count},
        )

    def _smart_truncate(self, text: str, max_length: int) -> str:
        """Truncate text at the last sentence boundary before max_length."""
        if len(text) <= max_length:
            return text

        # Find the last sentence-ending punctuation before max_length
        truncated = text[:max_length]
        sentence_endings = [". ", "! ", "? ", ".\n", "!\n", "?\n"]

        last_boundary = -1
        for ending in sentence_endings:
            pos = truncated.rfind(ending)
            if pos > last_boundary:
                last_boundary = pos + 1  # Include the punctuation

        if last_boundary > max_length // 2:
            return text[:last_boundary].strip()

        # Fallback: truncate at last space and add ellipsis
        last_space = truncated.rfind(" ")
        if last_space > max_length // 2:
            return text[:last_space].strip() + "..."

        return truncated.strip() + "..."

    def to_length_result(self, response_text: str, result: RuleResult) -> LengthCheckResult:
        """Convert RuleResult to LengthCheckResult model."""
        return LengthCheckResult(
            passed=result.passed,
            char_count=result.metadata.get("char_count", len(response_text)),
            min_length=self.config.min_length,
            max_length=self.config.max_length,
            was_truncated=result.metadata.get("was_truncated", False),
        )


class ProfanityRule(BusinessRule):
    """Detects and blocks profane or inappropriate content."""

    # Common profanity patterns (masked for code review)
    # In production, load from configuration or external service
    DEFAULT_PATTERNS: tuple[str, ...] = (
        r"\bf+u+c+k+\w*\b",
        r"\bs+h+i+t+\w*\b",
        r"\ba+s+s+h+o+l+e+\w*\b",
        r"\bb+i+t+c+h+\w*\b",
        r"\bd+a+m+n+\w*\b",
        r"\bc+r+a+p+\w*\b",
    )

    def __init__(self, config: ProfanityRuleConfig | None = None) -> None:
        """Initialize with profanity configuration."""
        self.config: ProfanityRuleConfig = config or ProfanityRuleConfig()
        self._patterns = self._compile_patterns()

    @property
    def rule_id(self) -> str:
        return "PROFANITY_001"

    @property
    def rule_name(self) -> str:
        return "Profanity Detection"

    @property
    def priority(self) -> int:
        return 5  # Run very early - critical check

    def _compile_patterns(self) -> list[re.Pattern]:
        """Compile regex patterns for efficient matching."""
        all_patterns = self.DEFAULT_PATTERNS + self.config.custom_terms
        return [re.compile(p, re.IGNORECASE) for p in all_patterns]

    def evaluate(self, response_text: str, request: ValidationRequest) -> RuleResult:
        """Check response for profane content."""
        detected_terms: list[str] = []

        for pattern in self._patterns:
            matches = pattern.findall(response_text)
            for match in matches:
                # Mask the term for logging (keep first and last char)
                masked = self._mask_term(match)
                detected_terms.append(masked)

        if detected_terms:
            logger.warning(
                "Profanity detected in response",
                extra={
                    "detected_count": len(detected_terms),
                    "conversation_id": request.conversation_id,
                    "tenant_id": request.tenant_id,
                },
            )
            return RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                passed=False,
                severity=self.config.severity,
                action=self.config.action,
                message=f"Profanity detected: {len(detected_terms)} term(s)",
                metadata={"detected_terms": detected_terms, "count": len(detected_terms)},
            )

        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=True,
            severity=RuleSeverity.LOW,
            action=ValidationAction.PASS,
        )

    def _mask_term(self, term: str) -> str:
        """Mask a profane term for safe logging."""
        if len(term) <= 2:
            return "*" * len(term)
        return term[0] + "*" * (len(term) - 2) + term[-1]

    def to_profanity_result(self, result: RuleResult) -> ProfanityCheckResult:
        """Convert RuleResult to ProfanityCheckResult model."""
        return ProfanityCheckResult(
            passed=result.passed,
            detected_terms=result.metadata.get("detected_terms", []),
            severity=self.config.severity if not result.passed else None,
        )


class TopicRestrictionRule(BusinessRule):
    """Detects and handles restricted topics like medical/legal advice."""

    # Topic detection patterns
    TOPIC_PATTERNS: dict[str, list[str]] = {
        "medical_advice": [
            r"\b(diagnos|symptom|treatment|medication|prescription|dosage)\w*\b",
            r"\b(you (should|must|need to) (take|stop taking|see a doctor))\b",
            r"\b(medical (advice|recommendation|diagnosis))\b",
        ],
        "legal_advice": [
            r"\b(legal (advice|recommendation|opinion))\b",
            r"\b(you (should|must|need to) (sue|file|consult a lawyer))\b",
            r"\b(liability|lawsuit|attorney|legal action)\b",
        ],
        "financial_advice": [
            r"\b(you (should|must|need to) (invest|buy|sell))\b",
            r"\b(financial (advice|recommendation))\b",
            r"\b(guaranteed (return|profit|income))\b",
        ],
    }

    DISCLAIMERS: dict[str, str] = {
        "medical_advice": (
            "\n\n*Disclaimer: This information is for general purposes only and "
            "should not be considered medical advice. Please consult a qualified "
            "healthcare professional for medical concerns.*"
        ),
        "legal_advice": (
            "\n\n*Disclaimer: This information is for general purposes only and "
            "should not be considered legal advice. Please consult a qualified "
            "attorney for legal matters.*"
        ),
        "financial_advice": (
            "\n\n*Disclaimer: This information is for general purposes only and "
            "should not be considered financial advice. Please consult a qualified "
            "financial advisor for investment decisions.*"
        ),
    }

    def __init__(self, config: TopicRestrictionConfig | None = None) -> None:
        """Initialize with topic restriction configuration."""
        self.config: TopicRestrictionConfig = config or TopicRestrictionConfig()
        self._compiled_patterns = self._compile_patterns()

    @property
    def rule_id(self) -> str:
        return "TOPIC_001"

    @property
    def rule_name(self) -> str:
        return "Topic Restriction"

    @property
    def priority(self) -> int:
        return 20  # Run after profanity, before general rules

    def _compile_patterns(self) -> dict[str, list[re.Pattern]]:
        """Compile regex patterns for each topic."""
        compiled: dict[str, list[re.Pattern]] = {}
        for topic, patterns in self.TOPIC_PATTERNS.items():
            if topic in self.config.restricted_topics:
                compiled[topic] = [re.compile(p, re.IGNORECASE) for p in patterns]
        return compiled

    def evaluate(self, response_text: str, request: ValidationRequest) -> RuleResult:
        """Check response for restricted topic content."""
        detected_topics: list[str] = []
        topic_matches: dict[str, int] = {}

        for topic, patterns in self._compiled_patterns.items():
            match_count = 0
            for pattern in patterns:
                matches = pattern.findall(response_text)
                match_count += len(matches)

            if match_count >= 2:  # Threshold: 2+ matches indicates topic presence
                detected_topics.append(topic)
                topic_matches[topic] = match_count

        if detected_topics:
            logger.info(
                "Restricted topic detected",
                extra={
                    "topics": detected_topics,
                    "matches": topic_matches,
                    "conversation_id": request.conversation_id,
                },
            )

            # Add disclaimers if configured
            modified_response = response_text
            if self.config.add_disclaimer:
                for topic in detected_topics:
                    if topic in self.DISCLAIMERS:
                        # Only add disclaimer if not already present
                        disclaimer = self.DISCLAIMERS[topic]
                        if disclaimer not in modified_response:
                            modified_response += disclaimer

            return RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                passed=True,  # Pass with modification
                severity=RuleSeverity.MEDIUM,
                action=(
                    ValidationAction.MODIFY if self.config.add_disclaimer else ValidationAction.WARN
                ),
                message=f"Restricted topic(s) detected: {', '.join(detected_topics)}",
                modified_response=modified_response if modified_response != response_text else None,
                metadata={
                    "detected_topics": detected_topics,
                    "topic_matches": topic_matches,
                    "disclaimer_added": modified_response != response_text,
                },
            )

        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=True,
            severity=RuleSeverity.LOW,
            action=ValidationAction.PASS,
        )


# =============================================================================
# Rules Engine
# =============================================================================


class RulesEngine:
    """Orchestrates evaluation of business rules against responses."""

    def __init__(self, rules: list[BusinessRule] | None = None) -> None:
        """Initialize with a list of rules.

        Args:
            rules: List of business rules to evaluate. If None, uses default rules.
        """
        self._rules = rules if rules is not None else self._default_rules()
        # Sort by priority (lower = higher priority)
        self._rules.sort(key=lambda r: r.priority)

    @staticmethod
    def _default_rules() -> list[BusinessRule]:
        """Create default rule set."""
        return [
            ProfanityRule(),
            ResponseLengthRule(),
            TopicRestrictionRule(),
        ]

    @property
    def rules(self) -> list[BusinessRule]:
        """Get the list of configured rules."""
        return self._rules

    @property
    def enabled_rules(self) -> list[BusinessRule]:
        """Get only enabled rules."""
        return [r for r in self._rules if r.is_enabled]

    def add_rule(self, rule: BusinessRule) -> None:
        """Add a rule and re-sort by priority."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID. Returns True if found and removed."""
        for i, rule in enumerate(self._rules):
            if rule.rule_id == rule_id:
                self._rules.pop(i)
                return True
        return False

    def evaluate(
        self,
        response_text: str,
        request: ValidationRequest,
        stop_on_block: bool = True,
    ) -> tuple[str, list[RuleResult]]:
        """Evaluate all enabled rules against a response.

        Args:
            response_text: The AI response to validate.
            request: The full validation request with context.
            stop_on_block: If True, stop evaluation after first blocking rule.

        Returns:
            Tuple of (final_response_text, list_of_results).
            final_response_text may be modified by rules.
        """
        results: list[RuleResult] = []
        current_response = response_text

        for rule in self.enabled_rules:
            logger.debug(
                "Evaluating rule",
                extra={"rule_id": rule.rule_id, "rule_name": rule.rule_name},
            )

            result = rule.evaluate(current_response, request)
            results.append(result)

            # Apply modifications if rule passed but modified response
            if result.passed and result.modified_response:
                current_response = result.modified_response

            # Stop on blocking failure if configured
            if not result.passed and result.action == ValidationAction.BLOCK and stop_on_block:
                logger.warning(
                    "Rule blocked response, stopping evaluation",
                    extra={
                        "rule_id": rule.rule_id,
                        "severity": result.severity.value,
                        "message": result.message,
                    },
                )
                break

        return current_response, results

    def to_business_rules_result(
        self,
        results: list[RuleResult],
        disclaimer_added: bool = False,
    ) -> BusinessRulesResult:
        """Convert list of RuleResults to BusinessRulesResult model."""
        violations: list[BusinessRuleViolation] = []
        for r in results:
            if not r.passed:
                violation = r.to_violation()
                if violation is not None:
                    violations.append(violation)

        all_passed = all(r.passed for r in results)

        return BusinessRulesResult(
            passed=all_passed,
            violations=violations,
            rules_evaluated=len(results),
            disclaimer_added=disclaimer_added,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def create_default_engine() -> RulesEngine:
    """Create a rules engine with default configuration."""
    return RulesEngine()


def create_strict_engine() -> RulesEngine:
    """Create a rules engine with strict configuration."""
    return RulesEngine(
        rules=[
            ProfanityRule(
                ProfanityRuleConfig(severity=RuleSeverity.CRITICAL, action=ValidationAction.BLOCK)
            ),
            ResponseLengthRule(
                LengthRuleConfig(min_length=50, max_length=1500, truncate_if_exceeded=False)
            ),
            TopicRestrictionRule(
                TopicRestrictionConfig(
                    restricted_topics=("medical_advice", "legal_advice", "financial_advice"),
                    add_disclaimer=True,
                )
            ),
        ]
    )
