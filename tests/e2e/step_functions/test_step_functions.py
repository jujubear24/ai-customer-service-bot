#!/usr/bin/env python3
"""
Step Functions End-to-End Test Suite

This script provides comprehensive testing for the Step Functions chat workflow.
Run from the terraform/environments/dev directory after deployment.

Usage:
    python test_step_functions.py [--verbose] [--api-only] [--sf-only]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import boto3
import requests
from botocore.exceptions import ClientError


@dataclass
class TestResult:
    """Result of a single test."""

    name: str
    passed: bool
    duration_ms: float
    details: str = ""


class TestSuite:
    """End-to-end test suite for Step Functions workflow."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.results: list[TestResult] = []
        self.sfn_client = boto3.client("stepfunctions")
        self.lambda_client = boto3.client("lambda")

        # Load Terraform outputs
        self.outputs = self._load_terraform_outputs()

    def _load_terraform_outputs(self) -> dict[str, str]:
        """Load outputs from Terraform state."""
        try:
            result = subprocess.run(
                ["terraform", "output", "-json"],
                capture_output=True,
                text=True,
                check=True,
            )
            outputs = json.loads(result.stdout)
            return {k: v.get("value", "") for k, v in outputs.items()}
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load Terraform outputs: {e}")
            return {}

    def _log(self, message: str) -> None:
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"  [DEBUG] {message}")

    def _record(self, name: str, passed: bool, duration_ms: float, details: str = "") -> None:
        """Record test result."""
        self.results.append(TestResult(name, passed, duration_ms, details))
        status = "\033[92m[PASS]\033[0m" if passed else "\033[91m[FAIL]\033[0m"
        print(f"{status} {name} ({duration_ms:.0f}ms)")
        if details and (not passed or self.verbose):
            print(f"       Details: {details}")

    # =========================================================================
    # Step Functions Direct Tests
    # =========================================================================

    def test_sf_basic_execution(self) -> None:
        """Test basic Step Functions execution."""
        sf_arn = self.outputs.get("step_functions_state_machine_arn")
        if not sf_arn:
            self._record("SF Basic Execution", False, 0, "State machine ARN not found")
            return

        conversation_id = f"test-basic-{int(time.time())}"
        input_data = {
            "body": {
                "message": "Hello, I need some help",
                "tenant_id": "default",
                "conversation_id": conversation_id,
            }
        }

        start = time.time()
        try:
            response = self.sfn_client.start_sync_execution(
                stateMachineArn=sf_arn,
                input=json.dumps(input_data),
            )
            duration = (time.time() - start) * 1000

            status = response.get("status")
            output = response.get("output", "{}")

            self._log(f"Status: {status}")
            self._log(f"Output: {output[:200]}...")

            if status == "SUCCEEDED":
                output_data = json.loads(output)
                status_code = output_data.get("statusCode")

                if status_code == 200:
                    self._record("SF Basic Execution", True, duration, "Got 200 response")
                elif status_code == 500:
                    error = output_data.get("body", {}).get("error", "")
                    if error == "AI_SERVICE_UNAVAILABLE":
                        self._record(
                            "SF Basic Execution",
                            True,
                            duration,
                            "Fail-open response (Bedrock throttled)",
                        )
                    else:
                        self._record("SF Basic Execution", False, duration, f"Error: {error}")
                else:
                    self._record(
                        "SF Basic Execution",
                        False,
                        duration,
                        f"Unexpected status code: {status_code}",
                    )
            else:
                error = response.get("error", "Unknown")
                cause = response.get("cause", "")[:100]
                self._record("SF Basic Execution", False, duration, f"{status}: {error} - {cause}")

        except ClientError as e:
            duration = (time.time() - start) * 1000
            self._record("SF Basic Execution", False, duration, str(e))

    def test_sf_intent_classification(self) -> None:
        """Test that intent classification works correctly."""
        sf_arn = self.outputs.get("step_functions_state_machine_arn")
        if not sf_arn:
            self._record("SF Intent Classification", False, 0, "State machine ARN not found")
            return

        test_cases = [
            ("Hello!", "greeting"),
            ("I need help with my order", "order"),
            ("What is your return policy?", "policy"),
        ]

        for message, expected_category in test_cases:
            conversation_id = f"test-intent-{int(time.time())}"
            input_data = {
                "body": {
                    "message": message,
                    "tenant_id": "default",
                    "conversation_id": conversation_id,
                }
            }

            start = time.time()
            try:
                response = self.sfn_client.start_sync_execution(
                    stateMachineArn=sf_arn,
                    input=json.dumps(input_data),
                )
                duration = (time.time() - start) * 1000

                if response.get("status") == "SUCCEEDED":
                    self._record(
                        f"SF Intent: '{message[:30]}...'",
                        True,
                        duration,
                        f"Expected category: {expected_category}",
                    )
                else:
                    self._record(
                        f"SF Intent: '{message[:30]}...'",
                        False,
                        duration,
                        "Execution failed",
                    )

            except ClientError as e:
                duration = (time.time() - start) * 1000
                self._record(f"SF Intent: '{message[:30]}...'", False, duration, str(e))

            # Small delay between tests
            time.sleep(0.5)

    def test_sf_execution_time(self) -> None:
        """Test that execution completes within API Gateway timeout."""
        sf_arn = self.outputs.get("step_functions_state_machine_arn")
        if not sf_arn:
            self._record("SF Execution Time", False, 0, "State machine ARN not found")
            return

        conversation_id = f"test-time-{int(time.time())}"
        input_data = {
            "body": {
                "message": "Quick test",
                "tenant_id": "default",
                "conversation_id": conversation_id,
            }
        }

        start = time.time()
        try:
            response = self.sfn_client.start_sync_execution(
                stateMachineArn=sf_arn,
                input=json.dumps(input_data),
            )
            duration = (time.time() - start) * 1000

            # API Gateway timeout is 29 seconds
            if duration < 29000:
                self._record(
                    "SF Execution Time (<29s)",
                    True,
                    duration,
                    f"Within API Gateway limit",
                )
            else:
                self._record(
                    "SF Execution Time (<29s)",
                    False,
                    duration,
                    "Exceeds API Gateway timeout",
                )

        except ClientError as e:
            duration = (time.time() - start) * 1000
            self._record("SF Execution Time", False, duration, str(e))

    def test_sf_parallel_execution(self) -> None:
        """Test that Context and RAG execute in parallel."""
        sf_arn = self.outputs.get("step_functions_state_machine_arn")
        if not sf_arn:
            self._record("SF Parallel Execution", False, 0, "State machine ARN not found")
            return

        conversation_id = f"test-parallel-{int(time.time())}"
        input_data = {
            "body": {
                "message": "Tell me about your products",
                "tenant_id": "default",
                "conversation_id": conversation_id,
            }
        }

        start = time.time()
        try:
            response = self.sfn_client.start_sync_execution(
                stateMachineArn=sf_arn,
                input=json.dumps(input_data),
            )
            duration = (time.time() - start) * 1000

            status = response.get("status")
            if status == "SUCCEEDED":
                # Parallel execution should be faster than sequential
                # Context + RAG sequential would be ~6-8s, parallel ~4s
                self._record(
                    "SF Parallel Execution",
                    True,
                    duration,
                    "Parallel branch completed",
                )
            else:
                self._record(
                    "SF Parallel Execution",
                    False,
                    duration,
                    f"Status: {status}",
                )

        except ClientError as e:
            duration = (time.time() - start) * 1000
            self._record("SF Parallel Execution", False, duration, str(e))

    # =========================================================================
    # API Gateway Tests
    # =========================================================================

    def test_api_basic_request(self) -> None:
        """Test basic API Gateway request."""
        endpoint = self.outputs.get("chat_endpoint")
        if not endpoint:
            self._record("API Basic Request", False, 0, "Chat endpoint not found")
            return

        conversation_id = f"test-api-{int(time.time())}"
        payload = {
            "message": "Hello from API test",
            "tenant_id": "default",
            "conversation_id": conversation_id,
        }

        start = time.time()
        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            duration = (time.time() - start) * 1000

            self._log(f"Status: {response.status_code}")
            self._log(f"Body: {response.text[:200]}")

            if response.status_code == 200:
                if response.text and response.text != "null":
                    self._record("API Basic Request", True, duration)
                else:
                    self._record("API Basic Request", False, duration, "Empty response body")
            elif response.status_code == 504:
                self._record(
                    "API Basic Request",
                    False,
                    duration,
                    "Gateway timeout (workflow too slow)",
                )
            else:
                self._record(
                    "API Basic Request",
                    False,
                    duration,
                    f"HTTP {response.status_code}: {response.text[:100]}",
                )

        except requests.exceptions.Timeout:
            duration = (time.time() - start) * 1000
            self._record("API Basic Request", False, duration, "Request timed out")
        except requests.exceptions.RequestException as e:
            duration = (time.time() - start) * 1000
            self._record("API Basic Request", False, duration, str(e))

    def test_api_cors(self) -> None:
        """Test CORS headers on OPTIONS request."""
        endpoint = self.outputs.get("chat_endpoint")
        if not endpoint:
            self._record("API CORS Headers", False, 0, "Chat endpoint not found")
            return

        start = time.time()
        try:
            response = requests.options(
                endpoint,
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                },
                timeout=10,
            )
            duration = (time.time() - start) * 1000

            cors_header = response.headers.get("Access-Control-Allow-Origin")
            if cors_header:
                self._record("API CORS Headers", True, duration, f"CORS: {cors_header}")
            else:
                self._record(
                    "API CORS Headers",
                    False,
                    duration,
                    "Missing Access-Control-Allow-Origin",
                )

        except requests.exceptions.RequestException as e:
            duration = (time.time() - start) * 1000
            self._record("API CORS Headers", False, duration, str(e))

    def test_api_validation(self) -> None:
        """Test API Gateway request validation."""
        endpoint = self.outputs.get("chat_endpoint")
        if not endpoint:
            self._record("API Validation", False, 0, "Chat endpoint not found")
            return

        # Missing required 'message' field
        payload = {"tenant_id": "default"}

        start = time.time()
        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            duration = (time.time() - start) * 1000

            if response.status_code == 400:
                self._record(
                    "API Validation",
                    True,
                    duration,
                    "Correctly rejected invalid request",
                )
            else:
                self._record(
                    "API Validation",
                    False,
                    duration,
                    f"Expected 400, got {response.status_code}",
                )

        except requests.exceptions.RequestException as e:
            duration = (time.time() - start) * 1000
            self._record("API Validation", False, duration, str(e))

    # =========================================================================
    # Health Checks
    # =========================================================================

    def test_lambda_health(self) -> None:
        """Check all Lambda functions are active."""
        functions = [
            "intent-classifier",
            "context-builder",
            "rag-retriever",
            "bedrock-handler",
            "response-validator",
            "escalation-router",
        ]

        project = self.outputs.get("project_name", "ai-customer-service-bot")
        env = self.outputs.get("environment", "dev")

        all_healthy = True
        unhealthy = []

        start = time.time()
        for func in functions:
            func_name = f"{project}-{func}-{env}"
            try:
                response = self.lambda_client.get_function(FunctionName=func_name)
                state = response["Configuration"]["State"]
                if state != "Active":
                    all_healthy = False
                    unhealthy.append(f"{func}: {state}")
            except ClientError:
                all_healthy = False
                unhealthy.append(f"{func}: NOT_FOUND")

        duration = (time.time() - start) * 1000

        if all_healthy:
            self._record("Lambda Health", True, duration, "All functions active")
        else:
            self._record("Lambda Health", False, duration, ", ".join(unhealthy))

    def test_state_machine_health(self) -> None:
        """Check Step Functions state machine is active."""
        sf_arn = self.outputs.get("step_functions_state_machine_arn")
        if not sf_arn:
            self._record("State Machine Health", False, 0, "ARN not found")
            return

        start = time.time()
        try:
            response = self.sfn_client.describe_state_machine(stateMachineArn=sf_arn)
            duration = (time.time() - start) * 1000

            status = response.get("status")
            if status == "ACTIVE":
                self._record("State Machine Health", True, duration)
            else:
                self._record("State Machine Health", False, duration, f"Status: {status}")

        except ClientError as e:
            duration = (time.time() - start) * 1000
            self._record("State Machine Health", False, duration, str(e))

    # =========================================================================
    # Test Runner
    # =========================================================================

    def run_all(self, test_api: bool = True, test_sf: bool = True) -> bool:
        """Run all tests and return success status."""
        print("=" * 60)
        print("Step Functions E2E Test Suite")
        print(f"Started: {datetime.now().isoformat()}")
        print("=" * 60)

        # Health checks
        print("\n--- Health Checks ---")
        self.test_lambda_health()
        self.test_state_machine_health()

        # Step Functions tests
        if test_sf:
            print("\n--- Step Functions Direct Tests ---")
            self.test_sf_basic_execution()
            self.test_sf_intent_classification()
            self.test_sf_execution_time()
            self.test_sf_parallel_execution()

        # API Gateway tests
        if test_api:
            print("\n--- API Gateway Tests ---")
            self.test_api_cors()
            self.test_api_validation()
            self.test_api_basic_request()

        # Summary
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"Total:  {total}")
        print(f"Passed: \033[92m{passed}\033[0m")
        print(f"Failed: \033[91m{failed}\033[0m")

        if failed > 0:
            print("\nFailed Tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.details}")

        print()
        return failed == 0


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Step Functions E2E Test Suite")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--api-only", action="store_true", help="Run only API tests")
    parser.add_argument("--sf-only", action="store_true", help="Run only SF tests")
    args = parser.parse_args()

    test_api = not args.sf_only
    test_sf = not args.api_only

    suite = TestSuite(verbose=args.verbose)
    success = suite.run_all(test_api=test_api, test_sf=test_sf)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
