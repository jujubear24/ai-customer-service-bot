.PHONY: help install test lint format clean deploy

# Variables
PYTHON := python3.12
TERRAFORM := terraform
AWS_REGION := us-east-1
PROJECT_NAME := ai-customer-service-bot

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Available commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

## Setup & Dependency Commands
install: ## Install all dependencies with UV
	@echo "$(BLUE)Installing dependencies with UV...$(NC)"
	uv sync --all-extras
	@echo "$(BLUE)Installing Node dependencies...$(NC)"
	cd web && npm install
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	uv run pre-commit install
	@echo "$(GREEN)✓ Installation complete$(NC)"

freeze: ## Generate requirements.txt from UV lock file
	@echo "$(BLUE)Generating requirements files...$(NC)"
	uv pip compile pyproject.toml -o requirements.txt
	uv pip compile pyproject.toml --extra dev -o requirements-dev.txt
	@echo "$(GREEN)✓ Requirements files generated$(NC)"

add-dep: ## Add a new dependency (use: make add-dep PKG=package-name)
	@echo "$(BLUE)Adding dependency: $(PKG)$(NC)"
	uv add $(PKG)
	$(MAKE) freeze
	@echo "$(GREEN)✓ Dependency added$(NC)"

add-dev-dep: ## Add a dev dependency (use: make add-dev-dep PKG=package-name)
	@echo "$(BLUE)Adding dev dependency: $(PKG)$(NC)"
	uv add --dev $(PKG)
	$(MAKE) freeze
	@echo "$(GREEN)✓ Dev dependency added$(NC)"

update-deps: ## Update all dependencies
	@echo "$(BLUE)Updating dependencies...$(NC)"
	uv sync --upgrade
	$(MAKE) freeze
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

setup-aws: ## Configure AWS CLI
	@echo "$(BLUE)Configuring AWS CLI...$(NC)"
	aws configure
	@echo "$(GREEN)✓ AWS configured$(NC)"

init-terraform: ## Initialize Terraform backend
	@echo "$(BLUE)Initializing Terraform...$(NC)"
	cd terraform/environments/dev && $(TERRAFORM) init
	@echo "$(GREEN)✓ Terraform initialized$(NC)"

## Development Commands

format: ## Format code (Python, Terraform, TypeScript)
	@echo "$(BLUE)Formatting Python code...$(NC)"
	uv run black lambda/ --line-length=100
	uv run isort lambda/ --profile=black --line-length=100
	@echo "$(BLUE)Formatting Terraform code...$(NC)"
	$(TERRAFORM) fmt -recursive terraform/
	@echo "$(BLUE)Formatting TypeScript code...$(NC)"
	cd web && npm run format
	@echo "$(GREEN)✓ Code formatted$(NC)"

lint: ## Run linters
	@echo "$(BLUE)Linting Python code...$(NC)"
	uv run flake8 lambda/ --max-line-length=100 --extend-ignore=E203
	uv run pylint lambda/functions lambda/layers --rcfile=.pylintrc || true
	@echo "$(BLUE)Linting TypeScript code...$(NC)"
	cd web && npm run lint
	@echo "$(GREEN)✓ Linting complete$(NC)"

typecheck: ## Run type checkers
	@echo "$(BLUE)Type checking Python code...$(NC)"
	uv run mypy lambda/ --ignore-missing-imports --python-version=3.12
	@echo "$(BLUE)Type checking TypeScript code...$(NC)"
	cd web && npm run typecheck
	@echo "$(GREEN)✓ Type checking complete$(NC)"

security-scan: ## Run security scans
	@echo "$(BLUE)Running security scans...$(NC)"
	uv run bandit -r lambda/ -ll
	cd terraform && tfsec .
	@echo "$(GREEN)✓ Security scan complete$(NC)"

## Testing Commands

test-unit: ## Run unit tests
	@echo "$(BLUE)Running Python unit tests...$(NC)"
	cd lambda && uv run pytest tests/unit -v --cov=functions --cov-report=term-missing
	@echo "$(BLUE)Running TypeScript unit tests...$(NC)"
	cd web && npm run test
	@echo "$(GREEN)✓ Unit tests complete$(NC)"

test-integration: ## Run integration tests
	@echo "$(BLUE)Running integration tests...$(NC)"
	cd lambda && uv run pytest tests/integration -v
	@echo "$(GREEN)✓ Integration tests complete$(NC)"

test-e2e: ## Run end-to-end tests
	@echo "$(BLUE)Running E2E tests...$(NC)"
	cd web && npm run test:e2e
	@echo "$(GREEN)✓ E2E tests complete$(NC)"

test-all: test-unit test-integration ## Run all tests
	@echo "$(GREEN)✓ All tests complete$(NC)"

coverage: ## Generate coverage report
	@echo "$(BLUE)Generating coverage report...$(NC)"
	cd lambda && uv run pytest tests/ --cov=functions --cov-report=html
	@echo "$(GREEN)✓ Coverage report generated at lambda/htmlcov/index.html$(NC)"

