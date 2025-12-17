# Data Flow

**Last Updated:** December 17, 2025
**Status:** Phase 2 Complete

---

## Overview

This document describes the data flows within the AI Customer Service Bot, focusing on how customer messages are processed, how RAG retrieval works, and how AI responses are generated.

---

## Chat Flow (Primary)

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AG as API Gateway
    participant CO as Chat Orchestrator
    participant RR as RAG Retriever
    participant KB as Knowledge Base
    participant BH as Bedrock Handler
    participant BR as Amazon Bedrock
    participant CW as CloudWatch

    C->>AG: POST /chat<br/>{"message": "...", "tenant_id": "..."}

    Note over AG: Request Validation<br/>(JSON Schema)

    AG->>CO: Invoke Lambda (AWS_PROXY)

    Note over CO: 1. Parse request body<br/>2. Validate with Pydantic<br/>3. Generate conversation_id

    CO->>RR: Invoke Lambda<br/>{"query": "...", "tenant_id": "...", "limit": 3}

    RR->>KB: Retrieve (Bedrock Agent Runtime)
    KB-->>RR: Retrieval results

    Note over RR: Filter by min_score<br/>Parse documents

    RR-->>CO: {documents: [...], scores: [...]}
    RR->>CW: Log retrieval metrics

    Note over CO: Build context from<br/>RAG documents

    CO->>BH: Invoke Lambda<br/>{"user_message": "...", "rag_context": [...]}

    Note over BH: 1. Build system prompt<br/>2. Inject RAG context<br/>3. Construct messages

    BH->>BR: Converse API<br/>(Claude Haiku 4.5)
    BR-->>BH: AI Response + usage

    Note over BH: Extract response text<br/>Track token usage

    BH-->>CO: {response_text, model_id, tokens}
    BH->>CW: Log Bedrock metrics

    Note over CO: Assemble ChatResponse<br/>with sources & latency

    CO->>CW: Log request metrics
    CO-->>AG: ChatResponse
    AG-->>C: HTTP 200 + JSON body
```

### Request/Response Format

**Request:**

```json
{
  "message": "How do I reset my password?",
  "tenant_id": "acme-corp",
  "conversation_id": "conv-abc123",
  "use_rag": true,
  "rag_options": {
    "top_k": 3,
    "min_score": 0.5
  }
}
```

**Response:**

```json
{
  "conversation_id": "conv-abc123",
  "message_id": "msg-xyz789",
  "response": "To reset your password, click 'Forgot Password' on the login page...",
  "sources": [
    {
      "source_name": "general-faqs.md",
      "content": "### How do I reset my password?\nClick 'Forgot Password'...",
      "source_uri": "s3://bucket/faqs/general-faqs.md",
      "score": 0.85,
      "metadata": {}
    }
  ],
  "metadata": {
    "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "rag_documents_used": 3,
    "rag_skipped": false,
    "latency": {
      "rag_ms": 1200.5,
      "bedrock_ms": 2500.3,
      "total_ms": 3700.8
    }
  }
}
```

---

## RAG Retrieval Flow

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant CO as Chat Orchestrator
    participant RR as RAG Retriever
    participant KBA as Bedrock Agent Runtime
    participant KB as Knowledge Base
    participant APG as Aurora PostgreSQL
    participant S3 as S3 Documents
    participant CW as CloudWatch

    CO->>RR: Invoke<br/>{"query": "...", "tenant_id": "...", "limit": 5}

    Note over RR: Validate request<br/>with Pydantic

    RR->>KBA: retrieve()<br/>knowledgeBaseId, query, top_k

    KBA->>KB: Semantic search
    KB->>APG: Vector similarity query<br/>(pgvector)
    APG-->>KB: Matching chunks + scores

    KB->>S3: Fetch document metadata
    S3-->>KB: Document info

    KB-->>KBA: Retrieval results
    KBA-->>RR: {retrievalResults: [...]}

    Note over RR: 1. Filter by min_score<br/>2. Parse to RetrievedDocument<br/>3. Calculate avg score

    RR->>CW: Publish metrics<br/>DocumentsRetrieved, Latency

    RR-->>CO: RetrievalResponse
```

### Request/Response Format

**Request:**

```json
{
  "query": "How do I reset my password?",
  "tenant_id": "acme-corp",
  "top_k": 5,
  "min_score": 0.5,
  "retrieval_type": "SEMANTIC"
}
```

**Response:**

