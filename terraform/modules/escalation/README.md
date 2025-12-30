# Escalation Infrastructure Module

This Terraform module creates the SQS FIFO queue and optional SNS topic for routing escalated customer conversations to human agents.

> **Note:** The Lambda function is managed by the main `lambda` module via the `functions` map. This module only creates the supporting infrastructure.

## Architecture

```bash
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Escalation Router Lambda (via lambda module)              │
│                                                                             │
│    • Determines priority (CRITICAL, HIGH, NORMAL)                           │
│    • Updates conversation status in DynamoDB                                │
│    • Sends message to SQS FIFO queue                                        │
│    • Optionally publishes SNS notification                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        ▼
    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │  DynamoDB   │         │ SQS FIFO    │         │ SNS Topic   │
    │  (existing) │         │ Queue       │         │ (optional)  │
    └─────────────┘         └──────┬──────┘         └─────────────┘
                                   │
                                   ▼
                            ┌─────────────┐
                            │ Agent       │
                            │ Service     │
                            │ (future)    │
                            └─────────────┘
```

## Resources Created

- `aws_sqs_queue.agent_escalations` - FIFO queue with priority message groups
- `aws_sqs_queue.agent_escalations_dlq` - Dead letter queue (optional)
- `aws_sns_topic.agent_escalation_alerts` - Real-time notifications (optional)
- `aws_iam_policy.escalation_router` - IAM policy for Lambda permissions
- `aws_cloudwatch_metric_alarm.*` - Queue monitoring alarms (optional)

## Usage

### 1. Add the module to your environment

```hcl
# ==============================================================================
# Escalation Module
# ==============================================================================

module "escalation" {
  source = "../../modules/escalation"

  project_name       = var.project_name
  environment        = var.environment
  dynamodb_table_arn = module.dynamodb.table_arn

  # Optional: Enable SNS notifications
  enable_sns_notifications = false

  # Optional: Enable CloudWatch alarms
  enable_alarms = false

  tags = local.common_tags
}
```

### 2. Add escalation-router to the Lambda functions map

```hcl
module "lambda" {
  source = "../../modules/lambda"
  # ... existing config ...

  functions = {
    # ... existing functions ...

    escalation-router = {
      handler     = "handler.handler"
      runtime     = "python3.12"
      timeout     = 10
      memory_size = 256
      environment_variables = {
        ESCALATION_QUEUE_URL       = module.escalation.queue_url
        DYNAMODB_TABLE_NAME        = module.dynamodb.table_name
        ENABLE_QUEUE               = "true"
        ENABLE_DYNAMODB_UPDATE     = "true"
        ENABLE_SNS_NOTIFICATIONS   = "false"
        ESCALATION_SNS_TOPIC_ARN   = ""
        CRITICAL_THRESHOLD         = "0.90"
        HIGH_THRESHOLD             = "0.80"
        FAIL_OPEN_ON_ERROR         = "false"
      }
      enable_xray                  = true
      additional_layers            = [module.lambda_layer.layer_arn]
      additional_policy_arns       = [module.escalation.iam_policy_arn]
      additional_policy_statements = []
    }
  }
}
```

### 3. Update Chat Orchestrator environment variables

```hcl
chat-orchestrator = {
  # ... existing config ...
  environment_variables = {
    # ... existing vars ...
    ESCALATION_ROUTER_FUNCTION_NAME = local.escalation_router_function_name
  }
}
```

### 4. Update orchestrator invoke policy

```hcl
resource "aws_iam_policy" "orchestrator_invoke_policy" {
  # ...
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "lambda:InvokeFunction"
        Resource = [
          # ... existing resources ...
          module.lambda.function_arns["escalation-router"]
        ]
      }
    ]
  })
}
```

## Inputs

| Name | Description | Type | Default | Required |
| ------ | ------------- | ------ | --------- | :--------: |
| project_name | Name of the project | `string` | n/a | yes |
| environment | Environment name | `string` | n/a | yes |
| dynamodb_table_arn | DynamoDB table ARN | `string` | n/a | yes |
| message_retention_seconds | SQS message retention | `number` | `86400` | no |
| visibility_timeout_seconds | SQS visibility timeout | `number` | `60` | no |
| enable_dlq | Enable dead letter queue | `bool` | `true` | no |
| max_receive_count | Max receives before DLQ | `number` | `3` | no |
| enable_sns_notifications | Enable SNS alerts | `bool` | `false` | no |
| enable_alarms | Enable CloudWatch alarms | `bool` | `false` | no |
| queue_depth_alarm_threshold | Queue depth alarm threshold | `number` | `100` | no |
| alarm_actions | Alarm notification ARNs | `list(string)` | `[]` | no |
| ok_actions | OK notification ARNs | `list(string)` | `[]` | no |
| tags | Additional resource tags | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
| ------ | ------------- |
| queue_url | SQS FIFO queue URL |
| queue_arn | SQS FIFO queue ARN |
| queue_name | SQS FIFO queue name |
| dlq_url | Dead letter queue URL |
| dlq_arn | Dead letter queue ARN |
| sns_topic_arn | SNS topic ARN (if enabled) |
| sns_topic_name | SNS topic name (if enabled) |
| iam_policy_arn | IAM policy ARN for Lambda |
| iam_policy_name | IAM policy name |

## Priority Tiers

Messages are grouped by priority using SQS FIFO MessageGroupId:

| Priority | Score Range | MessageGroupId |
| ---------- | ------------- | ---------------- |
| CRITICAL | ≥ 0.90 | `priority-critical` |
| HIGH | ≥ 0.80 | `priority-high` |
| NORMAL | ≥ 0.70 | `priority-normal` |

## Related ADRs

- [ADR-013: Sentiment Analysis & Escalation Scoring](../../docs/adr/ADR-013-sentiment-escalation.md)
- [ADR-014: Escalation Router](../../docs/adr/ADR-014-escalation-router.md)
