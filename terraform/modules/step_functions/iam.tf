# ==============================================================================
# IAM Role for Step Functions
# ==============================================================================

resource "aws_iam_role" "step_functions" {
  name = "${var.project_name}-step-functions-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:states:${var.region}:${var.account_id}:stateMachine:*"
          }
        }
      }
    ]
  })

  tags = merge(local.default_tags, var.tags, {
    Name = "${var.project_name}-step-functions-role-${var.environment}"
  })
}

# ==============================================================================
# Lambda Invocation Policy
# ==============================================================================

resource "aws_iam_role_policy" "step_functions_lambda" {
  name = "lambda-invoke"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeLambdaFunctions"
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          var.intent_classifier_arn,
          var.context_builder_arn,
          var.rag_retriever_arn,
          var.bedrock_handler_arn,
          var.response_validator_arn,
          var.escalation_router_arn,
          # Include qualified ARNs for versioned invocations
          "${var.intent_classifier_arn}:*",
          "${var.context_builder_arn}:*",
          "${var.rag_retriever_arn}:*",
          "${var.bedrock_handler_arn}:*",
          "${var.response_validator_arn}:*",
          "${var.escalation_router_arn}:*"
        ]
      }
    ]
  })
}

# ==============================================================================
# CloudWatch Logging Policy
# ==============================================================================

resource "aws_iam_role_policy" "step_functions_logging" {
  name = "cloudwatch-logging"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogsDelivery"
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogsPut"
        Effect = "Allow"
        Action = [
          "logs:PutLogEvents",
          "logs:CreateLogStream",
          "logs:DescribeLogStreams"
        ]
        Resource = "${aws_cloudwatch_log_group.step_functions.arn}:*"
      },
      {
        Sid    = "CloudWatchLogsDescribe"
        Effect = "Allow"
        Action = [
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      }
    ]
  })
}

# ==============================================================================
# X-Ray Tracing Policy
# ==============================================================================

resource "aws_iam_role_policy" "step_functions_xray" {
  name = "xray-tracing"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "XRayTracing"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets"
        ]
        Resource = "*"
      }
    ]
  })
}
