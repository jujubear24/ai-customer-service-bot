# ==============================================================================
# Step Functions State Machine - Chat Workflow (Express)
# ==============================================================================
#
# This module creates an AWS Step Functions Express workflow for orchestrating
# the AI Customer Service Bot chat flow. It replaces direct Lambda-to-Lambda
# invocations with a declarative state machine for better observability,
# error handling, and parallel execution.
#
# See ADR-015 for design decisions.
# ==============================================================================

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ==============================================================================
# Local Variables
# ==============================================================================

locals {
  state_machine_name = "${var.project_name}-chat-workflow-${var.environment}"
  log_group_name     = "/aws/vendedlogs/states/${local.state_machine_name}"

  default_tags = {
    Component   = "step-functions"
    ManagedBy   = "terraform"
    Project     = var.project_name
    Environment = var.environment
  }
}

# ==============================================================================
# CloudWatch Log Group
# ==============================================================================

resource "aws_cloudwatch_log_group" "step_functions" {
  name              = local.log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(local.default_tags, var.tags, {
    Name = "${local.state_machine_name}-logs"
  })
}

# ==============================================================================
# Step Functions State Machine
# ==============================================================================

resource "aws_sfn_state_machine" "chat_workflow" {
  name     = local.state_machine_name
  role_arn = aws_iam_role.step_functions.arn
  type     = "EXPRESS"

  definition = templatefile("${path.module}/state_machine.asl.json", {
    region                 = var.region
    account_id             = var.account_id
    project_name           = var.project_name
    environment            = var.environment
    intent_classifier_arn  = var.intent_classifier_arn
    context_builder_arn    = var.context_builder_arn
    rag_retriever_arn      = var.rag_retriever_arn
    bedrock_handler_arn    = var.bedrock_handler_arn
    response_validator_arn = var.response_validator_arn
    escalation_router_arn  = var.escalation_router_arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_functions.arn}:*"
    include_execution_data = var.include_execution_data
    level                  = var.log_level
  }

  tracing_configuration {
    enabled = var.enable_xray_tracing
  }

  tags = merge(local.default_tags, var.tags, {
    Name = local.state_machine_name
  })

  depends_on = [
    aws_iam_role_policy.step_functions_lambda,
    aws_iam_role_policy.step_functions_logging,
    aws_iam_role_policy.step_functions_xray
  ]
}
