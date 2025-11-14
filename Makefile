.PHONY: help install add-dep add-dev-dep update-deps setup-aws init-terraform \
        format lint typecheck security-scan validate \
        test-unit test-integration test-e2e test-all test coverage \
        tf-plan-dev tf-apply-dev tf-plan-prod tf-apply-prod tf-destroy-dev \
        deploy deploy-dev deploy-lambdas deploy-web \
        local-start local-stop run-lambda logs \
        seed-kb create-user performance-test clean docs check pre-commit ci \
        version status cost check-uv check-terraform check-aws

# Variables
PYTHON := python3.12
TERRAFORM := terraform
AWS_REGION := us-east-1
PROJECT_NAME := ai-customer-service-bot
ENV ?= dev
FUNCTION ?=
PKG ?=

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[1;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Available commands:$(NC)"
	@echo ""
	@echo "$(BLUE)Setup & Dependencies:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(install|add-dep|update-deps|setup-aws|init-terraform)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)Development:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(format|lint|typecheck|validate|security-scan|check|pre-commit|ci)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)Testing:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(test|coverage|performance-test)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)Infrastructure:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(tf-|deploy|local-)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)Utilities:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(seed|create-user|run-lambda|logs|clean|docs|version|status|cost)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# Dependency checks
check-uv: ## Check if uv is installed
	@command -v uv >/dev/null 2>&1 || { echo "$(RED)Error: uv is not installed. Install from https://docs.astral.sh/uv/$(NC)"; exit 1; }

check-terraform: ## Check if terraform is installed
	@command -v terraform >/dev/null 2>&1 || { echo "$(RED)Error: terraform is not installed$(NC)"; exit 1; }

check-aws: ## Check if AWS CLI is configured
	@aws sts get-caller-identity >/dev/null 2>&1 || { echo "$(RED)Error: AWS CLI not configured. Run 'make setup-aws'$(NC)"; exit 1; }

## Setup & Dependency Commands
install: check-uv ## Install all dependencies with UV
	@echo "$(BLUE)Installing dependencies with UV...$(NC)"
	uv sync --all-extras
	@echo "$(BLUE)Installing Node dependencies...$(NC)"
	cd web && npm install
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	uv run pre-commit install
	@echo "$(GREEN)✓ Installation complete$(NC)"

add-dep: check-uv ## Add a new dependency (use: make add-dep PKG=package-name)
ifndef PKG
	@echo "$(RED)Error: PKG is required. Usage: make add-dep PKG=boto3$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Adding dependency: $(PKG)$(NC)"
	uv add $(PKG)
	@echo "$(GREEN)✓ Dependency added$(NC)"

add-dev-dep: check-uv ## Add a dev dependency (use: make add-dev-dep PKG=package-name)
ifndef PKG
	@echo "$(RED)Error: PKG is required. Usage: make add-dev-dep PKG=pytest$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Adding dev dependency: $(PKG)$(NC)"
	uv add --dev $(PKG)
	@echo "$(GREEN)✓ Dev dependency added$(NC)"

update-deps: check-uv ## Update all dependencies
	@echo "$(BLUE)Updating dependencies...$(NC)"
	uv sync --upgrade
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

setup-aws: ## Configure AWS CLI
	@echo "$(BLUE)Configuring AWS CLI...$(NC)"
	aws configure
	@echo "$(GREEN)✓ AWS configured$(NC)"

init-terraform: check-terraform ## Initialize Terraform backend
	@echo "$(BLUE)Initializing Terraform...$(NC)"
	cd terraform/environments/dev && $(TERRAFORM) init
	@echo "$(GREEN)✓ Terraform initialized$(NC)"

## Development Commands

format: check-uv ## Format code (Python, Terraform, TypeScript)
	@echo "$(BLUE)Formatting Python code...$(NC)"
	uv run ruff format lambda/
	uv run ruff check lambda/ --fix
	@echo "$(BLUE)Formatting Terraform code...$(NC)"
	$(TERRAFORM) fmt -recursive terraform/
	@echo "$(BLUE)Formatting TypeScript code...$(NC)"
	cd web && npm run format
	@echo "$(GREEN)✓ Code formatted$(NC)"

lint: check-uv ## Run linters (without fixing)
	@echo "$(BLUE)Linting Python code...$(NC)"
	uv run ruff check lambda/
	@echo "$(BLUE)Linting TypeScript code...$(NC)"
	cd web && npm run lint
	@echo "$(GREEN)✓ Linting complete$(NC)"

typecheck: ## Run type checkers
	@echo "$(BLUE)Type checking Python code...$(NC)"
	./scripts/lint-lambdas.sh
	@echo "$(BLUE)Type checking TypeScript code...$(NC)"
	cd web && npm run typecheck
	@echo "$(GREEN)✓ Type checking complete$(NC)"

validate: check-uv ## Quick validation (format check + lint, no modifications)
	@echo "$(BLUE)Checking Python formatting...$(NC)"
	uv run ruff format lambda/ --check
	@echo "$(BLUE)Checking Python linting...$(NC)"
	uv run ruff check lambda/
	@echo "$(GREEN)✓ Validation passed$(NC)"

security-scan: check-uv ## Run security scans
	@echo "$(BLUE)Running security scans...$(NC)"
	uv run bandit -r lambda/ -ll
	cd terraform && tfsec .
	@echo "$(GREEN)✓ Security scan complete$(NC)"

check: lint typecheck test-unit ## Run all checks (without formatting)
	@echo "$(GREEN)✓ All checks passed$(NC)"

pre-commit: format check ## Format and run all checks (pre-commit workflow)
	@echo "$(GREEN)✓ Ready to commit$(NC)"

ci: lint typecheck test-all security-scan ## Run all CI checks
	@echo "$(GREEN)✓ CI checks passed$(NC)"

## Testing Commands

test-unit: check-uv ## Run unit tests
	@echo "$(BLUE)Running Python unit tests...$(NC)"
	cd lambda && uv run pytest tests/unit -v --cov=functions --cov-report=term-missing
	@echo "$(BLUE)Running TypeScript unit tests...$(NC)"
	cd web && npm run test
	@echo "$(GREEN)✓ Unit tests complete$(NC)"

test-integration: check-uv ## Run integration tests
	@echo "$(BLUE)Running integration tests...$(NC)"
	cd lambda && uv run pytest tests/integration -v
	@echo "$(GREEN)✓ Integration tests complete$(NC)"

test-e2e: ## Run end-to-end tests
	@echo "$(BLUE)Running E2E tests...$(NC)"
	cd web && npm run test:e2e
	@echo "$(GREEN)✓ E2E tests complete$(NC)"

test-all: test-unit test-integration ## Run all tests
	@echo "$(GREEN)✓ All tests complete$(NC)"

test: test-all ## Alias for test-all

coverage: check-uv ## Generate coverage report
	@echo "$(BLUE)Generating coverage report...$(NC)"
	cd lambda && uv run pytest tests/ --cov=functions --cov-report=html
	@echo "$(GREEN)✓ Coverage report generated at lambda/htmlcov/index.html$(NC)"

performance-test: check-uv ## Run performance tests
	@echo "$(BLUE)Running performance tests...$(NC)"
	uv run locust -f tests/load/locustfile.py --headless --users 50 --spawn-rate 5 --run-time 2m
	@echo "$(GREEN)✓ Performance test complete$(NC)"

## Infrastructure Commands

tf-plan-dev: check-terraform ## Terraform plan for dev
	@echo "$(BLUE)Running Terraform plan for dev...$(NC)"
	cd terraform/environments/dev && $(TERRAFORM) plan

tf-apply-dev: check-terraform ## Terraform apply for dev
	@echo "$(BLUE)Applying Terraform for dev...$(NC)"
	cd terraform/environments/dev && $(TERRAFORM) apply

tf-plan-prod: check-terraform ## Terraform plan for prod
	@echo "$(BLUE)Running Terraform plan for prod...$(NC)"
	cd terraform/environments/prod && $(TERRAFORM) plan

tf-apply-prod: check-terraform ## Terraform apply for prod (with approval)
	@echo "$(RED)⚠️  Deploying to PRODUCTION$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1
	cd terraform/environments/prod && $(TERRAFORM) apply

tf-destroy-dev: check-terraform ## Destroy dev environment
	@echo "$(RED)⚠️  Destroying dev environment$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1
	cd terraform/environments/dev && $(TERRAFORM) destroy

## Deployment Commands

deploy: deploy-dev ## Alias for deploy-dev

deploy-dev: check-aws ## Deploy to dev environment (default: ENV=dev)
	@echo "$(BLUE)Deploying to $(ENV)...$(NC)"
	$(MAKE) tf-apply-dev
	$(MAKE) deploy-lambdas ENV=$(ENV)
	@echo "$(GREEN)✓ Deployed to $(ENV)$(NC)"

deploy-lambdas: check-aws ## Deploy Lambda functions (use: ENV=dev or ENV=prod)
	@echo "$(BLUE)Packaging and deploying Lambda functions to $(ENV)...$(NC)"
	./scripts/deploy-lambdas.sh $(ENV)
	@echo "$(GREEN)✓ Lambdas deployed$(NC)"

deploy-web: check-aws ## Deploy Next.js frontend (use: ENV=dev or ENV=prod)
	@echo "$(BLUE)Building and deploying web app to $(ENV)...$(NC)"
	cd web && npm run build
	aws s3 sync web/out/ s3://$(PROJECT_NAME)-web-$(ENV) --delete
	@echo "$(GREEN)✓ Web app deployed$(NC)"

## Local Development Commands

local-start: ## Start local development environment
	@echo "$(BLUE)Starting LocalStack...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓ LocalStack started$(NC)"

local-stop: ## Stop local development environment
	@echo "$(BLUE)Stopping LocalStack...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ LocalStack stopped$(NC)"

run-lambda: ## Run Lambda function locally (use: FUNCTION=intent-classifier)
ifndef FUNCTION
	@echo "$(RED)Error: FUNCTION is required. Usage: make run-lambda FUNCTION=intent-classifier$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Running Lambda function: $(FUNCTION)$(NC)"
	@test -d lambda/functions/$(FUNCTION) || { echo "$(RED)Error: Function '$(FUNCTION)' not found$(NC)"; exit 1; }
	cd lambda/functions/$(FUNCTION) && sam local invoke -e test-event.json

logs: check-aws ## View Lambda logs (use: FUNCTION=intent-classifier)
ifndef FUNCTION
	@echo "$(RED)Error: FUNCTION is required. Usage: make logs FUNCTION=intent-classifier$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Fetching logs for: $(FUNCTION)$(NC)"
	aws logs tail /aws/lambda/$(PROJECT_NAME)-$(FUNCTION)-$(ENV) --follow

## Utility Commands

seed-kb: check-uv check-aws ## Seed knowledge base with sample data
	@echo "$(BLUE)Seeding knowledge base...$(NC)"
	uv run $(PYTHON) scripts/seed-knowledge-base.py --environment $(ENV)
	@echo "$(GREEN)✓ Knowledge base seeded$(NC)"

create-user: check-uv check-aws ## Create test user in Cognito
	@echo "$(BLUE)Creating test user...$(NC)"
	uv run $(PYTHON) scripts/create-test-user.py
	@echo "$(GREEN)✓ Test user created$(NC)"

clean: ## Clean build artifacts
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf lambda/functions/*/package lambda/functions/*/function.zip
	rm -rf web/.next web/out
	@echo "$(GREEN)✓ Cleaned$(NC)"

docs: check-uv ## Generate documentation
	@echo "$(BLUE)Generating documentation...$(NC)"
	cd docs && uv run mkdocs build
	@echo "$(GREEN)✓ Documentation generated$(NC)"

## Information Commands

version: ## Show project version
	@echo "$(BLUE)Project: $(PROJECT_NAME)$(NC)"
	@echo "$(BLUE)Version: $(shell cat VERSION 2>/dev/null || echo 'VERSION file not found')$(NC)"

status: check-aws ## Show infrastructure status
	@echo "$(BLUE)Checking infrastructure status...$(NC)"
	@echo "$(GREEN)API Gateway:$(NC)"
	@aws apigateway get-rest-apis --query 'items[?name==`$(PROJECT_NAME)-dev`].[id,name]' --output table 2>/dev/null || echo "Not deployed"
	@echo "$(GREEN)Lambda Functions:$(NC)"
	@aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `$(PROJECT_NAME)`)].[FunctionName,Runtime,LastModified]' --output table 2>/dev/null || echo "Not deployed"
	@echo "$(GREEN)DynamoDB Tables:$(NC)"
	@aws dynamodb list-tables --query 'TableNames[?starts_with(@, `$(PROJECT_NAME)`)]' --output table 2>/dev/null || echo "Not deployed"

cost: check-uv ## Estimate infrastructure cost
	@echo "$(BLUE)Estimating infrastructure cost...$(NC)"
	uv run $(PYTHON) scripts/cost-calculator.py
	@echo "$(GREEN)✓ Cost estimate complete$(NC)"
