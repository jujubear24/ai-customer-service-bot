# 🤖 AI Customer Service Bot

A **production-grade, AI-powered customer service platform** built on AWS with **multi-tenant support**, **real-time analytics**, and **intelligent escalation handling**.

---

## 🎯 Project Overview

This project demonstrates advanced **cloud engineering** and **AI/ML integration** for customer service automation using:

- **AI/ML:** Amazon Bedrock (Claude 3.5 Sonnet), Knowledge Bases for RAG, Amazon Comprehend
- **Orchestration:** AWS Step Functions, EventBridge, SQS
- **Data:** DynamoDB with DAX, ElastiCache Redis, OpenSearch
- **Frontend:** Next.js 14, TypeScript, Tailwind CSS, shadcn/ui
- **Infrastructure:** Terraform, GitHub Actions CI/CD
- **Observability:** CloudWatch, X-Ray, custom metrics

---

## ✨ Key Features

✅ **Intelligent Conversation Handling** — Multi-step workflow with context management
✅ **RAG-Enhanced Responses** — Knowledge base integration for accurate answers
✅ **Sentiment Analysis** — Real-time emotion tracking with escalation triggers
✅ **Smart Escalation** — Priority-based routing to human agents
✅ **Multi-Tenant Architecture** — SaaS-ready with data isolation
✅ **Real-Time Analytics** — OpenSearch-powered dashboards
✅ **Production-Grade Security** — WAF, encryption, audit logging

---

## 🏗️ Architecture

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
```bash

See [`docs/architecture/system-design.md`](docs/architecture/system-design.md) for details.

---

## 📋 Prerequisites

* AWS Account with appropriate permissions
* Terraform ≥ **1.6.0**
* Python **3.12+** & **uv**
* Node.js **18+**
* Docker (for local testing)
* Git with SSH keys configured

---

## 🚀 Quick Start

### 1️⃣ Clone the Repository

```bash
git clone git@github.com:jujubear24/ai-customer-service-bot.git
cd ai-customer-service-bot
```bash

### 2️⃣ Run the Setup Script

Installs dependencies (Python + Node), generates config files, and installs pre-commit hooks:

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```bash

### 3️⃣ Configure AWS Credentials

```bash
aws configure
# Enter your AWS Access Key ID, Secret Key, and Region
```bash

### 4️⃣ Set Up Terraform Backend

```bash
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your settings

terraform init
```bash

### 5️⃣ Deploy Infrastructure

```bash
# Deploy to dev environment
make deploy-dev

# Or manually
cd terraform/environments/dev
terraform plan
terraform apply
```bash

### 6️⃣ Seed Knowledge Base

```bash
python scripts/seed-knowledge-base.py --environment dev
```bash

### 7️⃣ Run Locally (Optional)

```bash
# Start LocalStack for AWS emulation
docker-compose up -d

# Run Next.js frontend
cd web
npm run dev
```bash

---

## 📁 Project Structure

```bash
ai-customer-service-bot/
├── .github/              # GitHub Actions workflows
├── terraform/            # Infrastructure as Code
│   ├── modules/          # Reusable Terraform modules
│   └── environments/     # Environment-specific configs
├── lambda/               # Lambda functions
│   ├── layers/           # Shared Lambda layers
│   └── functions/        # Individual Lambda functions
├── web/                  # Next.js frontend
├── tests/                # Integration and E2E tests
├── scripts/              # Utility scripts
├── docs/                 # Documentation
│   ├── adr/              # Architecture Decision Records
│   ├── architecture/     # System design docs
│   └── runbooks/         # Operational guides
└── Makefile              # Common commands
```bash

---

## 🛠️ Development

### 🧪 Running Tests

```bash
# Unit tests
make test-unit

# Integration tests
make test-integration

# E2E tests
make test-e2e

# All tests with coverage
make test-all
```bash

### 🧹 Code Quality

```bash
make format        # Format code
make lint          # Lint with Ruff
make typecheck     # Static type checking
make security-scan # Security scanning
```bash

### 🧩 Local Development

```bash
# Start LocalStack
docker-compose up -d

# Run Lambda locally
make run-lambda FUNCTION=intent-classifier

# View logs
make logs FUNCTION=intent-classifier
```bash

---

## 📊 Monitoring & Observability

* **CloudWatch Dashboard:** [Link to dashboard]
* **X-Ray Service Map:** Distributed request tracing
* **OpenSearch Dashboards:** Real-time analytics
* **Custom Metrics:** Resolution rate, response time, sentiment

---

## 🔒 Security

* **Encryption:** At rest (KMS) and in transit (TLS 1.3)
* **IAM:** Least-privilege roles for all services
* **WAF:** Rate limiting, geo-blocking, OWASP rules
* **Secrets:** AWS Secrets Manager with rotation
* **Audit Logs:** Logged to Kinesis/S3

See [`docs/architecture/security.md`](docs/architecture/security.md) for more details.

---

## 💰 Cost Estimation

| Service     | Monthly (Dev) | Monthly (Prod) |
| ----------- | ------------- | -------------- |
| Lambda      | $5            | $50            |
| DynamoDB    | $5            | $30            |
| Bedrock     | $20           | $200           |
| ElastiCache | $15           | $100           |
| OpenSearch  | $30           | $150           |
| Other       | $10           | $50            |
| **Total**   | **~$85**      | **~$580**      |

See [`docs/runbooks/cost-optimization.md`](docs/runbooks/cost-optimization.md) for details.

---

## 📚 Documentation

* **System Architecture**
* **API Documentation**
* **Deployment Guide**
* **Local Development Setup**
* **Architecture Decision Records (ADRs)**
* **Incident Response Runbook**

---

## 🤝 Contributing

This is a **portfolio project**, but feedback is welcome!

1. Fork the repository
2. Create a feature branch:

   ```bash
   git checkout -b feature/amazing-feature
   ```

1. Commit your changes:

   ```bash
   git commit -m 'Add amazing feature'
   ```

2. Push to the branch:

   ```bash
   git push origin feature/amazing-feature
   ```

3. Open a Pull Request

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

---

## 📝 License

This project is licensed under the **MIT License** — see the [`LICENSE`](LICENSE) file for details.

---

## 🙏 Acknowledgments

- AWS Documentation & Best Practices
- Anthropic Claude API
- Terraform AWS Modules Community
- Next.js Team

---

## 📧 Contact

**Jules Bahanyi** — [julesbahanyi@gmail.com](mailto:julesbahanyi@gmail.com)
[LinkedIn](https://linkedin.com/in/jules-bahanyi) • [GitHub](https://github.com/jujubear24)

⭐ *If this project helped you learn cloud engineering, please give it a star!* ⭐
