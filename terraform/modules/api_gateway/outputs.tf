# ==============================================================================
# API Gateway Outputs
# ==============================================================================

output "api_id" {
  description = "ID of the API Gateway REST API"
  value       = aws_api_gateway_rest_api.main.id
}

output "api_arn" {
  description = "ARN of the API Gateway REST API"
  value       = aws_api_gateway_rest_api.main.arn
}

output "api_name" {
  description = "Name of the API Gateway REST API"
  value       = aws_api_gateway_rest_api.main.name
}

output "execution_arn" {
  description = "Execution ARN of the API Gateway REST API (for Lambda permissions)"
  value       = aws_api_gateway_rest_api.main.execution_arn
}

output "api_endpoint" {
  description = "Base URL of the API Gateway"
  value       = aws_api_gateway_stage.main.invoke_url
}

output "classify_intent_endpoint" {
  description = "Full URL for the classify-intent endpoint"
  value       = "${aws_api_gateway_stage.main.invoke_url}/classify-intent"
}

output "chat_endpoint" {
  description = "Full URL for the chat endpoint"
  value       = "${aws_api_gateway_stage.main.invoke_url}/chat"
}

output "stage_name" {
  description = "Name of the deployed stage"
  value       = aws_api_gateway_stage.main.stage_name
}

output "api_log_group" {
  description = "CloudWatch log group for API Gateway"
  value       = aws_cloudwatch_log_group.api_gateway.name
}

# ==============================================================================
# Step Functions Integration Info
# ==============================================================================

output "chat_backend_type" {
  description = "Backend type for /chat endpoint (lambda or step_functions)"
  value       = var.use_step_functions ? "step_functions" : "lambda"
}
