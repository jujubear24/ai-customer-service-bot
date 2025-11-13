#!/bin/bash

# Exit on error, undefined variables, and pipe failures
set -euo pipefail

# Colors for output
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m' # No Color

# Project configuration
readonly PROJECT_ROOT="${PWD}"
readonly LAMBDA_DIR="lambda"
readonly LAYERS_DIR="${LAMBDA_DIR}/layers"
readonly FUNCTIONS_DIR="${LAMBDA_DIR}/functions"
readonly SHARED_LAYER_PATH="${LAYERS_DIR}/common/python/shared"

# Lambda functions to create
readonly FUNCTIONS=(
  "intent-classifier"
  "context-builder"
  "bedrock-handler"
  "response-validator"
  "escalation-router"
  "metrics-publisher"
)

# Logging functions
log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Check if uv is installed
check_uv() {
  if ! command -v uv &> /dev/null; then
    log_error "uv is not installed. Please install it first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi
  log_success "uv detected: $(uv --version)"
}

# Create directory with logging
create_dir() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
    log_warning "Directory already exists: $dir"
  else
    mkdir -p "$dir"
    log_info "Created directory: $dir"
  fi
}

# Create file with optional content
create_file() {
  local file="$1"
  local content="${2:-}"

  if [[ -f "$file" ]]; then
    log_warning "File already exists (skipping): $file"
  else
    if [[ -n "$content" ]]; then
      echo "$content" > "$file"
    else
      touch "$file"
    fi
    log_info "Created file: $file"
  fi
}

