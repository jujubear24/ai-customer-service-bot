# ADR-015: Step Functions Orchestration

**Status:** Accepted
**Date:** 2025-12-30

---

## Context

The Chat Orchestrator Lambda (ADR-011) currently coordinates the chat flow using direct Lambda-to-Lambda invocations:

```bash
Chat Orchestrator → RAG Retriever → Bedrock Handler → Response Validator → Escalation Router
```

While functional, this approach has limitations:

1. **Serial Execution:** RAG Retriever and Context Builder run sequentially despite having no data dependency
2. **Limited Visibility:** Debugging requires correlating logs across multiple Lambdas manually
3. **Error Handling:** Retry logic is implemented manually in application code
4. **Timeout Risk:** API Gateway has a 29-second hard timeout; orchestrator must complete within this window
5. **Complexity:** Orchestration logic is mixed with business logic in a single Lambda

### Requirements

| Requirement | Priority | Notes |
| ------------- | ---------- | ------- |
| Reduce end-to-end latency | P0 | Parallel execution where possible |
| Improve observability | P0 | Visual workflow, automatic tracing |
| Simplify error handling | P1 | Declarative retries with backoff |
| Maintain cost efficiency | P1 | Should not significantly increase costs |
| Enable gradual rollout | P2 | Feature flag for fallback to direct invocation |

### Options Considered

#### Option A: Keep Direct Lambda Invocation

Continue with current Chat Orchestrator pattern.

**Pros:** No migration effort, already working
**Cons:** Serial execution, manual error handling, limited observability

#### Option B: Step Functions Standard Workflow

Use Standard workflows with exactly-once execution semantics.

**Pros:** Exactly-once execution, 1-year max duration, audit history
**Cons:** Higher cost ($0.025/1000 transitions), higher latency (100-200ms startup)

#### Option C: Step Functions Express Workflow (Synchronous)

Use Express workflows with synchronous API Gateway integration.

**Pros:** Low cost ($1/million), low latency, sync invocation, parallel execution
**Cons:** At-least-once execution (acceptable for chat), 5-minute max duration

#### Option D: Step Functions Express Workflow (Asynchronous + WebSocket)

Use Express workflows with async invocation and WebSocket callback.

**Pros:** Decoupled from API Gateway timeout
**Cons:** Additional WebSocket infrastructure, complexity, higher latency

---

## Decision

**We will implement Option C: Step Functions Express Workflow with Synchronous Invocation.**

### Rationale

| Factor | Express Sync | Standard | Direct Invocation |
| -------- | -------------- | ---------- | ------------------- |
| Cost (100K requests/month) | ~$5.32 | ~$25.00 | ~$6.75 |
| Latency (typical) | 3-5s | 4-6s | 5-8s |
| Parallel execution | ✅ Native | ✅ Native | ❌ Manual |
| Visual debugging | ✅ Built-in | ✅ Built-in | ❌ Manual |
| Retry handling | ✅ Declarative | ✅ Declarative | ❌ Manual |
| Exactly-once | ❌ At-least-once | ✅ Yes | ❌ At-least-once |

Express Sync provides the best cost-latency trade-off for our use case:

- Chat workflows complete in <30 seconds (well under 5-minute Express limit)
- At-least-once execution is acceptable (responses are idempotent)
- Synchronous invocation eliminates WebSocket/polling complexity
- ~30-40% latency improvement from parallel execution
- ~21% cost reduction vs current architecture

---

## Architecture

### State Machine Design

