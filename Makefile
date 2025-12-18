.PHONY: help install add-dep add-dev-dep update-deps setup-aws \
        format lint typecheck security-scan validate \
        test test-unit test-integration test-e2e test-all test-function coverage \
        build build-all build-layer build-function build-list build-clean \
        tf-init tf-plan tf-apply tf-destroy tf-output tf-state tf-fmt tf-validate tf-refresh \
        deploy deploy-dev deploy-prod \
        logs logs-api logs-orchestrator logs-rag logs-bedrock logs-intent logs-context \
        sync-kb test-chat test-api \
        local-start local-stop clean docs \
        whoami endpoints status cost check pre-commit ci

# ==============================================================================
# Variables
# ==============================================================================
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
CYAN := \033[0;36m
NC := \033[0m # No Color

# ==============================================================================
# Help
# ==============================================================================
help: ## Show this help message
	@echo ""
	@echo "$(GREEN)AI Customer Service Bot - Development Commands$(NC)"
	@echo ""
	@echo "$(BLUE)━━━ Setup & Dependencies ━━━$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(install|add-dep|update-deps|setup-aws)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)━━━ Build ━━━$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '^build' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)━━━ Code Quality ━━━$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(format|lint|typecheck|validate|security-scan|check|pre-commit|ci)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)━━━ Testing ━━━$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '^test' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)━━━ Terraform ━━━$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '^tf-' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)━━━ Deployment ━━━$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '^deploy' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)━━━ Logs & Monitoring ━━━$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '^logs' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)━━━ Utilities ━━━$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(sync-kb|test-chat|test-api|local-|clean|docs|whoami|endpoints|status|cost)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Variables:$(NC)"
	@echo "  ENV=dev|staging|prod   Environment (default: dev)"
	@echo "  FUNCTION=name          Lambda function name"
	@echo "  PKG=package            Package name for add-dep"
	@echo ""

# ==============================================================================
# Dependency Checks (internal)
# ==============================================================================
.PHONY: _check-uv _check-terraform _check-aws _check-docker

_check-uv:
	@command -v uv >/dev/null 2>&1 || { echo "$(RED)Error: uv is not installed. Install from https://docs.astral.sh/uv/$(NC)"; exit 1; }

_check-terraform:
	@command -v terraform >/dev/null 2>&1 || { echo "$(RED)Error: terraform is not installed$(NC)"; exit 1; }

_check-aws:
	@aws sts get-caller-identity >/dev/null 2>&1 || { echo "$(RED)Error: AWS CLI not configured. Run 'make setup-aws'$(NC)"; exit 1; }

_check-docker:
	@docker info >/dev/null 2>&1 || { echo "$(RED)Error: Docker is not running$(NC)"; exit 1; }

# ==============================================================================
# Setup & Dependencies
# ==============================================================================
install: _check-uv ## Install all dependencies
	@echo "$(BLUE)Installing Python dependencies...$(NC)"
	@for dir in lambda/functions/*/; do \
		if [ -f "$$dir/pyproject.toml" ]; then \
			echo "  Installing $$(basename $$dir)..."; \
			cd "$$dir" && uv sync --quiet && cd - > /dev/null; \
		fi \
	done
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	@uv run pre-commit install 2>/dev/null || true
	@echo "$(GREEN)✓ Installation complete$(NC)"

add-dep: _check-uv ## Add a dependency (PKG=package-name FUNCTION=function-name)
ifndef PKG
	@echo "$(RED)Error: PKG required. Usage: make add-dep PKG=boto3 FUNCTION=chat-orchestrator$(NC)"
	@exit 1
endif
ifndef FUNCTION
	@echo "$(RED)Error: FUNCTION required. Usage: make add-dep PKG=boto3 FUNCTION=chat-orchestrator$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Adding $(PKG) to $(FUNCTION)...$(NC)"
	@cd lambda/functions/$(FUNCTION) && uv add $(PKG)
	@echo "$(GREEN)✓ Dependency added$(NC)"

add-dev-dep: _check-uv ## Add a dev dependency (PKG=package-name FUNCTION=function-name)
ifndef PKG
	@echo "$(RED)Error: PKG required. Usage: make add-dev-dep PKG=pytest FUNCTION=chat-orchestrator$(NC)"
	@exit 1
endif
ifndef FUNCTION
	@echo "$(RED)Error: FUNCTION required$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Adding dev dependency $(PKG) to $(FUNCTION)...$(NC)"
	@cd lambda/functions/$(FUNCTION) && uv add --dev $(PKG)
	@echo "$(GREEN)✓ Dev dependency added$(NC)"

update-deps: _check-uv ## Update all dependencies
	@echo "$(BLUE)Updating dependencies...$(NC)"
	@for dir in lambda/functions/*/; do \
		if [ -f "$$dir/pyproject.toml" ]; then \
			echo "  Updating $$(basename $$dir)..."; \
			cd "$$dir" && uv sync --upgrade --quiet && cd - > /dev/null; \
		fi \
	done
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

setup-aws: ## Configure AWS CLI interactively
	@echo "$(BLUE)Configuring AWS CLI...$(NC)"
	@aws configure
	@echo "$(GREEN)✓ AWS configured$(NC)"

# ==============================================================================
# Build Commands
# ==============================================================================
build: build-all ## Alias for build-all

build-all: _check-docker ## Build layer and all Lambda functions
	@echo "$(BLUE)Building all Lambda artifacts...$(NC)"
	@./scripts/build-lambdas.sh
	@echo "$(GREEN)✓ Build complete$(NC)"

build-layer: _check-docker ## Build only the shared Lambda layer
	@echo "$(BLUE)Building Lambda layer...$(NC)"
	@./scripts/build-lambdas.sh --layer-only
	@echo "$(GREEN)✓ Layer built$(NC)"

build-function: _check-docker ## Build specific function(s) (FUNCTION=name or FUNCTION="name1 name2")
ifndef FUNCTION
	@echo "$(RED)Error: FUNCTION required. Usage: make build-function FUNCTION=chat-orchestrator$(NC)"
	@echo "$(YELLOW)Tip: Use 'make build-list' to see available functions$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Building function(s): $(FUNCTION)...$(NC)"
	@for func in $(FUNCTION); do \
		./scripts/build-lambdas.sh -f $$func; \
	done
	@echo "$(GREEN)✓ Function(s) built$(NC)"

build-list: ## List all available Lambda functions
	@./scripts/build-lambdas.sh --list

build-clean: ## Clean all build artifacts
	@./scripts/build-lambdas.sh --clean

# ==============================================================================
# Code Quality
# ==============================================================================
format: _check-uv ## Format all code (Python + Terraform)
	@echo "$(BLUE)Formatting Python code...$(NC)"
	@uv run ruff format lambda/
	@uv run ruff check lambda/ --fix || true
	@echo "$(BLUE)Formatting Terraform code...$(NC)"
	@$(TERRAFORM) fmt -recursive terraform/
	@echo "$(GREEN)✓ Code formatted$(NC)"

lint: _check-uv ## Run linters (no fixes)
	@echo "$(BLUE)Linting Python code...$(NC)"
	@uv run ruff check lambda/
	@echo "$(BLUE)Validating Terraform...$(NC)"
	@cd terraform/environments/$(ENV) && $(TERRAFORM) validate
	@echo "$(GREEN)✓ Linting complete$(NC)"

typecheck: _check-uv ## Run type checking on all functions
	@echo "$(BLUE)Type checking Lambda functions...$(NC)"
	@./scripts/lint-lambdas.sh
	@echo "$(GREEN)✓ Type checking complete$(NC)"

validate: _check-uv ## Quick validation (format check + lint, no modifications)
	@echo "$(BLUE)Validating code...$(NC)"
	@uv run ruff format lambda/ --check
	@uv run ruff check lambda/
	@echo "$(GREEN)✓ Validation passed$(NC)"

security-scan: _check-uv ## Run security scans
	@echo "$(BLUE)Running security scans...$(NC)"
	@uv run bandit -r lambda/ -ll 2>/dev/null || echo "$(YELLOW)bandit not installed, skipping$(NC)"
	@cd terraform && tfsec . 2>/dev/null || echo "$(YELLOW)tfsec not installed, skipping$(NC)"
	@echo "$(GREEN)✓ Security scan complete$(NC)"

check: lint typecheck ## Run all checks (no formatting)
	@echo "$(GREEN)✓ All checks passed$(NC)"

pre-commit: format check ## Format + all checks (pre-commit workflow)
	@echo "$(GREEN)✓ Ready to commit$(NC)"

ci: validate typecheck test-unit ## Run CI pipeline checks
	@echo "$(GREEN)✓ CI checks passed$(NC)"

# ==============================================================================
# Testing
# ==============================================================================
test: test-unit ## Run unit tests (alias)

test-unit: _check-uv ## Run all unit tests
	@echo "$(BLUE)Running unit tests...$(NC)"
	@./scripts/test-lambdas.sh
	@echo "$(GREEN)✓ Unit tests complete$(NC)"

test-function: _check-uv ## Run tests for specific function (FUNCTION=name)
ifndef FUNCTION
	@echo "$(RED)Error: FUNCTION required. Usage: make test-function FUNCTION=chat-orchestrator$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Testing $(FUNCTION)...$(NC)"
	@cd lambda/functions/$(FUNCTION) && uv run pytest -v
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-cov: _check-uv ## Run tests with coverage for specific function (FUNCTION=name)
ifndef FUNCTION
	@echo "$(RED)Error: FUNCTION required. Usage: make test-cov FUNCTION=chat-orchestrator$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Testing $(FUNCTION) with coverage...$(NC)"
	@cd lambda/functions/$(FUNCTION) && uv run pytest -v --cov=src --cov-report=term-missing --cov-report=html
	@echo "$(GREEN)✓ Coverage report: lambda/functions/$(FUNCTION)/htmlcov/index.html$(NC)"

test-e2e: _check-uv _check-aws ## Run E2E tests
	@echo "$(BLUE)Running E2E tests...$(NC)"
	@uv run python scripts/test_chat_orchestrator.py
	@echo "$(GREEN)✓ E2E tests complete$(NC)"

test-all: test-unit test-e2e ## Run all tests
	@echo "$(GREEN)✓ All tests complete$(NC)"

test-chat: _check-aws ## Quick test of /chat endpoint
	@echo "$(BLUE)Testing /chat endpoint...$(NC)"
	@CHAT_URL=$$(cd terraform/environments/$(ENV) && terraform output -raw chat_endpoint 2>/dev/null) && \
	if [ -z "$$CHAT_URL" ]; then \
		echo "$(RED)Error: Could not get chat endpoint. Is infrastructure deployed?$(NC)"; \
		exit 1; \
	fi && \
	echo "Endpoint: $$CHAT_URL" && \
	curl -s -X POST "$$CHAT_URL" \
		-H "Content-Type: application/json" \
		-d '{"message": "How do I reset my password?", "tenant_id": "test"}' | jq .
	@echo ""
	@echo "$(GREEN)✓ Chat test complete$(NC)"

test-api: _check-aws ## Test /classify-intent endpoint
	@echo "$(BLUE)Testing /classify-intent endpoint...$(NC)"
	@API_URL=$$(cd terraform/environments/$(ENV) && terraform output -raw classify_intent_endpoint 2>/dev/null) && \
	if [ -z "$$API_URL" ]; then \
		echo "$(RED)Error: Could not get API endpoint. Is infrastructure deployed?$(NC)"; \
		exit 1; \
	fi && \
	echo "Endpoint: $$API_URL" && \
	curl -s -X POST "$$API_URL" \
		-H "Content-Type: application/json" \
		-d '{"message": "I need to speak to a manager"}' | jq .
	@echo ""
	@echo "$(GREEN)✓ API test complete$(NC)"

# ==============================================================================
# Terraform Commands
# ==============================================================================
tf-init: _check-terraform ## Initialize Terraform (ENV=dev|staging|prod)
	@echo "$(BLUE)Initializing Terraform for $(ENV)...$(NC)"
	@cd terraform/environments/$(ENV) && $(TERRAFORM) init
	@echo "$(GREEN)✓ Terraform initialized$(NC)"

tf-plan: _check-terraform _check-aws ## Plan Terraform changes (ENV=dev|staging|prod)
	@echo "$(BLUE)Planning Terraform for $(ENV)...$(NC)"
	@cd terraform/environments/$(ENV) && $(TERRAFORM) plan

tf-apply: _check-terraform _check-aws ## Apply Terraform changes (ENV=dev|staging|prod)
	@if [ "$(ENV)" = "prod" ]; then \
		echo "$(RED)⚠️  Deploying to PRODUCTION$(NC)"; \
		read -p "Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1; \
	fi
	@echo "$(BLUE)Applying Terraform for $(ENV)...$(NC)"
	@cd terraform/environments/$(ENV) && $(TERRAFORM) apply
	@echo "$(GREEN)✓ Terraform applied$(NC)"

tf-destroy: _check-terraform _check-aws ## Destroy infrastructure (ENV=dev|staging|prod)
	@echo "$(RED)⚠️  Destroying $(ENV) environment$(NC)"
	@read -p "Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1
	@cd terraform/environments/$(ENV) && $(TERRAFORM) destroy

tf-output: _check-terraform ## Show Terraform outputs (ENV=dev|staging|prod)
	@cd terraform/environments/$(ENV) && $(TERRAFORM) output

tf-state: _check-terraform ## List Terraform state resources (ENV=dev|staging|prod)
	@cd terraform/environments/$(ENV) && $(TERRAFORM) state list

tf-fmt: _check-terraform ## Format all Terraform files
	@echo "$(BLUE)Formatting Terraform files...$(NC)"
	@$(TERRAFORM) fmt -recursive terraform/
	@echo "$(GREEN)✓ Terraform formatted$(NC)"

tf-validate: _check-terraform ## Validate Terraform configuration (ENV=dev|staging|prod)
	@echo "$(BLUE)Validating Terraform for $(ENV)...$(NC)"
	@cd terraform/environments/$(ENV) && $(TERRAFORM) validate
	@echo "$(GREEN)✓ Terraform valid$(NC)"

tf-refresh: _check-terraform _check-aws ## Refresh Terraform state (ENV=dev|staging|prod)
	@echo "$(BLUE)Refreshing Terraform state for $(ENV)...$(NC)"
	@cd terraform/environments/$(ENV) && $(TERRAFORM) refresh

# ==============================================================================
# Deployment Commands
# ==============================================================================
deploy: deploy-dev ## Alias for deploy-dev

deploy-dev: build-all tf-apply ## Build and deploy to dev
	@echo "$(GREEN)✓ Deployed to dev$(NC)"

deploy-prod: ## Build and deploy to prod (with confirmation)
	@echo "$(RED)⚠️  Deploying to PRODUCTION$(NC)"
	@read -p "Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1
	@$(MAKE) build-all
	@$(MAKE) tf-apply ENV=prod
	@echo "$(GREEN)✓ Deployed to prod$(NC)"

# ==============================================================================
# Logs & Monitoring
# ==============================================================================
logs: _check-aws ## View Lambda logs (FUNCTION=name, default: chat-orchestrator)
	@FUNC=$${FUNCTION:-chat-orchestrator}; \
	echo "$(BLUE)Tailing logs for $$FUNC...$(NC)"; \
	aws logs tail /aws/lambda/$(PROJECT_NAME)-$$FUNC-$(ENV) --follow --format short

logs-orchestrator: _check-aws ## View chat-orchestrator logs
	@echo "$(BLUE)Tailing chat-orchestrator logs...$(NC)"
	@aws logs tail /aws/lambda/$(PROJECT_NAME)-chat-orchestrator-$(ENV) --follow --format short

logs-rag: _check-aws ## View rag-retriever logs
	@echo "$(BLUE)Tailing rag-retriever logs...$(NC)"
	@aws logs tail /aws/lambda/$(PROJECT_NAME)-rag-retriever-$(ENV) --follow --format short

logs-bedrock: _check-aws ## View bedrock-handler logs
	@echo "$(BLUE)Tailing bedrock-handler logs...$(NC)"
	@aws logs tail /aws/lambda/$(PROJECT_NAME)-bedrock-handler-$(ENV) --follow --format short

logs-intent: _check-aws ## View intent-classifier logs
	@echo "$(BLUE)Tailing intent-classifier logs...$(NC)"
	@aws logs tail /aws/lambda/$(PROJECT_NAME)-intent-classifier-$(ENV) --follow --format short

logs-context: _check-aws ## View context-builder logs
	@echo "$(BLUE)Tailing context-builder logs...$(NC)"
	@aws logs tail /aws/lambda/$(PROJECT_NAME)-context-builder-$(ENV) --follow --format short

logs-api: _check-aws ## View API Gateway logs
	@echo "$(BLUE)Tailing API Gateway logs...$(NC)"
	@LOG_GROUP=$$(aws logs describe-log-groups --log-group-name-prefix "API-Gateway" --query 'logGroups[0].logGroupName' --output text 2>/dev/null); \
	if [ "$$LOG_GROUP" = "None" ] || [ -z "$$LOG_GROUP" ]; then \
		echo "$(YELLOW)API Gateway logging not enabled or no logs found$(NC)"; \
	else \
		aws logs tail "$$LOG_GROUP" --follow --format short; \
	fi

logs-recent: _check-aws ## Show recent logs for a function (FUNCTION=name, last 30 min)
	@FUNC=$${FUNCTION:-chat-orchestrator}; \
	echo "$(BLUE)Recent logs for $$FUNC (last 30 min)...$(NC)"; \
	aws logs filter-log-events \
		--log-group-name /aws/lambda/$(PROJECT_NAME)-$$FUNC-$(ENV) \
		--start-time $$(( $$(date +%s) - 1800 ))000 \
		--query 'events[*].message' \
		--output text | head -100

logs-errors: _check-aws ## Show recent errors for a function (FUNCTION=name)
	@FUNC=$${FUNCTION:-chat-orchestrator}; \
	echo "$(BLUE)Recent errors for $$FUNC...$(NC)"; \
	aws logs filter-log-events \
		--log-group-name /aws/lambda/$(PROJECT_NAME)-$$FUNC-$(ENV) \
		--start-time $$(( $$(date +%s) - 3600 ))000 \
		--filter-pattern "ERROR" \
		--query 'events[*].message' \
		--output text

# ==============================================================================
# Knowledge Base & Utilities
# ==============================================================================
sync-kb: _check-aws ## Sync knowledge base documents to S3 and trigger ingestion
	@echo "$(BLUE)Syncing knowledge base...$(NC)"
	@./scripts/sync-knowledge-base.sh
	@echo "$(GREEN)✓ Knowledge base synced$(NC)"

local-start: _check-docker ## Start local development environment (LocalStack)
	@echo "$(BLUE)Starting LocalStack...$(NC)"
	@docker-compose up -d 2>/dev/null || echo "$(YELLOW)docker-compose.yml not found$(NC)"
	@echo "$(GREEN)✓ LocalStack started$(NC)"

local-stop: ## Stop local development environment
	@echo "$(BLUE)Stopping LocalStack...$(NC)"
	@docker-compose down 2>/dev/null || true
	@echo "$(GREEN)✓ LocalStack stopped$(NC)"

clean: ## Clean all build artifacts and caches
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	@./scripts/build-lambdas.sh --clean 2>/dev/null || true
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@rm -rf .build/ 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned$(NC)"

docs: ## Open architecture documentation
	@echo "$(BLUE)Documentation available at:$(NC)"
	@echo "  - docs/architecture/system-design.md"
	@echo "  - docs/architecture/data-flow.md"
	@echo "  - docs/architecture/security.md"
	@echo "  - docs/adr/ (Architecture Decision Records)"

# ==============================================================================
# Information Commands
# ==============================================================================
whoami: _check-aws ## Show current AWS identity
	@echo "$(BLUE)AWS Identity:$(NC)"
	@aws sts get-caller-identity --output table

endpoints: _check-aws ## Show API endpoints
	@echo "$(BLUE)API Endpoints ($(ENV)):$(NC)"
	@cd terraform/environments/$(ENV) && \
	echo "  Chat:    $$(terraform output -raw chat_endpoint 2>/dev/null || echo 'Not deployed')" && \
	echo "  Intent:  $$(terraform output -raw classify_intent_endpoint 2>/dev/null || echo 'Not deployed')" && \
	echo "  API Base: $$(terraform output -raw api_endpoint 2>/dev/null || echo 'Not deployed')"

status: _check-aws ## Show infrastructure status
	@echo "$(BLUE)Infrastructure Status ($(ENV)):$(NC)"
	@echo ""
	@echo "$(CYAN)Lambda Functions:$(NC)"
	@aws lambda list-functions \
		--query "Functions[?starts_with(FunctionName, '$(PROJECT_NAME)') && contains(FunctionName, '$(ENV)')].[FunctionName,Runtime,MemorySize,Timeout]" \
		--output table 2>/dev/null || echo "  No functions found"
	@echo ""
	@echo "$(CYAN)API Gateway:$(NC)"
	@aws apigateway get-rest-apis \
		--query "items[?contains(name, '$(PROJECT_NAME)')].[name,id,createdDate]" \
		--output table 2>/dev/null || echo "  No APIs found"
	@echo ""
	@echo "$(CYAN)DynamoDB Tables:$(NC)"
	@aws dynamodb list-tables \
		--query "TableNames[?contains(@, '$(PROJECT_NAME)')]" \
		--output table 2>/dev/null || echo "  No tables found"

cost: _check-aws ## Show estimated monthly cost (requires Cost Explorer access)
	@echo "$(BLUE)Cost Estimate (last 30 days):$(NC)"
	@aws ce get-cost-and-usage \
		--time-period Start=$$(date -d '30 days ago' +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d),End=$$(date +%Y-%m-%d) \
		--granularity MONTHLY \
		--metrics "BlendedCost" \
		--output table 2>/dev/null || echo "$(YELLOW)Cost Explorer access required$(NC)"

# ==============================================================================
# Quick Reference (shortcuts)
# ==============================================================================
# Common workflows:
#   make build-function FUNCTION=chat-orchestrator  # Build single function
#   make tf-apply                                    # Deploy to dev
#   make test-chat                                   # Test the /chat endpoint
#   make logs FUNCTION=chat-orchestrator             # Tail logs
#   make logs-errors FUNCTION=rag-retriever          # Check for errors