# Create or update shared layer structure
create_shared_layer() {
  log_info "Setting up Lambda shared layer structure..."

  # Ensure directories exist
  create_dir "$SHARED_LAYER_PATH"

  # Create Python package files
  create_file "${SHARED_LAYER_PATH}/__init__.py" '"""Shared utilities for Lambda functions."""

__version__ = "0.1.0"
'

  # Updated logger.py using AWS Lambda Powertools
  create_file "${SHARED_LAYER_PATH}/logger.py" '"""Logging configuration using AWS Lambda Powertools."""

from typing import Optional
from aws_lambda_powertools import Logger, Tracer, Metrics

# Initialize Powertools resources
# Service name will be automatically captured from POWERTOOLS_SERVICE_NAME env var
logger = Logger(utc=True)
tracer = Tracer()
metrics = Metrics()


def setup_logger(
    name: Optional[str] = None,
    level: str = "INFO",
    json_format: bool = False
) -> Logger:
    """
    Return the configured logger instance.
    Maintained for compatibility with existing handlers.

    Args:
        name: Logger name (ignored, uses Powertools logger)
        level: Log level (controlled via POWERTOOLS_LOG_LEVEL env var)
        json_format: Format flag (Powertools always uses JSON)

    Returns:
        Configured Logger instance
    """
    return logger


def get_logger() -> Logger:
    """Return the configured logger instance."""
    return logger


def get_tracer() -> Tracer:
    """Return the configured tracer instance."""
    return tracer


def get_metrics() -> Metrics:
    """Return the configured metrics instance."""
    return metrics
'

  # New tracing.py
  create_file "${SHARED_LAYER_PATH}/tracing.py" '"""X-Ray tracing configuration."""

from aws_lambda_powertools import Tracer

tracer = Tracer()
'

  # New metrics.py
  create_file "${SHARED_LAYER_PATH}/metrics.py" '"""CloudWatch embedded metrics configuration."""

from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics()

__all__ = ["metrics", "MetricUnit"]
'

  # Updated types.py using Pydantic
  create_file "${SHARED_LAYER_PATH}/types.py" '"""Common type definitions using Pydantic."""

from typing import Dict, Any, Optional, List, Literal, TypedDict
from datetime import datetime
from pydantic import BaseModel, Field


class LambdaResponse(TypedDict):
    """Standard Lambda response format."""
    statusCode: int
    body: str
    headers: Optional[Dict[str, str]]


class ConversationContext(BaseModel):
    """Context maintained across conversation turns."""
    conversation_id: str
    tenant_id: str
    user_id: str
    session_id: str
    message_history: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class IntentClassification(BaseModel):
    """Result of intent classification."""
    intent: Literal["greeting", "question", "complaint", "request", "escalation"]
    confidence: float = Field(ge=0.0, le=1.0)
    entities: Dict[str, str] = Field(default_factory=dict)
    requires_context: bool = False


class BedrockRequest(BaseModel):
    """Standardized Bedrock request wrapper."""
    prompt: str
    conversation_context: Optional[ConversationContext] = None
    max_tokens: int = 1000
    temperature: float = 0.7
    system_prompts: List[str] = Field(default_factory=list)


class EscalationTicket(BaseModel):
    """Escalation ticket structure."""
    conversation_id: str
    escalation_score: float = Field(ge=0.0, le=1.0)
    reason: str
    context: Dict[str, Any]
    customer_tier: str = "standard"
    sentiment: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    priority: str = "medium"
'

  create_file "${SHARED_LAYER_PATH}/config.py" '"""Configuration management."""

import os
from typing import Optional, Dict, Any
from functools import lru_cache


class Config:
    """Application configuration from environment variables."""

    def __init__(self) -> None:
        """Initialize configuration from environment."""
        self.environment = os.getenv("ENVIRONMENT", "dev")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.json_logging = os.getenv("JSON_LOGGING", "true").lower() == "true"

        # Powertools configuration
        self.service_name = os.getenv("POWERTOOLS_SERVICE_NAME", "customer-service-bot")

        # Bedrock configuration
        self.bedrock_model_id = os.getenv(
            "BEDROCK_MODEL_ID",
            "anthropic.claude-3-5-sonnet-20241022-v2:0"
        )
        self.bedrock_max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", "1000"))
        self.bedrock_temperature = float(os.getenv("BEDROCK_TEMPERATURE", "0.7"))

        # DynamoDB configuration
        self.dynamodb_table = os.getenv("DYNAMODB_TABLE", "")

        # SQS configuration
        self.escalation_queue_url = os.getenv("ESCALATION_QUEUE_URL", "")

        # CloudWatch metrics
        self.metrics_namespace = os.getenv("METRICS_NAMESPACE", "CustomerServiceBot")

        # Redis configuration
        self.redis_endpoint = os.getenv("REDIS_ENDPOINT", "")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_auth_token = os.getenv("REDIS_AUTH_TOKEN", "")

    @classmethod
    @lru_cache(maxsize=1)
    def from_env(cls) -> "Config":
        """
        Create configuration from environment variables.

        Returns:
            Cached configuration instance
        """
        return cls()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Configuration as dictionary (excluding sensitive values)
        """
        return {
            "environment": self.environment,
            "log_level": self.log_level,
            "region": self.region,
            "json_logging": self.json_logging,
            "service_name": self.service_name,
        }
'

  create_file "${SHARED_LAYER_PATH}/exceptions.py" '"""Custom exception classes."""


class LambdaError(Exception):
    """Base exception for Lambda functions."""
    pass


class ValidationError(LambdaError):
    """Raised when input validation fails."""
    pass


class ConfigurationError(LambdaError):
    """Raised when configuration is invalid."""
    pass


class ExternalServiceError(LambdaError):
    """Raised when external service call fails."""
    pass


class BedrockError(ExternalServiceError):
    """Raised when Bedrock API call fails."""
    pass


class DynamoDBError(ExternalServiceError):
    """Raised when DynamoDB operation fails."""
    pass


class CacheError(ExternalServiceError):
    """Raised when cache operation fails."""
    pass
'

  create_file "${SHARED_LAYER_PATH}/utils.py" '"""Utility functions."""

import json
from typing import Any, Dict, Optional
from datetime import datetime


def parse_json_body(body: Optional[str]) -> Dict[str, Any]:
    """
    Parse JSON body from API Gateway event.

    Args:
        body: JSON string from event body

    Returns:
        Parsed dictionary

    Raises:
        ValueError: If body is not valid JSON
    """
    if not body:
        return {}

    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in request body: {e}")


def format_response(
    status_code: int,
    body: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Format Lambda response for API Gateway.

    Args:
        status_code: HTTP status code
        body: Response body as dictionary
        headers: Optional HTTP headers

    Returns:
        Formatted response dictionary
    """
    default_headers = {
        "Content-Type": "application/json",
        "X-Timestamp": datetime.utcnow().isoformat(),
    }

    if headers:
        default_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body),
    }


def get_correlation_id(event: Dict[str, Any]) -> str:
    """
    Extract or generate correlation ID from event.

    Args:
        event: Lambda event

    Returns:
        Correlation ID string
    """
    # Try API Gateway request ID
    if "requestContext" in event:
        return event["requestContext"].get("requestId", "")

    # Try headers
    headers = event.get("headers", {})
    return headers.get("x-correlation-id", headers.get("x-request-id", ""))
'

  # Create cache_client.py for Redis integration
  create_file "${SHARED_LAYER_PATH}/cache_client.py" '"""Redis cache client for session caching and rate limiting."""

import json
import os
from typing import Any, Optional

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from aws_lambda_powertools import Logger

logger = Logger()


