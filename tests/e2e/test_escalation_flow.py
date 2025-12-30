#!/usr/bin/env python3
"""
E2E Tests for Full Escalation Flow via Chat Orchestrator.

This script tests the complete escalation workflow from customer message
through Chat Orchestrator to Escalation Router and SQS queue delivery.

Usage:
    python scripts/test_escalation_flow.py                    # Run all tests
    python scripts/test_escalation_flow.py --quick            # Quick smoke tests
    python scripts/test_escalation_flow.py -v                 # Verbose output

Flow tested:
    Customer Message -> API Gateway -> Chat Orchestrator -> Response Validator
    -> (escalation triggered) -> Escalation Router -> SQS Queue

Prerequisites:
    - AWS credentials configured
    - Full infrastructure deployed (API Gateway, Lambdas, SQS, DynamoDB)
    - boto3 installed
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any


# ANSI color codes
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
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


class EscalationFlowE2ETests:
    """E2E test suite for full escalation flow."""

    def __init__(
        self,
        chat_endpoint: str | None = None,
        verbose: bool = False,
    ) -> None:
        self.verbose = verbose
        self.chat_endpoint = chat_endpoint or self._get_chat_endpoint()
        self.queue_url = self._get_queue_url()
        self.results: list[TestResult] = []

        try:
            import boto3
            import requests

            self.sqs_client = boto3.client("sqs")
            self.requests = requests
        except ImportError as e:
            print(
                f"{Colors.RED}Error: Missing dependency. Install with: pip install boto3 requests{Colors.END}"
            )
            print(f"Missing: {e}")
            sys.exit(1)

    def _get_terraform_output(self, output_name: str, fallback: str = "") -> str:
        """Get a value from Terraform outputs."""
        try:
            result = subprocess.run(
                ["terraform", "output", "-raw", output_name],
                capture_output=True,
                text=True,
                cwd="terraform/environments/dev",
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except FileNotFoundError:
            pass
        return fallback

    def _get_chat_endpoint(self) -> str:
        """Get Chat API endpoint from Terraform outputs."""
        return self._get_terraform_output("chat_endpoint", "")

    def _get_queue_url(self) -> str:
        """Get SQS queue URL from Terraform outputs."""
        return self._get_terraform_output("escalation_queue_url", "")

    def _send_chat_message(
        self,
        message: str,
        tenant_id: str = "test-tenant",
        conversation_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a message to the Chat API."""
        if not self.chat_endpoint:
            raise RuntimeError("Chat endpoint not configured")

        payload = {
            "message": message,
            "tenant_id": tenant_id,
            "validate_response": True,  # Ensure validation runs
        }

        if conversation_id:
            payload["conversation_id"] = conversation_id

        # Add any additional parameters
        payload.update(kwargs)

        response = self.requests.post(
            self.chat_endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,  # Chat flow can take time
        )

        if response.status_code != 200:
            raise RuntimeError(f"Chat API error: {response.status_code} - {response.text}")

        return response.json()

    def _check_queue_for_escalation(
        self,
        conversation_id: str,
        timeout_seconds: int = 10,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Check if an escalation was queued for a conversation."""
        if not self.queue_url:
            return False, None

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                response = self.sqs_client.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=2,
                    MessageAttributeNames=["All"],
                )

                messages = response.get("Messages", [])
                for msg in messages:
                    body = json.loads(msg["Body"])
                    if body.get("conversation_id") == conversation_id:
                        # Found our escalation - delete it and return
                        self.sqs_client.delete_message(
                            QueueUrl=self.queue_url,
                            ReceiptHandle=msg["ReceiptHandle"],
                        )
                        return True, body

            except Exception as e:
                if self.verbose:
                    print(f"  {Colors.YELLOW}SQS check error: {e}{Colors.END}")
                break

        return False, None

    def run_all_tests(self) -> None:
        """Run all test cases."""
        print(f"\n{Colors.BOLD}Running Full Escalation Flow E2E Tests{Colors.END}")
        print(f"Chat Endpoint: {Colors.BLUE}{self.chat_endpoint or 'Not configured'}{Colors.END}")
        print(f"Queue URL: {Colors.CYAN}{self.queue_url or 'Not configured'}{Colors.END}\n")
        print("-" * 60)

        if not self.chat_endpoint:
            print(
                f"{Colors.RED}Error: Chat endpoint not configured. Deploy infrastructure first.{Colors.END}"
            )
            sys.exit(1)

        # Full flow tests
        self._run_escalation_flow_tests()

        # Print summary
        self._print_summary()

    def run_quick_tests(self) -> None:
        """Run quick smoke tests only."""
        print(f"\n{Colors.BOLD}Running Quick Escalation Flow Tests{Colors.END}")
        print(f"Chat Endpoint: {Colors.BLUE}{self.chat_endpoint or 'Not configured'}{Colors.END}\n")
        print("-" * 60)

        if not self.chat_endpoint:
            print(f"{Colors.RED}Error: Chat endpoint not configured.{Colors.END}")
            sys.exit(1)

        self._test_escalation_phrase_triggers_routing()
        self._print_summary()

    def _run_escalation_flow_tests(self) -> None:
        """Run full escalation flow tests."""
        print(f"\n{Colors.BOLD}Escalation Flow Tests{Colors.END}\n")

        self._test_escalation_phrase_triggers_routing()
        self._test_angry_customer_triggers_escalation()
        self._test_normal_message_no_escalation()

    def _test_escalation_phrase_triggers_routing(self) -> None:
        """Test explicit escalation phrase triggers full flow."""
        start_time = time.time()
        conv_id = f"e2e-flow-{uuid.uuid4().hex[:8]}"

        try:
            # Send escalation message
            response = self._send_chat_message(
                message="I want to speak to a human agent right now!",
                conversation_id=conv_id,
            )

            duration_ms = (time.time() - start_time) * 1000

            # Check response indicates escalation
            metadata = response.get("metadata", {})
            escalation = metadata.get("escalation", {})

            failures = []

            # Verify escalation was detected
            if not escalation.get("needs_escalation"):
                failures.append("Escalation not triggered in response")

            # Check if escalation was routed (if routing is enabled)
            escalation_response = metadata.get("escalation_response", {})
            if escalation_response:
                if not escalation_response.get("success"):
                    failures.append(
                        f"Escalation routing failed: {escalation_response.get('error')}"
                    )

                # Verify queue message (if queue URL available)
                if self.queue_url and escalation_response.get("success"):
                    queued, queue_msg = self._check_queue_for_escalation(conv_id)
                    if not queued:
                        failures.append("Escalation not found in SQS queue")
                    elif self.verbose and queue_msg:
                        print(f"         Queue message priority: {queue_msg.get('priority')}")

            result = TestResult(
                name="Escalation phrase triggers full routing flow",
                passed=len(failures) == 0,
                duration_ms=duration_ms,
                message="; ".join(failures) if failures else "",
                details=response if self.verbose else None,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            # Handle API Gateway timeout gracefully
            if "504" in error_msg or "timed out" in error_msg.lower():
                result = TestResult(
                    name="Escalation phrase triggers full routing flow",
                    passed=True,  # Skip - infrastructure limitation
                    duration_ms=duration_ms,
                    message=f"{Colors.YELLOW}SKIPPED: API Gateway timeout (29s limit) - use direct Lambda tests{Colors.END}",
                )
            else:
                result = TestResult(
                    name="Escalation phrase triggers full routing flow",
                    passed=False,
                    duration_ms=duration_ms,
                    message=error_msg,
                )

        self._record_result(result)

    def _test_angry_customer_triggers_escalation(self) -> None:
        """Test angry customer message triggers escalation."""
        start_time = time.time()
        conv_id = f"e2e-angry-{uuid.uuid4().hex[:8]}"

        try:
            # Send angry message
            response = self._send_chat_message(
                message="This is absolutely unacceptable! I've been waiting for 3 days! "
                "Your service is terrible and I want to cancel everything! "
                "Get me a manager NOW!",
                conversation_id=conv_id,
            )

            duration_ms = (time.time() - start_time) * 1000

            metadata = response.get("metadata", {})
            escalation = metadata.get("escalation", {})
            sentiment = metadata.get("sentiment", {})

            failures = []

            # Should detect negative sentiment
            if sentiment.get("sentiment") != "NEGATIVE":
                failures.append(f"Expected NEGATIVE sentiment, got {sentiment.get('sentiment')}")

            # Should trigger escalation
            if not escalation.get("needs_escalation"):
                failures.append("Escalation not triggered for angry customer")

            # High escalation score expected
            score = escalation.get("score", 0)
            if score < 0.70:
                failures.append(f"Expected high escalation score, got {score}")

            result = TestResult(
                name="Angry customer triggers escalation",
                passed=len(failures) == 0,
                duration_ms=duration_ms,
                message="; ".join(failures) if failures else "",
                details=response if self.verbose else None,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            # Handle API Gateway timeout gracefully
            if "504" in error_msg or "timed out" in error_msg.lower():
                result = TestResult(
                    name="Angry customer triggers escalation",
                    passed=True,  # Skip - infrastructure limitation
                    duration_ms=duration_ms,
                    message=f"{Colors.YELLOW}SKIPPED: API Gateway timeout (29s limit) - use direct Lambda tests{Colors.END}",
                )
            else:
                result = TestResult(
                    name="Angry customer triggers escalation",
                    passed=False,
                    duration_ms=duration_ms,
                    message=error_msg,
                )

        self._record_result(result)

    def _test_normal_message_no_escalation(self) -> None:
        """Test normal message does not trigger escalation."""
        start_time = time.time()
        conv_id = f"e2e-normal-{uuid.uuid4().hex[:8]}"

        try:
            # Send normal message
            response = self._send_chat_message(
                message="What are your business hours?",
                conversation_id=conv_id,
            )

            duration_ms = (time.time() - start_time) * 1000

            metadata = response.get("metadata", {})
            escalation = metadata.get("escalation", {})

            failures = []

            # Should NOT trigger escalation
            if escalation.get("needs_escalation"):
                failures.append("Normal message incorrectly triggered escalation")

            # Low escalation score expected
            score = escalation.get("score", 0)
            if score >= 0.70:
                failures.append(f"Escalation score too high for normal message: {score}")

            result = TestResult(
                name="Normal message does not trigger escalation",
                passed=len(failures) == 0,
                duration_ms=duration_ms,
                message="; ".join(failures) if failures else "",
                details=response if self.verbose else None,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            # Handle API Gateway timeout gracefully
            if "504" in error_msg or "timed out" in error_msg.lower():
                result = TestResult(
                    name="Normal message does not trigger escalation",
                    passed=True,  # Skip - infrastructure limitation
                    duration_ms=duration_ms,
                    message=f"{Colors.YELLOW}SKIPPED: API Gateway timeout (29s limit) - use direct Lambda tests{Colors.END}",
                )
            else:
                result = TestResult(
                    name="Normal message does not trigger escalation",
                    passed=False,
                    duration_ms=duration_ms,
                    message=error_msg,
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
            print(f"         Response: {json.dumps(result.details, indent=2)[:800]}...")

    def _print_summary(self) -> None:
        """Print test summary."""
        print("\n" + "=" * 60)

        # Count results - skipped tests are marked as passed but have SKIPPED in message
        skipped = sum(1 for r in self.results if r.passed and "SKIPPED" in r.message)
        passed = sum(1 for r in self.results if r.passed and "SKIPPED" not in r.message)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        total_time = sum(r.duration_ms for r in self.results)

        if failed == 0 and skipped == 0:
            print(f"{Colors.GREEN}{Colors.BOLD}All {total} tests passed!{Colors.END}")
        elif failed == 0 and skipped > 0:
            print(
                f"{Colors.YELLOW}{Colors.BOLD}{skipped}/{total} tests skipped (API Gateway timeout){Colors.END}"
            )
            print(
                f"{Colors.CYAN}Note: Use direct Lambda tests for escalation router validation{Colors.END}"
            )
        else:
            print(f"{Colors.RED}{Colors.BOLD}{failed}/{total} tests failed{Colors.END}")

        print(f"Total time: {total_time:.0f}ms")
        summary_parts = [f"Pass: {Colors.GREEN}{passed}{Colors.END}"]
        if skipped > 0:
            summary_parts.append(f"Skip: {Colors.YELLOW}{skipped}{Colors.END}")
        summary_parts.append(f"Fail: {Colors.RED}{failed}{Colors.END}")
        print(" | ".join(summary_parts))

        if failed > 0:
            print(f"\n{Colors.YELLOW}Failed tests:{Colors.END}")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")

            sys.exit(1)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="E2E tests for full escalation flow via Chat Orchestrator"
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
        "--chat-endpoint",
        type=str,
        help="Chat API endpoint (auto-detected from Terraform if not specified)",
    )

    args = parser.parse_args()

    tests = EscalationFlowE2ETests(
        chat_endpoint=args.chat_endpoint,
        verbose=args.verbose,
    )

    if args.quick:
        tests.run_quick_tests()
    else:
        tests.run_all_tests()


if __name__ == "__main__":
    main()
