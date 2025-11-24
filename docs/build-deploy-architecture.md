# Build & Deploy Architecture

## Overview

This document illustrates the separation of build and deploy phases in our Lambda deployment pipeline.

---

## 🏗️ Build Phase (Shell Scripts + Docker + uv)

```bash
┌─────────────────────────────────────────────────────────────────┐
│                    ./scripts/build-lambdas.sh                   │
│                         (Orchestrator)                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
┌───────────────────────────┐  ┌──────────────────────────────┐
│ build-lambda-layer.sh     │  │ Function Packaging           │
│                           │  │                              │
│ ┌───────────────────────┐ │  │ For each function:          │
│ │ Docker Container      │ │  │ ┌────────────────────────┐ │
│ │ (Lambda Python 3.12)  │ │  │ │ Check pyproject.toml   │ │
│ │                       │ │  │ │ for dependencies       │ │
│ │ 1. Copy shared code   │ │  │ └────────┬───────────────┘ │
│ │    └─ shared/         │ │  │          │                 │
│ │                       │ │  │          ├─ If deps exist: │
│ │ 2. Install deps:      │ │  │          │   ┌──────────────┐
│ │    ├─ boto3           │ │  │          │   │ Docker build │
│ │    ├─ pydantic        │ │  │          │   │ with deps    │
│ │    ├─ powertools      │ │  │          │   └──────────────┘
│ │    └─ redis           │ │  │          │                 │
│ │                       │ │  │          └─ Else:          │
│ │ 3. Clean artifacts    │ │  │              ┌──────────────┐
│ │    ├─ __pycache__     │ │  │              │ Simple ZIP   │
│ │    ├─ *.dist-info     │ │  │              │ source only  │
│ │    └─ tests/          │ │  │              └──────────────┘
│ │                       │ │  │                              │
│ │ 4. Create ZIP         │ │  │ Create function ZIPs        │
│ └───────────────────────┘ │  └──────────────────────────────┘
│                           │
│ Output:                   │  Output:
│ shared-layer.zip (~15MB)  │  intent-classifier.zip (~10KB)
└───────────────────────────┘  context-builder.zip (future)
                               bedrock-handler.zip (future)
                │
                └──────────────────────┐
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │  terraform/modules/lambda/   │
                        │         builds/              │
                        │                              │
                        │  📦 shared-layer.zip         │
                        │  📦 intent-classifier.zip    │
                        │  📦 context-builder.zip      │
                        │  📦 bedrock-handler.zip      │
                        └──────────────────────────────┘
```

---

## 🚀 Deploy Phase (Terraform)

```bash
┌─────────────────────────────────────────────────────────────────┐
│              terraform apply (dev environment)                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
┌───────────────────────────┐  ┌──────────────────────────────┐
│  Lambda Layer Deployment  │  │  Lambda Function Deployment  │
│                           │  │                              │
│  aws_lambda_layer_version │  │  aws_lambda_function         │
│  "shared"                 │  │  "intent_classifier"         │
│                           │  │                              │
│  filename =               │  │  filename =                  │
│    builds/shared-layer    │  │    builds/intent-classifier  │
│                           │  │                              │
│  source_code_hash =       │  │  source_code_hash =          │
│    filebase64sha256(...)  │  │    filebase64sha256(...)     │
└───────────────────────────┘  └──────────────────────────────┘
                │                              │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │       IAM Roles & Policies   │
                │                              │
                │  ├─ Lambda execution role    │
                │  ├─ CloudWatch logs          │
                │  ├─ X-Ray tracing            │
                │  └─ CloudWatch metrics       │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │      API Gateway             │
                │                              │
                │  ├─ REST API                 │
                │  ├─ /classify-intent         │
                │  ├─ Lambda integration       │
                │  ├─ CORS config              │
                │  └─ Request validation       │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │     Observability            │
                │                              │
                │  ├─ CloudWatch Logs          │
                │  ├─ X-Ray Traces             │
                │  ├─ Custom Metrics           │
                │  └─ Budget Alerts            │
                └──────────────────────────────┘
```

---

## 📋 Workflow Comparison

### Old Approach (Mixed Responsibilities)

```bash
# Layer build
./scripts/build-lambda-layer.sh    # Docker + Shell

# Function "build" (not really building)
terraform apply                    # Terraform zips source
                                   # ❌ Can't handle function deps
                                   # ❌ No Docker compilation
```

