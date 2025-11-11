#
# Observability Module
# Handles centralized logging, monitoring, and alerting foundations.
#

# ==============================================================================
# Data Sources
# ==============================================================================

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "archive_file" "canary_zip" {
  type        = "zip"
  source_file = "${path.module}/files/heartbeat.js"
  output_path = "${path.module}/files/heartbeat.zip"
}

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
# CloudWatch Dashboard
# ==============================================================================

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-dashboard-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Errors", { stat = "Sum", period = 300 }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = data.aws_region.current.name
          title   = "Lambda Errors (Aggregate)"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["CloudWatchSynthetics", "SuccessPercent", "CanaryName", aws_synthetics_canary.heartbeat.name, { stat = "Average", period = 300 }]
          ]
          view   = "timeSeries"
          region = data.aws_region.current.name
          title  = "API Canary Success Rate"
          yAxis = {
            left = {
              min = 0
              max = 100
            }
          }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 24
        height = 6
        properties = {
          metrics = [
            ["AWS/Billing", "EstimatedCharges", "Currency", "USD", { stat = "Maximum", period = 21600 }]
          ]
          view   = "timeSeries"
          region = "us-east-1" # Billing metrics are always in us-east-1
          title  = "Estimated Monthly Charges"
        }
      }
    ]
  })
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

# ==============================================================================
# Synthetics Canary - S3 Bucket
# ==============================================================================

resource "aws_s3_bucket" "canary_artifacts" {
  bucket        = "${var.project_name}-canary-artifacts-${data.aws_caller_identity.current.account_id}-${var.environment}"
  force_destroy = true # Allow deleting bucket even if it has canary run history

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-canary-artifacts-${var.environment}"
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "canary_artifacts" {
  bucket = aws_s3_bucket.canary_artifacts.id

  rule {
    id     = "cleanup-old-artifacts"
    status = "Enabled"
    filter {}

    expiration {
      days = 30 # Automatically delete artifacts after 30 days to save costs
    }
  }
}

# ==============================================================================
# Synthetics Canary - IAM Role
# ==============================================================================

resource "aws_iam_role" "canary" {
  name = "${var.project_name}-canary-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "canary" {
  name = "${var.project_name}-canary-policy-${var.environment}"
  role = aws_iam_role.canary.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CanaryArtifactsAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          aws_s3_bucket.canary_artifacts.arn,
          "${aws_s3_bucket.canary_artifacts.arn}/*"
        ]
      },
      {
        Sid    = "CloudWatchMetricsAccess"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "CloudWatchSynthetics"
          }
        }
      },
      {
        Sid    = "LambdaLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/cwsyn-*"
      }
    ]
  })
}

# ==============================================================================
# Synthetics Canary - Heartbeat
# ==============================================================================

resource "aws_synthetics_canary" "heartbeat" {
  name                 = "api-heartbeat-${var.environment}"
  artifact_s3_location = "s3://${aws_s3_bucket.canary_artifacts.bucket}/"
  execution_role_arn   = aws_iam_role.canary.arn
  handler              = "heartbeat.handler"
  zip_file             = data.archive_file.canary_zip.output_path
  runtime_version      = "syn-nodejs-puppeteer-6.2" # Latest stable runtime
  start_canary         = true

  schedule {
    expression = "rate(5 minutes)"
  }

  run_config {
    timeout_in_seconds = 60
    environment_variables = {
      API_URL = "https://api.example.com" # Placeholder until we have the real API Gateway URL
    }
  }

  tags = var.common_tags
}