```bash
                         ┌─────────────────┐
                         │  ReceiveMessage │
                         │   (Pass State)  │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │  ClassifyIntent │
                         │     (Task)      │
                         └────────┬────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │      Parallel Branch      │
                    │                           │
           ┌────────▼────────┐        ┌────────▼────────┐
           │  BuildContext   │        │   RetrieveRAG   │
           │     (Task)      │        │     (Task)      │
           └────────┬────────┘        └────────┬────────┘
                    │                           │
                    └─────────────┬─────────────┘
                                  │
                         ┌────────▼────────┐
                         │ GenerateResponse│
                         │  (Bedrock Task) │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │ValidateResponse │
                         │     (Task)      │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │ CheckEscalation │
                         │    (Choice)     │
                         └────────┬────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
           ┌────────▼────────┐        ┌────────▼────────┐
           │  RouteToAgent   │        │  SkipEscalation │
           │     (Task)      │        │     (Pass)      │
           └────────┬────────┘        └────────┬────────┘
                    │                           │
                    └─────────────┬─────────────┘
                                  │
                         ┌────────▼────────┐
                         │  FormatResponse │
                         │     (Pass)      │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │      End        │
                         └─────────────────┘
```

### API Gateway Integration

```bash
┌──────────┐     ┌─────────────┐     ┌─────────────────┐
│  Client  │────▶│ API Gateway │────▶│  Step Functions │
│          │     │  POST /chat │     │ (Express Sync)  │
└──────────┘     └─────────────┘     └────────┬────────┘
                                              │
                              ┌───────────────┼───────────────┐
                              │               │               │
                              ▼               ▼               ▼
                        ┌──────────┐   ┌──────────┐   ┌──────────┐
                        │  Lambda  │   │  Lambda  │   │  Lambda  │
                        │Functions │   │Functions │   │Functions │
                        └──────────┘   └──────────┘   └──────────┘
```

### Request/Response Flow

**API Gateway Request:**

```json
POST /chat
{
  "message": "How do I reset my password?",
  "tenant_id": "tenant-123",
  "conversation_id": "conv-456"
}
```

**Step Functions Input (transformed by API Gateway):**

```json
{
  "body": {
    "message": "How do I reset my password?",
    "tenant_id": "tenant-123",
    "conversation_id": "conv-456"
  },
  "requestContext": {
    "requestId": "abc-123"
  }
}
```

**Step Functions Output:**

```json
{
  "statusCode": 200,
  "body": {
    "conversation_id": "conv-456",
    "message_id": "msg-789",
    "response": "To reset your password...",
    "metadata": {
      "latency_ms": {
        "intent": 50,
        "context": 100,
        "rag": 150,
        "bedrock": 800,
        "validation": 200,
        "total": 1100
      }
    }
  }
}
```

---

## State Definitions

### State: ClassifyIntent

```json
{
  "ClassifyIntent": {
    "Type": "Task",
    "Resource": "arn:aws:lambda:${region}:${account}:function:${prefix}-intent-classifier-${env}",
    "Parameters": {
      "message.$": "$.body.message",
      "tenant_id.$": "$.body.tenant_id"
    },
    "ResultPath": "$.intent",
    "Retry": [
      {
        "ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
        "IntervalSeconds": 1,
        "MaxAttempts": 3,
        "BackoffRate": 2.0
      }
    ],
    "Catch": [
      {
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.error",
        "Next": "HandleIntentError"
      }
    ],
    "Next": "ParallelContextAndRAG"
  }
}
```

### State: ParallelContextAndRAG

```json
{
  "ParallelContextAndRAG": {
    "Type": "Parallel",
    "Branches": [
      {
        "StartAt": "BuildContext",
        "States": {
          "BuildContext": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:${region}:${account}:function:${prefix}-context-builder-${env}",
            "Parameters": {
              "conversation_id.$": "$.body.conversation_id",
              "tenant_id.$": "$.body.tenant_id"
            },
            "End": true
          }
        }
      },
      {
        "StartAt": "RetrieveRAG",
        "States": {
          "RetrieveRAG": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:${region}:${account}:function:${prefix}-rag-retriever-${env}",
            "Parameters": {
              "query.$": "$.body.message",
              "tenant_id.$": "$.body.tenant_id",
              "top_k": 3,
              "min_score": 0.5
            },
            "End": true
          }
        }
      }
    ],
    "ResultPath": "$.parallel_results",
    "Next": "GenerateResponse"
  }
}
```

