# System Design

**Last Updated:** November 2025
**Status:** Phase 1.2 Complete

---

## Overview

The AI Customer Service Bot is a serverless, event-driven platform that provides intelligent customer support through natural language processing and AI-powered responses.

---

## Architecture Principles

1. **Serverless-First** — No servers to manage; pay only for what you use
2. **Event-Driven** — Loosely coupled components communicate via events
3. **Infrastructure as Code** — All infrastructure defined in Terraform
4. **Separation of Concerns** — Each Lambda has a single responsibility
5. **Observability by Default** — Logging, tracing, and metrics built-in
6. **Security in Depth** — Encryption, least-privilege IAM, input validation

---

## Current Architecture (Phase 1.2)

### High-Level View

```mermaid
flowchart TB
    subgraph Client
        USER[Customer/Client]
    end

    subgraph AWS Cloud
        subgraph API Layer
            APIGW[API Gateway<br/>REST API]
        end

        subgraph Compute Layer
            IC[Intent Classifier<br/>Lambda]
            CB[Context Builder<br/>Lambda]
        end

        subgraph Data Layer
            DDB[(DynamoDB<br/>conversations)]
        end

        subgraph Observability
            CW[CloudWatch<br/>Logs & Metrics]
            XRAY[X-Ray<br/>Tracing]
        end

        subgraph Shared
            LAYER[Lambda Layer<br/>shared utilities]
        end
    end

    USER -->|POST /classify-intent| APIGW
    APIGW -->|AWS_PROXY| IC
    IC -.->|uses| LAYER
    CB -.->|uses| LAYER
    CB -->|Query/Put| DDB
    IC -->|logs| CW
    CB -->|logs| CW
    IC -->|traces| XRAY
    CB -->|traces| XRAY
```

### Component Details

```mermaid
flowchart LR
    subgraph Intent Classifier
        IC_IN[Request] --> IC_VAL[Validate Input]
        IC_VAL --> IC_CLASS[Classify Intent]
        IC_CLASS --> IC_ENT[Extract Entities]
        IC_ENT --> IC_OUT[Response]
    end

    subgraph Context Builder
        CB_IN[Request] --> CB_META[Get Metadata]
        CB_META --> CB_MSG[Get Messages]
        CB_MSG --> CB_TOK[Estimate Tokens]
        CB_TOK --> CB_TRUNC[Truncate if Needed]
        CB_TRUNC --> CB_OUT[Context Response]
    end
```

### API Gateway Integration

```mermaid
sequenceDiagram
    participant C as Client
    participant AG as API Gateway
    participant L as Lambda
    participant CW as CloudWatch

    C->>AG: POST /classify-intent
    AG->>AG: Validate Request Schema
    AG->>L: Invoke (AWS_PROXY)
    L->>L: Process Request
    L->>CW: Log & Metrics
    L-->>AG: Response
    AG-->>C: HTTP Response
```

---

## Target Architecture (Full Implementation)

### Complete System View

```mermaid
flowchart TB
    subgraph Clients
        WEB[Next.js Web App]
        MOBILE[Mobile App]
        API_CLIENT[API Clients]
    end

    subgraph Edge Layer
        CF[CloudFront CDN]
        WAF[AWS WAF]
    end

    subgraph API Layer
        APIGW_REST[API Gateway<br/>REST API]
        APIGW_WS[API Gateway<br/>WebSocket]
    end

    subgraph Orchestration
        SF[Step Functions<br/>Conversation Flow]
    end

    subgraph Compute Layer
        IC[Intent Classifier]
        CB[Context Builder]
        BH[Bedrock Handler]
        RV[Response Validator]
        ER[Escalation Router]
    end

    subgraph AI/ML Layer
        BEDROCK[Amazon Bedrock<br/>Claude 3.5 Sonnet]
        KB[Knowledge Base<br/>RAG]
        COMPREHEND[Amazon Comprehend<br/>Sentiment]
    end

    subgraph Data Layer
        DDB[(DynamoDB)]
        DAX[DAX Cache]
        REDIS[ElastiCache Redis]
        OS[OpenSearch]
    end

    subgraph Messaging
        SQS[SQS Queues]
        SNS[SNS Topics]
        EB[EventBridge]
    end

    subgraph Observability
        CW[CloudWatch]
        XRAY[X-Ray]
        DASH[Dashboards]
    end

    WEB --> CF
    MOBILE --> CF
    API_CLIENT --> WAF
    CF --> WAF
    WAF --> APIGW_REST
    WAF --> APIGW_WS

    APIGW_REST --> SF
    APIGW_WS --> SF

    SF --> IC
    SF --> CB
    SF --> BH
    SF --> RV
    SF --> ER

    CB --> DDB
    CB --> DAX
    BH --> BEDROCK
    BH --> KB
    RV --> COMPREHEND
    ER --> SQS

    DDB --> OS
    SF --> EB
    EB --> SNS
```

