# =============================================================================
# Escalation Module Outputs
# =============================================================================

# -----------------------------------------------------------------------------
# SQS Queue Outputs
# -----------------------------------------------------------------------------
output "queue_url" {
  description = "URL of the agent escalations SQS FIFO queue"
  value       = aws_sqs_queue.agent_escalations.url
}

output "queue_arn" {
  description = "ARN of the agent escalations SQS FIFO queue"
  value       = aws_sqs_queue.agent_escalations.arn
}

output "queue_name" {
  description = "Name of the agent escalations SQS FIFO queue"
  value       = aws_sqs_queue.agent_escalations.name
}

output "dlq_url" {
  description = "URL of the dead letter queue (if enabled)"
  value       = var.enable_dlq ? aws_sqs_queue.agent_escalations_dlq[0].url : null
}

output "dlq_arn" {
  description = "ARN of the dead letter queue (if enabled)"
  value       = var.enable_dlq ? aws_sqs_queue.agent_escalations_dlq[0].arn : null
}

# -----------------------------------------------------------------------------
# SNS Topic Outputs
# -----------------------------------------------------------------------------
output "sns_topic_arn" {
  description = "ARN of the agent escalation alerts SNS topic (if enabled)"
  value       = var.enable_sns_notifications ? aws_sns_topic.agent_escalation_alerts[0].arn : null
}

output "sns_topic_name" {
  description = "Name of the agent escalation alerts SNS topic (if enabled)"
  value       = var.enable_sns_notifications ? aws_sns_topic.agent_escalation_alerts[0].name : null
}

# -----------------------------------------------------------------------------
# IAM Policy Outputs
# -----------------------------------------------------------------------------
output "iam_policy_arn" {
  description = "ARN of the IAM policy for escalation router Lambda"
  value       = aws_iam_policy.escalation_router.arn
}

output "iam_policy_name" {
  description = "Name of the IAM policy for escalation router Lambda"
  value       = aws_iam_policy.escalation_router.name
}
