"""Unit tests for Response Validator business rules engine."""

from __future__ import annotations

from models import RuleSeverity, ValidationAction, ValidationRequest
from rules import (
    LengthRuleConfig,
    ProfanityRule,
    ProfanityRuleConfig,
    ResponseLengthRule,
    RulesEngine,
    TopicRestrictionConfig,
    TopicRestrictionRule,
    create_default_engine,
    create_strict_engine,
)


class TestResponseLengthRule:
    """Tests for ResponseLengthRule."""

    def test_valid_length(self, sample_request: ValidationRequest) -> None:
        """Test response within valid length bounds."""
        rule = ResponseLengthRule()
        result = rule.evaluate("This is a valid response with enough characters.", sample_request)

        assert result.passed is True
        assert result.action == ValidationAction.PASS
        assert "char_count" in result.metadata

    def test_too_short(self, sample_request: ValidationRequest) -> None:
        """Test response that is too short."""
        rule = ResponseLengthRule()
        result = rule.evaluate("Short", sample_request)

        assert result.passed is False
        assert result.action == ValidationAction.BLOCK
        assert result.message is not None
        assert "too short" in result.message.lower()

    def test_too_long_truncated(self, sample_request: ValidationRequest) -> None:
        """Test response that is too long gets truncated."""
        config = LengthRuleConfig(max_length=100, truncate_if_exceeded=True)
        rule = ResponseLengthRule(config=config)

        long_text = "This is a sentence. " * 20  # ~400 chars
        result = rule.evaluate(long_text, sample_request)

        assert result.passed is True  # Passes because truncation fixes it
        assert result.action == ValidationAction.MODIFY
        assert result.modified_response is not None
        assert len(result.modified_response) <= 100
        assert result.metadata.get("was_truncated") is True

    def test_too_long_blocked(self, sample_request: ValidationRequest) -> None:
        """Test response that is too long gets blocked when truncation disabled."""
        config = LengthRuleConfig(max_length=100, truncate_if_exceeded=False)
        rule = ResponseLengthRule(config=config)

        long_text = "This is a sentence. " * 20
        result = rule.evaluate(long_text, sample_request)

        assert result.passed is False
        assert result.message is not None
        assert "too long" in result.message.lower()

    def test_smart_truncate_at_sentence(self, sample_request: ValidationRequest) -> None:
        """Test truncation happens at sentence boundary."""
        config = LengthRuleConfig(max_length=50, truncate_if_exceeded=True)
        rule = ResponseLengthRule(config=config)

        text = "First sentence here. Second sentence here. Third sentence is longer than expected."
        result = rule.evaluate(text, sample_request)

        # Truncation should happen
        assert result.modified_response is not None
        # Should end with punctuation or ellipsis
        assert result.modified_response.rstrip().endswith(
            "."
        ) or result.modified_response.rstrip().endswith("...")

    def test_rule_properties(self) -> None:
        """Test rule properties."""
        rule = ResponseLengthRule()

        assert rule.rule_id == "LENGTH_001"
        assert rule.rule_name == "Response Length Validation"
        assert rule.priority == 10
        assert rule.is_enabled is True

    def test_to_length_result(self, sample_request: ValidationRequest) -> None:
        """Test conversion to LengthCheckResult model."""
        rule = ResponseLengthRule()
        result = rule.evaluate("Valid response text here.", sample_request)
        length_result = rule.to_length_result("Valid response text here.", result)

        assert length_result.passed is True
        assert length_result.char_count == 25
        assert length_result.min_length == 20
        assert length_result.max_length == 2000


