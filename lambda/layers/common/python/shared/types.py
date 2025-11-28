"""Common type definitions using Pydantic."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Use regular Dict for Lambda response to match actual returns
LambdaResponse = dict[str, Any]


class MessageContext(BaseModel):
    """Message context for conversation history."""

    message_id: str
    role: str  # USER, ASSISTANT, SYSTEM
    content: str
    timestamp: str
    intent: str | None = None
    entities: dict[str, str] | None = None
    sentiment: str | None = None


class ConversationContext(BaseModel):
    """Unified conversation context model (merged from both earlier versions)."""

    # Core identifiers
    conversation_id: str
    user_id: str | None = None
    tenant_id: str | None = None
    session_id: str | None = None

    # Structured message history
    messages: list[MessageContext] = Field(default_factory=list)

    # Metadata and extra contextual info
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Runtime metrics
    total_messages: int = 0
    estimated_tokens: int = 0
    is_truncated: bool = False

    # Conversation-level state
    status: str = "ACTIVE"  # e.g. ACTIVE, CLOSED
    last_intent: str | None = None
    sentiment_score: float | None = None

    # Audit timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class IntentClassification(BaseModel):
    """Result of intent classification."""

    intent: Literal[
        "greeting",
        "question",
        "complaint",
        "request",
        "escalation",
        "shipping",
        "technical_support",
    ]
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


class ContextBuilderRequest(BaseModel):
    """Request to build conversation context."""

    conversation_id: str
    include_system_prompt: bool = True
    max_messages: int | None = None
    max_tokens: int | None = None


class ContextBuilderResponse(BaseModel):
    """Response from context builder."""

    conversation_id: str
    context: ConversationContext
    timestamp: str