class RedisCache:
    """Redis cache client with connection pooling."""

    _instance: Optional["RedisCache"] = None
    _redis_client: Any = None

    def __new__(cls) -> "RedisCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not REDIS_AVAILABLE:
            logger.warning("Redis library not available, caching disabled")
            return

        if self._redis_client is None:
            self._connect()

    def _connect(self) -> None:
        """Establish Redis connection."""
        if not REDIS_AVAILABLE:
            return

        try:
            self._redis_client = redis.Redis(
                host=os.environ.get("REDIS_ENDPOINT", ""),
                port=int(os.environ.get("REDIS_PORT", "6379")),
                password=os.environ.get("REDIS_AUTH_TOKEN", ""),
                ssl=True,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            # Test connection
            self._redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.exception("Failed to connect to Redis")
            self._redis_client = None

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if not self._redis_client:
            return None

        try:
            value = self._redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis GET error: {str(e)}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self._redis_client:
            return False

        try:
            serialized = json.dumps(value, default=str)
            self._redis_client.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Redis SET error: {str(e)}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        if not self._redis_client:
            return False

        try:
            self._redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis DELETE error: {str(e)}")
            return False

    def increment(
        self, key: str, amount: int = 1, ttl: Optional[int] = None
    ) -> Optional[int]:
        """
        Increment counter (for rate limiting).

        Args:
            key: Counter key
            amount: Amount to increment
            ttl: Time to live for new counters

        Returns:
            New counter value or None on error
        """
        if not self._redis_client:
            return None

        try:
            value = self._redis_client.incr(key, amount)
            if ttl and value == amount:  # First increment, set TTL
                self._redis_client.expire(key, ttl)
            return value
        except Exception as e:
            logger.error(f"Redis INCR error: {str(e)}")
            return None


class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, cache: RedisCache) -> None:
        self.cache = cache

    def is_allowed(
        self, identifier: str, max_requests: int = 100, window_seconds: int = 60
    ) -> bool:
        """
        Check if request is allowed under rate limit.

        Args:
            identifier: User ID, IP, or API key
            max_requests: Maximum requests in window
            window_seconds: Time window in seconds

        Returns:
            True if allowed, False if rate limited
        """
        key = f"ratelimit:{identifier}"
        current_count = self.cache.increment(key, ttl=window_seconds)

        if current_count is None:
            # Cache unavailable, allow request (fail open)
            logger.warning("Rate limiter cache unavailable, allowing request")
            return True

        allowed = current_count <= max_requests

        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "identifier": identifier,
                    "count": current_count,
                    "limit": max_requests,
                },
            )

        return allowed
'

  # Create layer requirements file
  create_file "${LAYERS_DIR}/common/requirements.txt" '# AWS SDK
boto3>=1.35.0

# AWS Lambda Powertools
aws-lambda-powertools[tracer]>=2.31.0

# Data validation
pydantic>=2.5.0

# Redis (optional)
redis>=5.0.0

# Utilities
python-dateutil>=2.8.0
'

  log_success "Shared layer structure set up!"
}