```json
{
  "documents": [
    {
      "content": "### How do I reset my password?\nClick 'Forgot Password'...",
      "score": 0.85,
      "source_uri": "s3://bucket/faqs/general-faqs.md",
      "source_name": "general-faqs.md",
      "metadata": {}
    }
  ],
  "query": "How do I reset my password?",
  "total_found": 5,
  "retrieval_time_ms": 1200.5
}
```

---

## Bedrock Handler Flow

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant CO as Chat Orchestrator
    participant BH as Bedrock Handler
    participant BR as Amazon Bedrock
    participant CW as CloudWatch

    CO->>BH: Invoke<br/>{"user_message": "...", "rag_context": [...]}

    Note over BH: 1. Validate request<br/>2. Build system prompt<br/>3. Build messages array

    BH->>BH: Inject RAG context<br/>into system prompt

    BH->>BR: Converse API<br/>model, messages, system, config

    Note over BR: Claude Haiku 4.5<br/>generates response

    BR-->>BH: {output, usage, stopReason}

    Note over BH: 1. Extract response text<br/>2. Calculate latency<br/>3. Track token usage

    BH->>CW: Publish metrics<br/>Invocations, Tokens, Latency

    BH-->>CO: BedrockResponse
```

### Request/Response Format

**Request:**

```json
{
  "user_message": "How do I reset my password?",
  "rag_context": [
    "### How do I reset my password?\nClick 'Forgot Password' on the login page..."
  ],
  "conversation_id": "conv-abc123",
  "tenant_id": "acme-corp",
  "max_tokens": 1024,
  "temperature": 0.7
}
```

**Response:**

```json
{
  "conversation_id": "conv-abc123",
  "response_text": "To reset your password, follow these steps:\n1. Go to the login page...",
  "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
  "input_tokens": 450,
  "output_tokens": 120,
  "latency_ms": 2500,
  "stop_reason": "end_turn",
  "timestamp": "2025-12-15T10:30:00Z"
}
```

---

## Intent Classification Flow

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AG as API Gateway
    participant IC as Intent Classifier
    participant CW as CloudWatch

    C->>AG: POST /classify-intent<br/>{"message": "...", "conversation_history": [...]}

    Note over AG: Request Validation<br/>(JSON Schema)

    AG->>IC: Invoke Lambda (AWS_PROXY)

    Note over IC: 1. Validate input<br/>2. Classify intent<br/>3. Extract entities<br/>4. Calculate confidence

    IC->>CW: Log classification result
    IC->>CW: Publish metrics

    IC-->>AG: Classification response
    AG-->>C: HTTP 200 + JSON body
```

### Request/Response Format

**Request:**

```json
{
  "message": "I need to speak to a manager about order #ABC-12345",
  "conversation_history": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi! How can I help you today?"}
  ]
}
```

**Response:**

```json
{
  "message": "Intent classified successfully",
  "classification": {
    "intent": "escalation",
    "confidence": 0.85,
    "requires_context": true,
    "entities": {
      "order_id": "ABC-12345",
      "sentiment": "negative",
      "urgency": "high"
    }
  },
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Context Building Flow

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant SF as Step Functions<br/>(future)
    participant CB as Context Builder
    participant DDB as DynamoDB
    participant CW as CloudWatch

    SF->>CB: Invoke<br/>{"conversation_id": "conv-123"}

    CB->>DDB: GetItem<br/>pk=CONV#conv-123, sk=METADATA
    DDB-->>CB: Conversation metadata

    CB->>DDB: Query<br/>pk=CONV#conv-123, sk begins_with MSG#
    DDB-->>CB: Message records (chronological)

    Note over CB: 1. Estimate tokens<br/>2. Check against limit (8000)<br/>3. Truncate if needed

    CB->>CW: Log context built
    CB->>CW: Publish metrics

    CB-->>SF: Context response
```

### Request/Response Format

**Request:**

```json
{
  "conversation_id": "conv-123",
  "include_system_prompt": true
}
```

**Response:**

```json
{
  "conversation_id": "conv-123",
  "context": {
    "conversation_id": "conv-123",
    "user_id": "user-456",
    "status": "ACTIVE",
    "last_intent": "question",
    "messages": [
      {
        "role": "USER",
        "content": "Hello, I need help",
        "timestamp": "2025-01-01T10:00:00Z"
      },
      {
        "role": "ASSISTANT",
        "content": "Hi! How can I help you today?",
        "timestamp": "2025-01-01T10:02:00Z"
      }
    ],
    "total_messages": 2,
    "estimated_tokens": 45,
    "is_truncated": false
  },
  "timestamp": "2025-01-01T10:05:00Z"
}
```

---

## DynamoDB Access Patterns

### Entity Relationships

