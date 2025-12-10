# ==============================================================================
# DynamoDB Outputs
# ==============================================================================

output "dynamodb_table_name" {
  description = "The name of the DynamoDB table"
  value       = module.dynamodb.table_name
}

# ==============================================================================
# Lambda Outputs
# ==============================================================================

output "intent_classifier_function_name" {
  description = "Name of the intent classifier Lambda function"
  value       = module.lambda.intent_classifier_function_name
}

output "context_builder_function_name" {
  description = "Name of the context builder Lambda function"
  value       = module.lambda.context_builder_function_name
}

# ==============================================================================
# API Gateway Outputs
# ==============================================================================

output "api_endpoint" {
  description = "The base URL for the API Gateway"
  value       = module.api_gateway.api_endpoint
}

output "api_name" {
  description = "The name of the API Gateway"
  value       = module.api_gateway.api_name
}

output "api_execution_arn" {
  description = "The execution ARN of the API Gateway"
  value       = module.api_gateway.execution_arn
}

# ==============================================================================
# Observability Outputs
# ==============================================================================

output "cloudwatch_log_groups" {
  description = "List of CloudWatch Log Groups created for Lambdas"
  value       = module.observability.log_group_names
}

output "cloudwatch_log_group_arns" {
  description = "List of CloudWatch Log Group ARNs"
  value       = module.observability.log_group_arns
}

output "cloudwatch_dashboard_name" {
  description = "Name of the main CloudWatch dashboard"
  value       = module.observability.dashboard_name
}

# =============================================================================
# Knowledge Base and Rag Handler Outputs
# =============================================================================

output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base"
  value       = module.knowledge_base.knowledge_base_id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base"
  value       = module.knowledge_base.knowledge_base_arn
}

output "s3_bucket_name" {
  description = "S3 bucket for knowledge base documents"
  value       = module.knowledge_base.s3_bucket_name
}

output "data_source_id" {
  description = "ID of the S3 data source"
  value       = module.knowledge_base.data_source_id
}

output "aurora_cluster_endpoint" {
  description = "Aurora PostgreSQL cluster endpoint"
  value       = module.knowledge_base.aurora_cluster_endpoint
}
