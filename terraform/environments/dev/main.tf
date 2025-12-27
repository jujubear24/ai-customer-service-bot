# Note: terraform{} and provider{} blocks are in versions.tf

# ==============================================================================
# Local Variables
# ==============================================================================

locals {
  common_tags = var.common_tags

  # Predict function names to avoid circular dependencies in module.lambda
  # Pattern: {project}-{function}-{environment} (matches existing deployed resources)
  rag_function_name                = "${var.project_name}-rag-retriever-${var.environment}"
  bedrock_function_name            = "${var.project_name}-bedrock-handler-${var.environment}"
  response_validator_function_name = "${var.project_name}-response-validator-${var.environment}"
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
# Bedrock Module
# ==============================================================================

module "bedrock" {
  source = "../../modules/bedrock"

  project_name = var.project_name
  environment  = var.environment

  # Claude Haiku 4.5 for optimal price-performance
  allowed_model_ids = ["us.anthropic.claude-haiku-4-5-20251001-v1:0"]

  # Streaming disabled for now (can enable for Phase 6 frontend)
  enable_streaming = false

  # Alarms disabled for dev (enable in prod)
  enable_alarms       = false
  alarm_sns_topic_arn = null

  metrics_namespace = var.metrics_namespace

  tags = local.common_tags
}

# ==============================================================================
# Lambda Layer Module (Shared Dependencies)
# ==============================================================================

module "lambda_layer" {
  source = "../../modules/lambda"

  project_name      = var.project_name
  environment       = var.environment
  log_level         = var.log_level
  metrics_namespace = var.metrics_namespace
  common_tags       = local.common_tags

  # Layer configuration
  create_layer      = true
  layer_name        = "shared-layer"
  layer_zip_path    = "${path.module}/../../modules/lambda/builds/shared-layer.zip"
  layer_description = "Shared dependencies: Powertools, Pydantic, common utilities"

  # No functions in this module instance
  functions = {}
}

# ==============================================================================
# Lambda Functions Module
# ==============================================================================

module "lambda" {
  source = "../../modules/lambda"

  project_name      = var.project_name
  environment       = var.environment
  log_level         = var.log_level
  metrics_namespace = var.metrics_namespace
  common_tags       = local.common_tags

  # No layer creation in this instance
  create_layer = false

  functions = {
    intent-classifier = {
      handler                      = "handler.lambda_handler"
      runtime                      = "python3.12"
      timeout                      = 30
      memory_size                  = 256
      environment_variables        = {}
      enable_xray                  = true
      additional_layers            = [module.lambda_layer.layer_arn]
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
      additional_layers            = [module.lambda_layer.layer_arn]
      additional_policy_arns       = [module.dynamodb.iam_policy_arn]
      additional_policy_statements = []
    }

    bedrock-handler = {
      handler     = "handler.handler"
      runtime     = "python3.12"
      timeout     = 60 # Higher timeout for Bedrock calls
      memory_size = 512
      environment_variables = {
        BEDROCK_MODEL_ID = module.bedrock.primary_model_id
        MAX_TOKENS       = "1024"
        TEMPERATURE      = "0.7"
      }
      enable_xray                  = true
      additional_layers            = [module.lambda_layer.layer_arn]
      additional_policy_arns       = [module.bedrock.invoke_policy_arn]
      additional_policy_statements = []
    }

    rag-retriever = {
      handler     = "handler.handler"
      runtime     = "python3.12"
      timeout     = 30
      memory_size = 256
      environment_variables = {
        KNOWLEDGE_BASE_ID = module.knowledge_base.knowledge_base_id
      }
      enable_xray                  = true
      additional_layers            = [module.lambda_layer.layer_arn]
      additional_policy_arns       = [module.knowledge_base.rag_retriever_policy_arn]
      additional_policy_statements = []
    }

    chat-orchestrator = {
      handler     = "handler.lambda_handler"
      runtime     = "python3.12"
      timeout     = 29
      memory_size = 512
      environment_variables = {
        POWERTOOLS_SERVICE_NAME          = "chat-orchestrator"
        POWERTOOLS_METRICS_NAMESPACE     = "ChatBot"
        RAG_FUNCTION_NAME                = local.rag_function_name
        BEDROCK_FUNCTION_NAME            = local.bedrock_function_name
        RESPONSE_VALIDATOR_FUNCTION_NAME = local.response_validator_function_name
      }
      enable_xray                  = true
      additional_layers            = [module.lambda_layer.layer_arn]
      additional_policy_arns       = []
      additional_policy_statements = []
    }

    response-validator = {
      handler     = "handler.lambda_handler"
      runtime     = "python3.12"
      timeout     = 30
      memory_size = 512
      environment_variables = {
        ENABLE_PII_DETECTION     = "true"
        ENABLE_PROFANITY_CHECK   = "true"
        ENABLE_BUSINESS_RULES    = "true"
        ENABLE_LENGTH_CHECK      = "true"
        MIN_RESPONSE_LENGTH      = "20"
        MAX_RESPONSE_LENGTH      = "2000"
        TRUNCATE_LONG_RESPONSES  = "true"
        STOP_ON_CRITICAL_FAILURE = "true"
        USE_FALLBACK_ON_BLOCK    = "true"
        REDACT_PII_IN_RESPONSE   = "true"
        FAIL_OPEN_ON_ERROR       = "false"
      }
      enable_xray                  = true
      additional_layers            = [module.lambda_layer.layer_arn]
      additional_policy_arns       = []
      additional_policy_statements = []
    }

  }
}

# ==============================================================================
# Response Validator Permissions
# ==============================================================================

resource "aws_iam_policy" "response_validator_comprehend_policy" {
  name        = "${var.project_name}-${var.environment}-response-validator-comprehend"
  description = "Allow Response Validator to use Amazon Comprehend for PII detection"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ComprehendPII"
        Effect = "Allow"
        Action = [
          "comprehend:DetectPiiEntities",
          "comprehend:ContainsPiiEntities",
          "comprehend:DetectSentiment"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "response_validator_comprehend_attachment" {
  role       = module.lambda.role_names["response-validator"]
  policy_arn = aws_iam_policy.response_validator_comprehend_policy.arn
}


# ==============================================================================
# Orchestrator Permissions (Avoid Circular Dependencies)
# ==============================================================================

resource "aws_iam_policy" "orchestrator_invoke_policy" {
  name        = "${var.project_name}-${var.environment}-orchestrator-invoke-policy"
  description = "Allow Chat Orchestrator to invoke RAG and Bedrock Lambdas"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "lambda:InvokeFunction"
        Resource = [
          module.lambda.function_arns["rag-retriever"],
          module.lambda.function_arns["bedrock-handler"],
          module.lambda.function_arns["response-validator"]
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "orchestrator_invoke_attachment" {
  role       = module.lambda.role_names["chat-orchestrator"]
  policy_arn = aws_iam_policy.orchestrator_invoke_policy.arn
}

# ==============================================================================
# API Gateway Module
# ==============================================================================

module "api_gateway" {
  source = "../../modules/api_gateway"

  project_name = var.project_name
  environment  = var.environment

  #Intent Classier
  intent_classifier_invoke_arn    = module.lambda.function_invoke_arns["intent-classifier"]
  intent_classifier_function_name = module.lambda.function_names["intent-classifier"]

  #Chat Orchestrator
  chat_orchestrator_invoke_arn    = module.lambda.function_invoke_arns["chat-orchestrator"]
  chat_orchestrator_function_name = module.lambda.function_names["chat-orchestrator"]

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
    module.lambda.bedrock_handler_function_name,
    module.lambda.rag_retriever_function_name,
    module.lambda.chat_orchestrator_function_name,
    module.lambda.response_validator_function_name,
  ]

  log_retention_days = 7
  budget_amount      = "20"
  alert_emails       = [var.alert_email]

  common_tags = local.common_tags
  api_url     = module.api_gateway.api_endpoint
}

# ==============================================================================
# Knowledge Base Module
# ==============================================================================

module "knowledge_base" {
  source = "../../modules/knowledge_base"

  project_name = var.project_name
  environment  = var.environment

  # Aurora PostgreSQL configuration
  aurora_master_password = var.aurora_master_password
  aurora_min_capacity    = 0.5 # Minimum ACUs for cost savings
  aurora_max_capacity    = 4   # Max ACUs for dev

  # Embedding configuration
  embedding_model_id   = "amazon.titan-embed-text-v2:0"
  embedding_dimensions = 512

  # S3 data source configuration
  s3_version_retention_days = 30

  # Chunking configuration (semantic for customer service content)
  chunking_strategy                      = "SEMANTIC"
  semantic_chunking_max_tokens           = 300
  semantic_chunking_buffer_size          = 1
  semantic_chunking_breakpoint_threshold = 95

  tags = local.common_tags
}
