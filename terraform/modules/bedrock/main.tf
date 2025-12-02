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

data "aws_region" "current" {}

# ==============================================================================
# Local Variables
# ==============================================================================

locals {
  # Build model ARNs for the specified models
  # Foundation models use a special ARN format without account ID
  # Strip regional prefix (e.g., "us." or "eu.") for ARN construction
  model_arns = [
    for model_id in var.allowed_model_ids :
    "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/${
      replace(model_id, "/^(us|eu|apac)\\./", "")
    }"
  ]

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
        Resource = local.model_arns
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
        Resource = local.model_arns
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
