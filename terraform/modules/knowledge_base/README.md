# Knowledge Base Module

This Terraform module creates an Amazon Bedrock Knowledge Base with Aurora PostgreSQL Serverless v2 (pgvector) as the vector store.

## Architecture

```bash
┌─────────────────────────────────────────────────────────────────────────┐
│                        Knowledge Base Architecture                       │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────────┐     ┌───────────────────────┐
│   S3 Bucket  │────▶│  Bedrock KB      │────▶│  Aurora PostgreSQL    │
│  (Documents) │     │  (Data Source)   │     │  Serverless v2        │
└──────────────┘     └──────────────────┘     │  (pgvector)           │
                              │               └───────────────────────┘
                              │
                     ┌────────▼────────┐
                     │  Titan Embed V2  │
                     │  (Embeddings)    │
                     └─────────────────┘
```

## Resources Created

| Resource | Description |
|----------|-------------|
| `aws_s3_bucket` | S3 bucket for knowledge base documents |
| `aws_vpc` | VPC for Aurora (optional - uses existing if provided) |
| `aws_subnet` | Private subnets for Aurora (x2) |
| `aws_security_group` | Security group for Aurora |
| `aws_rds_cluster` | Aurora PostgreSQL Serverless v2 cluster |
| `aws_rds_cluster_instance` | Aurora Serverless v2 instance |
| `aws_secretsmanager_secret` | Credentials for Bedrock KB to access Aurora |
| `aws_bedrockagent_knowledge_base` | Bedrock Knowledge Base |
| `aws_bedrockagent_data_source` | S3 data source configuration |
| `aws_iam_role` (x2) | Roles for Bedrock KB and RAG Retriever Lambda |

## Usage

```hcl
module "knowledge_base" {
  source = "../../modules/knowledge_base"

  project_name = "my-service"
  environment  = "dev"

  # Aurora credentials (use secrets or tfvars)
  aurora_master_password = var.aurora_master_password

  # Embedding configuration
  embedding_model_id   = "amazon.titan-embed-text-v2:0"
  embedding_dimensions = 512  # 256, 512, or 1024

  # S3 data source
  s3_inclusion_prefixes = ["faqs/", "docs/"]

  # Aurora capacity (serverless v2)
  aurora_min_capacity = 0.5  # Minimum ACUs
  aurora_max_capacity = 4    # Maximum ACUs for dev

  # Chunking (semantic recommended for natural language)
  chunking_strategy            = "SEMANTIC"
  semantic_chunking_max_tokens = 300
  semantic_chunking_buffer_size = 1

  tags = {
    Team = "platform"
  }
}
```

## Using an Existing VPC

```hcl
module "knowledge_base" {
  source = "../../modules/knowledge_base"

  # ... other variables ...

  # Use existing VPC
  vpc_id     = "vpc-0123456789abcdef0"
  subnet_ids = ["subnet-111111", "subnet-222222"]
}
```

## Inputs

### Required

| Name | Description | Type |
|------|-------------|------|
| `project_name` | Project name for resource naming | `string` |
| `environment` | Environment (dev/staging/prod) | `string` |
| `aurora_master_password` | Master password for Aurora (sensitive) | `string` |

### Optional - General

| Name | Description | Default |
|------|-------------|---------|
| `tags` | Additional tags for resources | `{}` |

### Optional - VPC

| Name | Description | Default |
|------|-------------|---------|
| `vpc_id` | Existing VPC ID (creates new if null) | `null` |
| `subnet_ids` | Subnet IDs for Aurora (required if vpc_id set) | `[]` |

### Optional - Aurora

| Name | Description | Default |
|------|-------------|---------|
| `aurora_engine_version` | PostgreSQL version (15.4+ for pgvector) | `15.4` |
| `aurora_database_name` | Database name | `knowledgebase` |
| `aurora_master_username` | Master username | `kbadmin` |
| `aurora_min_capacity` | Minimum ACUs (0.5-128) | `0.5` |
| `aurora_max_capacity` | Maximum ACUs (0.5-128) | `4` |

