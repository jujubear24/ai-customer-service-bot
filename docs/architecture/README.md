# Architecture Documentation

This directory contains architecture documentation for the AI Customer Service Bot.

**Status:** Phase 2 Complete

---

## Documents

| Document | Description |
|----------|-------------|
| [System Design](./system-design.md) | High-level system architecture, component specifications, security, and observability |
| [Data Flow](./data-flow.md) | Detailed data flow diagrams for chat, RAG retrieval, Bedrock, intent classification, and DynamoDB access patterns |
| [Build & Deploy Architecture](../build-deploy-architecture.md) | CI/CD pipeline, build process, and deployment workflow |

---

## Architecture Decision Records

Key architectural decisions are documented in [ADRs](../adr/):

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-007](../adr/ADR-007-api-gateway-integration-and-request-validation.md) | API Gateway Integration and Request Validation | Accepted |
| [ADR-008](../adr/ADR-008-dynamodb-schema-design.md) | DynamoDB Schema Design | Accepted |
| [ADR-009](../adr/ADR-009-bedrock-integration.md) | Bedrock Integration | Accepted |
| [ADR-010](../adr/ADR-010-knowledge-base-rag.md) | Knowledge Base RAG | Accepted |
| [ADR-011](../adr/ADR-011-orchestrator-pattern.md) | Orchestrator Pattern | Accepted |

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

### Current State (Phase 2)

```bash
Client → API Gateway → Chat Orchestrator
                              ├── RAG Retriever → Knowledge Base → Aurora PostgreSQL
                              └── Bedrock Handler → Amazon Bedrock (Claude Haiku 4.5)

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
      Response Validator → Amazon Comprehend
              ↓
      Escalation Router → SQS
```

---

## Component Overview

### Phase 2 Components (Deployed)

| Component | Type | Purpose |
|-----------|------|---------|
| Chat Orchestrator | Lambda | Coordinates RAG → Bedrock chat flow |
| RAG Retriever | Lambda | Queries Knowledge Base for relevant documents |
| Bedrock Handler | Lambda | Generates AI responses via Claude Haiku 4.5 |
| Knowledge Base | Bedrock KB | Manages document embeddings and retrieval |
| Aurora PostgreSQL | Database | Vector storage with pgvector extension |
| Intent Classifier | Lambda | Classifies customer message intents |
| Context Builder | Lambda | Retrieves and manages conversation history |
| DynamoDB | Database | Stores conversations and messages |
| API Gateway | REST API | HTTP endpoints (/chat, /classify-intent) |

### Phase 3+ Components (Planned)

| Component | Type | Purpose |
|-----------|------|---------|
| Response Validator | Lambda | Content safety and business rules |
| Sentiment Analyzer | Lambda | Amazon Comprehend integration |
| Escalation Router | Lambda | Route to human agents |
| Step Functions | Orchestration | Full workflow state machine |
| ElastiCache Redis | Cache | Session caching and rate limiting |
| DAX | Cache | DynamoDB acceleration |

---

## API Endpoints

| Endpoint | Method | Lambda | Description |
|----------|--------|--------|-------------|
| `/chat` | POST | Chat Orchestrator | RAG-enhanced AI chat responses |
| `/classify-intent` | POST | Intent Classifier | Message intent classification |

---

## Contributing

When updating architecture documentation:

1. Keep diagrams in Mermaid format for version control
2. Update the "Last Updated" date in each document
3. Cross-reference related ADRs
4. Ensure diagrams render correctly on GitHub before merging