### Step Functions Workflow

```mermaid
stateDiagram-v2
    [*] --> ClassifyIntent
    ClassifyIntent --> BuildContext
    BuildContext --> CheckEscalation

    CheckEscalation --> RouteToAgent: needs_escalation
    CheckEscalation --> GenerateResponse: normal_flow

    GenerateResponse --> ValidateResponse
    ValidateResponse --> CheckSafety

    CheckSafety --> SaveAndRespond: safe
    CheckSafety --> FallbackResponse: unsafe

    RouteToAgent --> NotifyAgent
    NotifyAgent --> SaveAndRespond

    FallbackResponse --> SaveAndRespond
    SaveAndRespond --> [*]
```

---

## Component Specifications

### Intent Classifier Lambda

| Attribute | Value |
|-----------|-------|
| Runtime | Python 3.12 |
| Memory | 256 MB |
| Timeout | 30 seconds |
| Trigger | API Gateway (sync) |
| Layer | shared-layer |

**Responsibilities:**

- Classify customer messages into intent categories
- Extract entities (order IDs, products, sentiment)
- Calculate confidence scores
- Flag messages requiring escalation

**Intent Types:**

- `greeting` — Greetings and farewells
- `question` — General inquiries
- `complaint` — Customer complaints
- `request` — Action requests
- `escalation` — Human agent requests
- `shipping` — Delivery inquiries
- `technical_support` — Technical issues

### Context Builder Lambda

| Attribute | Value |
|-----------|-------|
| Runtime | Python 3.12 |
| Memory | 512 MB |
| Timeout | 30 seconds |
| Trigger | Direct invocation / Step Functions |
| Layer | shared-layer |

**Responsibilities:**

- Retrieve conversation history from DynamoDB
- Estimate token usage (4 chars ≈ 1 token)
- Manage context window (8000 tokens max)
- Truncate older messages when limits exceeded
- Return structured context for Bedrock

### DynamoDB Table

| Attribute | Value |
|-----------|-------|
| Table Name | conversations |
| Billing Mode | On-demand (PAY_PER_REQUEST) |
| Primary Key | pk (HASH), sk (RANGE) |
| TTL | 30 days |
| Streams | Enabled (NEW_AND_OLD_IMAGES) |

**Indexes:**

- **GSI1:** User queries (`gsi1_pk`, `gsi1_sk`)
- **GSI2:** Status queries (`gsi2_pk`, `gsi2_sk`)

See [ADR-008](../adr/008-dynamodb-schema-design.md) for schema details.

### Shared Lambda Layer

| Attribute | Value |
|-----------|-------|
| Runtime | Python 3.12 |
| Size | ~15 MB |
| Build | Docker (Amazon Linux 2) |

**Contents:**

- AWS Lambda Powertools (logging, tracing, metrics)
- Pydantic (data validation)
- boto3 (AWS SDK)
- Custom shared code (`shared/`)

---

## Security Architecture