```mermaid
erDiagram
    CONVERSATION ||--o{ MESSAGE : contains
    USER ||--o{ CONVERSATION : has

    CONVERSATION {
        string partition_key
        string sort_key
        string conversation_id
        string user_id
        string status
        int message_count
        string last_intent
        int ttl
    }

    MESSAGE {
        string partition_key
        string sort_key
        string message_id
        string role
        string content
        string intent
        int ttl
    }

    USER {
        string partition_key
        string sort_key
        string email
        int total_conversations
    }
```

**Key Patterns:**

- `CONVERSATION`: partition_key = `CONV#{conversation_id}`, sort_key = `METADATA`
- `MESSAGE`: partition_key = `CONV#{conversation_id}`, sort_key = `MSG#{timestamp}#{message_id}`
- `USER`: partition_key = `USER#{user_id}`, sort_key = `PROFILE`

### Access Pattern Flows

#### Pattern 1: Get Conversation Metadata

```mermaid
flowchart LR
    REQ[Request] --> QUERY[GetItem]
    QUERY --> KEY["pk = CONV#conv-123<br/>sk = METADATA"]
    KEY --> RESULT[ConversationMetadata]
```

#### Pattern 2: Get Messages (Chronological)

```mermaid
flowchart LR
    REQ[Request] --> QUERY[Query]
    QUERY --> KEY["pk = CONV#conv-123<br/>sk begins_with MSG#"]
    KEY --> SORT[ScanIndexForward = true]
    SORT --> RESULT[List of Messages<br/>oldest first]
```

#### Pattern 3: Get User's Conversations

```mermaid
flowchart LR
    REQ[Request] --> QUERY[Query GSI1]
    QUERY --> KEY["gsi1_pk = USER#user-456"]
    KEY --> SORT[ScanIndexForward = false]
    SORT --> RESULT[List of Conversations<br/>newest first]
```

#### Pattern 4: Get Escalated Conversations

```mermaid
flowchart LR
    REQ[Request] --> QUERY[Query GSI2]
    QUERY --> KEY["gsi2_pk = STATUS#ESCALATED"]
    KEY --> SORT[ScanIndexForward = false]
    SORT --> RESULT[Escalated Conversations<br/>most recent first]
```

---

## Token Management Flow

### Context Window Management

```mermaid
flowchart TB
    START[Get Messages] --> ESTIMATE[Estimate Tokens<br/>4 chars ≈ 1 token]
    ESTIMATE --> CHECK{tokens > 8000?}

    CHECK -->|No| RETURN[Return All Messages]
    CHECK -->|Yes| TRUNCATE[Remove Oldest Messages]

    TRUNCATE --> RECHECK{tokens > 8000?}
    RECHECK -->|No| MARK[Mark as Truncated]
    RECHECK -->|Yes| TRUNCATE

    MARK --> RETURN_TRUNC[Return Truncated Messages]
```

### Token Estimation Example

```markdown
Message: "Hello, I need help with my order"
Characters: 34
Estimated Tokens: 34 / 4 = 8.5 ≈ 9 tokens

Context Window Limit: 8000 tokens
Typical message: ~50 tokens
Max messages before truncation: ~160 messages
```

---

## Future: Step Functions Orchestration

### End-to-End Flow (Target State)

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AG as API Gateway
    participant SF as Step Functions
    participant IC as Intent Classifier
    participant CB as Context Builder
    participant RR as RAG Retriever
    participant BH as Bedrock Handler
    participant RV as Response Validator
    participant DDB as DynamoDB
    participant BR as Amazon Bedrock

    C->>AG: POST /chat<br/>{"message": "..."}
    AG->>SF: Start Execution

    SF->>IC: Classify Intent
    IC-->>SF: {intent, confidence, entities}

    alt needs_escalation
        SF->>SF: Route to Escalation
    else normal_flow
        SF->>CB: Build Context
        CB->>DDB: Get conversation history
        DDB-->>CB: Messages
        CB-->>SF: {context, tokens}

        SF->>RR: Retrieve RAG Context
        RR-->>SF: {documents, scores}

        SF->>BH: Generate Response
        BH->>BR: Invoke Claude
        BR-->>BH: AI Response
        BH-->>SF: {response}

        SF->>RV: Validate Response
        RV-->>SF: {is_safe, validated_response}
    end

    SF->>DDB: Save message + response
    SF-->>AG: Final response
    AG-->>C: HTTP 200 + response
