# Step Functions Validation Checklist

Use this checklist to validate the Step Functions deployment.

## Pre-Deployment Checks

- [ ] Lambda handlers refactored with StepFunctionsAdapter
- [ ] Shared layer updated with exceptions.py and sf_adapter.py
- [ ] Lambda builds include refactored code
- [ ] Step Functions module deployed
- [ ] API Gateway module updated with SF integration
- [ ] Feature flag `use_step_functions = true` set

## Health Checks

```bash
# Run from terraform/environments/dev

# State Machine Active?
aws stepfunctions describe-state-machine \
  --state-machine-arn "$(terraform output -raw step_functions_state_machine_arn)" \
  --query 'status' --output text
# Expected: ACTIVE

# Lambdas Active?
for fn in intent-classifier context-builder rag-retriever bedrock-handler response-validator escalation-router; do
  echo -n "$fn: "
  aws lambda get-function \
    --function-name "ai-customer-service-bot-$fn-dev" \
    --query 'Configuration.State' --output text 2>/dev/null || echo "NOT_FOUND"
done
# Expected: All "Active"
```

## Functional Tests

### Test 1: Direct Step Functions Execution

```bash
aws stepfunctions start-sync-execution \
  --state-machine-arn "$(terraform output -raw step_functions_state_machine_arn)" \
  --input '{"body": {"message": "Hello", "tenant_id": "default", "conversation_id": "check-1"}}' \
  --query 'status' --output text
```

- [ ] Status: SUCCEEDED

### Test 2: Response Contains statusCode

```bash
aws stepfunctions start-sync-execution \
  --state-machine-arn "$(terraform output -raw step_functions_state_machine_arn)" \
  --input '{"body": {"message": "Hello", "tenant_id": "default", "conversation_id": "check-2"}}' \
  --query 'output' --output text | jq -r '.statusCode'
```

- [ ] Returns: 200 or 500

### Test 3: API Gateway CORS

```bash
curl -s -I -X OPTIONS "$(terraform output -raw chat_endpoint)" | grep -i access-control
```

- [ ] Access-Control-Allow-Origin header present

### Test 4: API Gateway Validation

```bash
curl -s -w "\n%{http_code}" -X POST "$(terraform output -raw chat_endpoint)" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "default"}' | tail -1
```

- [ ] Returns: 400

### Test 5: Full E2E via API Gateway

```bash
curl -s -X POST "$(terraform output -raw chat_endpoint)" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "tenant_id": "default", "conversation_id": "check-5"}' \
  --max-time 60
```

- [ ] Returns JSON response (may be fail-open if Bedrock throttled)

### Test 6: Execution Time

```bash
time aws stepfunctions start-sync-execution \
  --state-machine-arn "$(terraform output -raw step_functions_state_machine_arn)" \
  --input '{"body": {"message": "Quick", "tenant_id": "default", "conversation_id": "check-6"}}' \
  --query 'status' --output text
```

- [ ] Completes in < 29 seconds (when Bedrock available)

## Performance Validation

| Metric | Target | Actual | Pass? |
| -------- | -------- | -------- | ------- |
| E2E Latency (happy path) | < 10s | _____ | [ ] |
| E2E Latency (fail-open) | < 30s | _____ | [ ] |
| API Gateway Response | 200/500 | _____ | [ ] |

## Error Handling

- [ ] Bedrock throttling triggers fail-open response
- [ ] RAG timeout triggers EmptyRAG fallback
- [ ] Invalid input returns 400 from API Gateway
- [ ] ASL Catch blocks route errors correctly

## Observability

- [ ] CloudWatch logs capture all Lambda invocations
- [ ] Step Functions execution history visible in console
- [ ] X-Ray traces show end-to-end flow
- [ ] Metrics published to CustomerServiceBot namespace

## Sign-Off

| Role | Name | Date | Signature |
| ------ | ------ | ------ | ----------- |
| Developer | | | |
| QA | | | |
| DevOps | | | |

## Notes

Record any issues, workarounds, or observations here:_

---

Last Updated: Dec 31, 2025
