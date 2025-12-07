# ADR-010: Knowledge Base for Amazon Bedrock (RAG)

**Status**: Accepted
**Date**: 2025-12-07
**Deciders:** Senior Cloud Architect, Development Team

## Context

Our AI Customer Service Bot needs to provide accurate, up-to-date responses based on company-specific knowledge (FAQs, product documentation, policies, troubleshooting guides).
The Bedrock Handler Lambda (Phase 2.1) already supports RAG context injection via the `rag_context` field, but we need to implement the knowledge retrieval infrastructure.

### Requirements

1. **Semantic Search**: Find relevant documents based on meaning, not just keywords
2. **Low Latency**: Retrieval must complete within ~500ms to maintain acceptable response times
3. **Serverless**: Align with existing serverless architecture (no server management)
4. **Cost-Effective**: Minimize costs for dev/staging environments
5. **Scalable**: Handle production traffic without manual scaling
6. **Maintainable**: Easy to update knowledge base content

### Options Evaluated

#### Vector Store Options

| Option | Pros | Cons |
|--------|------|------|
| **Aurora PostgreSQL Serverless v2 (pgvector)** | Native Bedrock KB integration, auto-scaling 0.5-128 ACUs, cost-effective (~$15-50/month), can auto-pause | Slightly more setup than OpenSearch |
| **OpenSearch Serverless** | Native AWS integration, fully managed, auto-scaling | High base cost (~$350/month minimum for 2 OCUs) |
| **Pinecone** | Purpose-built for vectors, excellent performance, free tier | External dependency, data residency concerns |
| **MongoDB Atlas** | Flexible document model | External dependency, additional complexity |

#### Embedding Model Options

| Model | Dimensions | Max Tokens | Pros | Cons |
|-------|------------|------------|------|------|
| **Titan Embeddings V2** | 256/512/1024 | 8,192 | Configurable dimensions, cost-effective | Newer, less battle-tested |
| **Titan Embeddings G1** | 1,536 | 8,192 | Well-established, good quality | Fixed dimensions, higher storage cost |
| **Cohere Embed English v3** | 1,024 | 512 | High quality for English | Lower token limit, additional cost |

#### Chunking Strategy Options

| Strategy | Use Case | Pros | Cons |
|----------|----------|------|------|
| **Fixed Size** | General documents | Predictable, simple | May split mid-sentence |
| **Semantic** | Natural language docs | Preserves meaning | More complex, variable sizes |
| **Hierarchical** | Structured docs | Parent-child relationships | Complex retrieval logic |
| **None** | Pre-chunked content | Full control | Requires pre-processing |

## Decision

### 1. Vector Store: Aurora PostgreSQL Serverless v2 with pgvector

**Choice**: Aurora PostgreSQL Serverless v2 with pgvector extension

**Rationale**:

- Native integration with Bedrock Knowledge Bases (zero custom embedding code)
- Cost-effective: ~$15-50/month vs ~$350/month for OpenSearch Serverless
- Auto-scaling from 0.5 to 128 ACUs based on demand
- Can auto-pause during inactivity (dev environments can approach $0)
- PostgreSQL familiarity for debugging and ad-hoc queries
- Reusable for other application data if needed
- AWS-native security (IAM, encryption at rest/in transit)

**Configuration**:

```bash
min_capacity = 0.5  # Minimum ACUs (cost savings)
max_capacity = 4    # Maximum ACUs for dev (scale up for prod)
auto_pause   = true # Pause after 5 min inactivity (dev only)
```

### 2. Embedding Model: Amazon Titan Text Embeddings V2

**Choice**: `amazon.titan-embed-text-v2:0` with 512 dimensions

**Rationale**:

- Configurable dimensions (512 balances quality vs. storage/cost)
- 8,192 token context window (sufficient for most FAQ/doc chunks)
- Native AWS service (no cross-account/external API calls)
- Cost-effective: $0.00002 per 1,000 input tokens
- Good multilingual support for future expansion

### 3. Chunking Strategy: Semantic Chunking

**Choice**: Semantic chunking with 300-token target, 20% overlap

**Rationale**:

