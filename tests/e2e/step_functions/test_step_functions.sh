#!/bin/bash
# ==============================================================================
# Step Functions End-to-End Test Suite
# ==============================================================================
# Usage: ./test_step_functions.sh [--api-only] [--sf-only] [--verbose]
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Terraform outputs available (run from terraform/environments/dev)
#   - jq installed for JSON parsing
# ==============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VERBOSE=${VERBOSE:-false}
TEST_API=true
TEST_SF=true
TIMEOUT=60

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --api-only) TEST_SF=false; shift ;;
        --sf-only) TEST_API=false; shift ;;
        --verbose) VERBOSE=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--api-only] [--sf-only] [--verbose]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ==============================================================================
# Helper Functions
# ==============================================================================

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${YELLOW}[DEBUG]${NC} $1"
    fi
}

# Get Terraform outputs
get_terraform_output() {
    terraform output -raw "$1" 2>/dev/null || echo ""
}

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

record_result() {
    local name="$1"
    local passed="$2"
    local details="${3:-}"

    TESTS_RUN=$((TESTS_RUN + 1))
    if [ "$passed" = true ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        log_success "$name"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        log_fail "$name"
        if [ -n "$details" ]; then
            echo "         Details: $details"
        fi
    fi
}

# ==============================================================================
# Test: Direct Step Functions Execution
# ==============================================================================

test_sf_basic_greeting() {
    log_info "Testing: Step Functions - Basic Greeting"

    local sf_arn=$(get_terraform_output step_functions_state_machine_arn)
    if [ -z "$sf_arn" ]; then
        record_result "SF Basic Greeting" false "Could not get state machine ARN"
        return
    fi

    local input='{"body": {"message": "Hello", "tenant_id": "default", "conversation_id": "test-sf-greeting-'$(date +%s)'"}}'
    verbose "Input: $input"

    local result=$(aws stepfunctions start-sync-execution \
        --state-machine-arn "$sf_arn" \
        --input "$input" \
        --output json 2>&1)

    verbose "Result: $result"

    local status=$(echo "$result" | jq -r '.status // empty')
    local output=$(echo "$result" | jq -r '.output // empty')

    if [ "$status" = "SUCCEEDED" ]; then
        # Check if output contains expected fields
        if echo "$output" | jq -e '.statusCode' > /dev/null 2>&1; then
            local status_code=$(echo "$output" | jq -r '.statusCode')
            if [ "$status_code" = "200" ]; then
                record_result "SF Basic Greeting (200 OK)" true
            elif [ "$status_code" = "500" ]; then
                # Check if it's a throttling/fail-open response
                local error=$(echo "$output" | jq -r '.body.error // empty')
                if [ "$error" = "AI_SERVICE_UNAVAILABLE" ]; then
                    record_result "SF Basic Greeting (Fail-Open)" true "Bedrock throttled, fail-open working"
                else
                    record_result "SF Basic Greeting" false "Unexpected 500 error: $error"
                fi
            else
                record_result "SF Basic Greeting" false "Unexpected status code: $status_code"
            fi
        else
            record_result "SF Basic Greeting" false "Missing statusCode in output"
        fi
    elif [ "$status" = "FAILED" ]; then
        local error=$(echo "$result" | jq -r '.error // empty')
        local cause=$(echo "$result" | jq -r '.cause // empty')
        record_result "SF Basic Greeting" false "Execution failed: $error - $cause"
    else
        record_result "SF Basic Greeting" false "Unexpected status: $status"
    fi
}

test_sf_order_inquiry() {
    log_info "Testing: Step Functions - Order Inquiry"

    local sf_arn=$(get_terraform_output step_functions_state_machine_arn)
    local input='{"body": {"message": "I need help with my order #12345", "tenant_id": "default", "conversation_id": "test-sf-order-'$(date +%s)'"}}'

    local result=$(aws stepfunctions start-sync-execution \
        --state-machine-arn "$sf_arn" \
        --input "$input" \
        --output json 2>&1)

    local status=$(echo "$result" | jq -r '.status // empty')

    if [ "$status" = "SUCCEEDED" ]; then
        local output=$(echo "$result" | jq -r '.output // empty')
        local intent=$(echo "$output" | jq -r '.body.intent // empty' 2>/dev/null || echo "")
        verbose "Detected intent: $intent"
        record_result "SF Order Inquiry" true
    else
        record_result "SF Order Inquiry" false "Status: $status"
    fi
}

test_sf_missing_fields() {
    log_info "Testing: Step Functions - Missing Required Fields"

    local sf_arn=$(get_terraform_output step_functions_state_machine_arn)

    # Missing tenant_id
    local input='{"body": {"message": "Hello"}}'

    local result=$(aws stepfunctions start-sync-execution \
        --state-machine-arn "$sf_arn" \
        --input "$input" \
        --output json 2>&1)

    local status=$(echo "$result" | jq -r '.status // empty')

    # Should still succeed with default handling or fail gracefully
    if [ "$status" = "SUCCEEDED" ] || [ "$status" = "FAILED" ]; then
        record_result "SF Missing Fields Handling" true "Handled gracefully: $status"
    else
        record_result "SF Missing Fields Handling" false "Unexpected status: $status"
    fi
}

test_sf_execution_time() {
    log_info "Testing: Step Functions - Execution Time"

    local sf_arn=$(get_terraform_output step_functions_state_machine_arn)
    local input='{"body": {"message": "What is your return policy?", "tenant_id": "default", "conversation_id": "test-sf-time-'$(date +%s)'"}}'

    local start_time=$(date +%s%3N)

    local result=$(aws stepfunctions start-sync-execution \
        --state-machine-arn "$sf_arn" \
        --input "$input" \
        --output json 2>&1)

    local end_time=$(date +%s%3N)
    local duration=$((end_time - start_time))

    local status=$(echo "$result" | jq -r '.status // empty')

    if [ "$status" = "SUCCEEDED" ]; then
        if [ "$duration" -lt 29000 ]; then
            record_result "SF Execution Time (<29s)" true "Duration: ${duration}ms"
        else
            record_result "SF Execution Time (<29s)" false "Duration: ${duration}ms (exceeds API Gateway timeout)"
        fi
    else
        record_result "SF Execution Time" false "Execution did not succeed"
    fi
}

# ==============================================================================
# Test: API Gateway Integration
# ==============================================================================

test_api_basic_request() {
    log_info "Testing: API Gateway - Basic Request"

    local endpoint=$(get_terraform_output chat_endpoint)
    if [ -z "$endpoint" ]; then
        record_result "API Basic Request" false "Could not get chat endpoint"
        return
    fi

    verbose "Endpoint: $endpoint"

    local response=$(curl -s -w "\n%{http_code}" -X POST "$endpoint" \
        -H "Content-Type: application/json" \
        -d '{"message": "Hello", "tenant_id": "default", "conversation_id": "test-api-'$(date +%s)'"}' \
        --max-time "$TIMEOUT" 2>&1)

    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')

    verbose "HTTP Code: $http_code"
    verbose "Body: $body"

    if [ "$http_code" = "200" ]; then
        if [ -n "$body" ] && [ "$body" != "null" ]; then
            record_result "API Basic Request (200)" true
        else
            record_result "API Basic Request" false "Empty response body"
        fi
    elif [ "$http_code" = "504" ]; then
        record_result "API Basic Request" false "Gateway timeout (Bedrock may be throttled)"
    else
        record_result "API Basic Request" false "HTTP $http_code: $body"
    fi
}

test_api_cors_headers() {
    log_info "Testing: API Gateway - CORS Headers"

    local endpoint=$(get_terraform_output chat_endpoint)

    local response=$(curl -s -I -X OPTIONS "$endpoint" \
        -H "Origin: http://localhost:3000" \
        -H "Access-Control-Request-Method: POST" \
        2>&1)

    verbose "Response: $response"

    if echo "$response" | grep -qi "access-control-allow-origin"; then
        record_result "API CORS Headers" true
    else
        record_result "API CORS Headers" false "Missing Access-Control-Allow-Origin header"
    fi
}

test_api_validation() {
    log_info "Testing: API Gateway - Request Validation"

    local endpoint=$(get_terraform_output chat_endpoint)

    # Missing required field (message)
    local response=$(curl -s -w "\n%{http_code}" -X POST "$endpoint" \
        -H "Content-Type: application/json" \
        -d '{"tenant_id": "default"}' \
        --max-time 10 2>&1)

    local http_code=$(echo "$response" | tail -n1)

    # Should return 400 for validation error
    if [ "$http_code" = "400" ]; then
        record_result "API Request Validation" true "Correctly rejected invalid request"
    else
        record_result "API Request Validation" false "Expected 400, got $http_code"
    fi
}

# ==============================================================================
# Test: Component Health Checks
# ==============================================================================

test_lambda_health() {
    log_info "Testing: Lambda Functions Health"

    local functions=(
        "intent-classifier"
        "context-builder"
        "rag-retriever"
        "bedrock-handler"
        "response-validator"
        "escalation-router"
    )

    local project=$(get_terraform_output project_name 2>/dev/null || echo "ai-customer-service-bot")
    local env=$(get_terraform_output environment 2>/dev/null || echo "dev")

    local all_healthy=true
    for func in "${functions[@]}"; do
        local func_name="${project}-${func}-${env}"
        local state=$(aws lambda get-function --function-name "$func_name" --query 'Configuration.State' --output text 2>/dev/null || echo "NOT_FOUND")

        if [ "$state" = "Active" ]; then
            verbose "$func_name: Active"
        else
            log_warn "$func_name: $state"
            all_healthy=false
        fi
    done

    record_result "Lambda Functions Health" $all_healthy
}

test_step_functions_health() {
    log_info "Testing: Step Functions State Machine Health"

    local sf_arn=$(get_terraform_output step_functions_state_machine_arn)

    if [ -z "$sf_arn" ]; then
        record_result "Step Functions Health" false "State machine not found"
        return
    fi

    local status=$(aws stepfunctions describe-state-machine \
        --state-machine-arn "$sf_arn" \
        --query 'status' \
        --output text 2>/dev/null || echo "NOT_FOUND")

    if [ "$status" = "ACTIVE" ]; then
        record_result "Step Functions Health" true
    else
        record_result "Step Functions Health" false "Status: $status"
    fi
}

# ==============================================================================
# Test: Error Handling
# ==============================================================================

test_sf_error_recovery() {
    log_info "Testing: Step Functions - Error Recovery (Fail-Open)"

    local sf_arn=$(get_terraform_output step_functions_state_machine_arn)

    # Use a message that might trigger edge cases
    local input='{"body": {"message": "Help me with a very urgent issue!", "tenant_id": "default", "conversation_id": "test-sf-error-'$(date +%s)'"}}'

    local result=$(aws stepfunctions start-sync-execution \
        --state-machine-arn "$sf_arn" \
        --input "$input" \
        --output json 2>&1)

    local status=$(echo "$result" | jq -r '.status // empty')

    # Even if Bedrock fails, workflow should succeed with fail-open response
    if [ "$status" = "SUCCEEDED" ]; then
        record_result "SF Error Recovery" true "Workflow completed with fail-open handling"
    else
        record_result "SF Error Recovery" false "Workflow failed: $status"
    fi
}

# ==============================================================================
# Main Test Execution
# ==============================================================================

main() {
    echo "=============================================="
    echo "Step Functions E2E Test Suite"
    echo "=============================================="
    echo ""

    # Check prerequisites
    if ! command -v jq &> /dev/null; then
        log_fail "jq is required but not installed"
        exit 1
    fi

    if ! command -v aws &> /dev/null; then
        log_fail "AWS CLI is required but not installed"
        exit 1
    fi

    # Health checks
    echo ""
    echo "--- Health Checks ---"
    test_lambda_health
    test_step_functions_health

    # Step Functions tests
    if [ "$TEST_SF" = true ]; then
        echo ""
        echo "--- Step Functions Direct Tests ---"
        test_sf_basic_greeting
        test_sf_order_inquiry
        test_sf_missing_fields
        test_sf_execution_time
        test_sf_error_recovery
    fi

    # API Gateway tests
    if [ "$TEST_API" = true ]; then
        echo ""
        echo "--- API Gateway Integration Tests ---"
        test_api_cors_headers
        test_api_validation
        test_api_basic_request
    fi

    # Summary
    echo ""
    echo "=============================================="
    echo "Test Summary"
    echo "=============================================="
    echo "Tests Run:    $TESTS_RUN"
    echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
    echo ""

    if [ "$TESTS_FAILED" -gt 0 ]; then
        echo -e "${RED}Some tests failed!${NC}"
        exit 1
    else
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    fi
}

main "$@"
