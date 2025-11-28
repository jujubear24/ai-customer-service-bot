output "layer_arn" {
  description = "ARN of the shared Lambda layer"
  value       = aws_lambda_layer_version.shared.arn
}

output "layer_version" {
  description = "Version of the shared Lambda layer"
  value       = aws_lambda_layer_version.shared.version
}

output "function_names" {
  description = "Map of Lambda function names"
  value       = { for k, v in aws_lambda_function.this : k => v.function_name }
}

output "function_arns" {
  description = "Map of Lambda function ARNs"
  value       = { for k, v in aws_lambda_function.this : k => v.arn }
}

output "function_invoke_arns" {
  description = "Map of Lambda function invoke ARNs (for API Gateway)"
  value       = { for k, v in aws_lambda_function.this : k => v.invoke_arn }
}

output "role_arns" {
  description = "Map of Lambda IAM role ARNs"
  value       = { for k, v in aws_iam_role.lambda : k => v.arn }
}

output "role_names" {
  description = "Map of Lambda IAM role names"
  value       = { for k, v in aws_iam_role.lambda : k => v.name }
}

# Convenience outputs for specific functions
output "intent_classifier_function_name" {
  description = "Intent Classifier function name"
  value       = try(aws_lambda_function.this["intent-classifier"].function_name, null)
}

output "intent_classifier_function_arn" {
  description = "Intent Classifier function ARN"
  value       = try(aws_lambda_function.this["intent-classifier"].arn, null)
}

output "intent_classifier_invoke_arn" {
  description = "Intent Classifier function invoke ARN"
  value       = try(aws_lambda_function.this["intent-classifier"].invoke_arn, null)
}

output "context_builder_function_name" {
  description = "Context Builder function name"
  value       = try(aws_lambda_function.this["context-builder"].function_name, null)
}

output "context_builder_function_arn" {
  description = "Context Builder function ARN"
  value       = try(aws_lambda_function.this["context-builder"].arn, null)
}

output "context_builder_invoke_arn" {
  description = "Context Builder function invoke ARN"
  value       = try(aws_lambda_function.this["context-builder"].invoke_arn, null)
}