- Customer service content is conversational/natural language
- Preserves complete thoughts and answers
- Overlap ensures context isn't lost at boundaries
- Bedrock KB handles chunking automatically (no custom code)

**Configuration**:

```toml
chunking_configuration {
  chunking_strategy = "SEMANTIC"
  semantic_chunking_configuration {
    max_tokens = 300
    buffer_size = 1  # sentences of overlap
    breakpoint_percentile_threshold = 95
  }
}
```

### 4. Architecture Pattern: Dedicated RAG Retriever Lambda

**Choice**: Separate `rag-retriever` Lambda function

**Rationale**:

- **Single Responsibility**: Retrieval logic isolated from generation
- **Testability**: Can test retrieval quality independently
- **Flexibility**: Can swap retrieval strategies without touching Bedrock Handler
- **Caching**: Can implement retrieval caching at this layer
- **Observability**: Clear metrics for retrieval latency vs. generation latency

**Integration Flow**:

```bash
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  API Gateway    │────▶│  RAG Retriever  │────▶│ Bedrock Handler │
│                 │     │     Lambda      │     │     Lambda      │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────▼────────┐
                        │ Bedrock KB API  │
                        │   (Retrieve)    │
                        └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │ Aurora Postgres │
                        │   (pgvector)    │
                        └─────────────────┘
```

### 5. Data Source Structure

**Choice**: S3 bucket with prefix-based organization

```bash
s3://ai-customer-service-kb-{env}/
├── faqs/
│   ├── general-faqs.md
│   ├── billing-faqs.md
│   └── technical-faqs.md
├── docs/
│   ├── product-guide.md
│   ├── troubleshooting.md
│   └── policies/
│       ├── refund-policy.md
│       └── privacy-policy.md
└── metadata/
    └── source-metadata.json
```

**Rationale**:

- Markdown format for human readability and easy editing
- Prefix structure enables selective syncing
- Metadata file for source attribution in responses

## Consequences

### Positive

- **Cost-Effective**: ~$15-50/month vs ~$350/month for OpenSearch Serverless (90% savings)
- **Native Integration**: Bedrock KB handles embedding, chunking, indexing automatically
- **Familiar Technology**: PostgreSQL + SQL for debugging and ad-hoc queries
- **Flexible Scaling**: Auto-scales from 0.5 to 128 ACUs based on demand
- **Auto-Pause**: Dev environments can pause during inactivity (near $0 cost)
- **Observable**: CloudWatch metrics for retrieval latency, relevance scores
- **Reusable**: Aurora cluster can serve other application needs

### Negative

- **Cold Start**: Auto-pause resume takes ~30 seconds (acceptable for dev)
- **Slightly More Setup**: Need to enable pgvector extension, create index
- **Vendor Lock-in**: Tight coupling to AWS Bedrock ecosystem
- **Not Hybrid Search**: pgvector does vector search only (no keyword fallback)

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Aurora cold starts | Disable auto-pause in prod; accept for dev |
| Poor retrieval quality | Iterative tuning of chunk size, overlap, top-k |
| Cost overrun | CloudWatch billing alerts; ACU monitoring |
| Stale knowledge | Automated sync on S3 changes; version tracking |

## Implementation Plan

### Phase 2.2 Milestones

1. **Terraform Module** (`knowledge_base/`)
   - S3 bucket for documents
   - Aurora PostgreSQL Serverless v2 cluster with pgvector
   - Bedrock Knowledge Base resource
   - IAM roles and policies

2. **Sample Knowledge Content**
   - 5-10 FAQ documents (Markdown)
   - 2-3 policy documents
   - Test queries for validation

3. **RAG Retriever Lambda**
   - Bedrock KB retrieve API integration
   - Relevance score filtering
   - Response formatting for Bedrock Handler

4. **Integration Testing**
   - End-to-end retrieval tests
   - Latency benchmarks
   - Relevance quality assessment

## References

- [Amazon Bedrock Knowledge Bases Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Aurora PostgreSQL pgvector Integration](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html)
- [Titan Embeddings V2 Model Card](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html)
- [ADR-009: Bedrock Integration (Phase 2.1)](./009-bedrock-integration.md)
