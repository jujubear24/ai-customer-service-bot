# 🤖 AI Customer Service Bot

A **production-grade, AI-powered customer service platform** built on AWS with **serverless architecture**, **intelligent intent classification**, and **context-aware responses**.

---

## 🎯 Project Overview

This project demonstrates advanced **cloud engineering** and **AI/ML integration** for customer service automation using:

- **AI/ML:** Amazon Bedrock (Claude Haiku 4.5), RAG with Knowledge Bases, intent classification
- **Compute:** AWS Lambda (Python 3.12), Lambda Layers
- **Orchestration:** Chat Orchestrator, API Gateway
- **Data:** DynamoDB (single-table design), Aurora PostgreSQL (pgvector), S3
- **Infrastructure:** Terraform (modular IaC), GitHub Actions CI/CD
- **Observability:** CloudWatch, X-Ray, custom metrics

---

## 📊 Implementation Status

### Phase 1: Core Infrastructure ✅

| Component | Status | Description |
|-----------|--------|-------------|
| Intent Classifier Lambda | ✅ Deployed | Rule-based classification with 7 intent types |
| Context Builder Lambda | ✅ Deployed | Retrieves conversation history, manages token limits |
| DynamoDB Table | ✅ Deployed | Single-table design with GSIs for flexible querying |
| Shared Lambda Layer | ✅ Deployed | AWS Powertools, Pydantic models, common utilities |
| REST API Gateway | ✅ Deployed | POST /classify-intent with request validation |
| Observability | ✅ Deployed | CloudWatch Logs, X-Ray tracing, custom metrics |

### Phase 2: AI Integration ✅

| Component | Status | Description |
|-----------|--------|-------------|
| Bedrock Handler Lambda | ✅ Deployed | Claude Haiku 4.5 integration for response generation |
| RAG Retriever Lambda | ✅ Deployed | Knowledge Base retrieval with semantic search |
| Chat Orchestrator Lambda | ✅ Deployed | Coordinates RAG → Bedrock flow |
| Knowledge Base | ✅ Deployed | Bedrock Knowledge Base with Aurora PostgreSQL (pgvector) |
| S3 Document Store | ✅ Deployed | FAQ and documentation storage for RAG |
| POST /chat Endpoint | ✅ Deployed | Unified chat API with RAG-enhanced responses |

### Phase 3: Response Validation & Sentiment 📋

| Component | Status | Description |
|-----------|--------|-------------|
| Response Validator Lambda | 📋 Planned | Output validation and safety checks |
| Sentiment Analyzer | 📋 Planned | Amazon Comprehend integration |
| Content Safety Checks | 📋 Planned | Business rules engine |

### Future Phases 📋

| Feature | Description |
|---------|-------------|
| Step Functions Workflow | Orchestrate full Lambda chain with error handling |
| Escalation Router | Priority-based routing to human agents |
| ElastiCache Redis | Session caching and rate limiting |
| Real-Time Analytics | OpenSearch dashboards for metrics |
| Multi-Tenant Support | SaaS-ready with data isolation |
| WebSocket API | Real-time chat interface |

---

## 🏗️ Architecture

### Current State (Phase 2)

```bash
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /chat
       ▼
┌──────────────────────────────────────────────────────┐
│              API Gateway (REST)                      │
│     • Request validation (JSON Schema)               │
│     • CORS enabled                                   │
│     • X-Ray tracing                                  │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│            Chat Orchestrator Lambda                  │
│     • Coordinates RAG + Bedrock flow                 │
│     • Generates conversation IDs                     │
│     • Aggregates latency metrics                     │
└──────┬───────────────────┬───────────────────────────┘
       │                   │
       ▼                   ▼
┌──────────────────┐  ┌──────────────────────────────┐
│  RAG Retriever   │  │     Bedrock Handler          │
│     Lambda       │  │        Lambda                │
│  • Query KB      │  │  • Claude Haiku 4.5          │
│  • Semantic      │  │  • Prompt engineering        │
│    search        │  │  • Token management          │
│  • Score filter  │  │  • Context injection         │
└────────┬─────────┘  └──────────────┬───────────────┘
         │                           │
         ▼                           ▼
┌──────────────────┐  ┌──────────────────────────────┐
│ Bedrock Knowledge│  │       Amazon Bedrock         │
│      Base        │  │   (Claude Haiku 4.5)         │
│  • Aurora PG     │  └──────────────────────────────┘
│  • pgvector      │
│  • S3 docs       │
└──────────────────┘

Additional Endpoints:
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /classify-intent
       ▼
┌──────────────────┐      ┌──────────────────┐
│ Intent Classifier│      │  Context Builder │
│     Lambda       │      │     Lambda       │
│  • 7 intent types│      │  • Token mgmt    │
│  • Entity extract│      │  • History fetch │
│  • Sentiment     │      │  • Truncation    │
└──────────────────┘      └────────┬─────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │    DynamoDB      │
                          │  • Conversations │
                          │  • Messages      │
                          │  • User profiles │
                          └──────────────────┘
```

