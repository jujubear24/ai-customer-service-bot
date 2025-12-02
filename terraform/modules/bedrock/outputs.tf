# Outputs for Bedrock module

# ==============================================================================
# IAM Policy Outputs
# ==============================================================================

output "invoke_policy_arn" {
  description = "ARN of the IAM policy for Bedrock model invocation"
  value       = aws_iam_policy.bedrock_invoke.arn
}

output "invoke_policy_name" {
  description = "Name of the IAM policy for Bedrock model invocation"
  value       = aws_iam_policy.bedrock_invoke.name
}

output "invoke_streaming_policy_arn" {
  description = "ARN of the IAM policy for Bedrock streaming invocation (if enabled)"
  value       = var.enable_streaming ? aws_iam_policy.bedrock_invoke_streaming[0].arn : null
}

# ==============================================================================
# Model Configuration Outputs
# ==============================================================================

output "allowed_model_ids" {
  description = "List of allowed Bedrock model IDs"
  value       = var.allowed_model_ids
}

output "allowed_model_arns" {
  description = "List of allowed Bedrock model ARNs"
  value       = local.model_arns
}

output "primary_model_id" {
  description = "Primary model ID (first in the allowed list)"
  value       = var.allowed_model_ids[0]
}

# ==============================================================================
# Alarm Outputs
# ==============================================================================

output "throttling_alarm_arn" {
  description = "ARN of the throttling CloudWatch alarm (if enabled)"
  value       = var.enable_alarms ? aws_cloudwatch_metric_alarm.bedrock_throttling[0].arn : null
}

output "errors_alarm_arn" {
  description = "ARN of the errors CloudWatch alarm (if enabled)"
  value       = var.enable_alarms ? aws_cloudwatch_metric_alarm.bedrock_errors[0].arn : null
}
