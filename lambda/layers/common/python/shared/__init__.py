"""Shared utilities for Lambda functions.

This package provides common functionality used across all Lambda functions
in the AI Customer Service Bot, including:

- Exception hierarchy (exceptions.py)
- Step Functions adapter (sf_adapter.py)
- Configuration management (config.py)
- Logging utilities (logger.py)
- Common type definitions (types.py)
- CloudWatch metrics (metrics.py)
- X-Ray tracing (tracing.py)
- DynamoDB models and repositories (models/, repositories/)
"""

from shared.exceptions import (
    BedrockError,
    BusinessLogicError,
    CacheError,
    ConfigurationError,
    DependencyError,
    DynamoDBError,
    ExternalServiceError,
    LambdaError,
    NonRetryableError,
    RetryableError,
    ServiceUnavailableError,
    ThrottlingError,
    ValidationError,
)
from shared.sf_adapter import (
    InvocationSource,
    StepFunctionsAdapter,
    StepFunctionsContext,
    convert_to_non_retryable,
    convert_to_retryable,
    is_retryable_boto_error,
    step_functions_handler,
)

__all__ = [
    # Exceptions
    "LambdaError",
    "ValidationError",
    "ConfigurationError",
    "RetryableError",
    "NonRetryableError",
    "ThrottlingError",
    "ServiceUnavailableError",
    "ExternalServiceError",
    "DependencyError",
    "BedrockError",
    "DynamoDBError",
    "CacheError",
    "BusinessLogicError",
    # Step Functions Adapter
    "StepFunctionsAdapter",
    "StepFunctionsContext",
    "InvocationSource",
    "step_functions_handler",
    "convert_to_retryable",
    "convert_to_non_retryable",
    "is_retryable_boto_error",
]
