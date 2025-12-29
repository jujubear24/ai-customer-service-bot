#!/usr/bin/env python3
"""
E2E Tests for Response Validator - Sentiment Analysis & Escalation Scoring.

This script tests the sentiment analysis and escalation scoring features
of the Response Validator Lambda function against a deployed AWS environment.

Usage:
    python scripts/test_sentiment_escalation.py                    # Run all tests
    python scripts/test_sentiment_escalation.py --quick            # Quick smoke tests only
    python scripts/test_sentiment_escalation.py -v                 # Verbose output
    python scripts/test_sentiment_escalation.py --function-name X  # Specify Lambda name

Prerequisites:
    - AWS credentials configured
    - Response Validator Lambda deployed
    - boto3 installed
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any


# ANSI color codes
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


@dataclass
class TestResult:
    """Result of a single test case."""

    name: str
    passed: bool
    duration_ms: float
    message: str = ""
    details: dict[str, Any] | None = None


class SentimentEscalationE2ETests:
    """E2E test suite for sentiment analysis and escalation scoring."""

    def __init__(
        self,
        function_name: str | None = None,
        verbose: bool = False,
    ) -> None:
        self.verbose = verbose
        self.function_name = function_name or self._get_function_name()
        self.results: list[TestResult] = []

        try:
            import boto3

            self.lambda_client = boto3.client("lambda")
        except ImportError:
            print(
                f"{Colors.RED}Error: boto3 is required. Install with: pip install boto3{Colors.END}"
            )
            sys.exit(1)

    def _get_function_name(self) -> str:
        """Get Lambda function name from Terraform outputs."""
        try:
            result = subprocess.run(
                [
                    "terraform",
                    "output",
                    "-raw",
                    "response_validator_function_name",
                ],
                capture_output=True,
                text=True,
                cwd="terraform/environments/dev",
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except FileNotFoundError:
            pass

        # Fallback to common naming pattern
        return "ai-customer-service-bot-response-validator-dev"

    def _invoke_lambda(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke the Response Validator Lambda and return the response."""
        response = self.lambda_client.invoke(
            FunctionName=self.function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        # Read and parse the response payload
        raw_payload = response["Payload"].read()
        if isinstance(raw_payload, bytes):
            response_payload: dict[str, Any] = json.loads(raw_payload.decode("utf-8"))
        elif isinstance(raw_payload, str):
            response_payload = json.loads(raw_payload)
        elif isinstance(raw_payload, dict):
            response_payload = raw_payload
        else:
            raise TypeError(f"Unexpected payload type: {type(raw_payload)}")

        # Handle Lambda errors
        if "FunctionError" in response:
            raise RuntimeError(f"Lambda error: {response_payload}")

        # Handle API Gateway format if present
        if "body" in response_payload:
            body_content = response_payload["body"]
            if isinstance(body_content, str):
                body: dict[str, Any] = json.loads(body_content)
                return body
            elif isinstance(body_content, dict):
                return body_content
            else:
                raise TypeError(f"Unexpected body type: {type(body_content)}")

        return response_payload

    def _run_test(
        self,
        name: str,
        payload: dict[str, Any],
        assertions: list[tuple[str, Any]],
    ) -> TestResult:
        """Run a single test case."""
        start_time = time.time()

        try:
            response = self._invoke_lambda(payload)
            duration_ms = (time.time() - start_time) * 1000

            # Run assertions
            failures = []
            for path, expected in assertions:
                actual = self._get_nested_value(response, path)
                if not self._check_assertion(actual, expected):
                    failures.append(f"{path}: expected {expected}, got {actual}")

            if failures:
                return TestResult(
                    name=name,
                    passed=False,
                    duration_ms=duration_ms,
                    message="; ".join(failures),
                    details=response if self.verbose else None,
                )

            return TestResult(
                name=name,
                passed=True,
                duration_ms=duration_ms,
                details=response if self.verbose else None,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return TestResult(
                name=name,
                passed=False,
                duration_ms=duration_ms,
                message=str(e),
            )

    def _get_nested_value(self, obj: dict[str, Any], path: str) -> Any:
        """Get a nested value from a dict using dot notation."""
        keys = path.split(".")
        value = obj
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def _check_assertion(self, actual: Any, expected: Any) -> bool:
        """Check if actual matches expected (supports callables for complex checks)."""
        if callable(expected):
            return expected(actual)
        return actual == expected

    def run_all_tests(self) -> None:
        """Run all test cases."""
        print(f"\n{Colors.BOLD}Running Sentiment & Escalation E2E Tests{Colors.END}")
        print(f"Lambda Function: {Colors.BLUE}{self.function_name}{Colors.END}\n")
        print("-" * 60)

        # Sentiment Analysis Tests
        self._run_sentiment_tests()

        # Escalation Scoring Tests
        self._run_escalation_tests()

        # Combined Tests
        self._run_combined_tests()

        # Print summary
        self._print_summary()

    def run_quick_tests(self) -> None:
        """Run quick smoke tests only."""
        print(f"\n{Colors.BOLD}Running Quick Smoke Tests{Colors.END}")
        print(f"Lambda Function: {Colors.BLUE}{self.function_name}{Colors.END}\n")
        print("-" * 60)

        # Basic sentiment test
        self._test_basic_sentiment()

        # Basic escalation test
        self._test_explicit_escalation()

        # Print summary
        self._print_summary()

    def _run_sentiment_tests(self) -> None:
        """Run sentiment analysis tests."""
        print(f"\n{Colors.BOLD}Sentiment Analysis Tests{Colors.END}\n")

        self._test_basic_sentiment()
        self._test_negative_sentiment()
        self._test_positive_sentiment()
        self._test_mixed_sentiment()

    def _run_escalation_tests(self) -> None:
        """Run escalation scoring tests."""
        print(f"\n{Colors.BOLD}Escalation Scoring Tests{Colors.END}\n")

        self._test_explicit_escalation()
        self._test_no_escalation()
        self._test_high_urgency_escalation()
        self._test_repeated_question_escalation()

    def _run_combined_tests(self) -> None:
        """Run combined sentiment + escalation tests."""
        print(f"\n{Colors.BOLD}Combined Tests{Colors.END}\n")

        self._test_angry_customer_escalation()
        self._test_happy_customer_no_escalation()

    # === Sentiment Tests ===

    def _test_basic_sentiment(self) -> None:
        """Test basic sentiment analysis returns results."""
        result = self._run_test(
            name="Basic sentiment analysis",
            payload={
                "response_text": "Here is the information you requested about your order.",
                "user_message": "What is my order status?",
                "conversation_id": "test-conv-001",
                "tenant_id": "test-tenant",
            },
            assertions=[
                ("is_valid", True),
                ("sentiment", lambda x: x is not None),
                (
                    "sentiment.sentiment",
                    lambda x: x in ["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"],
                ),
            ],
        )
        self._record_result(result)

    def _test_negative_sentiment(self) -> None:
        """Test negative sentiment is detected."""
        result = self._run_test(
            name="Negative sentiment detection",
            payload={
                "response_text": "I apologize for the inconvenience you've experienced.",
                "user_message": "This is terrible! Your service is awful and I'm very frustrated!",
                "conversation_id": "test-conv-002",
                "tenant_id": "test-tenant",
            },
            assertions=[
                ("is_valid", True),
                ("sentiment.sentiment", "NEGATIVE"),
                ("sentiment.confidence", lambda x: x is not None and x > 0.5),
            ],
        )
        self._record_result(result)

    def _test_positive_sentiment(self) -> None:
        """Test positive sentiment is detected."""
        result = self._run_test(
            name="Positive sentiment detection",
            payload={
                "response_text": "Great! I'm glad I could help.",
                "user_message": "Thank you so much! You've been incredibly helpful and I really appreciate it!",
                "conversation_id": "test-conv-003",
                "tenant_id": "test-tenant",
            },
            assertions=[
                ("is_valid", True),
                ("sentiment.sentiment", "POSITIVE"),
            ],
        )
        self._record_result(result)

    def _test_mixed_sentiment(self) -> None:
        """Test mixed/neutral sentiment."""
        result = self._run_test(
            name="Neutral/Mixed sentiment detection",
            payload={
                "response_text": "Your order is being processed.",
                "user_message": "Can you check on order number 12345?",
                "conversation_id": "test-conv-004",
                "tenant_id": "test-tenant",
            },
            assertions=[
                ("is_valid", True),
                ("sentiment", lambda x: x is not None),
                ("sentiment.sentiment", lambda x: x in ["NEUTRAL", "MIXED"]),
            ],
        )
        self._record_result(result)

    # === Escalation Tests ===

    def _test_explicit_escalation(self) -> None:
        """Test explicit escalation phrase triggers escalation."""
        result = self._run_test(
            name="Explicit escalation phrase detection",
            payload={
                "response_text": "I understand. Let me see how I can help.",
                "user_message": "I want to speak to a human agent right now!",
                "conversation_id": "test-conv-005",
                "tenant_id": "test-tenant",
            },
            assertions=[
                ("is_valid", True),
                ("escalation", lambda x: x is not None),
                ("escalation.factors.explicit_intent", 1.0),
                ("escalation.score", lambda x: x is not None and x >= 0.35),
            ],
        )
        self._record_result(result)

    def _test_no_escalation(self) -> None:
        """Test normal message doesn't trigger escalation."""
        result = self._run_test(
            name="No escalation for normal message",
            payload={
                "response_text": "Your password has been reset successfully.",
                "user_message": "How do I reset my password?",
                "conversation_id": "test-conv-006",
                "tenant_id": "test-tenant",
                "intent": "question",
                "intent_confidence": 0.95,
                "urgency": "low",
            },
            assertions=[
                ("is_valid", True),
                ("escalation.needs_escalation", False),
                ("escalation.factors.explicit_intent", 0.0),
            ],
        )
        self._record_result(result)

    def _test_high_urgency_escalation(self) -> None:
        """Test high urgency contributes to escalation score."""
        result = self._run_test(
            name="High urgency escalation factor",
            payload={
                "response_text": "I understand this is urgent.",
                "user_message": "This is an emergency situation!",
                "conversation_id": "test-conv-007",
                "tenant_id": "test-tenant",
                "urgency": "high",
            },
            assertions=[
                ("is_valid", True),
                ("escalation.factors.urgency", 1.0),
                ("escalation.score", lambda x: x is not None and x >= 0.20),
            ],
        )
        self._record_result(result)

    def _test_repeated_question_escalation(self) -> None:
        """Test repeated questions contribute to escalation score."""
        result = self._run_test(
            name="Repeated question escalation factor",
            payload={
                "response_text": "Let me check on that for you again.",
                "user_message": "Where is my order? I've asked this before!",
                "conversation_id": "test-conv-008",
                "tenant_id": "test-tenant",
                "intent": "shipping",
                "previous_intents": ["shipping", "shipping"],
            },
            assertions=[
                ("is_valid", True),
                ("escalation.factors.repeated_question", 1.0),
                ("escalation.score", lambda x: x is not None and x >= 0.15),
            ],
        )
        self._record_result(result)

    # === Combined Tests ===

    def _test_angry_customer_escalation(self) -> None:
        """Test angry customer with explicit request triggers full escalation."""
        result = self._run_test(
            name="Angry customer full escalation",
            payload={
                "response_text": "I sincerely apologize for your experience.",
                "user_message": "This is unacceptable! I've asked about this 3 times! Transfer me to a manager immediately!",
                "conversation_id": "test-conv-009",
                "tenant_id": "test-tenant",
                "intent": "complaint",
                "intent_confidence": 0.90,
                "urgency": "high",
                "previous_intents": ["complaint", "complaint"],
            },
            assertions=[
                ("is_valid", True),
                ("sentiment.sentiment", "NEGATIVE"),
                ("escalation.needs_escalation", True),
                ("escalation.score", lambda x: x is not None and x >= 0.70),
                ("escalation.primary_reason", lambda x: x is not None),
            ],
        )
        self._record_result(result)

    def _test_happy_customer_no_escalation(self) -> None:
        """Test happy customer doesn't trigger escalation."""
        result = self._run_test(
            name="Happy customer no escalation",
            payload={
                "response_text": "You're welcome! Have a great day!",
                "user_message": "Thank you so much, that solved my problem perfectly!",
                "conversation_id": "test-conv-010",
                "tenant_id": "test-tenant",
                "intent": "greeting",
                "intent_confidence": 0.95,
                "urgency": "low",
            },
            assertions=[
                ("is_valid", True),
                ("sentiment.sentiment", "POSITIVE"),
                ("escalation.needs_escalation", False),
                ("escalation.score", lambda x: x is not None and x < 0.30),
            ],
        )
        self._record_result(result)

    def _record_result(self, result: TestResult) -> None:
        """Record and print a test result."""
        self.results.append(result)

        if result.passed:
            status = f"{Colors.GREEN}✓ PASS{Colors.END}"
        else:
            status = f"{Colors.RED}✗ FAIL{Colors.END}"

        print(f"  {status} {result.name} ({result.duration_ms:.0f}ms)")

        if not result.passed and result.message:
            print(f"         {Colors.RED}{result.message}{Colors.END}")

        if self.verbose and result.details:
            print(f"         Response: {json.dumps(result.details, indent=2)[:500]}...")

    def _print_summary(self) -> None:
        """Print test summary."""
        print("\n" + "=" * 60)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        total_time = sum(r.duration_ms for r in self.results)

        if failed == 0:
            print(f"{Colors.GREEN}{Colors.BOLD}All {total} tests passed!{Colors.END}")
        else:
            print(f"{Colors.RED}{Colors.BOLD}{failed}/{total} tests failed{Colors.END}")

        print(f"Total time: {total_time:.0f}ms")
        print(f"Pass: {Colors.GREEN}{passed}{Colors.END} | Fail: {Colors.RED}{failed}{Colors.END}")

        if failed > 0:
            print(f"\n{Colors.YELLOW}Failed tests:{Colors.END}")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")

            sys.exit(1)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="E2E tests for Response Validator sentiment and escalation features"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick smoke tests only",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output with response details",
    )
    parser.add_argument(
        "--function-name",
        type=str,
        help="Lambda function name (auto-detected from Terraform if not specified)",
    )

    args = parser.parse_args()

    tests = SentimentEscalationE2ETests(
        function_name=args.function_name,
        verbose=args.verbose,
    )

    if args.quick:
        tests.run_quick_tests()
    else:
        tests.run_all_tests()


if __name__ == "__main__":
    main()
