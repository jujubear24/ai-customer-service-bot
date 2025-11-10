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
