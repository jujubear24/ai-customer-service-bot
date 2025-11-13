#!/bin/bash

set -e

echo "🔧 Fixing Lambda functions..."
echo ""

# Fix all Lambda function pyproject.toml files
for func_dir in lambda/functions/*/; do
  if [[ -f "${func_dir}pyproject.toml" ]]; then
    func_name=$(basename "${func_dir}")
    echo "Fixing ${func_name}..."

    # Add ruff to dev dependencies if not present
    if ! grep -q "ruff>=" "${func_dir}pyproject.toml"; then
      # For macOS
      if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' 's/"mypy>=1.8.0",/"mypy>=1.8.0",\n    "ruff>=0.3.0",/' "${func_dir}pyproject.toml"
      else
        # For Linux
        sed -i 's/"mypy>=1.8.0",/"mypy>=1.8.0",\n    "ruff>=0.3.0",/' "${func_dir}pyproject.toml"
      fi
      echo "  ✓ Added ruff dependency"
    else
      echo "  ✓ Ruff already present"
    fi
  fi
done

echo ""
echo "🔧 Fixing shared utils.py type annotations..."

# Fix utils.py
cat > lambda/layers/common/python/shared/utils.py << 'EOF'
"""Utility functions."""

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
        result: Dict[str, Any] = json.loads(body)
        return result
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
        request_id: str = event["requestContext"].get("requestId", "")
        return request_id

    # Try headers
    headers = event.get("headers", {})
    correlation_id: str = headers.get("x-correlation-id", headers.get("x-request-id", ""))
    return correlation_id
EOF

echo "  ✓ Fixed utils.py"

echo ""
echo "🔧 Reinstalling dependencies..."
uv sync --all-packages

echo ""
echo "✅ All fixes complete!"
echo ""
echo "Next steps:"
echo "  1. Run: make lint"
echo "  2. If still failing, check the output"