### State: CheckEscalation (Choice)

```json
{
  "CheckEscalation": {
    "Type": "Choice",
    "Choices": [
      {
        "Variable": "$.validation.escalation.needs_escalation",
        "BooleanEquals": true,
        "Next": "RouteToAgent"
      }
    ],
    "Default": "FormatResponse"
  }
}
```

---

## Error Handling Strategy

### Retry Configuration

| Error Type | Max Attempts | Interval | Backoff Rate | Rationale |
| ------------ | -------------- | ---------- | -------------- | ----------- |
| `Lambda.ServiceException` | 3 | 1s | 2.0 | Transient AWS errors |
| `Lambda.TooManyRequestsException` | 3 | 2s | 2.0 | Throttling |
| `States.Timeout` | 2 | 1s | 1.5 | Lambda cold starts |

### Error Categories

| Error | Handling | User Impact |
| ------- | ---------- | ------------- |
| Intent Classification Failure | Use default intent, continue | None (graceful degradation) |
| RAG Retrieval Failure | Continue without RAG context | Potentially less accurate response |
| Bedrock Failure | Return error to user | Error message, retry prompt |
| Validation Failure | Return original response (fail-open) | None |
| Escalation Routing Failure | Log error, return response without routing | Manual escalation needed |

### Fail-Open Design

Non-critical failures should not block the customer response:

```json
{
  "RetrieveRAG": {
    "Type": "Task",
    "Resource": "...",
    "Catch": [
      {
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.rag_error",
        "Next": "ContinueWithoutRAG"
      }
    ]
  },
  "ContinueWithoutRAG": {
    "Type": "Pass",
    "Result": {
      "documents": [],
      "error": "RAG retrieval failed, continuing without context"
    },
    "ResultPath": "$.parallel_results[1]",
    "Next": "GenerateResponse"
  }
}
```

---

## Lambda Refactoring Requirements

Each Lambda must be updated to support Step Functions integration:

### Input/Output Standardization

```python
# Before (Chat Orchestrator specific)
def handler(event: dict, context: LambdaContext) -> dict:
    request = ChatRequest.model_validate(event)
    # ... processing
    return response.model_dump()

# After (Step Functions compatible)
def handler(event: dict, context: LambdaContext) -> dict:
    # Accept both direct invocation and Step Functions input
    if "body" in event and isinstance(event["body"], str):
        # API Gateway direct
        body = json.loads(event["body"])
    elif "body" in event:
        # Step Functions (already parsed)
        body = event["body"]
    else:
        # Direct invocation
        body = event

    request = MyRequest.model_validate(body)
    # ... processing
    return {
        "statusCode": 200,
        "result": response.model_dump()
    }
```

### Error Types for Catch Blocks

```python
class RetryableError(Exception):
    """Errors that should trigger Step Functions retry."""
    pass

class NonRetryableError(Exception):
    """Errors that should fail immediately."""
    pass

class ValidationError(NonRetryableError):
    """Input validation failures."""
    pass

class ServiceUnavailableError(RetryableError):
    """Downstream service temporarily unavailable."""
    pass
```

### Idempotency

Lambdas must handle duplicate invocations (at-least-once delivery):

```python
from aws_lambda_powertools.utilities.idempotency import (
    IdempotencyConfig,
    DynamoDBPersistenceLayer,
    idempotent,
)

persistence_layer = DynamoDBPersistenceLayer(table_name="idempotency")
config = IdempotencyConfig(expires_after_seconds=3600)

@idempotent(config=config, persistence_store=persistence_layer)
def process_request(request: MyRequest) -> MyResponse:
    # Processing logic
    pass
```

---

## Terraform Implementation

### Module Structure

```bash
terraform/modules/step_functions/
├── main.tf              # State machine resource
├── variables.tf         # Input variables
├── outputs.tf           # Outputs (ARN, name)
├── iam.tf               # IAM role and policies
├── logging.tf           # CloudWatch log group
└── state_machine.asl.json  # ASL definition (templated)
```

