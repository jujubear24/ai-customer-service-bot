#!/bin/bash
# setup.sh - Initial project setup script

set -e

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Project variables
PROJECT_NAME="ai-customer-service-bot"
PYTHON_VERSION="3.12"
NODE_VERSION="18"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  AI Customer Service Bot - Setup      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if running from project root
if [ ! -f "Makefile" ]; then
    echo -e "${RED}❌ Error: Please run this script from the project root${NC}"
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print step
print_step() {
    echo ""
    echo -e "${BLUE}▶ $1${NC}"
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check prerequisites
print_step "Checking prerequisites..."

if ! command_exists python3; then
    print_error "Python 3 is not installed"
    exit 1
fi
print_success "Python 3 found"

if ! command_exists node; then
    print_error "Node.js is not installed"
    exit 1
fi
print_success "Node.js found"

if ! command_exists terraform; then
    print_warning "Terraform is not installed. Install from https://www.terraform.io/"
else
    print_success "Terraform found"
fi

if ! command_exists aws; then
    print_warning "AWS CLI is not installed. Install from https://aws.amazon.com/cli/"
else
    print_success "AWS CLI found"
fi

if ! command_exists docker; then
    print_warning "Docker is not installed. Install from https://www.docker.com/"
else
    print_success "Docker found"
fi

# Create directory structure
print_step "Creating directory structure..."

directories=(
    "lambda/layers/common/python/shared"
    "lambda/functions"
    "lambda/step-functions"
    "terraform/modules"
    "terraform/environments/dev"
    "terraform/environments/staging"
    "terraform/environments/prod"
    "tests/unit"
    "tests/integration"
    "tests/load"
    "tests/e2e"
    "scripts"
    "docs/adr"
    "docs/architecture"
    "docs/runbooks"
    "docs/api"
    "docs/setup"
    ".github/workflows"
    ".github/ISSUE_TEMPLATE"
)

for dir in "${directories[@]}"; do
    mkdir -p "$dir"
done
print_success "Directory structure created"

# Install Python dependencies
print_step "Installing dependencies with UV..."

if ! command_exists uv; then
    print_warning "UV not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to the current session's PATH
    export PATH="$HOME/.cargo/bin:$PATH"
    # The installer might modify .profile, but we source .cargo/env for the current session
    if ! command_exists uv; then
        print_warning "uv still not in PATH, trying to source cargo env..."
        source "$HOME/.cargo/env" 2>/dev/null || true
    fi
fi

if ! command_exists uv; then
    print_error "UV installation failed or it's not in PATH. Aborting."
    exit 1
fi

uv sync --all-extras
print_success "Dependencies installed with UV"

# Generate requirements.txt for Lambda compatibility
uv pip compile pyproject.toml -o requirements.txt
uv pip compile pyproject.toml --extra dev -o requirements-dev.txt
print_success "Requirements files generated"

# Install Node dependencies
print_step "Installing Node dependencies..."

if [ -d "web" ] && [ -f "web/package.json" ]; then
    cd web
    npm install
    cd ..
    print_success "Node dependencies installed"
else
    print_warning "web/package.json not found. Creating basic Next.js structure..."
    mkdir -p web
    cd web
    npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --import-alias "@/*" --use-npm
    cd ..
    print_success "Next.js project initialized"
fi

# Install pre-commit hooks
print_step "Installing pre-commit hooks..."

if command_exists uv; then
    # Assumes pre-commit is a dev dependency in pyproject.toml
    uv run pre-commit install
    print_success "Pre-commit hooks installed via uv"
elif command_exists pre-commit; then
    # Fallback for older setups or if uv failed
    print_warning "uv command not found. Falling back to system pre-commit."
    pre-commit install
    print_success "Pre-commit hooks installed"
else
    print_error "Could not find uv or pre-commit. Skipping hook installation."
    print_warning "Please ensure pre-commit is added as a dev dependency in pyproject.toml"
fi

# Create .env.example file
print_step "Creating environment template..."

cat > .env.example << 'EOF'
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=your-account-id

# Environment
ENVIRONMENT=dev

# DynamoDB
CONVERSATIONS_TABLE=ai-customer-service-conversations-dev

# Redis
REDIS_ENDPOINT=your-redis-endpoint
REDIS_AUTH_TOKEN=your-redis-token

# OpenSearch
OPENSEARCH_ENDPOINT=your-opensearch-endpoint

# Bedrock
KNOWLEDGE_BASE_ID=your-knowledge-base-id

# API Gateway
API_GATEWAY_URL=https://your-api-gateway-url

# Cognito
COGNITO_USER_POOL_ID=your-user-pool-id
COGNITO_CLIENT_ID=your-client-id

# Next.js (for web/.env.local)
NEXT_PUBLIC_API_URL=https://api-dev.example.com
NEXT_PUBLIC_WEBSOCKET_URL=wss://ws-dev.example.com
NEXT_PUBLIC_COGNITO_USER_POOL_ID=your-user-pool-id
NEXT_PUBLIC_COGNITO_CLIENT_ID=your-client-id
NEXT_PUBLIC_AWS_REGION=us-east-1
EOF

print_success "Environment template created (.env.example)"

# Create initial terraform.tfvars.example
print_step "Creating Terraform variables template..."

cat > terraform/environments/dev/terraform.tfvars.example << 'EOF'
# Project Configuration
project_name = "ai-customer-service-bot"
environment  = "dev"
aws_region   = "us-east-1"

# Networking
vpc_cidr              = "10.0.0.0/16"
availability_zones    = ["us-east-1a", "us-east-1b"]
private_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
public_subnet_cidrs   = ["10.0.101.0/24", "10.0.102.0/24"]

# Tags
common_tags = {
  Project     = "ai-customer-service-bot"
  Environment = "dev"
  ManagedBy   = "terraform"
  Owner       = "your-name"
}

# WAF
allowed_countries = ["US", "CA"]

# OpenSearch
opensearch_master_user = "admin"

# Alerting
alert_email = "your-email@example.com"
EOF

print_success "Terraform variables template created"

# Create VERSION file
print_step "Creating VERSION file..."
echo "0.1.0" > VERSION
print_success "VERSION file created"

# Create LICENSE file
print_step "Creating LICENSE file..."

cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2024

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF

print_success "LICENSE file created"

# Create initial ADR template
print_step "Creating ADR template..."

cat > docs/adr/template.md << 'EOF'
# ADR-XXX: [Title]

**Date:** YYYY-MM-DD
**Status:** [Proposed | Accepted | Deprecated | Superseded]
**Deciders:** [List of people involved]

## Context

What is the issue that we're addressing? What are the forces at play?

## Decision

What is the change that we're proposing and/or doing?

## Consequences

What becomes easier or more difficult to do because of this change?

### Positive

- Benefit 1
- Benefit 2

### Negative

- Drawback 1
- Drawback 2

### Neutral

- Trade-off 1

## Alternatives Considered

What other options were considered?

### Option 1
Description and why it was not chosen

### Option 2
Description and why it was not chosen

## References

- [Link to documentation]
- [Related ADRs]
EOF

print_success "ADR template created"

# Create docker-compose for local development
print_step "Creating docker-compose for local development..."

cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  localstack:
    image: localstack/localstack:latest
    ports:
      - "4566:4566"
      - "4571:4571"
    environment:
      - SERVICES=s3,dynamodb,lambda,sqs,sns,apigateway,cloudwatch,secretsmanager
      - DEBUG=1
      - DATA_DIR=/tmp/localstack/data
      - LAMBDA_EXECUTOR=docker
      - DOCKER_HOST=unix:///var/run/docker.sock
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock"
      - "./localstack-data:/tmp/localstack"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --requirepass devpassword

  opensearch:
    image: opensearchproject/opensearch:2.11.0
    environment:
      - discovery.type=single-node
      - "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m"
      - "DISABLE_SECURITY_PLUGIN=true"
    ports:
      - "9200:9200"
      - "9600:9600"
    volumes:
      - opensearch-data:/usr/share/opensearch/data

  opensearch-dashboards:
    image: opensearchproject/opensearch-dashboards:2.11.0
    ports:
      - "5601:5601"
    environment:
      - 'OPENSEARCH_HOSTS=["http://opensearch:9200"]'
      - "DISABLE_SECURITY_DASHBOARDS_PLUGIN=true"
    depends_on:
      - opensearch

volumes:
  opensearch-data:
EOF

print_success "docker-compose.yml created"

# Initialize git repository if not already initialized
if [ ! -d ".git" ]; then
    print_step "Initializing Git repository..."
    git init
    git add .
    git commit -m "Initial commit: Project structure setup"
    print_success "Git repository initialized"
else
    print_success "Git repository already initialized"
fi

# Summary
echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✓ Setup Complete!                    ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "1. Configure AWS credentials:"
echo "   ${YELLOW}aws configure${NC}"
echo ""
echo "2. Copy and edit environment files:"
echo "   ${YELLOW}cp .env.example .env${NC}"
echo "   ${YELLOW}cp terraform/environments/dev/terraform.tfvars.example terraform/environments/dev/terraform.tfvars${NC}"
echo ""
echo "3. Initialize Terraform:"
echo "   ${YELLOW}make init-terraform${NC}"
echo ""
echo "4. Start local development environment:"
echo "   ${YELLOW}make local-start${NC}"
echo ""
echo "5. Run tests:"
echo "   ${YELLOW}make test-all${NC}"
echo ""
echo -e "${GREEN}For more commands, run: ${YELLOW}make help${NC}"
echo ""
echo -e "${BLUE}Documentation: ${NC}docs/"
echo -e "${BLUE}GitHub: ${NC}https://github.com/YOUR_USERNAME/${PROJECT_NAME}"
echo ""
