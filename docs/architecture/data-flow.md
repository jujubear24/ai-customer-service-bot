# Data Flow

**Last Updated:** November 2025
**Status:** Phase 1.2 Complete

---

## Overview

This document describes the data flows within the AI Customer Service Bot, focusing on how customer messages are processed and how conversation context is managed.

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
        string pk PK
        string sk SK
        string conversation_id
        string user_id
        string status
        int message_count
        string last_intent
        int ttl
    }

    MESSAGE {
        string pk FK
        string sk SK
        string message_id
        string role
        string content
        string intent
        int ttl
    }

    USER {
        string pk PK
        string sk SK
        string email
        int total_conversations
    }
```

**Key Patterns:**

- `CONVERSATION`: pk = `CONV#{conversation_id}`, sk = `METADATA`
- `MESSAGE`: pk = `CONV#{conversation_id}`, sk = `MSG#{timestamp}#{message_id}`
- `USER`: pk = `USER#{user_id}`, sk = `PROFILE`

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

## Future: Full Conversation Flow

### End-to-End Flow (Target State)

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AG as API Gateway
    participant SF as Step Functions
    participant IC as Intent Classifier
    participant CB as Context Builder
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

    BuildContext --> GenerateResponse
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
    participant IC as Intent Classifier

    C->>AG: POST /classify-intent<br/>{"message": ""}
    AG->>IC: Invoke Lambda

    Note over IC: Validation fails:<br/>message cannot be empty

    IC-->>AG: HTTP 400<br/>{"error": "ValidationError"}
    AG-->>C: HTTP 400
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
        LAMBDA[Lambda]
        DDB[DynamoDB]
    end

    subgraph X-Ray
        TRACES[Trace Segments]
        MAP[Service Map]
    end

    AG -->|segment| TRACES
    LAMBDA -->|segment| TRACES
    DDB -->|segment| TRACES
    TRACES --> MAP
```

---

## Related Documentation

- [System Design](./system-design.md) — Overall architecture
- [ADR-008: DynamoDB Schema](../adr/008-dynamodb-schema-design.md) — Schema details
- [Build & Deploy Architecture](../build-deploy-architecture.md) — Deployment flows
