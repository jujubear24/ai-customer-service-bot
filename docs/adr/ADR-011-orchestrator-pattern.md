# ADR-011: Chat Orchestrator Pattern

**Date:** 2025-12-10
**Status:** Accepted


## Context

Phase 2.1 delivered the Bedrock Handler Lambda for AI response generation, and Phase 2.2 delivered the RAG Retriever Lambda for knowledge base retrieval.
These components work independently but need to be connected to provide a complete conversational AI experience.

### Current State

```bash
API Gateway → Individual Lambda endpoints
                ├── POST /classify-intent → Intent Classifier
                ├── POST /context → Context Builder
                ├── POST /retrieve → RAG Retriever
                └── POST /generate → Bedrock Handler
```

### Problem

- No unified endpoint for chat interactions
- Client must orchestrate multiple API calls
- No coordination between RAG retrieval and response generation
- Duplicated error handling across clients

### Options Considered

#### Option A: Client-Side Orchestration

Client makes sequential calls: RAG → Bedrock → Store

**Pros:** Simple backend, flexible client control
**Cons:** Multiple round trips, complex client logic, inconsistent error handling

#### Option B: API Gateway + Step Functions

API Gateway triggers Step Functions state machine

**Pros:** Visual workflow, built-in retries, full observability
**Cons:** Cold start latency (~200-500ms), overkill for simple flow, Phase 4 scope

#### Option C: Lightweight Orchestrator Lambda

Single Lambda coordinates RAG → Bedrock flow

**Pros:** Single API call, ~50ms overhead, simple to implement, testable
**Cons:** Another Lambda to maintain, not as flexible as Step Functions

## Decision

### Option C: Lightweight Orchestrator Lambda**

Create a `chat-orchestrator` Lambda that:

1. Receives user message
2. Invokes RAG Retriever (if knowledge base lookup needed)
3. Invokes Bedrock Handler with RAG context
4. Returns unified response

### Rationale

- **Simplicity**: Straightforward request → response flow
- **Performance**: Lambda-to-Lambda invoke is fast (~50-100ms)
- **Incremental**: Easy to migrate to Step Functions in Phase 4
- **Testability**: Can mock downstream Lambdas in unit tests
- **User Experience**: Single API endpoint for chat

## Architecture

### Request Flow

```bash
┌──────────────┐     ┌─────────────────────┐
│ API Gateway  │────▶│  Chat Orchestrator  │
│ POST /chat   │     │      Lambda         │
└──────────────┘     └──────────┬──────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
           ┌───────────────┐      ┌─────────────────┐
           │ RAG Retriever │      │ Bedrock Handler │
           │    Lambda     │      │     Lambda      │
           └───────┬───────┘      └────────┬────────┘
                   │                       │
                   │ rag_context[]         │ response_text
                   └───────────┬───────────┘
                               ▼
                        ┌─────────────┐
                        │  Response   │
                        └─────────────┘
```

### API Contract

#### Request

```json
POST /chat
{
  "message": "How do I reset my password?",
  "tenant_id": "tenant-123",
  "conversation_id": "conv-456",
  "use_rag": true,
  "rag_options": {
    "top_k": 3,
    "min_score": 0.5
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| message | string | Yes | User's message |
| tenant_id | string | Yes | Tenant identifier |
| conversation_id | string | No | Conversation ID (generated if not provided) |
| use_rag | boolean | No | Enable RAG retrieval (default: true) |
| rag_options.top_k | int | No | Max documents to retrieve (default: 3) |
| rag_options.min_score | float | No | Minimum relevance score (default: 0.5) |

#### Response

```json
{
  "conversation_id": "conv-456",
  "message_id": "msg-789",
  "response": "To reset your password, click 'Forgot Password' on the login page...",
  "sources": [
    {
      "name": "general-faqs.md",
      "score": 0.89
    }
  ],
  "metadata": {
    "model": "anthropic.claude-3-haiku-20240307-v1:0",
    "rag_documents_used": 2,
    "latency_ms": {
      "rag": 150,
      "bedrock": 800,
      "total": 980
    }
  }
}
```

#### Error Response

```json
{
  "error_type": "RAG_RETRIEVAL_FAILED",
  "message": "Failed to retrieve documents from knowledge base",
  "retryable": true,
  "conversation_id": "conv-456"
}
```

### Error Handling Strategy

| Error Source | Behavior | Retryable |
|--------------|----------|-----------|
| RAG Retriever timeout | Proceed without RAG context | N/A |
| RAG Retriever failure | Proceed without RAG context (degraded) | N/A |
| Bedrock Handler timeout | Return error | Yes |
| Bedrock Handler failure | Return error | Depends |
| Validation error | Return 400 | No |

**Key Decision**: RAG failures are non-fatal. The orchestrator continues with an empty `rag_context` to ensure the user gets a response (potentially less accurate).

### Observability

#### CloudWatch Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| ChatRequests | Count | Total requests |
| ChatLatency | Milliseconds | End-to-end latency |
| RAGLatency | Milliseconds | RAG retrieval time |
| BedrockLatency | Milliseconds | Bedrock generation time |
| RAGSkipped | Count | Requests where RAG was skipped/failed |
| RAGDocumentsUsed | Count | Documents included in context |

#### Structured Logging

```json
{
  "level": "INFO",
  "message": "Chat request completed",
  "tenant_id": "tenant-123",
  "conversation_id": "conv-456",
  "rag_documents": 2,
  "total_latency_ms": 980
}
```

## Consequences

### Positive

- Single API endpoint simplifies client integration
- Fast Lambda-to-Lambda communication
- Graceful degradation when RAG fails
- Clear separation of concerns
- Easy to test each component independently

### Negative

- Additional Lambda adds maintenance overhead
- Synchronous flow (no streaming yet)
- Lambda invoke costs (minimal: ~$0.0000002 per invoke)

### Migration Path to Step Functions (Phase 4)

The orchestrator logic maps directly to Step Functions states:

```bash
Orchestrator Lambda          →  Step Functions
─────────────────────────────────────────────────
invoke_rag_retriever()       →  Task: RAG Retriever
invoke_bedrock_handler()     →  Task: Bedrock Handler
error handling               →  Catch/Retry blocks
```

## Implementation

### Lambda Configuration

```hcl
chat-orchestrator = {
  handler     = "handler.handler"
  runtime     = "python3.12"
  timeout     = 60  # Sum of downstream timeouts + buffer
  memory_size = 256
  environment_variables = {
    RAG_RETRIEVER_FUNCTION    = "ai-customer-service-bot-rag-retriever-dev"
    BEDROCK_HANDLER_FUNCTION  = "ai-customer-service-bot-bedrock-handler-dev"
    RAG_TIMEOUT_MS            = "10000"
    BEDROCK_TIMEOUT_MS        = "45000"
  }
}
```

### IAM Permissions

```json
{
  "Effect": "Allow",
  "Action": "lambda:InvokeFunction",
  "Resource": [
    "arn:aws:lambda:*:*:function:*-rag-retriever-*",
    "arn:aws:lambda:*:*:function:*-bedrock-handler-*"
  ]
}
```

## References

- ADR-009: Bedrock Integration
- ADR-010: Knowledge Base RAG Architecture
- [AWS Lambda Invoke](https://docs.aws.amazon.com/lambda/latest/dg/invocation-sync.html)
