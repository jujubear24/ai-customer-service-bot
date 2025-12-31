"""Custom exception classes for Lambda functions.

This module provides a hierarchy of exceptions designed to work with both
direct Lambda invocation and AWS Step Functions orchestration.

Step Functions Error Handling:
    Step Functions catches exceptions by class name. Use RetryableError for
    transient failures (throttling, timeouts) and NonRetryableError for
    permanent failures (validation, bad input). The ASL definition uses
    these in Catch blocks to route to appropriate recovery states.

Exception Hierarchy:
    LambdaError (base)
    ├── ValidationError - Input validation failures
    ├── ConfigurationError - Missing/invalid configuration
    ├── RetryableError - Transient failures (Step Functions will retry)
    │   ├── ThrottlingError - Rate limiting / throttling
    │   └── ServiceUnavailableError - Temporary service outage
    └── NonRetryableError - Permanent failures (Step Functions won't retry)
        ├── ExternalServiceError - External service failures
        │   ├── BedrockError - Bedrock API errors
        │   ├── DynamoDBError - DynamoDB operation errors
        │   └── CacheError - Cache operation errors
        └── BusinessLogicError - Business rule violations
"""

from __future__ import annotations

from typing import Any


class LambdaError(Exception):
    """Base exception for Lambda functions.

    Attributes:
        message: Human-readable error description.
        error_code: Machine-readable error code for programmatic handling.
        details: Additional context for debugging.
        retryable: Whether the operation can be retried.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


class ValidationError(LambdaError):
    """Raised when input validation fails.

    This is a non-retryable error - the client must fix the input.
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if field:
            error_details["field"] = field
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=error_details,
            retryable=False,
        )


class ConfigurationError(LambdaError):
    """Raised when configuration is invalid or missing.

    This is a non-retryable error - requires deployment fix.
    """

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if config_key:
            error_details["config_key"] = config_key
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=error_details,
            retryable=False,
        )


# =============================================================================
# Step Functions Error Types
# =============================================================================


class RetryableError(LambdaError):
    """Base class for transient/retryable errors.

    Step Functions will catch this error type and can retry the operation
    with exponential backoff. Use for throttling, timeouts, and temporary
    service unavailability.

    ASL Catch Example:
        "Catch": [{
            "ErrorEquals": ["RetryableError"],
            "ResultPath": "$.error",
            "Next": "RetryState"
        }]
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "RETRYABLE_ERROR",
            details=details or {},
            retryable=True,
        )
        self.retry_after_seconds = retry_after_seconds
        if retry_after_seconds:
            self.details["retry_after_seconds"] = retry_after_seconds


class NonRetryableError(LambdaError):
    """Base class for permanent/non-retryable errors.

    Step Functions will catch this error type and route to a fallback
    or error handling state. Retrying will not help.

    ASL Catch Example:
        "Catch": [{
            "ErrorEquals": ["NonRetryableError"],
            "ResultPath": "$.error",
            "Next": "HandleFailure"
        }]
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "NON_RETRYABLE_ERROR",
            details=details or {},
            retryable=False,
        )


class ThrottlingError(RetryableError):
    """Raised when a service is throttling requests.

    This is a retryable error - back off and try again.
    """

    def __init__(
        self,
        message: str = "Request throttled",
        service: str | None = None,
        retry_after_seconds: int = 5,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if service:
            error_details["service"] = service
        super().__init__(
            message=message,
            error_code="THROTTLING_ERROR",
            details=error_details,
            retry_after_seconds=retry_after_seconds,
        )


class ServiceUnavailableError(RetryableError):
    """Raised when a service is temporarily unavailable.

    This is a retryable error - the service may recover.
    """

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        service: str | None = None,
        retry_after_seconds: int = 10,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if service:
            error_details["service"] = service
        super().__init__(
            message=message,
            error_code="SERVICE_UNAVAILABLE",
            details=error_details,
            retry_after_seconds=retry_after_seconds,
        )


# =============================================================================
# External Service Errors
# =============================================================================


class ExternalServiceError(NonRetryableError):
    """Raised when external service call fails permanently.

    For transient external service failures, use RetryableError instead.
    """

    def __init__(
        self,
        message: str,
        service: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if service:
            error_details["service"] = service
        super().__init__(
            message=message,
            error_code="EXTERNAL_SERVICE_ERROR",
            details=error_details,
        )


# Alias for backward compatibility
DependencyError = ExternalServiceError


class BedrockError(ExternalServiceError):
    """Raised when Bedrock API call fails.

    Note: For throttling errors, raise ThrottlingError instead.
    """

    def __init__(
        self,
        message: str,
        model_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if model_id:
            error_details["model_id"] = model_id
        error_details["service"] = "bedrock"
        super().__init__(
            message=message,
            service="bedrock",
            details=error_details,
        )
        self.error_code = "BEDROCK_ERROR"


class DynamoDBError(ExternalServiceError):
    """Raised when DynamoDB operation fails."""

    def __init__(
        self,
        message: str,
        table_name: str | None = None,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if table_name:
            error_details["table_name"] = table_name
        if operation:
            error_details["operation"] = operation
        error_details["service"] = "dynamodb"
        super().__init__(
            message=message,
            service="dynamodb",
            details=error_details,
        )
        self.error_code = "DYNAMODB_ERROR"


class CacheError(ExternalServiceError):
    """Raised when cache operation fails."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if operation:
            error_details["operation"] = operation
        error_details["service"] = "cache"
        super().__init__(
            message=message,
            service="cache",
            details=error_details,
        )
        self.error_code = "CACHE_ERROR"


class BusinessLogicError(NonRetryableError):
    """Raised when business logic validation fails.

    Use for domain-specific errors that aren't input validation
    but represent invalid business operations.
    """

    def __init__(
        self,
        message: str,
        rule: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if rule:
            error_details["rule"] = rule
        super().__init__(
            message=message,
            error_code="BUSINESS_LOGIC_ERROR",
            details=error_details,
        )
