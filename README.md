# 🤖 AI Customer Service Bot

A **production-grade, AI-powered customer service platform** built on AWS with **serverless architecture**, **intelligent intent classification**, and **context-aware responses**.

---

## 🎯 Project Overview

This project demonstrates advanced **cloud engineering** and **AI/ML integration** for customer service automation using:

- **AI/ML:** Amazon Bedrock (Claude 3.5 Sonnet), intent classification, sentiment analysis
- **Compute:** AWS Lambda (Python 3.12), Lambda Layers
- **Orchestration:** AWS Step Functions (planned), API Gateway
- **Data:** DynamoDB (single-table design)
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

### Phase 2: AI Integration 🚧

| Component | Status | Description |
|-----------|--------|-------------|
| Bedrock Handler Lambda | 📋 Planned | Claude integration for response generation |
| Response Validator Lambda | 📋 Planned | Output validation and safety checks |
| Step Functions Workflow | 📋 Planned | Orchestrate Lambda chain |

### Future Phases 📋

| Feature | Description |
|---------|-------------|
| RAG Integration | Knowledge base for accurate, contextual answers |
| Escalation Router | Priority-based routing to human agents |
| Real-Time Analytics | OpenSearch dashboards for metrics |
| Multi-Tenant Support | SaaS-ready with data isolation |
| WebSocket API | Real-time chat interface |

---

## 🏗️ Architecture

### Current State (Phase 1)

```bash
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /classify-intent
       ▼
┌──────────────────────────────────────────────┐
│          API Gateway (REST)                  │
│     • Request validation                     │
│     • CORS enabled                           │
│     • X-Ray tracing                          │
└──────┬───────────────────────────────────────┘
       │
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
                          │  • GSI1, GSI2    │
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
│  │ Intent → Context → Bedrock → Validate   │   │
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

See [ADR-008](docs/adr/008-dynamodb-schema-design.md) for schema design details.

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
./scripts/build-lambda-layer.sh

# Deploy infrastructure
make tf-apply-dev
```

### 6️⃣ Test the API

```bash
curl -X POST https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/dev/classify-intent \
  -H "Content-Type: application/json" \
  -d '{"message": "I need to speak to a manager"}'
```

---

## 📁 Project Structure

```bash
ai-customer-service-bot/
├── .github/                    # GitHub Actions workflows
├── terraform/                  # Infrastructure as Code
│   ├── modules/
│   │   ├── lambda/             # Lambda function module (dynamic for_each)
│   │   ├── api_gateway/        # REST API configuration
│   │   ├── dynamodb/           # DynamoDB table and GSIs
│   │   └── observability/      # CloudWatch, X-Ray, alarms
│   └── environments/
│       └── dev/                # Development environment
├── lambda/
│   ├── functions/
│   │   ├── intent-classifier/  # ✅ Intent classification Lambda
│   │   ├── context-builder/    # ✅ Context retrieval Lambda
│   │   ├── bedrock-handler/    # 📋 AI response generation (planned)
│   │   └── response-validator/ # 📋 Output validation (planned)
│   └── layers/
│       └── common/             # Shared Lambda layer
│           └── python/shared/
│               ├── models/
│               │   └── dynamodb.py    # Entity models
│               ├── repositories/
│               │   └── dynamodb.py    # Data access layer
│               ├── types.py           # Shared type definitions
│               └── exceptions.py      # Custom exceptions
├── web/                        # Next.js frontend (planned)
├── tests/                      # Integration and E2E tests
├── scripts/
│   ├── setup.sh                # Initial project setup
│   ├── build-lambdas.sh        # Build Lambda artifacts
│   └── build-lambda-layer.sh   # Build shared layer
├── docs/
│   ├── adr/                    # Architecture Decision Records
│   ├── architecture/           # System design docs
│   └── runbooks/               # Operational guides
└── Makefile                    # Common commands
```

---

## 🛠️ Development

### 🧪 Running Tests

```bash
# Unit tests (Lambda functions)
cd lambda/functions/intent-classifier && uv run pytest -v
cd lambda/functions/context-builder && uv run pytest -v

# All tests with coverage
make test-unit

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
- **Custom Metrics:** Classification counts, latency percentiles, error rates
- **CloudWatch Alarms:** DynamoDB throttling, Lambda errors

---

## 🔒 Security

- **Encryption:** Server-side encryption (SSE) for DynamoDB
- **IAM:** Least-privilege roles for all Lambda functions
- **API Gateway:** Request validation, throttling (100 burst, 50 req/sec)
- **Secrets:** Environment variables via Terraform (Secrets Manager planned)

See [`docs/architecture/security.md`](docs/architecture/security.md) for details.

---

## 💰 Current Cost (Dev Environment)

| Service | Monthly Estimate |
|---------|------------------|
| Lambda | $1-5 |
| DynamoDB (on-demand) | $1-5 |
| API Gateway | $1-3 |
| CloudWatch | $1-3 |
| **Total** | **~$5-15** |

Costs scale with usage. Production estimates available after Phase 2.

---

## 📚 Documentation

- [Architecture Decision Records (ADRs)](docs/adr/)
- [System Architecture](docs/architecture/)
- [Operational Runbooks](docs/runbooks/)

### Key ADRs

| ADR | Title |
|-----|-------|
| [ADR-007](docs/adr/007-api-gateway-integration-and-request-validation.md) | API Gateway Integration |
| [ADR-008](docs/adr/008-dynamodb-schema-design.md) | DynamoDB Schema Design |

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
