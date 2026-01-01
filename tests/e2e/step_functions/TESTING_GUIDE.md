# Step 4.1.7: End-to-End Testing Documentation

This document provides comprehensive testing procedures for validating the Step Functions chat workflow.

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. Terraform deployment completed with `use_step_functions = true`
3. Python 3.12+ with `boto3` and `requests` installed
4. `jq` installed for JSON parsing (bash script)

## Quick Start

```bash
# From terraform/environments/dev directory
cd terraform/environments/dev

# Run bash test suite
chmod +x test_step_functions.sh
./test_step_functions.sh

# Or run Python test suite
python test_step_functions.py --verbose
```

## Test Categories

### 1. Health Checks

| Test | Description | Expected Result |
|------|-------------|-----------------|
| Lambda Functions Health | Verify all 6 Lambdas are Active | All functions in Active state |
| State Machine Health | Verify Step Functions is Active | State machine status = ACTIVE |

### 2. Step Functions Direct Tests

| Test | Description | Expected Result |
| ------ | ------------- | ----------------- |
| SF Basic Execution | Simple greeting message | SUCCEEDED status, 200 or fail-open response |
| SF Intent Classification | Various message types | Correct intent detected |
| SF Execution Time | Measure total execution time | < 29 seconds (API Gateway limit) |
| SF Parallel Execution | Context + RAG parallel | Both branches complete |
| SF Error Recovery | Test fail-open handling | Graceful degradation response |

### 3. API Gateway Integration Tests

| Test | Description | Expected Result |
| ------ | ------------- | ----------------- |
| API CORS Headers | OPTIONS request | Access-Control-Allow-Origin present |
| API Validation | Missing required fields | 400 Bad Request |
| API Basic Request | Full end-to-end request | 200 with response body |

## Manual Testing Commands

### Direct Step Functions Execution

```bash
# Get the state machine ARN
SF_ARN=$(terraform output -raw step_functions_state_machine_arn)

# Basic test
aws stepfunctions start-sync-execution \
  --state-machine-arn "$SF_ARN" \
  --input '{"body": {"message": "Hello", "tenant_id": "default", "conversation_id": "manual-test-1"}}' \
  --query '[status, output]' --output text

# Test with timing
time aws stepfunctions start-sync-execution \
  --state-machine-arn "$SF_ARN" \
  --input '{"body": {"message": "What is your return policy?", "tenant_id": "default", "conversation_id": "manual-test-2"}}' \
  --query 'status' --output text
```

### API Gateway Test

```bash
# Get the chat endpoint
CHAT_ENDPOINT=$(terraform output -raw chat_endpoint)

# Basic request
curl -X POST "$CHAT_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "tenant_id": "default", "conversation_id": "curl-test-1"}'

# With timing
time curl -X POST "$CHAT_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"message": "I need help with my order", "tenant_id": "default"}' \
  --max-time 60

# CORS preflight
curl -X OPTIONS "$CHAT_ENDPOINT" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -v

# Validation test (should return 400)
curl -X POST "$CHAT_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "default"}'
```

### View Execution Logs

```bash
# Step Functions logs
aws logs tail /aws/vendedlogs/states/ai-customer-service-bot-chat-workflow-dev --since 10m --format short

# Individual Lambda logs
aws logs tail /aws/lambda/ai-customer-service-bot-intent-classifier-dev --since 10m --format short
aws logs tail /aws/lambda/ai-customer-service-bot-context-builder-dev --since 10m --format short
aws logs tail /aws/lambda/ai-customer-service-bot-rag-retriever-dev --since 10m --format short
aws logs tail /aws/lambda/ai-customer-service-bot-bedrock-handler-dev --since 10m --format short
aws logs tail /aws/lambda/ai-customer-service-bot-response-validator-dev --since 10m --format short
aws logs tail /aws/lambda/ai-customer-service-bot-escalation-router-dev --since 10m --format short

# API Gateway logs
aws logs tail /aws/apigateway/ai-customer-service-bot-dev --since 10m --format short
```

## Test Scenarios

### Scenario 1: Happy Path

**Input:**

```json
{
  "message": "What are your business hours?",
  "tenant_id": "default",
  "conversation_id": "test-happy-path"
}
```

**Expected Flow:**

