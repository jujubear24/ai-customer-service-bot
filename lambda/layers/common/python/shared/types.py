"""Common type definitions using Pydantic."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Use regular Dict for Lambda response to match actual returns
LambdaResponse = dict[str, Any]


class ConversationContext(BaseModel):
    """Context maintained across conversation turns."""

    conversation_id: str
    tenant_id: str
    user_id: str
    session_id: str
    message_history: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class IntentClassification(BaseModel):
    """Result of intent classification."""

    intent: Literal["greeting", "question", "complaint", "request", "escalation"]
    confidence: float = Field(ge=0.0, le=1.0)
    entities: dict[str, str] = Field(default_factory=dict)
    requires_context: bool = False


class BedrockRequest(BaseModel):
    """Standardized Bedrock request wrapper."""

    prompt: str
    conversation_context: ConversationContext | None = None
    max_tokens: int = 1000
    temperature: float = 0.7
    system_prompts: list[str] = Field(default_factory=list)


class EscalationTicket(BaseModel):
    """Escalation ticket structure."""

    conversation_id: str
    escalation_score: float = Field(ge=0.0, le=1.0)
    reason: str
    context: dict[str, Any]
    customer_tier: str = "standard"
    sentiment: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    priority: str = "medium"