### Target State (Full Implementation)

```bash
┌─────────────┐
│   Next.js   │
│  (Customer  │
│  & Agent UI)│
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────────┐
│          API Gateway + CloudFront               │
│               (REST + WebSocket)                │
└──────┬──────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────┐
│         Step Functions State Machine            │
│  ┌─────────────────────────────────────────┐   │
│  │ Intent → Context → RAG → Bedrock → Val  │   │
│  └─────────────────────────────────────────┘   │
└──────┬──────────────────────────────────────────┘
       │
┌──────▼─────────┬──────────┬──────────┬─────────┐
│   DynamoDB     │  Bedrock │  Redis   │OpenSearch│
│   + DAX        │   + KB   │  Cache   │Analytics │
└────────────────┴──────────┴──────────┴──────────┘
```

See [`docs/architecture/`](docs/architecture/) for detailed design documents.

---

## 🧩 Components

### Chat Orchestrator Lambda (NEW)

Orchestrates the complete chat flow, coordinating RAG retrieval and AI response generation.

- **Endpoint:** `POST /chat`
- **Features:**
  - Invokes RAG Retriever for context retrieval
  - Invokes Bedrock Handler for response generation
  - Auto-generates conversation IDs
  - Aggregates latency metrics (RAG, Bedrock, total)
  - Resilient with retry logic (tenacity)
- **Performance:** 512 MB memory, ~8-10s total latency (cold), ~3-5s (warm)

### RAG Retriever Lambda (NEW)

Retrieves relevant documents from the Knowledge Base for context-aware responses.

- **Trigger:** Invoked by Chat Orchestrator
- **Features:**
  - Semantic search against Bedrock Knowledge Base
  - Configurable top_k and min_score filtering
  - Returns scored document chunks with source attribution
  - Aurora PostgreSQL with pgvector for embeddings
- **Performance:** 256 MB memory, ~1-2s retrieval time

### Bedrock Handler Lambda (NEW)

Generates AI responses using Amazon Bedrock Claude models.

- **Trigger:** Invoked by Chat Orchestrator
- **Features:**
  - Claude Haiku 4.5 integration (us.anthropic.claude-haiku-4-5-20251001-v1:0)
  - Prompt engineering with system prompts
  - RAG context injection
  - Token usage tracking and metrics
  - Configurable temperature, max_tokens, top_p
- **Performance:** 512 MB memory, ~2-4s generation time

### Knowledge Base (NEW)

Bedrock Knowledge Base with Aurora PostgreSQL for vector storage.

- **Vector Store:** Aurora PostgreSQL Serverless v2 with pgvector
- **Document Store:** S3 bucket with FAQ markdown files
- **Chunking:** Semantic chunking for optimal retrieval
- **Sync:** Manual sync via `scripts/sync-knowledge-base.sh`

### Intent Classifier Lambda

Classifies customer messages into intent categories for routing and response generation.

- **Endpoint:** `POST /classify-intent`
- **Intents:** greeting, question, complaint, request, escalation, shipping, technical_support
- **Features:**
  - Entity extraction (order IDs, product names)
  - Sentiment detection (positive, negative, neutral)
  - Urgency classification
  - Confidence scoring
- **Performance:** 128 MB memory, ~50ms execution time
- **Test Coverage:** 96% (34 unit tests)

### Context Builder Lambda

Retrieves and manages conversation history for context-aware AI responses.

- **Trigger:** Direct invocation (future: Step Functions)
- **Features:**
  - Retrieves conversation history from DynamoDB
  - Token estimation (4 chars ≈ 1 token)
  - Context window management (8000 tokens max)
  - Automatic message truncation when exceeding limits
  - Chronological message ordering
- **Performance:** 512 MB memory, ~100ms execution time

### DynamoDB Table

Single-table design storing conversations, messages, and user profiles.

- **Table Name:** `conversations`
- **Billing:** On-demand (PAY_PER_REQUEST)
- **TTL:** 30-day automatic cleanup
- **Indexes:**
  - GSI1: Query conversations by user
  - GSI2: Query conversations by status (for escalations)
- **Streams:** Enabled for future event processing

See [ADR-008](docs/adr/ADR-008-dynamodb-schema-design.md) for schema design details.