```

### State Machine Definition

```mermaid
stateDiagram-v2
    [*] --> ReceiveMessage

    ReceiveMessage --> ClassifyIntent
    ClassifyIntent --> EvaluateIntent

    EvaluateIntent --> BuildContext: normal
    EvaluateIntent --> InitiateEscalation: escalation_needed

    BuildContext --> RetrieveRAG
    RetrieveRAG --> GenerateResponse
    GenerateResponse --> ValidateResponse

    ValidateResponse --> SaveResponse: valid
    ValidateResponse --> GenerateFallback: invalid

    GenerateFallback --> SaveResponse

    InitiateEscalation --> NotifyAgent
    NotifyAgent --> SaveResponse

    SaveResponse --> SendResponse
    SendResponse --> [*]
```

---

## Error Handling Flows

### Validation Error

```mermaid
sequenceDiagram
    participant C as Client
    participant AG as API Gateway
    participant CO as Chat Orchestrator

    C->>AG: POST /chat<br/>{"message": ""}
    AG->>CO: Invoke Lambda

    Note over CO: Validation fails:<br/>message cannot be empty

    CO-->>AG: HTTP 400<br/>{"error": "ValidationError"}
    AG-->>C: HTTP 400
```

### RAG Retrieval Error (Non-Fatal)

```mermaid
sequenceDiagram
    participant CO as Chat Orchestrator
    participant RR as RAG Retriever
    participant BH as Bedrock Handler
    participant CW as CloudWatch

    CO->>RR: Invoke
    RR-->>CO: Error (timeout/unavailable)

    CO->>CW: Log RAG error (warning)

    Note over CO: Continue without RAG context

    CO->>BH: Invoke (empty rag_context)
    BH-->>CO: Response (without RAG)

    CO-->>CO: Return response<br/>(rag_skipped: true)
```

### Bedrock Error (Fatal)

```mermaid
sequenceDiagram
    participant CO as Chat Orchestrator
    participant BH as Bedrock Handler
    participant BR as Amazon Bedrock
    participant CW as CloudWatch

    CO->>BH: Invoke

    BH->>BR: Converse API
    BR-->>BH: Error (throttled/model error)

    BH->>BH: Retry with backoff (3 attempts)
    BH->>BR: Retry...
    BR-->>BH: Error persists

    BH->>CW: Log error + metrics
    BH-->>CO: Error response

    CO->>CW: Log error
    CO-->>CO: Return error to client
```

### DynamoDB Error

```mermaid
sequenceDiagram
    participant CB as Context Builder
    participant DDB as DynamoDB
    participant CW as CloudWatch

    CB->>DDB: Query messages
    DDB-->>CB: Error (throttled/unavailable)

    CB->>CW: Log error
    CB->>CW: Increment error metric

    Note over CB: Raise DependencyError

    CB-->>CB: Return error response
```

---

## Observability Data Flow

### Logging Flow

```mermaid
flowchart LR
    subgraph Lambda
        CODE[Application Code]
        PT[Powertools Logger]
    end

    subgraph CloudWatch
        LOGS[Log Groups]
        INSIGHTS[Log Insights]
    end

    CODE -->|structured log| PT
    PT -->|JSON| LOGS
    LOGS -->|query| INSIGHTS
```

### Metrics Flow

```mermaid
flowchart LR
    subgraph Lambda
        CODE[Application Code]
        METRICS[Powertools Metrics]
    end

    subgraph CloudWatch
        CW_METRICS[CloudWatch Metrics]
        ALARMS[Alarms]
        DASH[Dashboards]
    end

    CODE -->|record metric| METRICS
    METRICS -->|EMF| CW_METRICS
    CW_METRICS --> ALARMS
    CW_METRICS --> DASH
```

### Tracing Flow

```mermaid
flowchart LR
    subgraph Request Path
        AG[API Gateway]
        CO[Chat Orchestrator]
        RR[RAG Retriever]
        BH[Bedrock Handler]
    end

    subgraph X-Ray
        TRACES[Trace Segments]
        MAP[Service Map]
    end

    AG -->|segment| TRACES
    CO -->|segment| TRACES
    RR -->|segment| TRACES
    BH -->|segment| TRACES
    TRACES --> MAP
```

---

## Related Documentation

- [System Design](./system-design.md) — Overall architecture
- [ADR-008: DynamoDB Schema](../adr/ADR-008-dynamodb-schema-design.md) — Schema details
- [ADR-009: Bedrock Integration](../adr/ADR-009-bedrock-integration.md) — Bedrock design
- [ADR-010: Knowledge Base RAG](../adr/ADR-010-knowledge-base-rag.md) — RAG architecture
- [ADR-011: Orchestrator Pattern](../adr/ADR-011-orchestrator-pattern.md) — Orchestration design
- [Build & Deploy Architecture](../build-deploy-architecture.md) — Deployment flows
