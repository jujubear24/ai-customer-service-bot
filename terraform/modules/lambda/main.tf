# Deploys Lambda functions and shared layers

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

# ==============================================================================
# Data Sources
# ==============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ==============================================================================
# Shared Lambda Layer
# ==============================================================================

# Deploy the shared layer (built by scripts/build-lambda-layer.sh)
resource "aws_lambda_layer_version" "shared" {
  filename            = "${path.module}/builds/shared-layer.zip"
  layer_name          = "${var.project_name}-shared-layer-${var.environment}"
  source_code_hash    = filebase64sha256("${path.module}/builds/shared-layer.zip")
  compatible_runtimes = ["python3.12"]

  description = "Shared utilities for Lambda functions (Powertools, Pydantic models, config)"

  lifecycle {
    create_before_destroy = true
  }
}

# ==============================================================================
# Lambda Functions (Dynamic)
# ==============================================================================

# Lambda function resource
resource "aws_lambda_function" "this" {
  for_each = var.functions

  filename         = "${path.module}/builds/${each.key}.zip"
  function_name    = "${var.project_name}-${each.key}-${var.environment}"
  role             = aws_iam_role.lambda[each.key].arn
  handler          = each.value.handler
  source_code_hash = filebase64sha256("${path.module}/builds/${each.key}.zip")
  runtime          = each.value.runtime

  timeout     = each.value.timeout
  memory_size = each.value.memory_size

  layers = concat([aws_lambda_layer_version.shared.arn], each.value.additional_layers)

  environment {
    variables = merge(
      {
        ENVIRONMENT                        = var.environment
        POWERTOOLS_SERVICE_NAME            = each.key
        POWERTOOLS_METRICS_NAMESPACE       = var.metrics_namespace
        POWERTOOLS_LOG_LEVEL               = var.log_level
        POWERTOOLS_LOGGER_SAMPLE_RATE      = "0.1"
        POWERTOOLS_LOGGER_LOG_EVENT        = "true"
        POWERTOOLS_TRACER_CAPTURE_RESPONSE = "true"
        POWERTOOLS_TRACER_CAPTURE_ERROR    = "true"
      },
      each.value.environment_variables
    )
  }

  tracing_config {
    mode = each.value.enable_xray ? "Active" : "PassThrough"
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda
  ]

  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-${each.key}"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# ==============================================================================
# IAM Roles and Policies
# ==============================================================================

# IAM role for each Lambda function
resource "aws_iam_role" "lambda" {
  for_each = var.functions

  name = "${var.project_name}-${each.key}-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-${each.key}-role"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# Attach basic execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  for_each = var.functions

  role       = aws_iam_role.lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Custom policy for each Lambda
resource "aws_iam_role_policy" "lambda" {
  for_each = var.functions

  name = "${var.project_name}-${each.key}-policy-${var.environment}"
  role = aws_iam_role.lambda[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid    = "CloudWatchLogs"
          Effect = "Allow"
          Action = [
            "logs:CreateLogStream",
            "logs:PutLogEvents"
          ]
          Resource = [
            "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${each.key}-${var.environment}:*"
          ]
        },
        {
          Sid    = "XRayTracing"
          Effect = "Allow"
          Action = [
            "xray:PutTraceSegments",
            "xray:PutTelemetryRecords"
          ]
          Resource = "*"
        },
        {
          Sid    = "CloudWatchMetrics"
          Effect = "Allow"
          Action = [
            "cloudwatch:PutMetricData"
          ]
          Resource = "*"
          Condition = {
            StringEquals = {
              "cloudwatch:namespace" = var.metrics_namespace
            }
          }
        }
      ],
      each.value.additional_policy_statements
    )
  })
}

# Attach additional policies (e.g., DynamoDB, Bedrock)
resource "aws_iam_role_policy_attachment" "lambda_additional" {
  for_each = merge([
    for function_name, config in var.functions : {
      for idx, policy_arn in config.additional_policy_arns :
      "${function_name}-${idx}" => {
        role       = function_name
        policy_arn = policy_arn
      }
    }
  ]...)

  role       = aws_iam_role.lambda[each.value.role].name
  policy_arn = each.value.policy_arn
}
