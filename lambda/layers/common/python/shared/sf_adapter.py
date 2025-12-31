"""Step Functions adapter for Lambda handlers.

This module provides utilities for Lambda functions to work seamlessly with
both AWS Step Functions and API Gateway invocations. It handles:

1. Input Detection: Auto-detect invocation source (Step Functions vs API Gateway)
2. Input Parsing: Extract payload regardless of invocation type
3. Output Formatting: Return appropriate format for the invocation source
4. Error Handling: Convert exceptions to Step Functions-compatible errors

Usage Example:
    ```python
    from shared.sf_adapter import StepFunctionsAdapter, InvocationSource

    adapter = StepFunctionsAdapter(event)

    # Parse input
    payload = adapter.get_payload()

    # Process request...
    result = process(payload)

    # Return appropriate response
    return adapter.success_response(result)
    ```

For Step Functions, responses are returned as direct dicts.
For API Gateway, responses are wrapped in statusCode/body/headers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

from shared.exceptions import (
    LambdaError,
    NonRetryableError,
    RetryableError,
    ThrottlingError,
    ValidationError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T", bound=BaseModel)


class InvocationSource(str, Enum):
    """Source of Lambda invocation."""

    STEP_FUNCTIONS = "step_functions"
    API_GATEWAY = "api_gateway"
    DIRECT = "direct"  # Direct Lambda invoke (SDK/CLI)


@dataclass
class StepFunctionsContext:
    """Context information from Step Functions execution.

    When invoked by Step Functions, the state machine can pass
    execution context that may be useful for logging and tracing.
    """

    execution_id: str | None = None
    state_name: str | None = None
    state_entered_time: str | None = None
    workflow_name: str | None = None

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> StepFunctionsContext:
        """Extract Step Functions context from event if present."""
        sf_context = event.get("_sf_context", {})
        return cls(
            execution_id=sf_context.get("execution_id"),
            state_name=sf_context.get("state_name"),
            state_entered_time=sf_context.get("state_entered_time"),
            workflow_name=sf_context.get("workflow_name"),
        )


class StepFunctionsAdapter:
    """Adapter for handling Lambda invocations from multiple sources.

    This adapter provides a unified interface for Lambda handlers to work
    with Step Functions, API Gateway, and direct invocations without
    changing their core logic.

    Attributes:
        event: The raw Lambda event.
        source: Detected invocation source.
        sf_context: Step Functions context (if applicable).
    """

    def __init__(self, event: dict[str, Any]) -> None:
        """Initialize adapter with Lambda event.

        Args:
            event: The Lambda event dictionary.
        """
        self.event = event
        self.source = self._detect_source()
        self.sf_context = StepFunctionsContext.from_event(event)

    def _detect_source(self) -> InvocationSource:
        """Detect the invocation source from event structure.

        Detection logic:
        - API Gateway: Has 'httpMethod' or 'requestContext.http'
        - Step Functions: Has '_sf_context' or specific SF markers
        - Direct: Default fallback
        """
        # API Gateway REST API
        if "httpMethod" in self.event:
            return InvocationSource.API_GATEWAY

        # API Gateway HTTP API (v2)
        if "requestContext" in self.event:
            request_context = self.event.get("requestContext", {})
            if "http" in request_context or "httpMethod" in request_context:
                return InvocationSource.API_GATEWAY

        # Step Functions context marker (added by our ASL definition)
        if "_sf_context" in self.event:
            return InvocationSource.STEP_FUNCTIONS

        # Step Functions typically passes clean payloads
        # If we have a simple dict without API Gateway markers, treat as SF/direct
        if "body" not in self.event and "statusCode" not in self.event:
            return InvocationSource.STEP_FUNCTIONS

        return InvocationSource.DIRECT

    @property
    def is_step_functions(self) -> bool:
        """Check if invoked by Step Functions."""
        return self.source == InvocationSource.STEP_FUNCTIONS

    @property
    def is_api_gateway(self) -> bool:
        """Check if invoked by API Gateway."""
        return self.source == InvocationSource.API_GATEWAY

    def get_payload(self) -> dict[str, Any]:
        """Extract the request payload from the event.

        For API Gateway: Parses the 'body' field (JSON string or dict).
        For Step Functions/Direct: Returns the event directly (minus context).

        Returns:
            The request payload as a dictionary.

        Raises:
            ValidationError: If the payload cannot be parsed.
        """
        if self.is_api_gateway:
            return self._parse_api_gateway_body()
        else:
            # For Step Functions, return event without internal context
            payload = {k: v for k, v in self.event.items() if not k.startswith("_")}
            return payload

    def _parse_api_gateway_body(self) -> dict[str, Any]:
        """Parse body from API Gateway event."""
        body = self.event.get("body")

        if body is None:
            return {}

        if isinstance(body, dict):
            return body

        if isinstance(body, str):
            try:
                result: dict[str, Any] = json.loads(body)
                return result
            except json.JSONDecodeError as e:
                raise ValidationError(
                    message=f"Invalid JSON in request body: {e}",
                    field="body",
                ) from e

        return {}

    def parse_model(self, model_class: type[T]) -> T:
        """Parse payload into a Pydantic model.

        Args:
            model_class: The Pydantic model class to parse into.

        Returns:
            Validated model instance.

        Raises:
            ValidationError: If validation fails.
        """
        from pydantic import ValidationError as PydanticValidationError

        payload = self.get_payload()

        try:
            return model_class.model_validate(payload)
        except PydanticValidationError as e:
            raise ValidationError(
                message=f"Request validation failed: {e.error_count()} error(s)",
                details={"errors": e.errors()},
            ) from e

    def success_response(
        self,
        data: dict[str, Any] | BaseModel,
        status_code: int = 200,
    ) -> dict[str, Any]:
        """Format a success response for the invocation source.

        Args:
            data: Response data (dict or Pydantic model).
            status_code: HTTP status code (only used for API Gateway).

        Returns:
            Formatted response dictionary.
        """
        # Convert Pydantic model to dict
        response_data = data.model_dump(mode="json") if isinstance(data, BaseModel) else data

        if self.is_api_gateway:
            return self._api_gateway_response(status_code, response_data)
        else:
            # Step Functions expects direct payload
            return response_data

    def error_response(
        self,
        error: Exception,
        status_code: int | None = None,
    ) -> dict[str, Any]:
        """Format an error response for the invocation source.

        For Step Functions: Re-raises the exception so Step Functions
        can catch it in the ASL Catch block.

        For API Gateway: Returns a formatted error response with
        appropriate status code.

        Args:
            error: The exception that occurred.
            status_code: Override status code (API Gateway only).

        Returns:
            For API Gateway: Error response dictionary.

        Raises:
            For Step Functions: Re-raises the original exception.
        """
        if self.is_step_functions:
            # Step Functions catches exceptions directly
            # Re-raise so the ASL Catch block can handle it
            raise error

        # API Gateway gets formatted error response
        if isinstance(error, LambdaError):
            code = status_code or self._error_to_status_code(error)
            return self._api_gateway_response(code, error.to_dict())
        else:
            # Generic exception
            code = status_code or 500
            return self._api_gateway_response(
                code,
                {
                    "error_type": "InternalError",
                    "message": str(error),
                    "retryable": False,
                },
            )

    def _error_to_status_code(self, error: LambdaError) -> int:
        """Map exception type to HTTP status code."""
        if isinstance(error, ValidationError):
            return 400
        elif isinstance(error, ThrottlingError):
            return 429
        elif isinstance(error, RetryableError):
            return 503
        elif isinstance(error, NonRetryableError):
            return 500
        else:
            return 500

    def _api_gateway_response(
        self,
        status_code: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Build API Gateway response format."""
        return {
            "statusCode": status_code,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST,OPTIONS",
            },
            "body": json.dumps(body, default=str),
        }


