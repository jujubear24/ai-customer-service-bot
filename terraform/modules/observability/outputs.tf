# ==============================================================================
# SNS Outputs
# ==============================================================================

output "sns_topic_arn" {
  description = "The ARN of the SNS alerting topic"
  value       = aws_sns_topic.alerts.arn
}

# ==============================================================================
# KMS Outputs
# ==============================================================================

output "cloudwatch_kms_key_arn" {
  description = "The ARN of the KMS key used for CloudWatch logs"
  value       = aws_kms_key.cloudwatch.arn
}

# ==============================================================================
# Synthetics Canary Outputs
# ==============================================================================

output "canary_name" {
  description = "Name of the heartbeat canary"
  value       = aws_synthetics_canary.heartbeat.name
}

# ==============================================================================
# CloudWatch Outputs (Added)
# ==============================================================================

output "log_group_names" {
  description = "Map of Lambda function names to their CloudWatch Log Group names"
  # Iterates over the for_each resource to return a map
  value = { for k, v in aws_cloudwatch_log_group.lambda_logs : k => v.name }
}

output "log_group_arns" {
  description = "Map of Lambda function names to their CloudWatch Log Group ARNs"
  value       = { for k, v in aws_cloudwatch_log_group.lambda_logs : k => v.arn }
}

output "dashboard_name" {
  description = "Name of the CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}
