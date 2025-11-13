#!/bin/bash

set -e

echo "🔧 Comprehensive Lambda Fix Script"
echo "=================================="
echo ""

# 1. Fix the ruff error in utils.py
echo "1️⃣ Fixing Ruff B904 error in utils.py..."
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
        raise ValueError(f"Invalid JSON in request body: {e}") from e


def format_response(
    status_code: int,
    body: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
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
    correlation_id: str = headers.get(
        "x-correlation-id", headers.get("x-request-id", "")
    )
    return correlation_id
EOF
echo "  ✓ Fixed utils.py with proper exception chaining"

# 2. Fix LambdaResponse type to match actual return
echo ""
echo "2️⃣ Fixing LambdaResponse TypedDict..."
cat > lambda/layers/common/python/shared/types.py << 'EOF'
"""Common type definitions using Pydantic."""

from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field


# Use regular Dict for Lambda response to match actual returns
LambdaResponse = Dict[str, Any]


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
EOF
echo "  ✓ Fixed LambdaResponse type"

# 3. Add ruff to each function's dev dependencies
echo ""
echo "3️⃣ Adding ruff to Lambda function dependencies..."
for func_dir in lambda/functions/*/; do
  if [[ -f "${func_dir}pyproject.toml" ]]; then
    func_name=$(basename "${func_dir}")

    if ! grep -q '"ruff>=' "${func_dir}pyproject.toml"; then
      echo "  Adding ruff to ${func_name}..."

      # For macOS
      if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' 's/"mypy>=1.8.0",/"mypy>=1.8.0",\
    "ruff>=0.3.0",/' "${func_dir}pyproject.toml"
      else
        # For Linux
        sed -i 's/"mypy>=1.8.0",/"mypy>=1.8.0",\n    "ruff>=0.3.0",/' "${func_dir}pyproject.toml"
      fi
      echo "    ✓ Added"
    else
      echo "  ${func_name}: ruff already present"
    fi
  fi
done

# 4. Reinstall dependencies
echo ""
echo "4️⃣ Reinstalling all dependencies..."
uv sync --all-packages

# 5. Fix README markdown issues
echo ""
echo "5️⃣ Fixing README.md markdown linting..."
if [[ -f "README.md" ]]; then
  # Add bash language to code blocks (lines 34 and 142)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS version
    sed -i '' 's/^```$/```bash/g' README.md
  else
    # Linux version
    sed -i 's/^```$/```bash/g' README.md
  fi
  echo "  ✓ Fixed README.md code blocks"
fi

echo ""
echo "✅ All fixes complete!"
echo ""
echo "Summary of changes:"
echo "  1. Fixed exception chaining in utils.py (raise ... from e)"
echo "  2. Changed LambdaResponse from TypedDict to Dict[str, Any]"
echo "  3. Added ruff to all Lambda function dev dependencies"
echo "  4. Reinstalled all dependencies with uv"
echo "  5. Fixed README.md markdown code blocks"
echo ""
echo "Next step: Run pre-commit to verify:"
echo "  pre-commit run --all-files"