# =============================================================================
# Decorator for Handler Functions
# =============================================================================


def step_functions_handler(
    parse_model: type[BaseModel] | None = None,
    fail_open: bool = False,
    default_response: dict[str, Any] | None = None,
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Decorator to add Step Functions compatibility to Lambda handlers.

    This decorator wraps a handler function to:
    1. Auto-detect invocation source
    2. Parse input into a Pydantic model (optional)
    3. Format output appropriately
    4. Handle errors with proper Step Functions semantics

    Args:
        parse_model: Optional Pydantic model class to parse input into.
        fail_open: If True, return default_response on error instead of raising.
        default_response: Default response when fail_open=True.

    Usage:
        ```python
        @step_functions_handler(parse_model=MyRequest)
        def handler(event, context, request: MyRequest, adapter: StepFunctionsAdapter):
            result = process(request)
            return adapter.success_response(result)
        ```
    """
    from functools import wraps

    def decorator(
        func: Callable[..., dict[str, Any]],
    ) -> Callable[..., dict[str, Any]]:
        @wraps(func)
        def wrapper(event: dict[str, Any], context: Any) -> dict[str, Any]:
            adapter = StepFunctionsAdapter(event)

            try:
                if parse_model:
                    request = adapter.parse_model(parse_model)
                    return func(event, context, request=request, adapter=adapter)
                else:
                    return func(event, context, adapter=adapter)

            except Exception as e:
                if fail_open and default_response is not None:
                    # Fail open - return default response
                    if adapter.is_step_functions:
                        return default_response
                    else:
                        return adapter.success_response(default_response)

                # Propagate error appropriately
                return adapter.error_response(e)

        return wrapper

    return decorator


# =============================================================================
# Utility Functions
# =============================================================================


def convert_to_retryable(
    error: Exception,
    message: str | None = None,
) -> RetryableError:
    """Convert any exception to a RetryableError.

    Useful for wrapping external service exceptions that should trigger
    Step Functions retry logic.

    Args:
        error: The original exception.
        message: Optional override message.

    Returns:
        RetryableError wrapping the original exception.
    """
    return RetryableError(
        message=message or str(error),
        details={"original_error": type(error).__name__},
    )


def convert_to_non_retryable(
    error: Exception,
    message: str | None = None,
) -> NonRetryableError:
    """Convert any exception to a NonRetryableError.

    Useful for wrapping exceptions that should not trigger retries.

    Args:
        error: The original exception.
        message: Optional override message.

    Returns:
        NonRetryableError wrapping the original exception.
    """
    return NonRetryableError(
        message=message or str(error),
        details={"original_error": type(error).__name__},
    )


def is_retryable_boto_error(error: Exception) -> bool:
    """Check if a boto3/botocore error is retryable.

    Args:
        error: The exception to check.

    Returns:
        True if the error is transient and should be retried.
    """
    from botocore.exceptions import ClientError

    if not isinstance(error, ClientError):
        return False

    error_code = error.response.get("Error", {}).get("Code", "")
    retryable_codes = {
        "ThrottlingException",
        "TooManyRequestsException",
        "ProvisionedThroughputExceededException",
        "ServiceUnavailable",
        "InternalServerError",
        "RequestLimitExceeded",
        "BandwidthLimitExceeded",
    }

    return error_code in retryable_codes
