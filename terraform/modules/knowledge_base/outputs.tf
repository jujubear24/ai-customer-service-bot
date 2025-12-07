# =============================================================================
# Knowledge Base Module - Outputs (Step 2: S3 & IAM)
# =============================================================================

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