### Shared Lambda Layer

Common utilities shared across all Lambda functions.

- **AWS Lambda Powertools:** Structured logging, tracing, metrics
- **Pydantic Models:** Type-safe request/response validation
- **DynamoDB Entities:** ConversationMetadata, MessageRecord, UserProfile
- **Repository Pattern:** Clean data access abstraction

---

## 📋 Prerequisites

- AWS Account with appropriate permissions
- Terraform ≥ **1.6.0**
- Python **3.12+** & **[uv](https://docs.astral.sh/uv/)**
- Node.js **18+**
- Docker (for Lambda builds and local testing)
- Git with SSH keys configured

---

## 🚀 Quick Start

### 1️⃣ Clone the Repository

```bash
git clone git@github.com:jujubear24/ai-customer-service-bot.git
cd ai-customer-service-bot
```

### 2️⃣ Run the Setup Script

Installs dependencies (Python + Node), generates config files, and installs pre-commit hooks:

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### 3️⃣ Configure AWS Credentials

```bash
aws configure
# Or use: make setup-aws
```

### 4️⃣ Set Up Terraform Backend

```bash
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your settings

terraform init
# Or use: make init-terraform
```

### 5️⃣ Build and Deploy

```bash
# Build Lambda artifacts
./scripts/build-lambdas.sh

# Deploy infrastructure
make tf-apply-dev
```

### 6️⃣ Test the API

```bash
# Get the chat endpoint
CHAT_URL=$(cd terraform/environments/dev && terraform output -raw chat_endpoint)

# Test the /chat endpoint (RAG-enhanced AI response)
curl -X POST "$CHAT_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I reset my password?",
    "tenant_id": "test-tenant"
  }'

# Test intent classification
curl -X POST "$(cd terraform/environments/dev && terraform output -raw classify_intent_endpoint)" \
  -H "Content-Type: application/json" \
  -d '{"message": "I need to speak to a manager"}'
```

---

## 📁 Project Structure

```bash
ai-customer-service-bot/
├── .github/                    # GitHub Actions workflows
├── docs/
│   ├── adr/                    # Architecture Decision Records (ADR-001 to ADR-011)
│   ├── architecture/           # System design docs
│   │   ├── data-flow.md
│   │   └── system-design.md
│   ├── guides/                 # Implementation guides
│   └── runbooks/               # Operational guides
├── knowledge-base-docs/        # RAG source documents
│   ├── docs/policies/          # Policy documents
│   └── faqs/                   # FAQ markdown files
├── lambda/
│   ├── functions/
│   │   ├── bedrock-handler/    # ✅ AI response generation
│   │   ├── chat-orchestrator/  # ✅ Chat flow orchestration
│   │   ├── context-builder/    # ✅ Context retrieval Lambda
│   │   ├── escalation-router/  # 📋 Escalation handling (planned)
│   │   ├── intent-classifier/  # ✅ Intent classification Lambda
│   │   ├── metrics-publisher/  # 📋 Custom metrics (planned)
│   │   ├── rag-retriever/      # ✅ Knowledge Base retrieval
│   │   └── response-validator/ # 📋 Output validation (planned)
│   ├── layers/
│   │   └── common/             # Shared Lambda layer
│   └── step-functions/         # Step Functions definitions (planned)
├── scripts/
│   ├── build-lambda-layer.sh   # Build shared layer
│   ├── build-lambdas.sh        # Build Lambda artifacts
│   ├── setup.sh                # Initial project setup
│   ├── sync-knowledge-base.sh  # Sync KB documents to S3
│   ├── test_chat_orchestrator.py  # E2E test script
│   └── ...                     # Other utility scripts
├── terraform/
│   ├── backend_bootstrap/      # S3/DynamoDB state backend setup
│   ├── environments/
│   │   ├── dev/                # Development environment
│   │   ├── staging/            # Staging environment
│   │   └── prod/               # Production environment
│   └── modules/
│       ├── api_gateway/        # REST API configuration
│       ├── bedrock/            # Bedrock IAM and config
│       ├── dynamodb/           # DynamoDB table and GSIs
│       ├── knowledge_base/     # Bedrock KB + Aurora PostgreSQL
│       ├── lambda/             # Lambda function module
│       ├── networking/         # VPC, subnets, security groups
│       └── observability/      # CloudWatch, X-Ray, alarms
├── tests/
│   ├── e2e/                    # End-to-end tests
│   ├── integration/            # Integration tests
│   ├── load/                   # Load/performance tests
│   └── unit/                   # Unit tests
├── Makefile                    # Common commands
└── pyproject.toml              # Root Python config
```

---

## 🛠️ Development

### 🧪 Running Tests

```bash
# Unit tests (Lambda functions)
cd lambda/functions/intent-classifier && uv run pytest -v
cd lambda/functions/context-builder && uv run pytest -v
cd lambda/functions/bedrock-handler && uv run pytest -v
cd lambda/functions/rag-retriever && uv run pytest -v
cd lambda/functions/chat-orchestrator && uv run pytest -v

# All tests with coverage
make test-unit

# E2E test for chat orchestrator
python scripts/test_chat_orchestrator.py

# Integration tests (when implemented)
make test-integration
```

### 🧹 Code Quality

```bash
make format        # Format code (Ruff, Terraform, Prettier)
make lint          # Lint without fixing
make typecheck     # Static type checking (mypy)
make validate      # Quick validation (no modifications)
make pre-commit    # Format + all checks
```

### 🧩 Local Development

```bash
# Start LocalStack + Redis + OpenSearch
make local-start

# Run Lambda locally (requires SAM CLI)
make run-lambda FUNCTION=intent-classifier

# View Lambda logs
make logs FUNCTION=intent-classifier

# Stop local environment
make local-stop
```

---

## 📊 Monitoring & Observability

- **CloudWatch Logs:** 7-day retention, structured JSON logging
- **X-Ray Tracing:** Distributed request tracing across all Lambdas
- **Custom Metrics:** Classification counts, latency percentiles, error rates, token usage
- **CloudWatch Alarms:** DynamoDB throttling, Lambda errors, Bedrock throttling

### Key Metrics (Phase 2)

| Metric | Source | Description |
|--------|--------|-------------|
| BedrockInvocations | Bedrock Handler | Total AI invocations |
| BedrockInputTokens | Bedrock Handler | Input token usage |
| BedrockOutputTokens | Bedrock Handler | Output token usage |
| BedrockLatency | Bedrock Handler | AI response time |
| DocumentsRetrieved | RAG Retriever | RAG documents found |
| RetrievalLatency | RAG Retriever | KB query time |
| AverageRelevanceScore | RAG Retriever | RAG result quality |

---

## 🔒 Security

- **Encryption:** Server-side encryption (SSE) for DynamoDB, S3, Aurora
- **IAM:** Least-privilege roles for all Lambda functions
- **API Gateway:** Request validation, throttling (100 burst, 50 req/sec)
- **VPC:** Aurora PostgreSQL in private subnets
- **Secrets:** Environment variables via Terraform (Secrets Manager planned)

> 📋 **TODO:** Create `docs/architecture/security.md` with detailed security documentation.

---

## 💰 Current Cost (Dev Environment)

| Service | Monthly Estimate |
|---------|------------------|
| Lambda | $1-5 |
| DynamoDB (on-demand) | $1-5 |
| API Gateway | $1-3 |
| CloudWatch | $1-3 |
| Aurora Serverless v2 | $15-50 |
| Bedrock (Claude Haiku) | $5-20 |
| S3 | <$1 |
| **Total** | **~$25-85** |

Costs scale with usage. Aurora Serverless v2 is the primary cost driver in dev.

---

## 📚 Documentation

- [Architecture Decision Records (ADRs)](docs/adr/)
- [System Architecture](docs/architecture/)
- [Operational Runbooks](docs/runbooks/)

### Key ADRs

| ADR | Title |
|-----|-------|
| [ADR-007](docs/adr/ADR-007-api-gateway-integration-and-request-validation.md) | API Gateway Integration |
| [ADR-008](docs/adr/ADR-008-dynamodb-schema-design.md) | DynamoDB Schema Design |
| [ADR-009](docs/adr/ADR-009-bedrock-integration.md) | Bedrock Integration |
| [ADR-010](docs/adr/ADR-010-knowledge-base-rag.md) | Knowledge Base RAG |
| [ADR-011](docs/adr/ADR-011-orchestrator-pattern.md) | Orchestrator Pattern |

---

## 🤝 Contributing

This is a **portfolio project**, but feedback is welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

---

## 📝 License

This project is licensed under the **MIT License** — see the [`LICENSE`](LICENSE) file for details.

---

## 🙏 Acknowledgments

- AWS Documentation & Best Practices
- Anthropic Claude API
- Terraform AWS Modules Community
- Astral (uv package manager)

---

## 📧 Contact

**Jules Bahanyi** — [julesbahanyi@gmail.com](mailto:julesbahanyi@gmail.com)

[LinkedIn](https://linkedin.com/in/jules-bahanyi) • [GitHub](https://github.com/jujubear24)

⭐ *If this project helped you learn cloud engineering, please give it a star!* ⭐
