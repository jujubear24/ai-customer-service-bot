#
# Lambda Module
# Packages and deploys Lambda functions and shared layers
#

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
# Intent Classifier Lambda Function
# ==============================================================================

# Package the intent-classifier function
data "archive_file" "intent_classifier" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambda/functions/intent-classifier/src"
  output_path = "${path.module}/builds/intent-classifier.zip"
  excludes = [
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "*.egg-info",
    "tests",
  ]
}

# IAM role for intent-classifier
resource "aws_iam_role" "intent_classifier" {
  name = "${var.project_name}-intent-classifier-${var.environment}"

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
    Name        = "${var.project_name}-intent-classifier-role"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"

  })
}

# Attach basic execution policy
resource "aws_iam_role_policy_attachment" "intent_classifier_basic" {
  role       = aws_iam_role.intent_classifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Custom policy for intent-classifier
resource "aws_iam_role_policy" "intent_classifier" {
  name = "${var.project_name}-intent-classifier-policy-${var.environment}"
  role = aws_iam_role.intent_classifier.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-intent-classifier-${var.environment}:*"
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
    ]
  })
}

# Deploy the intent-classifier function
resource "aws_lambda_function" "intent_classifier" {
  filename         = data.archive_file.intent_classifier.output_path
  function_name    = "${var.project_name}-intent-classifier-${var.environment}"
  role             = aws_iam_role.intent_classifier.arn
  handler          = "handler.lambda_handler"
  source_code_hash = data.archive_file.intent_classifier.output_base64sha256
  runtime          = "python3.12"

  timeout     = 30
  memory_size = 256

  layers = [aws_lambda_layer_version.shared.arn]

  environment {
    variables = {
      ENVIRONMENT                        = var.environment
      POWERTOOLS_SERVICE_NAME            = "intent-classifier"
      POWERTOOLS_METRICS_NAMESPACE       = var.metrics_namespace
      POWERTOOLS_LOG_LEVEL               = var.log_level
      POWERTOOLS_LOGGER_SAMPLE_RATE      = "0.1"
      POWERTOOLS_LOGGER_LOG_EVENT        = "true"
      POWERTOOLS_TRACER_CAPTURE_RESPONSE = "true"
      POWERTOOLS_TRACER_CAPTURE_ERROR    = "true"
    }
  }

  tracing_config {
    mode = "Active"
  }

  # Ensure log group exists before function
  depends_on = [
    aws_iam_role_policy_attachment.intent_classifier_basic,
    aws_iam_role_policy.intent_classifier
  ]

  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-intent-classifier"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"


  })
}

# CloudWatch Log Group (already created by observability module, but adding explicit dependency)
# This ensures the log group has the correct retention and encryption settings
