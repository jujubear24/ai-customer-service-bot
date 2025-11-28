# DynamoDB single-table design for AI Customer Service Bot

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
# DynamoDB Table
# ==============================================================================

resource "aws_dynamodb_table" "conversations" {
  name             = var.table_name
  billing_mode     = var.billing_mode
  hash_key         = "pk"
  range_key        = "sk"
  stream_enabled   = var.stream_enabled
  stream_view_type = var.stream_enabled ? "NEW_AND_OLD_IMAGES" : null

  # Capacity settings (only for PROVISIONED mode)
  read_capacity  = var.billing_mode == "PROVISIONED" ? var.read_capacity : null
  write_capacity = var.billing_mode == "PROVISIONED" ? var.write_capacity : null

  # Primary key attributes
  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # GSI-1: Query by user
  attribute {
    name = "gsi1_pk"
    type = "S"
  }

  attribute {
    name = "gsi1_sk"
    type = "S"
  }

  # GSI-2: Query by status
  attribute {
    name = "gsi2_pk"
    type = "S"
  }

  attribute {
    name = "gsi2_sk"
    type = "S"
  }

  # GSI-1: User's conversations
  global_secondary_index {
    name            = "GSI1"
    hash_key        = "gsi1_pk"
    range_key       = "gsi1_sk"
    projection_type = "ALL"
    read_capacity   = var.billing_mode == "PROVISIONED" ? var.gsi_read_capacity : null
    write_capacity  = var.billing_mode == "PROVISIONED" ? var.gsi_write_capacity : null
  }

  # GSI-2: Conversations by status
  global_secondary_index {
    name            = "GSI2"
    hash_key        = "gsi2_pk"
    range_key       = "gsi2_sk"
    projection_type = "ALL"
    read_capacity   = var.billing_mode == "PROVISIONED" ? var.gsi_read_capacity : null
    write_capacity  = var.billing_mode == "PROVISIONED" ? var.gsi_write_capacity : null
  }

  # TTL for automatic cleanup (30 days)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery (enable in prod)
  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  # Server-side encryption
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  tags = merge(
    var.tags,
    {
      Name        = var.table_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  )
}

# ==============================================================================
# CloudWatch Alarms
# ==============================================================================

resource "aws_cloudwatch_metric_alarm" "read_throttle" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.environment}-${var.table_name}-read-throttle"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ReadThrottleEvents"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "DynamoDB read throttle events"
  alarm_actions       = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    TableName = aws_dynamodb_table.conversations.name
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "write_throttle" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.environment}-${var.table_name}-write-throttle"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "WriteThrottleEvents"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "DynamoDB write throttle events"
  alarm_actions       = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    TableName = aws_dynamodb_table.conversations.name
  }

  tags = var.tags
}

# ==============================================================================
# IAM Policy for Lambda Access
# ==============================================================================

resource "aws_iam_policy" "dynamodb_access" {
  name        = "${var.environment}-${var.table_name}-access"
  description = "IAM policy for Lambda functions to access DynamoDB ${var.table_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
        ]
        Resource = [
          aws_dynamodb_table.conversations.arn,
          "${aws_dynamodb_table.conversations.arn}/index/*",
        ]
      },
      {
        Sid    = "DynamoDBStreams"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams",
        ]
        Resource = [
          "${aws_dynamodb_table.conversations.arn}/stream/*",
        ]
      }
    ]
  })

  tags = var.tags
}
