# Architecture Documentation

This directory contains architecture documentation for the AI Customer Service Bot.

**Status:** Phase 3.3 Complete (Escalation Router)

---

## Documents

| Document | Description |
| ---------- | ------------- |
| [System Design](./system-design.md) | High-level system architecture, component specifications, security, and observability |
| [Data Flow](./data-flow.md) | Detailed data flow diagrams for chat, RAG retrieval, Bedrock, validation, sentiment, escalation, and routing |
| [Security](./security.md) | Security architecture, controls, encryption, IAM, and compliance |
| [Build & Deploy Architecture](../build-deploy-architecture.md) | CI/CD pipeline, build process, and deployment workflow |

---

## Architecture Decision Records

Key architectural decisions are documented in [ADRs](../adr/):

| ADR | Title | Status |
| ----- | ------- | -------- |
| [ADR-007](../adr/ADR-007-api-gateway-integration-and-request-validation.md) | API Gateway Integration and Request Validation | Accepted |
| [ADR-008](../adr/ADR-008-dynamodb-schema-design.md) | DynamoDB Schema Design | Accepted |
| [ADR-009](../adr/ADR-009-bedrock-integration.md) | Bedrock Integration | Accepted |
| [ADR-010](../adr/ADR-010-knowledge-base-rag.md) | Knowledge Base RAG | Accepted |
| [ADR-011](../adr/ADR-011-orchestrator-pattern.md) | Orchestrator Pattern | Accepted |
| [ADR-012](../adr/ADR-012-response-validation.md) | Response Validation Strategy | Accepted |
| [ADR-013](../adr/ADR-013-sentiment-escalation.md) | Sentiment Analysis & Escalation Scoring | Accepted |
| [ADR-014](../adr/ADR-014-escalation-router.md) | Escalation Router Design | Accepted |

---

## Diagrams