class TestProfanityRule:
    """Tests for ProfanityRule."""

    def test_clean_text(self, sample_request: ValidationRequest) -> None:
        """Test clean text passes."""
        rule = ProfanityRule()
        result = rule.evaluate("This is a clean and professional response.", sample_request)

        assert result.passed is True
        assert result.action == ValidationAction.PASS

    def test_profanity_detected(self, sample_request: ValidationRequest) -> None:
        """Test profanity is detected and blocked."""
        rule = ProfanityRule()
        result = rule.evaluate("This is a shit response.", sample_request)

        assert result.passed is False
        assert result.action == ValidationAction.BLOCK
        assert result.severity == RuleSeverity.CRITICAL
        assert len(result.metadata.get("detected_terms", [])) > 0

    def test_profanity_masked_in_logging(self, sample_request: ValidationRequest) -> None:
        """Test profanity terms are masked in results."""
        rule = ProfanityRule()
        result = rule.evaluate("What the fuck is this?", sample_request)

        # Terms should be masked (first and last char visible)
        detected = result.metadata.get("detected_terms", [])
        assert len(detected) > 0
        for term in detected:
            assert "*" in term  # Should contain masking

    def test_case_insensitive(self, sample_request: ValidationRequest) -> None:
        """Test detection is case insensitive."""
        rule = ProfanityRule()

        result_lower = rule.evaluate("this is shit", sample_request)
        result_upper = rule.evaluate("this is SHIT", sample_request)
        result_mixed = rule.evaluate("this is ShIt", sample_request)

        assert result_lower.passed is False
        assert result_upper.passed is False
        assert result_mixed.passed is False

    def test_custom_terms(self, sample_request: ValidationRequest) -> None:
        """Test custom profanity terms."""
        config = ProfanityRuleConfig(custom_terms=(r"\bbadword\b",))
        rule = ProfanityRule(config=config)

        result = rule.evaluate("This contains badword in it.", sample_request)

        assert result.passed is False

    def test_rule_properties(self) -> None:
        """Test rule properties."""
        rule = ProfanityRule()

        assert rule.rule_id == "PROFANITY_001"
        assert rule.rule_name == "Profanity Detection"
        assert rule.priority == 5  # High priority
        assert rule.is_enabled is True

    def test_to_profanity_result(self, sample_request: ValidationRequest) -> None:
        """Test conversion to ProfanityCheckResult model."""
        rule = ProfanityRule()

        # Clean text
        result_clean = rule.evaluate("Clean text.", sample_request)
        profanity_result = rule.to_profanity_result(result_clean)
        assert profanity_result.passed is True
        assert profanity_result.detected_terms == []

        # Profane text
        result_dirty = rule.evaluate("This is damn annoying.", sample_request)
        profanity_result_dirty = rule.to_profanity_result(result_dirty)
        assert profanity_result_dirty.passed is False


class TestTopicRestrictionRule:
    """Tests for TopicRestrictionRule."""

    def test_clean_topic(self, sample_request: ValidationRequest) -> None:
        """Test non-restricted topic passes."""
        rule = TopicRestrictionRule()
        result = rule.evaluate(
            "Here's how to reset your password. Go to settings and click reset.",
            sample_request,
        )

        assert result.passed is True

    def test_medical_advice_detected(self, request_with_medical_content: ValidationRequest) -> None:
        """Test medical advice is detected."""
        rule = TopicRestrictionRule()
        result = rule.evaluate(
            request_with_medical_content.response_text,
            request_with_medical_content,
        )

        assert result.passed is True  # Passes with disclaimer
        assert result.action == ValidationAction.MODIFY
        assert result.modified_response is not None
        assert "medical advice" in result.modified_response.lower()
        assert result.metadata.get("disclaimer_added") is True

    def test_legal_advice_detected(self, sample_request: ValidationRequest) -> None:
        """Test legal advice is detected."""
        rule = TopicRestrictionRule()
        legal_text = (
            "Based on the situation, you should sue the company. "
            "This is my legal advice to pursue legal action. "
            "You need to consult a lawyer about this liability."
        )
        result = rule.evaluate(legal_text, sample_request)

        assert result.passed is True
        assert result.modified_response is not None
        assert "legal advice" in result.modified_response.lower()

    def test_financial_advice_detected(self, sample_request: ValidationRequest) -> None:
        """Test financial advice is detected."""
        rule = TopicRestrictionRule()
        financial_text = (
            "You should invest in this stock immediately. "
            "This financial advice will give you guaranteed returns. "
            "You need to buy now before prices go up."
        )
        result = rule.evaluate(financial_text, sample_request)

        assert result.passed is True
        assert result.modified_response is not None
        assert "financial advice" in result.modified_response.lower()

    def test_disclaimer_content(self, sample_request: ValidationRequest) -> None:
        """Test that disclaimer is added correctly."""
        rule = TopicRestrictionRule()
        medical_text = (
            "Based on your symptoms, you should see a doctor. "
            "The recommended treatment is rest and fluids. "
            "You need to take medication as prescribed."
        )
        result = rule.evaluate(medical_text, sample_request)

        assert result.modified_response is not None
        assert "Disclaimer" in result.modified_response
        assert result.metadata.get("disclaimer_added") is True

    def test_rule_disabled(self, sample_request: ValidationRequest) -> None:
        """Test rule can be disabled via config."""
        config = TopicRestrictionConfig(enabled=False)
        rule = TopicRestrictionRule(config=config)

        assert rule.is_enabled is False