# Create Lambda function scaffolding
create_lambda_function() {
  local func_name="$1"
  local func_dir="${FUNCTIONS_DIR}/${func_name}"

  log_info "Creating function: ${func_name}"

  # Create directories
  create_dir "${func_dir}/src"
  create_dir "${func_dir}/tests"

  # Create source files
  create_file "${func_dir}/src/__init__.py" "\"\"\"${func_name} Lambda function.\"\"\""

  create_file "${func_dir}/src/handler.py" "\"\"\"Main handler for ${func_name} Lambda function.\"\"\"

import json
from typing import Any, Dict

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from shared.config import Config
from shared.exceptions import LambdaError, ValidationError
from shared.metrics import metrics, MetricUnit
from shared.types import LambdaResponse
from shared.utils import format_response, get_correlation_id

# Initialize
config = Config.from_env()
logger = Logger(service=\"${func_name}\")
tracer = Tracer(service=\"${func_name}\")


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> LambdaResponse:
    \"\"\"
    Main Lambda handler function.

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        Response dictionary with statusCode, headers, and body
    \"\"\"
    correlation_id = get_correlation_id(event)

    logger.info(
        \"Processing event for ${func_name}\",
        extra={\"correlation_id\": correlation_id}
    )

    # Add custom metric
    metrics.add_metric(name=\"FunctionInvocation\", unit=MetricUnit.Count, value=1)

    try:
        # Validate input
        validate_event(event)

        # Process event
        result = process_event(event, context)

        logger.info(
            \"Successfully processed event\",
            extra={\"correlation_id\": correlation_id}
        )

        metrics.add_metric(name=\"SuccessfulProcessing\", unit=MetricUnit.Count, value=1)

        return format_response(
            200,
            {
                \"message\": \"Success\",
                \"data\": result,
                \"correlation_id\": correlation_id,
            }
        )

    except ValidationError as e:
        logger.warning(f\"Validation error: {str(e)}\", exc_info=True)
        metrics.add_metric(name=\"ValidationError\", unit=MetricUnit.Count, value=1)

        return format_response(
            400,
            {
                \"error\": \"ValidationError\",
                \"message\": str(e),
                \"correlation_id\": correlation_id,
            }
        )

    except LambdaError as e:
        logger.error(f\"Lambda error: {str(e)}\", exc_info=True)
        metrics.add_metric(name=\"LambdaError\", unit=MetricUnit.Count, value=1)

        return format_response(
            500,
            {
                \"error\": type(e).__name__,
                \"message\": str(e),
                \"correlation_id\": correlation_id,
            }
        )

    except Exception as e:
        logger.error(f\"Unexpected error: {str(e)}\", exc_info=True)
        metrics.add_metric(name=\"UnexpectedError\", unit=MetricUnit.Count, value=1)

        return format_response(
            500,
            {
                \"error\": \"InternalServerError\",
                \"message\": \"An unexpected error occurred\",
                \"correlation_id\": correlation_id,
            }
        )


@tracer.capture_method
def validate_event(event: Dict[str, Any]) -> None:
    \"\"\"
    Validate incoming event.

    Args:
        event: Lambda event object

    Raises:
        ValidationError: If event is invalid
    \"\"\"
    # TODO: Implement validation logic specific to ${func_name}
    if not event:
        raise ValidationError(\"Event cannot be empty\")


@tracer.capture_method
def process_event(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    \"\"\"
    Process the incoming event.

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        Processed result dictionary
    \"\"\"
    # TODO: Implement your business logic here
    logger.debug(f\"Processing event: {json.dumps(event)}\")

    return {
        \"function\": \"${func_name}\",
        \"request_id\": context.aws_request_id if hasattr(context, 'aws_request_id') else None,
        \"remaining_time_ms\": context.get_remaining_time_in_millis() if hasattr(context, 'get_remaining_time_in_millis') else None,
    }
"

  # Create test file
  create_file "${func_dir}/tests/__init__.py"
  create_file "${func_dir}/tests/test_handler.py" "\"\"\"Unit tests for ${func_name} handler.\"\"\"

import json
from unittest.mock import Mock, patch

import pytest

from shared.exceptions import ValidationError
from src.handler import lambda_handler, process_event, validate_event


@pytest.fixture
def lambda_context() -> Mock:
    \"\"\"Create mock Lambda context.\"\"\"
    context = Mock()
    context.function_name = \"${func_name}\"
    context.function_version = \"\$LATEST\"
    context.invoked_function_arn = \"arn:aws:lambda:us-east-1:123456789012:function:${func_name}\"
    context.memory_limit_in_mb = 128
    context.aws_request_id = \"test-request-id\"
    context.log_group_name = \"/aws/lambda/${func_name}\"
    context.log_stream_name = \"2024/01/01/[\$LATEST]test\"
    context.get_remaining_time_in_millis = Mock(return_value=30000)
    return context


@pytest.fixture
def sample_event() -> dict:
    \"\"\"Create sample Lambda event.\"\"\"
    return {
        \"body\": json.dumps({\"test\": \"data\"}),
        \"headers\": {
            \"Content-Type\": \"application/json\",
            \"x-correlation-id\": \"test-correlation-id\"
        },
        \"requestContext\": {
            \"requestId\": \"test-request-id\"
        }
    }


class TestLambdaHandler:
    \"\"\"Test cases for lambda_handler function.\"\"\"

    def test_lambda_handler_success(self, sample_event: dict, lambda_context: Mock) -> None:
        \"\"\"Test successful lambda handler invocation.\"\"\"
        response = lambda_handler(sample_event, lambda_context)

        assert response[\"statusCode\"] == 200
        assert \"body\" in response

        body = json.loads(response[\"body\"])
        assert body[\"message\"] == \"Success\"
        assert \"correlation_id\" in body

    def test_lambda_handler_validation_error(self, lambda_context: Mock) -> None:
        \"\"\"Test lambda handler with validation error.\"\"\"
        event = {}

        response = lambda_handler(event, lambda_context)

        assert response[\"statusCode\"] == 400
        body = json.loads(response[\"body\"])
        assert body[\"error\"] == \"ValidationError\"

    def test_lambda_handler_unexpected_error(
        self, sample_event: dict, lambda_context: Mock
    ) -> None:
        \"\"\"Test lambda handler with unexpected error.\"\"\"
        with patch(\"src.handler.process_event\", side_effect=Exception(\"Unexpected\")):
            response = lambda_handler(sample_event, lambda_context)

            assert response[\"statusCode\"] == 500
            body = json.loads(response[\"body\"])
            assert body[\"error\"] == \"InternalServerError\"


class TestValidateEvent:
    \"\"\"Test cases for validate_event function.\"\"\"

    def test_validate_event_success(self, sample_event: dict) -> None:
        \"\"\"Test successful event validation.\"\"\"
        # Should not raise any exception
        validate_event(sample_event)

    def test_validate_event_empty(self) -> None:
        \"\"\"Test validation with empty event.\"\"\"
        with pytest.raises(ValidationError):
            validate_event({})


class TestProcessEvent:
    \"\"\"Test cases for process_event function.\"\"\"

    def test_process_event_success(
        self, sample_event: dict, lambda_context: Mock
    ) -> None:
        \"\"\"Test successful event processing.\"\"\"
        result = process_event(sample_event, lambda_context)

        assert \"function\" in result
        assert result[\"function\"] == \"${func_name}\"
        assert \"request_id\" in result
"

  # Create pyproject.toml for the function
  create_file "${func_dir}/pyproject.toml" "[project]
name = \"${func_name}\"
version = \"0.1.0\"
description = \"Lambda function for ${func_name}\"
requires-python = \">=3.12\"
dependencies = [
    \"boto3>=1.35.0\",
    \"aws-lambda-powertools[tracer]>=2.31.0\",
    \"pydantic>=2.5.0\",
]

[project.optional-dependencies]
dev = [
    \"pytest>=8.0.0\",
    \"pytest-cov>=4.1.0\",
    \"pytest-mock>=3.12.0\",
    \"moto[all]>=5.0.0\",
    \"mypy>=1.8.0\",
    \"ruff>=0.1.0\",
]

[tool.pytest.ini_options]
testpaths = [\"tests\"]
python_files = [\"test_*.py\"]
python_classes = [\"Test*\"]
python_functions = [\"test_*\"]
addopts = \"--cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=80\"

[tool.coverage.run]
source = [\"src\"]
omit = [\"*/tests/*\", \"*/__pycache__/*\"]

[tool.coverage.report]
exclude_lines = [
    \"pragma: no cover\",
    \"def __repr__\",
    \"raise AssertionError\",
    \"raise NotImplementedError\",
    \"if __name__ == .__main__.:\",
    \"if TYPE_CHECKING:\",
    \"@abstractmethod\",
]

[tool.mypy]
python_version = \"3.11\"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
strict_equality = true

[tool.ruff]
line-length = 100
target-version = \"py311\"

[tool.ruff.lint]
select = [
    \"E\",  # pycodestyle errors
    \"W\",  # pycodestyle warnings
    \"F\",  # pyflakes
    \"I\",  # isort
    \"B\",  # flake8-bugbear
    \"C4\", # flake8-comprehensions
    \"UP\", # pyupgrade
]
ignore = [
    \"E501\",  # line too long (handled by formatter)
]

[tool.ruff.lint.isort]
known-first-party = [\"src\", \"shared\"]
"

  # Create function-specific README
  create_file "${func_dir}/README.md" "# ${func_name}

## Description
Lambda function for ${func_name}.

## Environment Variables

### Required
- \`ENVIRONMENT\`: Deployment environment (dev, staging, prod)
- \`AWS_REGION\`: AWS region
- \`POWERTOOLS_SERVICE_NAME\`: Service name for AWS Lambda Powertools

### Optional
- \`POWERTOOLS_LOG_LEVEL\`: Logging level (INFO, DEBUG, WARNING, ERROR)
- \`POWERTOOLS_METRICS_NAMESPACE\`: CloudWatch metrics namespace
- \`POWERTOOLS_TRACER_CAPTURE_RESPONSE\`: Enable response capture in traces (true/false)
- \`POWERTOOLS_TRACER_CAPTURE_ERROR\": Enable error capture in traces (true/false)

## Local Development

### Setup
\`\`\`bash
# From the function directory
uv sync

# Or from project root
cd lambda/functions/${func_name}
uv sync
\`\`\`

### Testing
\`\`\`bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/test_handler.py -v

# Run with type checking
uv run mypy src/

# Run linting
uv run ruff check src/
\`\`\`

### Code Quality
\`\`\`bash
# Format code
uv run ruff format src/ tests/

# Check types
uv run mypy src/

# Run all checks
uv run pytest && uv run mypy src/ && uv run ruff check src/
\`\`\`

## Architecture Decision Records (ADRs)
See \`docs/adr/\` for architectural decisions related to this function.

## Deployment
This function is deployed via Terraform. See \`terraform/modules/\` for infrastructure configuration.

## Dependencies
- **Shared layer**: \`lambda/layers/common/python/shared\`
- **AWS Lambda Powertools**: Logging, tracing, and metrics
- **Pydantic**: Data validation and settings management

## Monitoring
- **CloudWatch Logs**: \`/aws/lambda/${func_name}\`
- **X-Ray Traces**: View in AWS X-Ray console
- **Metrics**: Custom metrics in CloudWatch under configured namespace

## Troubleshooting

### Common Issues
1. **Cold start latency**: Consider provisioned concurrency for production
2. **Timeout errors**: Increase timeout setting in Terraform
3. **Memory errors**: Increase memory allocation in Terraform

### Debug Mode
Enable debug logging:
\`\`\`bash
export POWERTOOLS_LOG_LEVEL=DEBUG
\`\`\`
"
}

# Create all Lambda functions
create_all_functions() {
  log_info "Creating Lambda function scaffolding..."
  echo ""

  for func in "${FUNCTIONS[@]}"; do
    create_lambda_function "$func"
    echo ""
  done

  log_success "All Lambda functions created!"
}

# Update root pyproject.toml with workspace configuration
update_pyproject() {
  log_info "Checking pyproject.toml for workspace configuration..."

  if [[ ! -f "pyproject.toml" ]]; then
    log_warning "pyproject.toml not found, skipping workspace update"
    return
  fi

  # Check if workspace is already configured
  if grep -q "tool.uv.workspace" pyproject.toml; then
    log_warning "Workspace already configured in pyproject.toml"
  else
    log_info "Add the following to your pyproject.toml to enable uv workspace:"
    echo ""
    echo "[tool.uv.workspace]"
    echo "members = ["
    for func in "${FUNCTIONS[@]}"; do
      echo "    \"lambda/functions/${func}\","
    done
    echo "]"
    echo ""
  fi
}

# Create test runner script
create_test_runner() {
  log_info "Creating test runner script..."

  create_file "scripts/test-lambdas.sh" '#!/bin/bash

set -e

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
NC="\033[0m" # No Color

echo -e "${BLUE}Running tests for all Lambda functions...${NC}"
echo ""

FAILED_FUNCTIONS=()
PASSED_FUNCTIONS=()
TOTAL_COVERAGE=0
FUNCTION_COUNT=0

for func_dir in lambda/functions/*/; do
  if [[ -f "${func_dir}pyproject.toml" ]]; then
    func_name=$(basename "${func_dir}")
    echo -e "${BLUE}Testing ${func_name}...${NC}"

    cd "$func_dir"

    # Run tests with coverage
    if uv run pytest --cov=src --cov-report=term --cov-report=json; then
      echo -e "${GREEN}✓ ${func_name} tests passed${NC}"
      PASSED_FUNCTIONS+=("$func_name")

      # Extract coverage percentage if available
      if [[ -f "coverage.json" ]]; then
        coverage=$(python3 -c "import json; data=json.load(open(\"coverage.json\")); print(data.get(\"totals\", {}).get(\"percent_covered\", 0))" 2>/dev/null || echo "0")
        echo -e "  Coverage: ${coverage}%"
        TOTAL_COVERAGE=$(echo "$TOTAL_COVERAGE + $coverage" | bc)
        FUNCTION_COUNT=$((FUNCTION_COUNT + 1))
      fi
    else
      echo -e "${RED}✗ ${func_name} tests failed${NC}"
      FAILED_FUNCTIONS+=("$func_name")
    fi

    cd - > /dev/null
    echo ""
  fi
done

echo "================================"
echo "Test Summary:"
echo "  Passed: ${#PASSED_FUNCTIONS[@]}"
echo "  Failed: ${#FAILED_FUNCTIONS[@]}"

if [[ $FUNCTION_COUNT -gt 0 ]]; then
  AVG_COVERAGE=$(echo "scale=2; $TOTAL_COVERAGE / $FUNCTION_COUNT" | bc)
  echo "  Average Coverage: ${AVG_COVERAGE}%"
fi

if [ ${#FAILED_FUNCTIONS[@]} -gt 0 ]; then
  echo -e "${RED}Failed functions:${NC}"
  for func in "${FAILED_FUNCTIONS[@]}"; do
    echo "  - $func"
  done
  exit 1
else
  echo -e "${GREEN}All tests passed!${NC}"
fi
'

  chmod +x "scripts/test-lambdas.sh"
  log_success "Test runner script created!"
}

# Create linting script
create_lint_script() {
  log_info "Creating linting script..."

  create_file "scripts/lint-lambdas.sh" '#!/bin/bash

set -e

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m"

echo -e "${BLUE}Running linting and type checking for all Lambda functions...${NC}"
echo ""

FAILED_FUNCTIONS=()
PASSED_FUNCTIONS=()

for func_dir in lambda/functions/*/; do
  if [[ -f "${func_dir}pyproject.toml" ]]; then
    func_name=$(basename "${func_dir}")
    echo -e "${BLUE}Checking ${func_name}...${NC}"

    cd "$func_dir"

    # Run ruff
    echo "  Running ruff..."
    if ! uv run ruff check src/ tests/; then
      echo -e "${RED}✗ Ruff failed for ${func_name}${NC}"
      FAILED_FUNCTIONS+=("$func_name:ruff")
    fi

    # Run mypy
    echo "  Running mypy..."
    if ! uv run mypy src/; then
      echo -e "${RED}✗ Mypy failed for ${func_name}${NC}"
      FAILED_FUNCTIONS+=("$func_name:mypy")
    fi

    if [[ ! " ${FAILED_FUNCTIONS[@]} " =~ " ${func_name}: " ]]; then
      echo -e "${GREEN}✓ ${func_name} passed all checks${NC}"
      PASSED_FUNCTIONS+=("$func_name")
    fi

    cd - > /dev/null
    echo ""
  fi
done

echo "================================"
echo "Linting Summary:"
echo "  Passed: ${#PASSED_FUNCTIONS[@]}"
echo "  Failed: ${#FAILED_FUNCTIONS[@]}"

if [ ${#FAILED_FUNCTIONS[@]} -gt 0 ]; then
  echo -e "${RED}Failed checks:${NC}"
  for func in "${FAILED_FUNCTIONS[@]}"; do
    echo "  - $func"
  done
  exit 1
else
  echo -e "${GREEN}All checks passed!${NC}"
fi
'

  chmod +x "scripts/lint-lambdas.sh"
  log_success "Linting script created!"
}

# Create ADR template
create_adr_template() {
  log_info "Checking for ADR template..."

  if [[ ! -f "docs/adr/template.md" ]]; then
    log_warning "ADR template not found at docs/adr/template.md"
    log_info "You may want to create one following the project structure"
  else
    log_success "ADR template already exists"
  fi
}

# Check if project README needs Lambda documentation
check_project_readme() {
  log_info "Checking project README..."

  if [[ ! -f "README.md" ]]; then
    log_warning "No project README.md found"
    log_info "Consider creating one with project overview and Lambda function documentation"
  else
    log_success "Project README.md exists"
    log_info "You may want to add links to individual Lambda function READMEs"
  fi
}

# Create Makefile for common commands
create_makefile() {
  log_info "Checking for Makefile..."

  if [[ -f "Makefile" ]]; then
    log_warning "Makefile already exists - skipping"
    log_info "You can manually add targets from the template if needed"
    return
  fi

  log_info "Creating Makefile for common commands..."

  create_file "Makefile" '.PHONY: help install test lint format clean

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E "^[a-zA-Z_-]+:.*?## .*$" $(MAKEFILE_LIST) | awk "BEGIN {FS = \":.*?## \"}; {printf \"  \\033[36m%-20s\\033[0m %s\\n\", $1, $2}"

install: ## Install all dependencies
	@echo "Installing dependencies for all Lambda functions..."
	@uv sync --all-packages

test: ## Run tests for all Lambda functions
	@./scripts/test-lambdas.sh

lint: ## Run linting and type checking
	@./scripts/lint-lambdas.sh

format: ## Format code with ruff
	@echo "Formatting all Lambda functions..."
	@for func_dir in lambda/functions/*/; do \
		if [ -f "${func_dir}pyproject.toml" ]; then \
			echo "Formatting $(basename $func_dir)..."; \
			cd $func_dir && uv run ruff format src/ tests/ && cd - > /dev/null; \
		fi \
	done

clean: ## Clean generated files
	@echo "Cleaning generated files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "coverage.json" -delete 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete!"

tf-init: ## Initialize Terraform
	@cd terraform/environments/dev && terraform init

tf-plan: ## Run Terraform plan
	@cd terraform/environments/dev && terraform plan

tf-apply: ## Apply Terraform changes
	@cd terraform/environments/dev && terraform apply

validate-terraform: ## Validate all Terraform configurations
	@echo "Validating Terraform configurations..."
	@for env_dir in terraform/environments/*/; do \
		echo "Validating $(basename $env_dir)..."; \
		cd $env_dir && terraform init -backend=false && terraform validate && cd - > /dev/null; \
	done

pre-commit: lint test ## Run pre-commit checks
	@echo "Pre-commit checks passed!"
'

  log_success "Makefile created!"
}

# Create pre-commit configuration
create_pre_commit_config() {
  log_info "Checking pre-commit configuration..."

  if [[ -f ".pre-commit-config.yaml" ]]; then
    log_success "Pre-commit config already exists - skipping"
    log_info "Your existing pre-commit hooks will be preserved"
    return
  fi

  log_info "Creating pre-commit configuration..."

  create_file ".pre-commit-config.yaml" 'repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-json
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        args: [--ignore-missing-imports]

  - repo: https://github.com/antonbabenko/pre-commit-terraform
    rev: v1.88.0
    hooks:
      - id: terraform_fmt
      - id: terraform_validate
      - id: terraform_docs
'

  log_success "Pre-commit configuration created!"
  log_info "To install pre-commit hooks, run: pre-commit install"
}

# Create GitHub Actions workflow template
create_github_workflow() {
  log_info "Checking for GitHub Actions workflows..."

  create_dir ".github/workflows"

  if [[ -f ".github/workflows/lambda-test.yml" ]]; then
    log_warning "GitHub Actions workflow already exists - skipping"
    return
  fi

  log_info "Creating GitHub Actions workflow template..."

  create_file ".github/workflows/lambda-test.yml" 'name: Lambda Tests

on:
  pull_request:
    paths:
      - "lambda/**"
      - ".github/workflows/lambda-test.yml"
  push:
    branches:
      - main
      - develop

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v2
        with:
          version: "latest"

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          uv sync --all-packages

      - name: Run tests
        run: |
          ./scripts/test-lambdas.sh

      - name: Run linting
        run: |
          ./scripts/lint-lambdas.sh

      - name: Upload coverage reports
        uses: codecov/codecov-action@v3
        with:
          files: ./lambda/functions/*/coverage.xml
          flags: unittests
          name: lambda-coverage
'

  log_success "GitHub Actions workflow created!"
}

# Main execution
main() {
  log_info "Starting Lambda project scaffolding..."
  log_info "Using uv for package management"
  echo ""

  # Check prerequisites
  check_uv
  echo ""

  # Create structures
  create_shared_layer
  echo ""

  create_all_functions
  echo ""

  create_test_runner
  echo ""

  create_lint_script
  echo ""

  create_makefile
  echo ""

  create_pre_commit_config
  echo ""

  create_github_workflow
  echo ""

  create_adr_template
  echo ""

  check_project_readme
  echo ""

  update_pyproject
  echo ""

  log_success "✓ Lambda project scaffolding complete!"
  echo ""
  log_info "Next steps:"
  echo "  1. Add workspace configuration to pyproject.toml (see output above)"
  echo "  2. Install dependencies: make install (or uv sync --all-packages)"
  if [[ ! -f ".pre-commit-config.yaml" ]]; then
    echo "  3. Install pre-commit hooks: pre-commit install"
  else
    echo "  3. Pre-commit hooks already configured"
  fi
  echo "  4. Run tests: make test (or ./scripts/test-lambdas.sh)"
  echo "  5. Run linting: make lint (or ./scripts/lint-lambdas.sh)"
  echo "  6. Review and customize handler implementations"
  echo "  7. Update terraform modules to deploy functions"
  echo ""
  log_info "Available commands:"
  if [[ -f "Makefile" ]]; then
    echo "  make help          - Show all available make targets"
    echo "  make test          - Run all tests"
    echo "  make lint          - Run linting and type checking"
    echo "  make format        - Format all code"
    echo "  make clean         - Clean generated files"
    echo "  make pre-commit    - Run pre-commit checks"
  else
    echo "  ./scripts/test-lambdas.sh  - Run all tests"
    echo "  ./scripts/lint-lambdas.sh  - Run linting and type checking"
  fi
  echo ""
  log_warning "Note: Existing configurations preserved:"
  [[ -f ".pre-commit-config.yaml" ]] && echo "  - Pre-commit config"
  [[ -f "Makefile" ]] && echo "  - Makefile"
  [[ -f "README.md" ]] && echo "  - Project README.md"
  echo ""

  # Check for tool conflicts
  if [[ -f ".pre-commit-config.yaml" ]] && grep -q "black\|isort" .pre-commit-config.yaml; then
    log_info "💡 Tool Configuration Note:"
    echo "  Your pre-commit config uses Black + isort for formatting."
    echo "  The generated Lambda functions use Ruff (which replaces both)."
    echo ""
    echo "  Options:"
    echo "  1. Keep your existing tools (Black + isort) - they'll work fine"
    echo "  2. Migrate to Ruff for consistency (faster, single tool)"
    echo ""
    echo "  To migrate to Ruff, update your .pre-commit-config.yaml:"
    echo "  - Remove 'psf/black' and 'PyCQA/isort' repos"
    echo "  - Add 'astral-sh/ruff-pre-commit' repo (see generated template)"
  fi
}

# Run main function
main "$@"
