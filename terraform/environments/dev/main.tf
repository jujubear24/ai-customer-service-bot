# Note: terraform{} and provider{} blocks are in versions.tf

# ==============================================================================
# Local Variables
# ==============================================================================

locals {
  common_tags = var.common_tags
}

# ==============================================================================
# DynamoDB Module
# ==============================================================================

module "dynamodb" {
  source = "../../modules/dynamodb"

  environment                   = var.environment
  table_name                    = "conversations"
  billing_mode                  = "PAY_PER_REQUEST"
  stream_enabled                = true
  enable_point_in_time_recovery = false
  enable_alarms                 = true
  alarm_sns_topic_arn           = null

  tags = local.common_tags
}

# ==============================================================================
# Lambda Module
# ==============================================================================

module "lambda" {
  source = "../../modules/lambda"

  project_name      = var.project_name
  environment       = var.environment
  log_level         = var.log_level
  metrics_namespace = var.metrics_namespace
  common_tags       = local.common_tags

  functions = {
    intent-classifier = {
      handler               = "handler.lambda_handler"
      runtime               = "python3.12"
      timeout               = 30
      memory_size           = 256
      environment_variables = {}
      enable_xray           = true
      # Explicitly empty lists are fine
      additional_layers            = []
      additional_policy_arns       = []
      additional_policy_statements = []
    }

    context-builder = {
      handler     = "handler.handler"
      runtime     = "python3.12"
      timeout     = 30
      memory_size = 512
      environment_variables = {
        TABLE_NAME   = module.dynamodb.table_name
        MAX_MESSAGES = "10"
        MAX_TOKENS   = "8000"
      }
      enable_xray                  = true
      additional_layers            = []
      additional_policy_arns       = [module.dynamodb.iam_policy_arn]
      additional_policy_statements = []
    }
  }
}

# ==============================================================================
# API Gateway Module
# ==============================================================================

module "api_gateway" {
  source = "../../modules/api_gateway"

  project_name = var.project_name
  environment  = var.environment


  intent_classifier_invoke_arn    = module.lambda.intent_classifier_invoke_arn
  intent_classifier_function_name = module.lambda.intent_classifier_function_name


  log_retention_days     = 7
  api_logging_level      = "INFO"
  cloudwatch_kms_key_arn = null

  throttle_burst_limit = 100
  throttle_rate_limit  = 50






  common_tags = local.common_tags
}

# ==============================================================================
# Observability Module
# ==============================================================================

module "observability" {
  source = "../../modules/observability"

  project_name = var.project_name
  environment  = var.environment

  lambda_functions = [
    module.lambda.intent_classifier_function_name,
    module.lambda.context_builder_function_name,
  ]

  log_retention_days = 7
  budget_amount      = "20"
  alert_emails       = [var.alert_email]

  common_tags = local.common_tags
  api_url     = module.api_gateway.api_endpoint
}
