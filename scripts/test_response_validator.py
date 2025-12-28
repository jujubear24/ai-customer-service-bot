#!/usr/bin/env python3
"""
E2E Test Script for Response Validator Lambda.

Tests the deployed Response Validator Lambda function with various scenarios
to verify PII detection, profanity filtering, business rules, and length validation.

Usage:
    python scripts/test_response_validator.py
    python scripts/test_response_validator.py --project my-project --env prod
    python scripts/test_response_validator.py --quick  # Run only basic tests
"""

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import ClientError


@dataclass
class TestCase:
    """Test case definition."""

    name: str
    response_text: str
    user_message: str
    expected_valid: bool
    expected_action: str
    description: str


# Test cases covering all validation scenarios
TEST_CASES = [
    # Valid responses
    TestCase(
        name="valid_response",
        response_text="Thank you for contacting us. Your order has been processed and will ship within 2-3 business days. Is there anything else I can help you with?",
        user_message="When will my order ship?",
        expected_valid=True,
        expected_action="PASS",
        description="Clean response that passes all checks",
    ),
    TestCase(
        name="valid_with_order_id",
        response_text="Your order ORD-ABC12345 has been shipped and is on its way. You can track it using the link in your confirmation email.",
        user_message="Where is my order?",
        expected_valid=True,
        expected_action="PASS",
        description="Response with allowed PII (order ID)",
    ),
    # PII Detection - Should Block
    TestCase(
        name="pii_ssn_blocked",
        response_text="Your Social Security Number is 123-45-6789. Please keep this information secure.",
        user_message="What is my SSN?",
        expected_valid=False,
        expected_action="BLOCK",
        description="SSN in response should be blocked",
    ),
    TestCase(
        name="pii_credit_card_blocked",
        response_text="Your credit card number is 4111-1111-1111-1111. Your payment has been processed.",
        user_message="What is my card number?",
        expected_valid=False,
        expected_action="BLOCK",
        description="Credit card in response should be blocked",
    ),
    # Profanity - Should Block
    TestCase(
        name="profanity_blocked",
        response_text="What the fuck do you want? This is such shit service.",
        user_message="I need help",
        expected_valid=False,
        expected_action="BLOCK",
        description="Profanity in response should be blocked",
    ),
    # Length Validation
    TestCase(
        name="too_short_blocked",
        response_text="OK",
        user_message="Help me with my account",
        expected_valid=False,
        expected_action="BLOCK",
        description="Too short response should be blocked",
    ),
    # Business Rules - Should Modify (add disclaimer)
    TestCase(
        name="medical_advice_disclaimer",
        response_text="Based on your symptoms, you should take ibuprofen 400mg every 6 hours. You should see a doctor if the pain persists for more than a week.",
        user_message="What should I take for my headache?",
        expected_valid=True,
        expected_action="MODIFY",
        description="Medical advice should get disclaimer added",
    ),
    TestCase(
        name="legal_advice_disclaimer",
        response_text="You should sue the company for damages. This is my legal advice based on the contract terms. You need to consult with a lawyer about liability.",
        user_message="Should I take legal action?",
        expected_valid=True,
        expected_action="MODIFY",
        description="Legal advice should get disclaimer added",
    ),
    TestCase(
        name="financial_advice_disclaimer",
        response_text="You should invest in index funds for retirement. This financial advice is based on your risk tolerance. I recommend putting your savings in stocks.",
        user_message="How should I invest my money?",
        expected_valid=True,
        expected_action="MODIFY",
        description="Financial advice should get disclaimer added",
    ),
]

# Quick test subset for fast validation
QUICK_TESTS = ["valid_response", "pii_ssn_blocked", "profanity_blocked", "too_short_blocked"]


