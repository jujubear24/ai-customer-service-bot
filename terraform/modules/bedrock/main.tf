# Bedrock access module - IAM policies for invoking foundation models

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ==============================================================================
# Data Sources
# ==============================================================================

data "aws_caller_identity" "current" {}

# ==============================================================================
# Local Variables
# ==============================================================================

locals {
  # Build model ARNs for the specified models
  # Strip regional prefix (e.g., "us." or "eu.") for ARN construction
  base_model_ids = [
    for model_id in var.allowed_model_ids :
    replace(model_id, "/^(us|eu|apac)\\./", "")
  ]

  # Foundation model ARNs - use wildcard for region to support cross-region inference
  # Cross-region inference can route to any region (us-east-1, us-east-2, us-west-2, etc.)
  foundation_model_arns = [
    for model_id in local.base_model_ids :
    "arn:aws:bedrock:*::foundation-model/${model_id}"
  ]

  # Inference profile ARNs (for newer Claude 4.x models with regional prefix)
  # Use wildcard for region and account to support cross-region inference
  inference_profile_arns = [
    for model_id in var.allowed_model_ids :
    "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/${model_id}"
  ]

  # Combine both ARN types for IAM policy
  all_model_arns = concat(local.foundation_model_arns, local.inference_profile_arns)

  # Resource name prefix
  name_prefix = "${var.project_name}-bedrock-${var.environment}"
}

# ==============================================================================
# IAM Policy for Bedrock Model Invocation
# ==============================================================================

resource "aws_iam_policy" "bedrock_invoke" {
  name        = "${local.name_prefix}-invoke-policy"
  description = "Allows invocation of specified Bedrock foundation models"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "BedrockInvokeModel"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = local.all_model_arns
      }
    ]
  })

  tags = merge(var.tags, {
    Name        = "${local.name_prefix}-invoke-policy"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# ==============================================================================
# IAM Policy for Bedrock Model Invocation with Streaming (Optional)
# ==============================================================================

resource "aws_iam_policy" "bedrock_invoke_streaming" {
  count = var.enable_streaming ? 1 : 0

  name        = "${local.name_prefix}-invoke-streaming-policy"
  description = "Allows streaming invocation of specified Bedrock foundation models"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeModelStreaming"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = local.all_model_arns
      }
    ]
  })

  tags = merge(var.tags, {
    Name        = "${local.name_prefix}-invoke-streaming-policy"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# ==============================================================================
# CloudWatch Alarms for Bedrock Usage (Optional)
# ==============================================================================

resource "aws_cloudwatch_metric_alarm" "bedrock_throttling" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-throttling"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = var.throttling_alarm_threshold

  metric_name = "BedrockThrottles"
  namespace   = var.metrics_namespace
  statistic   = "Sum"
  period      = 300

  alarm_description = "Bedrock API throttling detected"
  alarm_actions     = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = merge(var.tags, {
    Name        = "${local.name_prefix}-throttling-alarm"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_cloudwatch_metric_alarm" "bedrock_errors" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = var.error_alarm_threshold

  metric_name = "BedrockErrors"
  namespace   = var.metrics_namespace
  statistic   = "Sum"
  period      = 300

  alarm_description = "Bedrock API errors detected"
  alarm_actions     = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = merge(var.tags, {
    Name        = "${local.name_prefix}-errors-alarm"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}
