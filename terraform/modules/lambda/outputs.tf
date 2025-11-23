# ==============================================================================
# Shared Layer Outputs
# ==============================================================================

output "shared_layer_arn" {
  description = "ARN of the shared Lambda layer"
  value       = aws_lambda_layer_version.shared.arn
}

output "shared_layer_version" {
  description = "Version of the shared Lambda layer"
  value       = aws_lambda_layer_version.shared.version
}

# ==============================================================================
# Intent Classifier Outputs
# ==============================================================================

output "intent_classifier_function_name" {
  description = "Name of the intent-classifier Lambda function"
  value       = aws_lambda_function.intent_classifier.function_name
}

output "intent_classifier_function_arn" {
  description = "ARN of the intent-classifier Lambda function"
  value       = aws_lambda_function.intent_classifier.arn
}

output "intent_classifier_invoke_arn" {
  description = "Invoke ARN of the intent-classifier Lambda function (for API Gateway)"
  value       = aws_lambda_function.intent_classifier.invoke_arn
}

output "intent_classifier_role_arn" {
  description = "ARN of the intent-classifier IAM role"
  value       = aws_iam_role.intent_classifier.arn
}