1. ReceiveMessage → Wraps input
2. ClassifyIntent → Detects "business_hours" or "general_inquiry" intent
3. ParallelContextAndRAG → Executes Context and RAG in parallel
4. MergeParallelResults → Combines results
5. GenerateResponse → Bedrock generates response
6. ValidateResponse → Validates output
7. CheckEscalation → No escalation needed
8. FormatSuccessResponse → Returns 200 with AI response

**Expected Response:**

```json
{
  "statusCode": 200,
  "body": {
    "response": "Our business hours are...",
    "conversation_id": "test-happy-path",
    "escalated": false
  }
}
```

### Scenario 2: Bedrock Throttled (Fail-Open)

**Input:**

```json
{
  "message": "Hello",
  "tenant_id": "default",
  "conversation_id": "test-throttled"
}
```

**Expected Flow:**

1. ReceiveMessage → ClassifyIntent → ParallelContextAndRAG → MergeParallelResults
2. GenerateResponse → Bedrock throttled → Catch block
3. BedrockErrorResponse → Returns fail-open message

**Expected Response:**

```json
{
  "statusCode": 500,
  "body": {
    "error": "AI_SERVICE_UNAVAILABLE",
    "message": "I apologize, but I'm temporarily unable to process your request...",
    "retryable": true,
    "conversation_id": "test-throttled"
  }
}
```

### Scenario 3: Escalation Required

**Input:**

```json
{
  "message": "I am extremely frustrated and want to speak to a manager!",
  "tenant_id": "default",
  "conversation_id": "test-escalation"
}
```

**Expected Flow:**

1. Full pipeline executes
2. ValidateResponse → High escalation score detected
3. CheckEscalation → Yes condition met
4. RouteEscalation → Sends to SQS queue
5. FormatEscalatedResponse → Returns with escalated=true

**Expected Response:**

```json
{
  "statusCode": 200,
  "body": {
    "response": "I understand your frustration...",
    "conversation_id": "test-escalation",
    "escalated": true,
    "escalation_id": "esc-xxx"
  }
}
```

## Performance Benchmarks

| Metric | Target | Current |
| -------- | -------- | --------- |
| Total Execution Time | < 10s (ideal), < 29s (max) | TBD |
| Intent Classification | < 2s | ~1.7s |
| Context Building | < 3s | ~2s |
| RAG Retrieval | < 5s | ~3-4s |
| Bedrock Generation | < 5s | ~3s (when not throttled) |
| Response Validation | < 2s | ~1s |

## Troubleshooting

### Common Issues

#### 1. Timeout (504 Gateway Timeout)

**Symptoms:** API Gateway returns 504 after 29 seconds

**Causes:**

- Bedrock throttled (retries add ~23s)
- RAG retriever cold start + Knowledge Base latency
- Multiple Lambda cold starts

**Solutions:**

- Check Bedrock quota in AWS Console
- Reduce retry attempts temporarily
- Use provisioned concurrency for critical Lambdas

#### 2. Empty Response Body

**Symptoms:** HTTP 200 but empty or "null" response

**Causes:**

- Response mapping template error
- Step Functions output parsing issue

**Solutions:**

- Check API Gateway integration response templates
- Verify Step Functions output format matches expected structure

#### 3. JSONPath Not Found

**Symptoms:** `States.Runtime` error with JSONPath message

**Causes:**

- Input structure doesn't match ASL expectations
- Lambda output format changed

**Solutions:**

- Verify request wrapper: `{"body": {...}}`
- Check Lambda response structure matches ASL Parameters

#### 4. Validation Error (400)

**Symptoms:** API Gateway returns 400 Bad Request

**Causes:**

- Missing required fields (message, tenant_id)
- Field validation failed (length, type)

**Solutions:**

- Include all required fields in request
- Check request model schema in API Gateway

## Validation Checklist

- [ ] All health checks pass
- [ ] Step Functions execution succeeds (status = SUCCEEDED)
- [ ] Execution time < 29 seconds (when Bedrock not throttled)
- [ ] API Gateway returns valid response
- [ ] CORS headers present on OPTIONS
- [ ] Request validation rejects invalid input
- [ ] Fail-open response returned when Bedrock unavailable
- [ ] Escalation flow works for high-urgency messages
- [ ] CloudWatch logs show proper tracing

## Commit Message

```bash
test(e2e): add Step Functions end-to-end test suite

- Add bash test script with health checks and integration tests
- Add Python test suite with comprehensive coverage
- Add test documentation with scenarios and benchmarks
- Add troubleshooting guide for common issues
- Add manual testing commands for debugging
```
