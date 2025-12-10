# Phase 2.2: Knowledge Base RAG Integration Guide

This guide covers deploying and testing the Knowledge Base for Amazon Bedrock (RAG) integration.

## Architecture Overview

```bash
┌─────────────────┐     ┌───────────────────┐     ┌─────────────────────┐
│   API Gateway   │────▶│  RAG Retriever    │────▶│  Bedrock Knowledge  │
│                 │     │  Lambda           │     │  Base API           │
└─────────────────┘     └───────────────────┘     └─────────────────────┘
                                │                          │
                                │                          ▼
                                │                 ┌─────────────────────┐
                                │                 │  Aurora PostgreSQL  │
                                │                 │  (pgvector)         │
                                │                 └─────────────────────┘
                                ▼
                        ┌───────────────────┐
                        │  Bedrock Handler  │
                        │  Lambda           │
                        │  (rag_context)    │
                        └───────────────────┘
```

## Prerequisites

- AWS CLI configured with appropriate permissions
- Terraform >= 1.5.0
- uv package manager
- Bedrock model access enabled (Claude Haiku, Titan Embeddings V2)

## Deployment Steps

### 1. Set Aurora Password

Create a `terraform.tfvars` file (do NOT commit this):

```bash
cd terraform/environments/dev
echo 'aurora_master_password = "YourSecurePassword123!"' > terraform.tfvars
```

### 2. Deploy Infrastructure

```bash
cd terraform/environments/dev

# Initialize modules
terraform init

# Review changes
terraform plan

# Deploy
terraform apply
```

**Expected resources:**

- S3 bucket for knowledge base documents
- Aurora PostgreSQL Serverless v2 cluster
- Bedrock Knowledge Base
- RAG Retriever Lambda function
- IAM roles and policies

### 3. Upload Knowledge Base Documents

```bash
# From project root
./scripts/sync-knowledge-base.sh
```

Or manually:

```bash
# Get outputs
cd terraform/environments/dev
BUCKET=$(terraform output -raw s3_bucket_name)
KB_ID=$(terraform output -raw knowledge_base_id)
DS_ID=$(terraform output -raw data_source_id)

# Upload documents
aws s3 sync ./knowledge-base-docs/faqs/ s3://$BUCKET/faqs/
aws s3 sync ./knowledge-base-docs/docs/ s3://$BUCKET/docs/

# Trigger ingestion
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id $KB_ID \
  --data-source-id $DS_ID
```

### 4. Verify Ingestion

```bash
# Check job status
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id $KB_ID \
  --data-source-id $DS_ID
```

Wait for status: `COMPLETE`

## Testing

### Test RAG Retriever Lambda

```bash
# Get function name
FUNCTION=$(terraform output -raw rag_retriever_function_name)

# Invoke directly
aws lambda invoke \
  --function-name $FUNCTION \
  --payload '{
    "query": "How do I reset my password?",
    "tenant_id": "test-tenant",
    "top_k": 3
  }' \
  --cli-binary-format raw-in-base64-out \
  response.json

# View response
cat response.json | jq .
```

**Expected response:**

```json
{
  "statusCode": 200,
  "body": "{\"documents\":[{\"content\":\"To reset your password...\",\"score\":0.92,...}],\"query\":\"How do I reset my password?\",\"total_found\":3,\"retrieval_time_ms\":125.5}",
  "headers": {"Content-Type": "application/json"}
}
```

### Test End-to-End Flow (RAG → Bedrock Handler)

