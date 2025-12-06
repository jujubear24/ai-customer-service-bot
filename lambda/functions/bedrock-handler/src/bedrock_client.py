"""Bedrock client for invoking Claude models.

This module wraps the Bedrock Runtime API with retry logic and
error handling. See ADR-009 for error handling strategy.
"""

import json
import logging
import os
import time
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from shared.exceptions import DependencyError

logger = logging.getLogger(__name__)


class BedrockClientError(Exception):
    """Base exception for Bedrock client errors."""

    pass


class BedrockThrottlingError(BedrockClientError):
    """Raised when Bedrock API is throttled."""

    pass


class BedrockModelError(BedrockClientError):
    """Raised when model returns an error."""

    pass


class BedrockClient:
    """Client for invoking Bedrock Claude models.

    Handles model invocation with retry logic for transient errors.
    """

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
    ) -> None:
        """Initialize Bedrock client.

        Args:
            model_id: Bedrock model ID. Defaults to BEDROCK_MODEL_ID env var.
            region: AWS region. Defaults to AWS_REGION env var.
        """
        self.model_id = model_id or os.environ.get(
            "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")

        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
        )

    def _is_retryable_error(self, error: ClientError) -> bool:
        """Check if an error is retryable.

        Args:
            error: Boto3 ClientError.

        Returns:
            True if the error is retryable.
        """
        error_code = error.response.get("Error", {}).get("Code", "")
        retryable_codes = [
            "ThrottlingException",
            "ServiceUnavailableException",
            "ModelTimeoutException",
            "InternalServerException",
        ]
        return error_code in retryable_codes

    @retry(
        retry=retry_if_exception_type(BedrockThrottlingError),
        wait=wait_exponential(multiplier=1, min=1, max=10) + wait_random(0, 1),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def invoke_model(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> dict[str, Any]:
        """Invoke the Bedrock model with retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: System prompt for the model.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
            top_p: Nucleus sampling parameter.

        Returns:
            Dict containing response text, token counts, and metadata.

        Raises:
            BedrockThrottlingError: When API is throttled (will retry).
            BedrockModelError: When model returns an error.
            DependencyError: When Bedrock service is unavailable.
        """
        start_time = time.time()

        # Build the request body for Claude Messages API
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "system": system_prompt,
            "messages": messages,
        }

        try:
            response = self._client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_body),
            )

            # Parse response
            response_body = json.loads(response["body"].read())
            latency_ms = int((time.time() - start_time) * 1000)

            # Extract response content
            content = response_body.get("content", [])
            response_text = ""
            if content and len(content) > 0:
                response_text = content[0].get("text", "")

            # Extract usage metrics
            usage = response_body.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            return {
                "response_text": response_text,
                "model_id": self.model_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": latency_ms,
                "stop_reason": response_body.get("stop_reason", "unknown"),
                "request_id": response.get("ResponseMetadata", {}).get("RequestId"),
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            logger.error(
                "Bedrock API error",
                extra={
                    "error_code": error_code,
                    "error_message": error_message,
                    "model_id": self.model_id,
                },
            )

            # Handle retryable errors
            if error_code in ("ThrottlingException", "ServiceUnavailableException"):
                raise BedrockThrottlingError(f"Bedrock throttled: {error_message}") from e

            # Handle model timeout
            if error_code == "ModelTimeoutException":
                raise BedrockThrottlingError(f"Model timeout: {error_message}") from e

            # Handle validation errors (don't retry)
            if error_code == "ValidationException":
                raise BedrockModelError(f"Invalid request: {error_message}") from e

            # Handle access denied (don't retry)
            if error_code == "AccessDeniedException":
                raise BedrockModelError(
                    f"Access denied: {error_message}. Check IAM permissions and model access."
                ) from e

            # Generic error
            raise DependencyError(f"Bedrock error: {error_message}") from e

        except Exception as e:
            logger.exception("Unexpected error invoking Bedrock")
            raise DependencyError(f"Unexpected Bedrock error: {str(e)}") from e
