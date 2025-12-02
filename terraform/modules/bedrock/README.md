# Bedrock Module

Terraform module for managing Amazon Bedrock access permissions.

## Overview

This module creates IAM policies for invoking Amazon Bedrock foundation models. It follows the principle of least privilege by restricting access to specific model ARNs.

## Usage

### Basic Usage

```hcl
module "bedrock" {
  source = "../../modules/bedrock"

  project_name = "ai-customer-service"
  environment  = "dev"

  tags = local.common_tags
}
```

### With Custom Models and Streaming

```hcl
module "bedrock" {
  source = "../../modules/bedrock"

  project_name = "ai-customer-service"
  environment  = "dev"

  # Use regional prefix for newer Claude 4.x models
  allowed_model_ids = [
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-sonnet-4-20250514-v1:0"
  ]

  enable_streaming = true

  tags = local.common_tags
}
```

### With Alarms

```hcl
module "bedrock" {
  source = "../../modules/bedrock"

  project_name = "ai-customer-service"
  environment  = "prod"

  enable_alarms              = true
  alarm_sns_topic_arn        = aws_sns_topic.alerts.arn
  throttling_alarm_threshold = 10
  error_alarm_threshold      = 5

  tags = local.common_tags
}
```

### Attaching to Lambda

```hcl
module "lambda" {
  source = "../../modules/lambda"

  functions = {
    bedrock-handler = {
      handler     = "handler.handler"
      runtime     = "python3.12"
      timeout     = 60
      memory_size = 512

      environment_variables = {
        BEDROCK_MODEL_ID = module.bedrock.primary_model_id
      }

      additional_policy_arns = [module.bedrock.invoke_policy_arn]
    }
  }
}
```

## Requirements

| Name | Version |
|------|---------|
| Terraform | >= 1.6.0 |
| AWS | ~> 5.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| project_name | Name of the project | `string` | n/a | yes |
| environment | Environment name | `string` | n/a | yes |
| allowed_model_ids | List of Bedrock model IDs | `list(string)` | `["us.anthropic.claude-haiku-4-5-20251001-v1:0"]` | no |
| enable_streaming | Enable streaming responses | `bool` | `false` | no |
| metrics_namespace | CloudWatch namespace | `string` | `"AICustomerService"` | no |
| enable_alarms | Create CloudWatch alarms | `bool` | `false` | no |
| alarm_sns_topic_arn | SNS topic for alarms | `string` | `null` | no |
| throttling_alarm_threshold | Throttle count for alarm | `number` | `5` | no |
| error_alarm_threshold | Error count for alarm | `number` | `10` | no |
| tags | Additional tags | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| invoke_policy_arn | ARN of the invoke policy |
| invoke_policy_name | Name of the invoke policy |
| invoke_streaming_policy_arn | ARN of streaming policy (if enabled) |
| allowed_model_ids | List of allowed model IDs |
| allowed_model_arns | List of allowed model ARNs |
| primary_model_id | First model ID in the list |
| throttling_alarm_arn | Throttling alarm ARN (if enabled) |
| errors_alarm_arn | Errors alarm ARN (if enabled) |

## Notes

### Bedrock Model Access

Before using this module, ensure that Amazon Bedrock model access is enabled in your AWS account:

1. Go to Amazon Bedrock console
2. Navigate to "Model access" in the left sidebar
3. Request access to the Claude models you need
4. Wait for access to be granted (usually immediate for Claude models)

### Model ID Format (Regional Prefix)

Newer Claude 4.x models require a regional prefix when invoking:

```bash
# Invocation format (use in Lambda code)
us.anthropic.claude-haiku-4-5-20251001-v1:0     # US regions
eu.anthropic.claude-haiku-4-5-20251001-v1:0     # EU regions
apac.anthropic.claude-haiku-4-5-20251001-v1:0   # APAC regions
```

This module automatically strips the regional prefix when constructing IAM policy ARNs.

### Model ARN Format

Bedrock foundation models use a special ARN format without an account ID:

```bash
arn:aws:bedrock:{region}::foundation-model/{model-id}
```

This module handles this automatically.

### Cost Considerations

Claude Haiku 4.5 pricing (us-east-1):

- Input: ~$1.00 per 1M tokens
- Output: ~$5.00 per 1M tokens

This is approximately 70% cheaper than Claude Sonnet models ($3/$15 per 1M tokens).

Monitor the `BedrockInputTokens` and `BedrockOutputTokens` CloudWatch metrics emitted by the Lambda handler.
