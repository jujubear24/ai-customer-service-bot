#
# Observability Module
# Handles centralized logging, monitoring, and alerting foundations.
#

# ==============================================================================
# Data Sources
# ==============================================================================

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

# ==============================================================================
# SNS Topic for Alerts
# ==============================================================================

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts-${var.environment}"

  # Use the default master key for SNS encryption for simplicity,
  # or create a custom CMK if stricter compliance is needed.
  kms_master_key_id = "alias/aws/sns"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-alerts-${var.environment}"
  })
}

# ==============================================================================
# KMS Key for CloudWatch Logs
# ==============================================================================

# CloudWatch needs a specific policy to allow it to use this key
resource "aws_kms_key" "cloudwatch" {
  description             = "KMS key for CloudWatch Log Group encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow CloudWatch Logs"
        Effect = "Allow"
        Principal = {
          Service = "logs.${data.aws_region.current.name}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
          }
        }
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cloudwatch-key-${var.environment}"
  })
}

resource "aws_kms_alias" "cloudwatch" {
  name          = "alias/${var.project_name}-cloudwatch-key-${var.environment}"
  target_key_id = aws_kms_key.cloudwatch.key_id
}

# ==============================================================================
# CloudWatch Log Groups
# ==============================================================================

# Pre-created Lambda Log Groups
# We pre-create these so we can enforce retention and encryption.
resource "aws_cloudwatch_log_group" "lambda_logs" {
  for_each = toset(var.lambda_functions)

  name              = "/aws/lambda/${var.project_name}-${each.key}-${var.environment}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.cloudwatch.arn

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${each.key}-log-group"
  })
}

# ==============================================================================
# CloudWatch Alarms
# ==============================================================================

# Global Account-level High Error Rate Alarm
# This is a catch-all alarm that triggers if the aggregate error rate
# across ALL Lambdas in this account/region goes too high.
resource "aws_cloudwatch_metric_alarm" "aggregate_lambda_errors" {
  alarm_name          = "${var.project_name}-aggregate-lambda-errors-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 5 # Alarm if more than 5 errors in 1 minute across all functions
  alarm_description   = "Triggers if aggregate Lambda errors exceed threshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  tags = var.common_tags
}

# ==============================================================================
# AWS Budget Alerts
# ==============================================================================

resource "aws_budgets_budget" "cost" {
  name              = "${var.project_name}-monthly-budget-${var.environment}"
  budget_type       = "COST"
  limit_amount      = var.budget_amount
  limit_unit        = "USD"
  time_period_start = "2024-01-01_00:00"
  time_period_end   = "2087-06-15_00:00"
  time_unit         = "MONTHLY"

  # Alert when forecasted to exceed 100% of budget
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.alert_emails
  }

  # Alert when actual costs exceed 80% of budget
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_emails
  }

  tags = var.common_tags
}
