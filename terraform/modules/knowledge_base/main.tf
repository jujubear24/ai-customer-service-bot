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

# =============================================================================
# VPC Configuration (for Aurora)
# =============================================================================

# Use existing VPC or create a simple one for the knowledge base
data "aws_vpc" "selected" {
  count = var.vpc_id != null ? 1 : 0
  id    = var.vpc_id
}

resource "aws_vpc" "knowledge_base" {
  count = var.vpc_id == null ? 1 : 0

  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-kb-vpc"
  })
}

locals {
  vpc_id = var.vpc_id != null ? var.vpc_id : aws_vpc.knowledge_base[0].id
}

# Private subnets for Aurora (need at least 2 AZs)
data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "private" {
  count = var.vpc_id == null ? 2 : 0

  vpc_id            = local.vpc_id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-kb-private-${count.index + 1}"
    Type = "private"
  })
}

locals {
  subnet_ids = var.vpc_id != null ? var.subnet_ids : aws_subnet.private[*].id
}

# =============================================================================
# Security Group for Aurora
# =============================================================================

resource "aws_security_group" "aurora" {
  name        = "${local.name_prefix}-aurora-kb-sg"
  description = "Security group for Knowledge Base Aurora cluster"
  vpc_id      = local.vpc_id

  # Ingress from Bedrock service (managed by AWS)
  # Bedrock accesses Aurora via AWS PrivateLink internally
  ingress {
    description = "PostgreSQL from VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.vpc_id != null ? [data.aws_vpc.selected[0].cidr_block] : ["10.0.0.0/16"]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-kb-sg"
  })
}

# =============================================================================
# Aurora PostgreSQL Serverless v2
# =============================================================================

resource "aws_db_subnet_group" "aurora" {
  name        = "${local.name_prefix}-kb-subnet-group"
  description = "Subnet group for Knowledge Base Aurora cluster"
  subnet_ids  = local.subnet_ids

  tags = local.common_tags
}

resource "aws_rds_cluster" "knowledge_base" {
  cluster_identifier = "${local.name_prefix}-kb-cluster"

  engine         = "aurora-postgresql"
  engine_mode    = "provisioned"
  engine_version = var.aurora_engine_version

  database_name   = var.aurora_database_name
  master_username = var.aurora_master_username
  master_password = var.aurora_master_password

  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [aws_security_group.aurora.id]

  # Serverless v2 scaling configuration
  serverlessv2_scaling_configuration {
    min_capacity = var.aurora_min_capacity
    max_capacity = var.aurora_max_capacity
  }

  # Storage encryption
  storage_encrypted = true

  # Backup configuration
  backup_retention_period = var.environment == "prod" ? 7 : 1
  preferred_backup_window = "03:00-04:00"

  # Skip final snapshot in non-prod
  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${local.name_prefix}-kb-final-snapshot" : null

  # Allow deletion in non-prod
  deletion_protection = var.environment == "prod"

  # Enable IAM authentication for Bedrock
  iam_database_authentication_enabled = true

  tags = local.common_tags
}

resource "aws_rds_cluster_instance" "knowledge_base" {
  identifier         = "${local.name_prefix}-kb-instance"
  cluster_identifier = aws_rds_cluster.knowledge_base.id

  instance_class = "db.serverless"
  engine         = aws_rds_cluster.knowledge_base.engine
  engine_version = aws_rds_cluster.knowledge_base.engine_version

  # Performance insights (free tier for 7 days retention)
  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  tags = local.common_tags
}

# =============================================================================
# IAM Policy for Bedrock KB to Access Aurora
# =============================================================================

resource "aws_iam_role_policy" "bedrock_kb_rds" {
  name = "${local.name_prefix}-bedrock-kb-rds"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBClusters",
          "rds:DescribeDBInstances"
        ]
        Resource = [
          aws_rds_cluster.knowledge_base.arn,
          aws_rds_cluster_instance.knowledge_base.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "rds-db:connect"
        ]
        Resource = [
          "arn:aws:rds-db:${local.region}:${local.account_id}:dbuser:${aws_rds_cluster.knowledge_base.cluster_resource_id}/*"
        ]
      }
    ]
  })
}

# =============================================================================
# Secrets Manager for Aurora Credentials (for Bedrock KB)
# =============================================================================

resource "aws_secretsmanager_secret" "aurora_credentials" {
  name        = "${local.name_prefix}-kb-aurora-credentials"
  description = "Credentials for Knowledge Base Aurora cluster"

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "aurora_credentials" {
  secret_id = aws_secretsmanager_secret.aurora_credentials.id

  secret_string = jsonencode({
    username = var.aurora_master_username
    password = var.aurora_master_password
    host     = aws_rds_cluster.knowledge_base.endpoint
    port     = aws_rds_cluster.knowledge_base.port
    dbname   = var.aurora_database_name
    engine   = "postgres"
  })
}

# Allow Bedrock to read the secret
resource "aws_iam_role_policy" "bedrock_kb_secrets" {
  name = "${local.name_prefix}-bedrock-kb-secrets"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.aurora_credentials.arn
        ]
      }
    ]
  })
}