```mermaid
flowchart TB
    subgraph Public Internet
        CLIENT[Client]
    end

    subgraph AWS Edge
        WAF[AWS WAF<br/>Rate limiting, Geo-blocking]
    end

    subgraph AWS Cloud
        subgraph Public Subnet
            APIGW[API Gateway<br/>TLS 1.2+, Throttling]
        end

        subgraph Private Resources
            LAMBDA[Lambda Functions<br/>Least-privilege IAM]
            DDB[(DynamoDB<br/>Encryption at rest)]
        end

        subgraph Secrets
            SM[Secrets Manager]
            KMS[KMS Keys]
        end
    end

    CLIENT -->|HTTPS| WAF
    WAF -->|Filtered| APIGW
    APIGW -->|IAM Auth| LAMBDA
    LAMBDA -->|IAM Role| DDB
    LAMBDA -.->|Decrypt| KMS
    LAMBDA -.->|Retrieve| SM
    DDB -.->|Encrypt| KMS
```

### Security Controls

| Layer | Control | Status |
|-------|---------|--------|
| Edge | AWS WAF | 📋 Planned |
| Transport | TLS 1.2+ | ✅ Enabled |
| API | Request validation | ✅ Enabled |
| API | Throttling | ✅ Enabled (100/50) |
| API | Authentication | 📋 Planned (Cognito) |
| Compute | Least-privilege IAM | ✅ Enabled |
| Data | Encryption at rest | ✅ Enabled (KMS) |
| Logs | Encryption | ✅ Enabled (KMS) |
| Secrets | Secrets Manager | 📋 Planned |

---

## Observability Architecture

```mermaid
flowchart LR
    subgraph Sources
        LAMBDA[Lambda Logs]
        APIGW[API Gateway Logs]
        DDB[DynamoDB Metrics]
    end

    subgraph Collection
        CW_LOGS[CloudWatch Logs]
        CW_METRICS[CloudWatch Metrics]
        XRAY[X-Ray Traces]
    end

    subgraph Analysis
        INSIGHTS[CloudWatch Insights]
        DASH[Dashboards]
        ALARMS[CloudWatch Alarms]
    end

    subgraph Alerting
        SNS[SNS Topics]
        EMAIL[Email Alerts]
    end

    LAMBDA --> CW_LOGS
    LAMBDA --> CW_METRICS
    LAMBDA --> XRAY
    APIGW --> CW_LOGS
    DDB --> CW_METRICS

    CW_LOGS --> INSIGHTS
    CW_METRICS --> DASH
    CW_METRICS --> ALARMS
    XRAY --> DASH

    ALARMS --> SNS
    SNS --> EMAIL
```

### Metrics Collected

| Metric | Source | Purpose |
|--------|--------|---------|
| Invocations | Lambda | Usage tracking |
| Duration | Lambda | Performance |
| Errors | Lambda | Reliability |
| Throttles | Lambda/API GW | Capacity |
| 4XX/5XX | API Gateway | Error rates |
| Latency | API Gateway | User experience |
| ReadThrottleEvents | DynamoDB | Capacity |
| WriteThrottleEvents | DynamoDB | Capacity |
| Intent counts | Custom | Business metrics |

---

## Deployment Architecture

See [Build & Deploy Architecture](../build-deploy-architecture.md) for detailed deployment pipeline documentation.

### Summary

```mermaid
flowchart LR
    subgraph Build Phase
        CODE[Source Code] --> DOCKER[Docker Build]
        DOCKER --> ARTIFACTS[ZIP Artifacts]
    end

    subgraph Deploy Phase
        ARTIFACTS --> TF[Terraform]
        TF --> AWS[AWS Resources]
    end

    subgraph Environments
        AWS --> DEV[Dev]
        AWS --> STAGING[Staging]
        AWS --> PROD[Prod]
    end
```

---

## Related Documentation

- [Data Flow](./data-flow.md) — Detailed data flow diagrams
- [Build & Deploy Architecture](../build-deploy-architecture.md) — CI/CD pipeline
- [ADR-007: API Gateway Integration](../adr/007-api-gateway-integration-and-request-validation.md)
- [ADR-008: DynamoDB Schema Design](../adr/008-dynamodb-schema-design.md)