class TestRulesEngine:
    """Tests for RulesEngine."""

    def test_default_rules(self) -> None:
        """Test default rules are created."""
        engine = RulesEngine()

        assert len(engine.rules) == 3
        rule_ids = [r.rule_id for r in engine.rules]
        assert "PROFANITY_001" in rule_ids
        assert "LENGTH_001" in rule_ids
        assert "TOPIC_001" in rule_ids

    def test_rules_sorted_by_priority(self) -> None:
        """Test rules are sorted by priority."""
        engine = RulesEngine()

        priorities = [r.priority for r in engine.rules]
        assert priorities == sorted(priorities)

    def test_evaluate_all_pass(self, sample_request: ValidationRequest) -> None:
        """Test evaluation when all rules pass."""
        engine = RulesEngine()
        response_text = "This is a perfectly valid response with enough content."

        final_response, results = engine.evaluate(response_text, sample_request)

        assert final_response == response_text
        assert all(r.passed for r in results)

    def test_evaluate_with_modification(
        self, request_with_medical_content: ValidationRequest
    ) -> None:
        """Test evaluation with response modification."""
        engine = RulesEngine()

        final_response, results = engine.evaluate(
            request_with_medical_content.response_text,
            request_with_medical_content,
        )

        # Response should be modified with disclaimer
        assert final_response != request_with_medical_content.response_text
        assert "Disclaimer" in final_response

    def test_evaluate_with_profanity(self, sample_request: ValidationRequest) -> None:
        """Test evaluation blocks on profanity."""
        engine = RulesEngine()
        profane_text = "This is a shit response that fails."

        final_response, results = engine.evaluate(
            profane_text,
            sample_request,
            stop_on_block=True,
        )

        # Should have at least one blocking result
        blocking_results = [r for r in results if not r.passed]
        assert len(blocking_results) >= 1

    def test_evaluate_continue_on_block(self, sample_request: ValidationRequest) -> None:
        """Test evaluation continues when stop_on_block is False."""
        engine = RulesEngine()
        # Short and profane
        bad_text = "shit"

        final_response, results = engine.evaluate(
            bad_text,
            sample_request,
            stop_on_block=False,
        )

        # Should evaluate all rules
        assert len(results) == len(engine.enabled_rules)

    def test_add_rule(self) -> None:
        """Test adding a rule."""
        engine = RulesEngine(rules=[])
        assert len(engine.rules) == 0

        engine.add_rule(ProfanityRule())
        assert len(engine.rules) == 1

        engine.add_rule(ResponseLengthRule())
        assert len(engine.rules) == 2

        # Should be sorted by priority
        assert engine.rules[0].priority <= engine.rules[1].priority

    def test_remove_rule(self) -> None:
        """Test removing a rule."""
        engine = RulesEngine()
        initial_count = len(engine.rules)

        removed = engine.remove_rule("PROFANITY_001")
        assert removed is True
        assert len(engine.rules) == initial_count - 1

        # Try removing non-existent rule
        removed = engine.remove_rule("NONEXISTENT")
        assert removed is False

    def test_enabled_rules_filter(self) -> None:
        """Test enabled_rules property filters correctly."""
        config = ProfanityRuleConfig(enabled=False)
        disabled_rule = ProfanityRule(config=config)

        engine = RulesEngine(rules=[disabled_rule, ResponseLengthRule()])

        assert len(engine.rules) == 2
        assert len(engine.enabled_rules) == 1

    def test_to_business_rules_result(self, sample_request: ValidationRequest) -> None:
        """Test conversion to BusinessRulesResult."""
        engine = RulesEngine()
        response_text = "Valid response here."

        _, results = engine.evaluate(response_text, sample_request)
        business_result = engine.to_business_rules_result(results)

        assert business_result.passed is True
        assert business_result.violations == []
        assert business_result.rules_evaluated == len(results)


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_default_engine(self) -> None:
        """Test create_default_engine function."""
        engine = create_default_engine()

        assert engine is not None
        assert len(engine.rules) == 3

    def test_create_strict_engine(self) -> None:
        """Test create_strict_engine function."""
        engine = create_strict_engine()

        assert engine is not None
        # Strict engine should have same rules but different config
        assert len(engine.rules) == 3


class TestRuleResult:
    """Tests for RuleResult conversion."""

    def test_to_violation_passed(self, sample_request: ValidationRequest) -> None:
        """Test to_violation returns None for passed rules."""
        rule = ResponseLengthRule()
        result = rule.evaluate("Valid response text.", sample_request)

        violation = result.to_violation()
        assert violation is None

    def test_to_violation_failed(self, sample_request: ValidationRequest) -> None:
        """Test to_violation returns BusinessRuleViolation for failed rules."""
        rule = ResponseLengthRule()
        result = rule.evaluate("Short", sample_request)

        violation = result.to_violation()
        assert violation is not None
        assert violation.rule_id == "LENGTH_001"
        assert violation.severity == RuleSeverity.HIGH
        assert violation.action_taken == ValidationAction.BLOCK
