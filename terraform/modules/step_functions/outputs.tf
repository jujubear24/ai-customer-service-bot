# ==============================================================================
# State Machine Outputs
# ==============================================================================

output "state_machine_arn" {
  description = "ARN of the Step Functions state machine"
  value       = aws_sfn_state_machine.chat_workflow.arn
}

output "state_machine_name" {
  description = "Name of the Step Functions state machine"
  value       = aws_sfn_state_machine.chat_workflow.name
}

output "state_machine_id" {
  description = "ID of the Step Functions state machine"
  value       = aws_sfn_state_machine.chat_workflow.id
}

output "state_machine_status" {
  description = "Status of the Step Functions state machine"
  value       = aws_sfn_state_machine.chat_workflow.status
}

# ==============================================================================
# IAM Outputs
# ==============================================================================

output "role_arn" {
  description = "ARN of the Step Functions IAM role"
  value       = aws_iam_role.step_functions.arn
}

output "role_name" {
  description = "Name of the Step Functions IAM role"
  value       = aws_iam_role.step_functions.name
}

# ==============================================================================
# CloudWatch Outputs
# ==============================================================================

output "log_group_arn" {
  description = "ARN of the CloudWatch log group for Step Functions"
  value       = aws_cloudwatch_log_group.step_functions.arn
}

output "log_group_name" {
  description = "Name of the CloudWatch log group for Step Functions"
  value       = aws_cloudwatch_log_group.step_functions.name
}

# ==============================================================================
# API Gateway Integration Outputs
# ==============================================================================

output "execution_arn" {
  description = "Execution ARN prefix for API Gateway integration"
  value       = "arn:aws:states:${var.region}:${var.account_id}:express:${aws_sfn_state_machine.chat_workflow.name}"
}

output "sync_execution_uri" {
  description = "URI for API Gateway synchronous execution integration"
  value       = "arn:aws:apigateway:${var.region}:states:action/StartSyncExecution"
}