All diagrams use [Mermaid](https://mermaid.js.org/) syntax for version control and easy updates. They render automatically on GitHub and in most Markdown viewers.

### Viewing Diagrams

**GitHub:** Diagrams render automatically in `.md` files.

**VS Code:** Install the [Markdown Preview Mermaid Support](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid) extension.

**CLI:** Use [mermaid-cli](https://github.com/mermaid-js/mermaid-cli) to export as PNG/SVG:

```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i system-design.md -o system-design.png
```

---

## Quick Reference

### Current State (Phase 3.3)

```bash
Client → API Gateway → Chat Orchestrator
                              ├── RAG Retriever → Knowledge Base → Aurora PostgreSQL
                              ├── Bedrock Handler → Amazon Bedrock (Claude Haiku 4.5)
                              └── Response Validator
                                    ├── PII Detection → Amazon Comprehend
                                    ├── Business Rules Engine
                                    ├── Sentiment Analyzer → Amazon Comprehend
                                    └── Escalation Scorer (5-factor algorithm)
                                          │
                                          ▼ (if needs_escalation)
                                    Escalation Router
                                          ├── Priority Classification (CRITICAL/HIGH/NORMAL)
                                          ├── SQS FIFO Queue → Human Agents
                                          ├── DynamoDB Status Update
                                          └── SNS Notification (optional)

Additional Endpoints:
Client → API Gateway → Intent Classifier
                    ↘
         Context Builder → DynamoDB
```

### Target State (Full)

```bash
Client → CloudFront → WAF → API Gateway → Step Functions
                                              ↓
              ┌───────────────────────────────┼───────────────────────────────┐
              ↓                               ↓                               ↓
      Intent Classifier              Context Builder                  RAG Retriever
                                            ↓                               ↓
                                        DynamoDB                     Knowledge Base
                                                                            ↓
              ┌─────────────────────────────────────────────────────────────┘
              ↓
      Bedrock Handler → Amazon Bedrock
              ↓
      Response Validator
              ├── PII Detection → Amazon Comprehend
              ├── Sentiment Analysis → Amazon Comprehend
              └── Escalation Scoring
              ↓
      Escalation Router → SQS FIFO (if escalation triggered)
              ↓
      Customer Response
```

---

## Component Overview

### Phase 1-2 Components (Deployed)

| Component | Type | Purpose |
| ----------- | ------ | --------- |
| Chat Orchestrator | Lambda | Coordinates RAG → Bedrock → Validation → Escalation flow |
| RAG Retriever | Lambda | Queries Knowledge Base for relevant documents |
| Bedrock Handler | Lambda | Generates AI responses via Claude Haiku 4.5 |
| Knowledge Base | Bedrock KB | Manages document embeddings and retrieval |
| Aurora PostgreSQL | Database | Vector storage with pgvector extension |
| Intent Classifier | Lambda | Classifies customer message intents |
| Context Builder | Lambda | Retrieves and manages conversation history |
| DynamoDB | Database | Stores conversations and messages |
| API Gateway | REST API | HTTP endpoints (/chat, /classify-intent) |

### Phase 3 Components (Deployed)

| Component | Type | Purpose |
| ----------- | ------ | --------- |
| Response Validator | Lambda | Content safety, PII detection, business rules |
| Sentiment Analyzer | Service | Amazon Comprehend sentiment analysis integration |
| Escalation Scorer | Service | 5-factor weighted escalation algorithm |
| Escalation Router | Lambda | Priority-based routing to human agents |
| SQS FIFO Queue | Queue | Reliable escalation message delivery |

### Future Components (Planned)

| Component | Type | Purpose |
| ----------- | ------ | --------- |
| Step Functions | Orchestration | Full workflow state machine |
| ElastiCache Redis | Cache | Session caching and rate limiting |
| DAX | Cache | DynamoDB acceleration |
| Agent Dashboard | Web App | Human agent interface for escalations |

---

## API Endpoints

| Endpoint | Method | Lambda | Description |
|----------|--------|--------|-------------|
| `/chat`  | POST   | Chat Orchestrator | RAG-enhanced AI chat with validation, sentiment, escalation, routing |
| `/classify-intent` | POST | Intent Classifier | Message intent classification |

---

## Response Validation Pipeline

The Response Validator performs multiple checks in priority order:

```bash
┌─────────────────────────────────────────────────────────────────┐
│                    Response Validator Lambda                     │
├─────────────────────────────────────────────────────────────────┤
│  1. Profanity Check (P5)      → BLOCK if detected               │
│  2. Length Check (P10)        → BLOCK (short) / MODIFY (long)   │
│  3. Topic Rules (P20)         → MODIFY (add disclaimer)         │
│  4. PII Detection (P30)       → BLOCK (SSN/CC) / WARN (other)   │
│  5. Sentiment Analysis        → Analyze user message sentiment  │
│  6. Escalation Scoring        → Calculate 5-factor score        │
└─────────────────────────────────────────────────────────────────┘
```

### Escalation Scoring Algorithm

| Factor | Weight | Trigger |
| -------- | -------- | --------- |
| Explicit Intent | 0.35 | User says "speak to human", "agent", etc. |
| Negative Sentiment | 0.25 | Comprehend negative sentiment score |
| Urgency | 0.20 | High/critical urgency classification |
| Repeated Question | 0.15 | Same intent asked 2+ times |
| Low Confidence | 0.05 | Intent confidence < 0.70 |

**Threshold:** Score ≥ 0.70 triggers escalation routing.

---

## Escalation Router Pipeline

When escalation is triggered, the Escalation Router handles routing to human agents:

```bash
┌─────────────────────────────────────────────────────────────────┐
│                    Escalation Router Lambda                      │
├─────────────────────────────────────────────────────────────────┤
│  1. Priority Classification                                      │
│     • CRITICAL (≥0.90) → < 2 min wait                           │
│     • HIGH (0.80-0.89) → < 5 min wait                           │
│     • NORMAL (0.70-0.79) → < 10 min wait                        │
│                                                                  │
│  2. Queue Message (SQS FIFO)                                    │
│     • Message group by priority tier                            │
│     • Deduplication by escalation_id                            │
│     • Full context for agent handoff                            │
│                                                                  │
│  3. Update DynamoDB                                             │
│     • Set conversation status to ESCALATED                      │
│     • Record escalation metadata                                │
│                                                                  │
│  4. Notify Agents (Optional)                                    │
│     • SNS notification for CRITICAL/HIGH priority               │
│     • Real-time alerts for urgent escalations                   │
│                                                                  │
│  5. Return Customer Message                                     │
│     • Priority-appropriate acknowledgment                       │
│     • Estimated wait time                                       │
└─────────────────────────────────────────────────────────────────┘
```

### Priority Tiers

| Priority | Score Range | Wait Time | Message Group |
|----------|-------------|-----------|---------------|
| CRITICAL | ≥ 0.90 | < 2 minutes | priority-critical |
| HIGH | 0.80 - 0.89 | < 5 minutes | priority-high |
| NORMAL | 0.70 - 0.79 | < 10 minutes | priority-normal |

---

## Contributing

When updating architecture documentation:

1. Keep diagrams in Mermaid format for version control
2. Update the "Last Updated" date in each document
3. Cross-reference related ADRs
4. Ensure diagrams render correctly on GitHub before merging