### New Approach (Separation of Concerns)

```bash
# Build Phase: All packaging with Docker
./scripts/build-lambdas.sh
  ├─> Builds layer (Docker)
  └─> Builds functions (Docker if needed)

# Deploy Phase: Infrastructure only
terraform apply
  └─> References pre-built artifacts
```

---

## 🎯 Key Benefits

| Aspect | Old Approach | New Approach |
|--------|-------------|--------------|
| **Build Tool** | Mixed (Shell + Terraform) | Unified (Shell + Docker) |
| **Function Deps** | ❌ Not supported | ✅ Fully supported |
| **Consistency** | ❌ Layer≠Function | ✅ All use Docker |
| **CI/CD** | ❌ Build during deploy | ✅ Build once, deploy many |
| **Terraform Role** | Build + Deploy | ✅ Deploy only |
| **Portability** | ❌ Tied to Terraform | ✅ Artifacts are portable |
| **Speed** | Slow (builds each time) | ✅ Fast (cached builds) |

---

## 🔄 Development Workflow

### Quick Changes (Code Only)

```bash
# 1. Edit code
vim lambda/functions/intent-classifier/src/handler.py

# 2. Test locally
cd lambda/functions/intent-classifier
uv run pytest -v

# 3. Rebuild functions only (skip layer)
cd ../../..
./scripts/build-lambdas.sh --functions-only

# 4. Deploy
cd terraform/environments/dev
terraform apply
```

### Dependency Changes (Layer + Functions)

```bash
# 1. Update dependencies
vim lambda/layers/common/pyproject.toml

# 2. Full rebuild
./scripts/build-lambdas.sh

# 3. Deploy
cd terraform/environments/dev
terraform apply
```

### Layer Only (Shared Code Changes)

```bash
# 1. Edit shared code
vim lambda/layers/common/python/shared/types.py

# 2. Rebuild layer only
./scripts/build-lambdas.sh --layer-only

# 3. Deploy
cd terraform/environments/dev
terraform apply
```

---

## 📦 Artifact Structure

### Layer Package (`shared-layer.zip`)

```bash
python/
├── shared/                    # Your custom code
│   ├── __init__.py
│   ├── config.py
│   ├── types.py
│   ├── utils.py
│   ├── exceptions.py
│   ├── logger.py
│   ├── metrics.py
│   ├── cache_client.py
│   └── tracing.py
├── boto3/                     # Dependencies
├── pydantic/
├── aws_lambda_powertools/
└── redis/
```

### Function Package (`intent-classifier.zip`)

```bash
handler.py                     # Entry point
classifier.py                  # Business logic
[optional dependencies/]       # If function-specific deps exist
```

---

## 🎓 Why This Architecture?

### Problem: Python Dependency Complexity

- Packages like `pydantic` have **native extensions** (C/Rust code)
- Must be compiled for the **target platform** (Amazon Linux 2)
- Terraform isn't designed for build toolchains
- Mixed build approaches lead to inconsistency

### Solution: Separation of Concerns

- **Build Phase**: Handle all Python complexity with proper tools (Docker, uv)
- **Deploy Phase**: Terraform focuses on infrastructure (IAM, networking, config)

### Result

- ✅ Clean, maintainable codebase
- ✅ Predictable builds
- ✅ CI/CD friendly
- ✅ Production-ready architecture

---

## 🚀 CI/CD Integration (Future)

```yaml
# .github/workflows/deploy.yml (example)
name: Deploy Lambda Functions

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build Lambda Artifacts
        run: ./scripts/build-lambdas.sh

      - name: Run Tests
        run: |
          cd lambda/functions/intent-classifier
          uv run pytest

      - name: Upload Artifacts
        uses: actions/upload-artifact@v3
        with:
          name: lambda-builds
          path: terraform/modules/lambda/builds/

  deploy-dev:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Download Artifacts
        uses: actions/download-artifact@v3
        with:
          name: lambda-builds
          path: terraform/modules/lambda/builds/

      - name: Terraform Deploy
        run: |
          cd terraform/environments/dev
          terraform init
          terraform apply -auto-approve
```

---

## 📚 Related Documentation

- [Lambda Module README](../../terraform/modules/lambda/README.md)
- [Build Scripts Documentation](../../scripts/README.md)
- [Sprint 1.1 Summary](./sprint-1.1-summary.md)
- [Architecture Decision Records](../adr/)

---

Last Updated: November 23, 2025
