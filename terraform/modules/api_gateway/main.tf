#
# API Gateway Module
# Creates a REST API Gateway with Lambda integration
#

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
# Data Sources
# ==============================================================================


# ==============================================================================
# REST API Gateway
# ==============================================================================

resource "aws_api_gateway_rest_api" "main" {
  name        = "${var.project_name}-api-${var.environment}"
  description = "AI Customer Service Bot API - ${var.environment}"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-api-${var.environment}"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# ==============================================================================
# CloudWatch Log Group for API Gateway
# ==============================================================================

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.cloudwatch_kms_key_arn

  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-api-logs"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# ==============================================================================
# API Gateway Account Settings (for CloudWatch logging)
# ==============================================================================

resource "aws_api_gateway_account" "main" {
  cloudwatch_role_arn = aws_iam_role.api_gateway_cloudwatch.arn
}

resource "aws_iam_role" "api_gateway_cloudwatch" {
  name = "${var.project_name}-api-gateway-cloudwatch-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-api-gateway-cloudwatch-role"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_iam_role_policy_attachment" "api_gateway_cloudwatch" {
  role       = aws_iam_role.api_gateway_cloudwatch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

# ==============================================================================
# /classify-intent Resource and Method
# ==============================================================================

resource "aws_api_gateway_resource" "classify_intent" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "classify-intent"
}

# POST method
resource "aws_api_gateway_method" "classify_intent_post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.classify_intent.id
  http_method   = "POST"
  authorization = "NONE"

  request_validator_id = aws_api_gateway_request_validator.body.id

  request_models = {
    "application/json" = aws_api_gateway_model.classify_intent_request.name
  }
}

# Request validator
resource "aws_api_gateway_request_validator" "body" {
  name                        = "${var.project_name}-validate-body-${var.environment}"
  rest_api_id                 = aws_api_gateway_rest_api.main.id
  validate_request_body       = true
  validate_request_parameters = false
}

# Request model
resource "aws_api_gateway_model" "classify_intent_request" {
  rest_api_id  = aws_api_gateway_rest_api.main.id
  name         = "ClassifyIntentRequest"
  description  = "Request schema for classify-intent endpoint"
  content_type = "application/json"

  schema = jsonencode({
    "$schema" = "http://json-schema.org/draft-04/schema#"
    title     = "ClassifyIntentRequest"
    type      = "object"
    required  = ["message"]
    properties = {
      message = {
        type      = "string"
        minLength = 1
        maxLength = 2000
      }
      conversation_history = {
        type = "array"
        items = {
          type = "object"
        }
        maxItems = 50
      }
    }
  })
}

# Lambda integration
resource "aws_api_gateway_integration" "classify_intent_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.classify_intent.id
  http_method             = aws_api_gateway_method.classify_intent_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.intent_classifier_invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway_intent_classifier" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.intent_classifier_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# ==============================================================================
# CORS Configuration
# ==============================================================================

# OPTIONS method for CORS preflight
resource "aws_api_gateway_method" "classify_intent_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.classify_intent.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "classify_intent_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.classify_intent.id
  http_method = aws_api_gateway_method.classify_intent_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "classify_intent_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.classify_intent.id
  http_method = aws_api_gateway_method.classify_intent_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }

  response_models = {
    "application/json" = "Empty"
  }
}

resource "aws_api_gateway_integration_response" "classify_intent_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.classify_intent.id
  http_method = aws_api_gateway_method.classify_intent_options.http_method
  status_code = aws_api_gateway_method_response.classify_intent_options.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

# ==============================================================================
# API Deployment
# ==============================================================================

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    # Redeploy when any of these resources change
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.classify_intent.id,
      aws_api_gateway_method.classify_intent_post.id,
      aws_api_gateway_integration.classify_intent_lambda.id,
      aws_api_gateway_method.classify_intent_options.id,
      aws_api_gateway_integration.classify_intent_options.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.classify_intent_lambda,
    aws_api_gateway_integration.classify_intent_options,
  ]
}

resource "aws_api_gateway_stage" "main" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = var.environment

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      caller           = "$context.identity.caller"
      user             = "$context.identity.user"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      resourcePath     = "$context.resourcePath"
      status           = "$context.status"
      protocol         = "$context.protocol"
      responseLength   = "$context.responseLength"
      errorMessage     = "$context.error.message"
      integrationError = "$context.integrationErrorMessage"
    })
  }

  xray_tracing_enabled = true

  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-api-stage-${var.environment}"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })

  depends_on = [aws_api_gateway_account.main]
}

# ==============================================================================
# API Gateway Method Settings
# ==============================================================================

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.main.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled        = true
    logging_level          = var.api_logging_level
    data_trace_enabled     = var.environment == "dev" ? true : false
    throttling_burst_limit = var.throttle_burst_limit
    throttling_rate_limit  = var.throttle_rate_limit
  }
}
