output "layer_arn" {
  description = "ARN of the Lambda layer (if created)"
  value       = var.create_layer ? aws_lambda_layer_version.this[0].arn : null
}

output "layer_version" {
  description = "Version of the Lambda layer (if created)"
  value       = var.create_layer ? aws_lambda_layer_version.this[0].version : null
}

output "layer_name" {
  description = "Name of the Lambda layer (if created)"
  value       = var.create_layer ? aws_lambda_layer_version.this[0].layer_name : null
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

# =============================================================================
# Convenience outputs for specific functions
# =============================================================================

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

output "bedrock_handler_function_name" {
  description = "Name of the Bedrock Handler Lambda function"
  value       = try(aws_lambda_function.this["bedrock-handler"].function_name, null)
}

output "bedrock_handler_function_arn" {
  description = "ARN of the Bedrock Handler Lambda function"
  value       = try(aws_lambda_function.this["bedrock-handler"].arn, null)
}

output "bedrock_handler_invoke_arn" {
  description = "Invoke ARN of the Bedrock Handler Lambda function"
  value       = try(aws_lambda_function.this["bedrock-handler"].invoke_arn, null)
}

output "rag_retriever_function_name" {
  description = "RAG Retriever function name"
  value       = try(aws_lambda_function.this["rag-retriever"].function_name, null)
}

output "rag_retriever_function_arn" {
  description = "RAG Retriever function ARN"
  value       = try(aws_lambda_function.this["rag-retriever"].arn, null)
}

output "rag_retriever_invoke_arn" {
  description = "RAG Retriever function invoke ARN"
  value       = try(aws_lambda_function.this["rag-retriever"].invoke_arn, null)
}

output "chat_orchestrator_function_name" {
  description = "Chat Orchestrator function name"
  value       = try(aws_lambda_function.this["chat-orchestrator"].function_name, null)
}

output "chat_orchestrator_function_arn" {
  description = "Chat Orchestrator function ARN"
  value       = try(aws_lambda_function.this["chat-orchestrator"].arn, null)
}

output "chat_orchestrator_invoke_arn" {
  description = "Chat Orchestrator function invoke ARN"
  value       = try(aws_lambda_function.this["chat-orchestrator"].invoke_arn, null)
}