### Main Resources

```hcl
# terraform/modules/step_functions/main.tf

resource "aws_sfn_state_machine" "chat_workflow" {
  name     = "${var.project_name}-chat-workflow-${var.environment}"
  role_arn = aws_iam_role.step_functions.arn
  type     = "EXPRESS"

  definition = templatefile("${path.module}/state_machine.asl.json", {
    region                   = var.region
    account_id               = var.account_id
    intent_classifier_arn    = var.intent_classifier_arn
    context_builder_arn      = var.context_builder_arn
    rag_retriever_arn        = var.rag_retriever_arn
    bedrock_handler_arn      = var.bedrock_handler_arn
    response_validator_arn   = var.response_validator_arn
    escalation_router_arn    = var.escalation_router_arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_functions.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "step_functions" {
  name              = "/aws/vendedlogs/states/${var.project_name}-chat-workflow-${var.environment}"
  retention_in_days = 7

  tags = var.tags
}
```

### IAM Role

```hcl
# terraform/modules/step_functions/iam.tf

resource "aws_iam_role" "step_functions" {
  name = "${var.project_name}-step-functions-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "step_functions_lambda" {
  name = "lambda-invoke"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "lambda:InvokeFunction"
        Resource = [
          var.intent_classifier_arn,
          var.context_builder_arn,
          var.rag_retriever_arn,
          var.bedrock_handler_arn,
          var.response_validator_arn,
          var.escalation_router_arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "step_functions_logging" {
  name = "cloudwatch-logging"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutLogEvents",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "step_functions_xray" {
  name = "xray-tracing"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets"
        ]
        Resource = "*"
      }
    ]
  })
}
```

### API Gateway Integration

```hcl
# terraform/modules/api_gateway/step_functions.tf

resource "aws_api_gateway_integration" "chat_step_functions" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.chat.id
  http_method             = aws_api_gateway_method.chat_post.http_method
  integration_http_method = "POST"
  type                    = "AWS"
  uri                     = "arn:aws:apigateway:${var.region}:states:action/StartSyncExecution"
  credentials             = aws_iam_role.api_gateway_step_functions.arn

  request_templates = {
    "application/json" = <<EOF
{
  "input": "$util.escapeJavaScript($input.body)",
  "stateMachineArn": "${var.step_functions_arn}"
}
EOF
  }
}

resource "aws_api_gateway_integration_response" "chat_step_functions" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.chat.id
  http_method = aws_api_gateway_method.chat_post.http_method
  status_code = "200"

  response_templates = {
    "application/json" = <<EOF
#set($output = $util.parseJson($input.path('$.output')))
$output.body
EOF
  }

  depends_on = [aws_api_gateway_integration.chat_step_functions]
}
```

---

## Feature Flag for Gradual Rollout

```hcl
# terraform/environments/dev/variables.tf

variable "use_step_functions" {
  description = "Use Step Functions for chat orchestration (false = direct Lambda invocation)"
  type        = bool
  default     = false  # Start with false, enable after testing
}
```

```hcl
# terraform/environments/dev/main.tf

resource "aws_api_gateway_integration" "chat" {
  # Conditional integration based on feature flag
  type = var.use_step_functions ? "AWS" : "AWS_PROXY"
  uri  = var.use_step_functions ? (
    "arn:aws:apigateway:${var.region}:states:action/StartSyncExecution"
  ) : (
    var.chat_orchestrator_invoke_arn
  )
  # ... rest of configuration
}
```

---

## Observability

### CloudWatch Metrics

| Metric | Source | Description |
| -------- | -------- | ------------- |
| `ExecutionsStarted` | Step Functions | Total workflow executions |
| `ExecutionsSucceeded` | Step Functions | Successful completions |
| `ExecutionsFailed` | Step Functions | Failed executions |
| `ExecutionTime` | Step Functions | End-to-end duration |
| `ExecutionThrottled` | Step Functions | Throttled executions |
| `ParallelBranchDuration` | Custom | RAG + Context parallel time |

