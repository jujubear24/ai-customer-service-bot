"""Utility functions."""

import json
from datetime import datetime
from typing import Any


def parse_json_body(body: str | None) -> dict[str, Any]:
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
        result: dict[str, Any] = json.loads(body)
        return result
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in request body: {e}") from e


def format_response(
    status_code: int,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
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


def get_correlation_id(event: dict[str, Any]) -> str:
    """
    Extract or generate correlation ID from event.

    Args:
        event: Lambda event

    Returns:
        Correlation ID string
    """
    # Try API Gateway request ID
    if "requestContext" in event:
        request_id: str = event["requestContext"].get("requestId", "")
        return request_id

    # Try headers
    headers = event.get("headers", {})
    correlation_id: str = headers.get("x-correlation-id", headers.get("x-request-id", ""))
    return correlation_id
