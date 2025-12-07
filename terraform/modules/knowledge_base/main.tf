# =============================================================================
# Knowledge Base for Amazon Bedrock - Main Configuration
# =============================================================================
# This module creates:
# - S3 bucket for knowledge base documents
# - Aurora PostgreSQL Serverless v2 with pgvector (vector store)
# - Amazon Bedrock Knowledge Base
# - Required IAM roles and policies
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.id

  # Resource naming
  name_prefix = "${var.project_name}-${var.environment}"

  # Common tags
  common_tags = merge(var.tags, {
    Module      = "knowledge_base"
    Environment = var.environment
    Project     = var.project_name
  })
}

# =============================================================================
# S3 Bucket for Knowledge Base Documents
# =============================================================================

resource "aws_s3_bucket" "knowledge_base" {
  bucket        = "${local.name_prefix}-knowledge-base-${local.account_id}"
  force_destroy = var.environment != "prod" # Allow destroy in non-prod

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-knowledge-base"
  })
}

resource "aws_s3_bucket_versioning" "knowledge_base" {
  bucket = aws_s3_bucket.knowledge_base.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "knowledge_base" {
  bucket = aws_s3_bucket.knowledge_base.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "knowledge_base" {
  bucket = aws_s3_bucket.knowledge_base.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "knowledge_base" {
  bucket = aws_s3_bucket.knowledge_base.id

  rule {
    id     = "cleanup-old-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = var.s3_version_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# =============================================================================
# IAM Role for Bedrock Knowledge Base
# =============================================================================

resource "aws_iam_role" "bedrock_kb" {
  name = "${local.name_prefix}-bedrock-kb-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = local.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:bedrock:${local.region}:${local.account_id}:knowledge-base/*"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# S3 access policy for Bedrock KB
resource "aws_iam_role_policy" "bedrock_kb_s3" {
  name = "${local.name_prefix}-bedrock-kb-s3"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.knowledge_base.arn,
          "${aws_s3_bucket.knowledge_base.arn}/*"
        ]
      }
    ]
  })
}

# Bedrock model access policy (for embeddings)
resource "aws_iam_role_policy" "bedrock_kb_model" {
  name = "${local.name_prefix}-bedrock-kb-model"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:${local.region}::foundation-model/${var.embedding_model_id}",
          "arn:aws:bedrock:*::foundation-model/${var.embedding_model_id}"
        ]
      }
    ]
  })
}

# =============================================================================
# IAM Role for RAG Retriever Lambda
# =============================================================================

resource "aws_iam_role" "rag_retriever" {
  name = "${local.name_prefix}-rag-retriever-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

# Basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "rag_retriever_basic" {
  role       = aws_iam_role.rag_retriever.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# X-Ray tracing policy
resource "aws_iam_role_policy_attachment" "rag_retriever_xray" {
  role       = aws_iam_role.rag_retriever.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# Note: Bedrock KB retrieval policy will be added in Step 4 after KB is created