## Infrastructure Commands

tf-plan-dev: ## Terraform plan for dev
	@echo "$(BLUE)Running Terraform plan for dev...$(NC)"
	cd terraform/environments/dev && $(TERRAFORM) plan

tf-apply-dev: ## Terraform apply for dev
	@echo "$(BLUE)Applying Terraform for dev...$(NC)"
	cd terraform/environments/dev && $(TERRAFORM) apply

tf-plan-prod: ## Terraform plan for prod
	@echo "$(BLUE)Running Terraform plan for prod...$(NC)"
	cd terraform/environments/prod && $(TERRAFORM) plan

tf-apply-prod: ## Terraform apply for prod (with approval)
	@echo "$(RED)⚠️  Deploying to PRODUCTION$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1
	cd terraform/environments/prod && $(TERRAFORM) apply

tf-destroy-dev: ## Destroy dev environment
	@echo "$(RED)⚠️  Destroying dev environment$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1
	cd terraform/environments/dev && $(TERRAFORM) destroy

## Deployment Commands

deploy-dev: ## Deploy to dev environment
	@echo "$(BLUE)Deploying to dev...$(NC)"
	$(MAKE) tf-apply-dev
	$(MAKE) deploy-lambdas ENV=dev
	@echo "$(GREEN)✓ Deployed to dev$(NC)"

deploy-lambdas: ## Deploy Lambda functions
	@echo "$(BLUE)Packaging and deploying Lambda functions...$(NC)"
	./scripts/deploy-lambdas.sh $(ENV)
	@echo "$(GREEN)✓ Lambdas deployed$(NC)"

deploy-web: ## Deploy Next.js frontend
	@echo "$(BLUE)Building and deploying web app...$(NC)"
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

run-lambda: ## Run Lambda function locally (use FUNCTION=name)
	@echo "$(BLUE)Running Lambda function: $(FUNCTION)$(NC)"
	cd lambda/functions/$(FUNCTION) && sam local invoke -e test-event.json

logs: ## View Lambda logs (use FUNCTION=name)
	@echo "$(BLUE)Fetching logs for: $(FUNCTION)$(NC)"
	aws logs tail /aws/lambda/$(PROJECT_NAME)-$(FUNCTION)-dev --follow

## Utility Commands

seed-kb: ## Seed knowledge base with sample data
	@echo "$(BLUE)Seeding knowledge base...$(NC)"
	uv run $(PYTHON) scripts/seed-knowledge-base.py --environment dev
	@echo "$(GREEN)✓ Knowledge base seeded$(NC)"

create-user: ## Create test user in Cognito
	@echo "$(BLUE)Creating test user...$(NC)"
	uv run $(PYTHON) scripts/create-test-user.py
	@echo "$(GREEN)✓ Test user created$(NC)"

performance-test: ## Run performance tests
	@echo "$(BLUE)Running performance tests...$(NC)"
	uv run locust -f tests/load/locustfile.py --headless --users 50 --spawn-rate 5 --run-time 2m
	@echo "$(GREEN)✓ Performance test complete$(NC)"

clean: ## Clean build artifacts
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf lambda/functions/*/package lambda/functions/*/function.zip
	rm -rf web/.next web/out
	@echo "$(GREEN)✓ Cleaned$(NC)"

docs: ## Generate documentation
	@echo "$(BLUE)Generating documentation...$(NC)"
	cd docs && uv run mkdocs build
	@echo "$(GREEN)✓ Documentation generated$(NC)"

check: format lint typecheck test-unit ## Run all checks (pre-commit)
	@echo "$(GREEN)✓ All checks passed$(NC)"

## Information Commands

version: ## Show project version
	@echo "$(BLUE)Project: $(PROJECT_NAME)$(NC)"
	@echo "$(BLUE)Version: $(shell cat VERSION)$(NC)"

status: ## Show infrastructure status
	@echo "$(BLUE)Checking infrastructure status...$(NC)"
	@echo "$(GREEN)API Gateway:$(NC)"
	@aws apigateway get-rest-apis --query 'items[?name==`$(PROJECT_NAME)-dev`].[id,name]' --output table || echo "Not deployed"
	@echo "$(GREEN)Lambda Functions:$(NC)"
	@aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `$(PROJECT_NAME)`)].[FunctionName,Runtime,LastModified]' --output table || echo "Not deployed"
	@echo "$(GREEN)DynamoDB Tables:$(NC)"
	@aws dynamodb list-tables --query 'TableNames[?starts_with(@, `$(PROJECT_NAME)`)]' --output table || echo "Not deployed"

cost: ## Estimate infrastructure cost
	@echo "$(BLUE)Estimating infrastructure cost...$(NC)"
	uv run $(PYTHON) scripts/cost-calculator.py
	@echo "$(GREEN)✓ Cost estimate complete$(NC)"