def invoke_validator(
    lambda_client: Any,
    function_name: str,
    response_text: str,
    user_message: str,
    conversation_id: str = "e2e-test-conv",
    tenant_id: str = "e2e-test-tenant",
) -> dict[str, Any]:
    """Invoke the Response Validator Lambda function."""
    payload = {
        "response_text": response_text,
        "user_message": user_message,
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
    }

    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )

    raw_payload = response["Payload"].read().decode("utf-8")
    result: dict[str, Any] = json.loads(raw_payload)

    # Check for function error
    if "FunctionError" in response:
        raise RuntimeError(f"Lambda function error: {result}")

    # Parse API Gateway style response if present
    if "statusCode" in result:
        if result["statusCode"] != 200:
            raise RuntimeError(f"Non-200 status: {result['statusCode']} - {result.get('body')}")
        body = result.get("body", {})
        if isinstance(body, str):
            return dict(json.loads(body))
        return dict(body)

    return result


def run_test(
    lambda_client: Any,
    function_name: str,
    test_case: TestCase,
    verbose: bool = False,
) -> tuple[bool, str]:
    """Run a single test case and return (passed, message)."""
    try:
        result = invoke_validator(
            lambda_client=lambda_client,
            function_name=function_name,
            response_text=test_case.response_text,
            user_message=test_case.user_message,
        )

        is_valid = result.get("is_valid")
        action = result.get("action")

        # Check expectations
        valid_match = is_valid == test_case.expected_valid
        action_match = action == test_case.expected_action

        if valid_match and action_match:
            msg = f"✅ {test_case.name}: PASSED"
            if verbose:
                msg += f"\n   Expected: valid={test_case.expected_valid}, action={test_case.expected_action}"
                msg += f"\n   Got: valid={is_valid}, action={action}"
                if action == "MODIFY":
                    msg += f"\n   Modified response preview: {result.get('validated_response', '')[:100]}..."
            return True, msg
        else:
            msg = f"❌ {test_case.name}: FAILED"
            msg += f"\n   Expected: valid={test_case.expected_valid}, action={test_case.expected_action}"
            msg += f"\n   Got: valid={is_valid}, action={action}"
            return False, msg

    except Exception as e:
        return False, f"❌ {test_case.name}: ERROR - {e}"


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="E2E Test for Response Validator")
    parser.add_argument("--project", default="ai-customer-service-bot", help="Project name")
    parser.add_argument("--env", default="dev", help="Environment (dev/staging/prod)")
    parser.add_argument("--quick", action="store_true", help="Run only quick tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--test", type=str, help="Run specific test by name")

    args = parser.parse_args()

    function_name = f"{args.project}-response-validator-{args.env}"
    print(f"🔎 Target Function: {function_name}")
    print(f"📋 Environment: {args.env}")
    print()

    lambda_client = boto3.client("lambda")

    # Verify function exists
    try:
        lambda_client.get_function(FunctionName=function_name)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"❌ Function not found: {function_name}")
            sys.exit(1)
        raise

    # Select tests to run
    if args.test:
        tests = [t for t in TEST_CASES if t.name == args.test]
        if not tests:
            print(f"❌ Test not found: {args.test}")
            print(f"Available tests: {', '.join(t.name for t in TEST_CASES)}")
            sys.exit(1)
    elif args.quick:
        tests = [t for t in TEST_CASES if t.name in QUICK_TESTS]
        print(f"🚀 Running quick tests ({len(tests)} tests)")
    else:
        tests = TEST_CASES
        print(f"🧪 Running all tests ({len(tests)} tests)")

    print("-" * 60)

    # Run tests
    passed = 0
    failed = 0

    for test_case in tests:
        if args.verbose:
            print(f"\n📝 {test_case.description}")

        success, message = run_test(
            lambda_client=lambda_client,
            function_name=function_name,
            test_case=test_case,
            verbose=args.verbose,
        )

        print(message)

        if success:
            passed += 1
        else:
            failed += 1

    # Summary
    print()
    print("-" * 60)
    print(f"📊 Results: {passed} passed, {failed} failed, {len(tests)} total")

    if failed == 0:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("💥 Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
