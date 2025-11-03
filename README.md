# AI Customer Service Bot

> A production-grade, AI-powered customer service platform built on AWS with multi-tenant support, real-time analytics, and intelligent escalation handling.

[![CI/CD](https://github.com/jujubear24/ai-customer-service-bot/workflows/CI/badge.svg)](https://github.com/jujubear24/ai-customer-service-bot/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Terraform](https://img.shields.io/badge/terraform-1.6+-purple.svg)](https://www.terraform.io/)

## 🎯 Project Overview

This is a **portfolio project** demonstrating advanced cloud engineering skills for customer service automation using:

- **AI/ML**: Amazon Bedrock (Claude 3.5 Sonnet), Knowledge Bases for RAG, Amazon Comprehend
- **Orchestration**: AWS Step Functions, EventBridge, SQS
- **Data**: DynamoDB with DAX, ElastiCache Redis, OpenSearch
- **Frontend**: Next.js 14 with TypeScript, Tailwind CSS, shadcn/ui
- **Infrastructure**: Terraform, GitHub Actions CI/CD
- **Observability**: CloudWatch, X-Ray, custom metrics

### Key Features

✅ **Intelligent Conversation Handling** - Multi-step workflow with context management  
✅ **RAG-Enhanced Responses** - Knowledge base integration for accurate answers  
✅ **Sentiment Analysis** - Real-time emotion tracking with escalation triggers  
✅ **Smart Escalation** - Priority-based routing to human agents  
✅ **Multi-Tenant Architecture** - SaaS-ready with data isolation  
✅ **Real-Time Analytics** - OpenSearch-powered dashboards  
✅ **Production-Grade Security** - WAF, encryption, audit logging

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
│   + DAX        │   + KB   │  Cache   │Analytics│
└────────────────┴──────────┴──────────┴──────────┘
```

See [Architecture Documentation](docs/architecture/system-design.md) for details.

## 📋 Prerequisites

- **AWS Account** with appropriate permissions
- **Terraform** >= 1.6.0
- **Python** 3.11+
- **Node.js** 18+
- **Docker** (for local testing)
- **Git** with SSH keys configured

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone git@github.com:jujubear24/ai-customer-service-bot.git
cd ai-customer-service-bot
```

### 2. Install Dependencies

```bash
# Python dependencies
pip install -r requirements.txt

# Node dependencies
cd web && npm install && cd ..

# Pre-commit hooks
pre-commit install
```

### 3. Configure AWS Credentials

```bash
aws configure
# Enter your AWS Access Key ID, Secret Key, and Region
```

### 4. Set Up Terraform Backend

```bash
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your settings

terraform init
```

### 5. Deploy Infrastructure

```bash
# Deploy to dev environment
make deploy-dev

# Or manually
cd terraform/environments/dev
terraform plan
terraform apply
```

### 6. Seed Knowledge Base

```bash
python scripts/seed-knowledge-base.py --environment dev
```

### 7. Run Locally (Optional)

```bash
# Start local dev environment with LocalStack
docker-compose up -d

# Run Next.js frontend
cd web
npm run dev
```

## 📁 Project Structure

```
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
```

## 🛠️ Development

### Running Tests

```bash
# Unit tests
make test-unit

# Integration tests
make test-integration

# E2E tests
make test-e2e

# All tests with coverage
make test-all
```

### Code Quality

```bash
# Format code
make format

# Lint
make lint

# Type check
make typecheck

# Security scan
make security-scan
```

### Local Development

```bash
# Start LocalStack
docker-compose up -d

# Run Lambda locally
make run-lambda FUNCTION=intent-classifier

# View logs
make logs FUNCTION=intent-classifier
```

## 📊 Monitoring & Observability

- **CloudWatch Dashboard**: [Link to dashboard]
- **X-Ray Service Map**: Traces distributed requests
- **OpenSearch Dashboards**: Real-time analytics
- **Custom Metrics**: Resolution rate, response time, sentiment

## 🔒 Security

- **Encryption**: At-rest (KMS) and in-transit (TLS 1.3)
- **IAM**: Least-privilege roles for all services
- **WAF**: Rate limiting, geo-blocking, OWASP rules
- **Secrets**: Managed via AWS Secrets Manager with rotation
- **Audit Logs**: All actions logged to Kinesis/S3

See [Security Documentation](docs/architecture/security.md).

## 💰 Cost Estimation

| Service | Monthly Cost (Dev) | Monthly Cost (Prod) |
|---------|-------------------|---------------------|
| Lambda | $5 | $50 |
| DynamoDB | $5 | $30 |
| Bedrock | $20 | $200 |
| ElastiCache | $15 | $100 |
| OpenSearch | $30 | $150 |
| Other | $10 | $50 |
| **Total** | **~$85** | **~$580** |

See [Cost Analysis](docs/runbooks/cost-optimization.md) for details.

## 📚 Documentation

- [System Architecture](docs/architecture/system-design.md)
- [API Documentation](docs/api/openapi.yaml)
- [Deployment Guide](docs/setup/deployment.md)
- [Local Development Setup](docs/setup/local-development.md)
- [Architecture Decision Records](docs/adr/)
- [Incident Response Runbook](docs/runbooks/incident-response.md)

## 🤝 Contributing

This is a portfolio project, but feedback is welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## 📝 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file.

## 🙏 Acknowledgments

- AWS Documentation and Best Practices
- Anthropic Claude API
- Terraform AWS Modules Community
- Next.js Team

## 📧 Contact

**Jules Bahanyi** - [julesbahanyi@gmail.com](mailto:julesbahanyi@gmail.com)
 
LinkedIn: [linkedin.com/in/jules-bahanyi](https://www.linkedin.com/in/jules-bahanyi/)  
GitHub: [@jujubear24](https://github.com/yourusername)

---

⭐ **If this project helped you learn cloud engineering, please give it a star!** ⭐
