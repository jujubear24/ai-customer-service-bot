# =============================================================================
# Knowledge Base Module - Outputs
# =============================================================================

# -----------------------------------------------------------------------------
# Knowledge Base Outputs
# -----------------------------------------------------------------------------

output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.arn
}

output "knowledge_base_name" {
  description = "Name of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.name
}

output "data_source_id" {
  description = "ID of the S3 data source"
  value       = aws_bedrockagent_data_source.s3.data_source_id
}

# -----------------------------------------------------------------------------
# S3 Bucket Outputs
# -----------------------------------------------------------------------------

output "s3_bucket_name" {
  description = "Name of the S3 bucket for knowledge base documents"
  value       = aws_s3_bucket.knowledge_base.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket for knowledge base documents"
  value       = aws_s3_bucket.knowledge_base.arn
}

output "s3_bucket_domain_name" {
  description = "Domain name of the S3 bucket"
  value       = aws_s3_bucket.knowledge_base.bucket_domain_name
}

# -----------------------------------------------------------------------------
# IAM Role Outputs
# -----------------------------------------------------------------------------

output "bedrock_kb_role_arn" {
  description = "ARN of the IAM role used by Bedrock Knowledge Base"
  value       = aws_iam_role.bedrock_kb.arn
}

output "bedrock_kb_role_name" {
  description = "Name of the IAM role used by Bedrock Knowledge Base"
  value       = aws_iam_role.bedrock_kb.name
}

output "rag_retriever_role_arn" {
  description = "ARN of the IAM role for RAG Retriever Lambda"
  value       = aws_iam_role.rag_retriever.arn
}

output "rag_retriever_role_name" {
  description = "Name of the IAM role for RAG Retriever Lambda"
  value       = aws_iam_role.rag_retriever.name
}

# -----------------------------------------------------------------------------
# VPC Outputs
# -----------------------------------------------------------------------------

output "vpc_id" {
  description = "VPC ID (created or provided)"
  value       = local.vpc_id
}

output "subnet_ids" {
  description = "Subnet IDs used by Aurora"
  value       = local.subnet_ids
}

output "aurora_security_group_id" {
  description = "Security group ID for Aurora cluster"
  value       = aws_security_group.aurora.id
}

# -----------------------------------------------------------------------------
# Aurora PostgreSQL Outputs
# -----------------------------------------------------------------------------

output "aurora_cluster_id" {
  description = "Aurora cluster identifier"
  value       = aws_rds_cluster.knowledge_base.id
}

output "aurora_cluster_arn" {
  description = "Aurora cluster ARN"
  value       = aws_rds_cluster.knowledge_base.arn
}

output "aurora_cluster_endpoint" {
  description = "Aurora cluster writer endpoint"
  value       = aws_rds_cluster.knowledge_base.endpoint
}

output "aurora_cluster_reader_endpoint" {
  description = "Aurora cluster reader endpoint"
  value       = aws_rds_cluster.knowledge_base.reader_endpoint
}

output "aurora_cluster_port" {
  description = "Aurora cluster port"
  value       = aws_rds_cluster.knowledge_base.port
}

output "aurora_database_name" {
  description = "Aurora database name"
  value       = aws_rds_cluster.knowledge_base.database_name
}

output "aurora_cluster_resource_id" {
  description = "Aurora cluster resource ID (for IAM auth)"
  value       = aws_rds_cluster.knowledge_base.cluster_resource_id
}

# -----------------------------------------------------------------------------
# Secrets Manager Outputs
# -----------------------------------------------------------------------------

output "aurora_credentials_secret_arn" {
  description = "ARN of the Secrets Manager secret containing Aurora credentials"
  value       = aws_secretsmanager_secret.aurora_credentials.arn
}

output "aurora_credentials_secret_name" {
  description = "Name of the Secrets Manager secret containing Aurora credentials"
  value       = aws_secretsmanager_secret.aurora_credentials.name
}

# -----------------------------------------------------------------------------
# Configuration Outputs (for Lambda environment variables)
# -----------------------------------------------------------------------------

output "lambda_environment_variables" {
  description = "Environment variables for RAG Retriever Lambda"
  value = {
    KNOWLEDGE_BASE_ID = aws_bedrockagent_knowledge_base.main.id
    AWS_REGION        = local.region
  }
}

# -----------------------------------------------------------------------------
# Embedding Configuration Outputs
# -----------------------------------------------------------------------------

output "embedding_model_id" {
  description = "ID of the embedding model used"
  value       = var.embedding_model_id
}

output "embedding_dimensions" {
  description = "Vector dimensions used for embeddings"
  value       = var.embedding_dimensions
}