```python
#!/usr/bin/env python3
"""Test end-to-end RAG flow."""

import json
import boto3

lambda_client = boto3.client("lambda")

# Step 1: Retrieve context
rag_response = lambda_client.invoke(
    FunctionName="your-project-rag-retriever-dev",
    Payload=json.dumps({
        "query": "What is your refund policy?",
        "tenant_id": "test-tenant",
        "top_k": 3,
        "min_score": 0.5,
    }),
)

rag_result = json.loads(rag_response["Payload"].read())
rag_body = json.loads(rag_result["body"])

# Extract rag_context
rag_context = [
    f"[Source: {doc['source_name']}]\n{doc['content']}"
    for doc in rag_body["documents"]
]

print(f"Retrieved {len(rag_context)} documents")

# Step 2: Call Bedrock Handler with RAG context
bedrock_response = lambda_client.invoke(
    FunctionName="your-project-bedrock-handler-dev",
    Payload=json.dumps({
        "conversation_id": "test-conv-123",
        "user_message": "What is your refund policy?",
        "rag_context": rag_context,
    }),
)

bedrock_result = json.loads(bedrock_response["Payload"].read())
print(f"AI Response: {bedrock_result['response_text']}")
```

## Integration with Existing Flow

The RAG Retriever integrates with the Bedrock Handler via the `rag_context` field:

```python
# In your orchestrator/API handler:

# 1. Get RAG context (optional, based on intent)
rag_context = None
if intent in ["question", "technical_support", "shipping"]:
    rag_response = invoke_rag_retriever(user_query, tenant_id)
    if rag_response["documents"]:
        rag_context = rag_response["rag_context"]

# 2. Call Bedrock Handler
response = invoke_bedrock_handler(
    conversation_id=conversation_id,
    user_message=user_message,
    rag_context=rag_context,  # Injected into prompt
)
```

## Monitoring

### CloudWatch Metrics

The RAG Retriever emits these metrics:

| Metric | Description |
|--------|-------------|
| `DocumentsRetrieved` | Number of documents returned |
| `RetrievalLatency` | Time to retrieve documents (ms) |
| `AverageRelevanceScore` | Mean relevance score |
| `NoResultsReturned` | Count of queries with no results |
| `ValidationErrors` | Invalid request count |
| `ThrottlingErrors` | Rate limit errors |
| `ServiceErrors` | Backend service errors |

### CloudWatch Logs

```bash
# View recent logs
aws logs tail /aws/lambda/your-project-rag-retriever-dev --follow
```

### X-Ray Tracing

The RAG Retriever integrates with X-Ray for distributed tracing. View traces in the AWS X-Ray console.

## Troubleshooting

### "Knowledge base not found" (404)

- Verify `KNOWLEDGE_BASE_ID` environment variable
- Check Knowledge Base exists: `aws bedrock-agent list-knowledge-bases`

### Low relevance scores

- Verify documents are ingested: Check ingestion job status
- Try adjusting `min_score` threshold (default: 0.5)
- Review document quality and chunking strategy

### "No results returned"

- Check S3 bucket has documents in correct prefixes (`faqs/`, `docs/`)
- Verify ingestion job completed successfully
- Try broader search terms

### Aurora connection errors

- Check Aurora cluster status in RDS console
- Verify security group allows inbound on port 5432
- Check Secrets Manager secret has correct credentials

## Cost Optimization

### Aurora Serverless v2

- **Minimum**: 0.5 ACU (~$0.06/hour when active)
- **Auto-pause**: Consider enabling for dev (not yet implemented)
- **Scaling**: Adjust `aurora_max_capacity` based on load

### Bedrock Knowledge Base

- **Embeddings**: ~$0.02 per 1M tokens (one-time ingestion)
- **Retrieval**: ~$0.00002 per query (negligible)

## Next Steps

1. **Phase 2.3**: Add orchestrator Lambda to coordinate RAG + Bedrock flow
2. **Phase 3**: Implement conversation memory with DynamoDB
3. **Phase 4**: Add streaming responses
4. **Phase 5**: Production hardening (VPC, WAF, etc.)

## Related Documentation

- [ADR-010: Knowledge Base RAG Architecture](../adr/ADR-010-knowledge-base-rag.md)
- [AWS Bedrock Knowledge Base Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Aurora PostgreSQL pgvector](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html)