### Optional - Embeddings

| Name | Description | Default |
|------|-------------|---------|
| `embedding_model_id` | Bedrock embedding model | `amazon.titan-embed-text-v2:0` |
| `embedding_dimensions` | Vector dimensions (256/512/1024) | `512` |

### Optional - Chunking

| Name | Description | Default |
|------|-------------|---------|
| `chunking_strategy` | NONE, FIXED_SIZE, SEMANTIC, HIERARCHICAL | `SEMANTIC` |
| `semantic_chunking_max_tokens` | Max tokens per chunk | `300` |
| `semantic_chunking_buffer_size` | Sentence overlap | `1` |
| `semantic_chunking_breakpoint_threshold` | Breakpoint percentile | `95` |

See `variables.tf` for all available inputs.

## Outputs

| Name | Description |
|------|-------------|
| `knowledge_base_id` | ID of the Bedrock Knowledge Base |
| `knowledge_base_arn` | ARN of the Bedrock Knowledge Base |
| `data_source_id` | ID of the S3 data source |
| `s3_bucket_name` | Name of the S3 bucket |
| `aurora_cluster_endpoint` | Aurora cluster endpoint |
| `rag_retriever_role_arn` | IAM role ARN for RAG Retriever Lambda |
| `lambda_environment_variables` | Environment variables for Lambda |

## Uploading Documents

After deployment, upload documents to the S3 bucket:

```bash
# Get bucket name
BUCKET=$(terraform output -raw s3_bucket_name)

# Upload FAQs
aws s3 sync ./faqs/ s3://$BUCKET/faqs/

# Upload documentation
aws s3 sync ./docs/ s3://$BUCKET/docs/

# Trigger sync
KB_ID=$(terraform output -raw knowledge_base_id)
DS_ID=$(terraform output -raw data_source_id)

aws bedrock-agent start-ingestion-job \
  --knowledge-base-id $KB_ID \
  --data-source-id $DS_ID
```

## Setting Up pgvector

Bedrock automatically creates the pgvector extension and table. If you need to manually set up:

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create embeddings table (Bedrock does this automatically)
CREATE TABLE IF NOT EXISTS bedrock_knowledge_base (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding vector(512),
  content TEXT,
  metadata JSONB
);

-- Create HNSW index for fast similarity search
CREATE INDEX ON bedrock_knowledge_base
  USING hnsw (embedding vector_cosine_ops);
```

## Cost Estimates

### Aurora Serverless v2

- **Per ACU-hour**: ~$0.12
- **Minimum (0.5 ACU)**: ~$44/month if always on
- **Typical dev usage**: ~$15-30/month with variable load

### Embeddings (Titan V2)

- **Per 1M input tokens**: $0.02
- **One-time ingestion**: Depends on document size
- **Per query**: ~$0.00002 (negligible)

### Total Dev Environment

- **Estimated**: $15-50/month (much less than OpenSearch Serverless ~$350/month)

## Troubleshooting

### "Database connection failed" error

1. Verify security group allows port 5432 from VPC CIDR
2. Check Secrets Manager secret has correct credentials
3. Ensure Aurora cluster is in "Available" state

### "pgvector extension not found"

Aurora PostgreSQL 15.4+ includes pgvector. Bedrock enables it automatically during KB creation.

### Documents not appearing in search

1. Check ingestion job status in AWS Console
2. Verify documents are in the correct S3 prefix
3. Check document format is supported (MD, TXT, PDF, DOCX, HTML)

### Low relevance scores

1. Try increasing `semantic_chunking_max_tokens`
2. Adjust `embedding_dimensions` (higher = more precision)
3. Review document quality and structure

## Related ADRs

- [ADR-010: Knowledge Base for Amazon Bedrock (RAG)](../../../docs/adr/ADR-010-knowledge-base-rag.md)