### CloudWatch Dashboard Widgets

```json
{
  "widgets": [
    {
      "title": "Step Functions Executions",
      "metrics": [
        ["AWS/States", "ExecutionsStarted", "StateMachineArn", "${state_machine_arn}"],
        [".", "ExecutionsSucceeded", ".", "."],
        [".", "ExecutionsFailed", ".", "."]
      ]
    },
    {
      "title": "Execution Duration",
      "metrics": [
        ["AWS/States", "ExecutionTime", "StateMachineArn", "${state_machine_arn}", {"stat": "p50"}],
        ["...", {"stat": "p90"}],
        ["...", {"stat": "p99"}]
      ]
    }
  ]
}
```

### X-Ray Tracing

All Lambdas already have X-Ray tracing enabled. Step Functions will automatically create trace segments that link to Lambda traces, providing end-to-end visibility.

---

## Consequences

### Positive

- **~30-40% latency reduction** from parallel RAG + Context execution
- **~21% cost reduction** vs current architecture
- **Visual debugging** with Step Functions console
- **Declarative error handling** with automatic retries
- **Better observability** with built-in metrics and X-Ray integration
- **Simplified orchestrator** — business logic stays in Lambdas, workflow in ASL
- **Gradual rollout** via feature flag

### Negative

- **At-least-once execution** — Lambdas must be idempotent (already a best practice)
- **5-minute max duration** — sufficient for chat but not for batch processing
- **Learning curve** — team needs familiarity with ASL
- **Additional infrastructure** — new Terraform module to maintain

### Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
| ------ | ------------- | -------- | ------------ |
| Express workflow timeout | Low | High | Monitor execution times, alert on p99 > 4min |
| Lambda cold starts in parallel | Medium | Low | Consider Provisioned Concurrency for critical Lambdas |
| State machine definition errors | Medium | Medium | Thorough testing, feature flag for rollback |
| Cost increase with high volume | Low | Medium | Monitor costs, Standard workflow option available |

---

## Migration Plan

| Phase | Action | Rollback |
| ------- | -------- | ---------- |
| 1 | Deploy Step Functions module with `use_step_functions = false` | N/A |
| 2 | Test state machine via direct invocation (console/CLI) | N/A |
| 3 | Enable feature flag in dev: `use_step_functions = true` | Set to `false` |
| 4 | Run E2E tests, monitor metrics for 24-48 hours | Set to `false` |
| 5 | Enable in staging | Set to `false` |
| 6 | Enable in production | Set to `false` |
| 7 | Remove feature flag and legacy integration | Redeploy with flag |

---

## Success Criteria

1. ✅ Step Functions state machine deployed and processing requests
2. ✅ Parallel execution reduces P50 latency by ≥30%
3. ✅ Error handling with automatic retries (3 attempts, exponential backoff)
4. ✅ All existing E2E tests pass via Step Functions path
5. ✅ CloudWatch dashboard showing state machine metrics
6. ✅ X-Ray traces show end-to-end flow through state machine
7. ✅ Feature flag enables instant rollback if issues arise

---

## References

- [ADR-011: Orchestrator Pattern](./ADR-011-orchestrator-pattern.md) — Current architecture being replaced
- [ADR-012: Response Validation Strategy](./ADR-012-response-validation.md) — Validation state
- [ADR-013: Sentiment Analysis & Escalation](./ADR-013-sentiment-escalation.md) — Escalation check state
- [ADR-014: Escalation Router](./ADR-014-escalation-router.md) — RouteToAgent state
- [AWS Step Functions Express Workflows](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-standard-vs-express.html)
- [API Gateway Step Functions Integration](https://docs.aws.amazon.com/step-functions/latest/dg/tutorial-api-gateway.html)
- [Step Functions Best Practices](https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html)
