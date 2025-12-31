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

output "escalation_router_function_name" {
  description = "Name of the escalation router Lambda function"
  value       = module.lambda.escalation_router_function_name
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

output "chat_endpoint" {
  description = "Full URL for the /chat endpoint"
  value       = module.api_gateway.chat_endpoint
}

output "classify_intent_endpoint" {
  description = "Full URL for the /classify-intent endpoint"
  value       = module.api_gateway.classify_intent_endpoint
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

# =============================================================================
# Escalation Outputs
# =============================================================================

output "escalation_queue_url" {
  description = "URL of the escalation SQS FIFO queue"
  value       = module.escalation.queue_url
}

output "escalation_queue_arn" {
  description = "ARN of the escalation SQS FIFO queue"
  value       = module.escalation.queue_arn
}

output "escalation_dlq_url" {
  description = "URL of the escalation dead letter queue"
  value       = module.escalation.dlq_url
}

output "escalation_sns_topic_arn" {
  description = "ARN of the escalation SNS topic (if enabled)"
  value       = module.escalation.sns_topic_arn
}

# ==============================================================================
# Step Functions Outputs
# ==============================================================================

output "step_functions_state_machine_arn" {
  description = "ARN of the Step Functions state machine (if enabled)"
  value       = var.use_step_functions ? module.step_functions[0].state_machine_arn : null
}

output "step_functions_state_machine_name" {
  description = "Name of the Step Functions state machine (if enabled)"
  value       = var.use_step_functions ? module.step_functions[0].state_machine_name : null
}

output "step_functions_execution_arn" {
  description = "Execution ARN prefix for API Gateway integration (if enabled)"
  value       = var.use_step_functions ? module.step_functions[0].execution_arn : null
}

output "step_functions_sync_execution_uri" {
  description = "URI for API Gateway synchronous execution (if enabled)"
  value       = var.use_step_functions ? module.step_functions[0].sync_execution_uri : null
}

output "step_functions_log_group_name" {
  description = "CloudWatch log group for Step Functions (if enabled)"
  value       = var.use_step_functions ? module.step_functions[0].log_group_name : null
}

output "step_functions_role_arn" {
  description = "IAM role ARN for Step Functions (if enabled)"
  value       = var.use_step_functions ? module.step_functions[0].role_arn : null
}

output "api_gateway_step_functions_role_arn" {
  description = "IAM role ARN for API Gateway to invoke Step Functions (if enabled)"
  value       = var.use_step_functions ? aws_iam_role.api_gateway_step_functions[0].arn : null
}
