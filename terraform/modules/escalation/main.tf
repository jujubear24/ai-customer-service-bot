# =============================================================================
# Escalation Infrastructure Module
# =============================================================================
# Creates SQS FIFO queue and optional SNS topic for escalation routing.
# The Lambda function is managed by the main lambda module.
# =============================================================================

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# -----------------------------------------------------------------------------
# SQS FIFO Queue for Agent Escalations
# -----------------------------------------------------------------------------
resource "aws_sqs_queue" "agent_escalations" {
  name                        = "${var.project_name}-agent-escalations-${var.environment}.fifo"
  fifo_queue                  = true
  content_based_deduplication = false # We provide explicit deduplication IDs
  deduplication_scope         = "messageGroup"
  fifo_throughput_limit       = "perMessageGroupId"

  # Message settings
  message_retention_seconds  = var.message_retention_seconds
  visibility_timeout_seconds = var.visibility_timeout_seconds
  receive_wait_time_seconds  = 20 # Long polling

  # Dead letter queue
  redrive_policy = var.enable_dlq ? jsonencode({
    deadLetterTargetArn = aws_sqs_queue.agent_escalations_dlq[0].arn
    maxReceiveCount     = var.max_receive_count
  }) : null

  tags = merge(var.tags, {
    Name        = "${var.project_name}-agent-escalations"
    Environment = var.environment
    Purpose     = "Escalated conversation routing"
  })
}

# Dead Letter Queue for failed escalations
resource "aws_sqs_queue" "agent_escalations_dlq" {
  count = var.enable_dlq ? 1 : 0

  name                       = "${var.project_name}-agent-escalations-dlq-${var.environment}.fifo"
  fifo_queue                 = true
  message_retention_seconds  = 1209600 # 14 days
  visibility_timeout_seconds = 300

  tags = merge(var.tags, {
    Name        = "${var.project_name}-agent-escalations-dlq"
    Environment = var.environment
    Purpose     = "Dead letter queue for failed escalations"
  })
}

# -----------------------------------------------------------------------------
# SNS Topic for Real-Time Agent Notifications (Optional)
# -----------------------------------------------------------------------------
resource "aws_sns_topic" "agent_escalation_alerts" {
  count = var.enable_sns_notifications ? 1 : 0

  name         = "${var.project_name}-agent-escalation-alerts-${var.environment}"
  display_name = "Agent Escalation Alerts"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-agent-escalation-alerts"
    Environment = var.environment
    Purpose     = "Real-time escalation notifications"
  })
}

# -----------------------------------------------------------------------------
# IAM Policy for Escalation Router Lambda
# -----------------------------------------------------------------------------
resource "aws_iam_policy" "escalation_router" {
  name        = "${var.project_name}-escalation-router-policy-${var.environment}"
  description = "Allows Escalation Router Lambda to access SQS, DynamoDB, and SNS"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        # SQS permissions
        {
          Sid    = "SQSSendMessage"
          Effect = "Allow"
          Action = [
            "sqs:SendMessage",
            "sqs:GetQueueAttributes"
          ]
          Resource = aws_sqs_queue.agent_escalations.arn
        },
        # DynamoDB permissions
        {
          Sid    = "DynamoDBUpdateItem"
          Effect = "Allow"
          Action = [
            "dynamodb:UpdateItem",
            "dynamodb:GetItem"
          ]
          Resource = var.dynamodb_table_arn
        }
      ],
      # SNS permissions (only if enabled)
      var.enable_sns_notifications ? [
        {
          Sid    = "SNSPublish"
          Effect = "Allow"
          Action = [
            "sns:Publish"
          ]
          Resource = aws_sns_topic.agent_escalation_alerts[0].arn
        }
      ] : []
    )
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Alarms (Optional)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "escalation_queue_depth" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-escalation-queue-depth-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Average"
  threshold           = var.queue_depth_alarm_threshold
  alarm_description   = "Escalation queue depth is high - agents may be falling behind"

  dimensions = {
    QueueName = aws_sqs_queue.agent_escalations.name
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = merge(var.tags, {
    Name        = "${var.project_name}-escalation-queue-depth-alarm"
    Environment = var.environment
  })
}

resource "aws_cloudwatch_metric_alarm" "escalation_dlq_messages" {
  count = var.enable_alarms && var.enable_dlq ? 1 : 0

  alarm_name          = "${var.project_name}-escalation-dlq-messages-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Escalations are failing and landing in DLQ"

  dimensions = {
    QueueName = aws_sqs_queue.agent_escalations_dlq[0].name
  }

  alarm_actions = var.alarm_actions

  tags = merge(var.tags, {
    Name        = "${var.project_name}-escalation-dlq-alarm"
    Environment = var.environment
  })
}
