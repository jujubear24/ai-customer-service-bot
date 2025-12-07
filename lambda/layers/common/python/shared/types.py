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


# =============================================================================
# Bedrock Models (ADR-009)
# =============================================================================


class BedrockRequest(BaseModel):
    """Request payload for Bedrock Handler Lambda.

    This model represents the input to the Bedrock Handler, containing
    the user message, conversation context, and inference parameters.
    """

    # Required fields
    conversation_id: str = Field(..., description="Unique conversation identifier")
    user_message: str = Field(..., description="Current user message to respond to")

    # Context from upstream Lambdas
    conversation_context: ConversationContext | None = Field(
        default=None, description="Conversation history from Context Builder"
    )
    intent: str | None = Field(default=None, description="Classified intent from Intent Classifier")
    entities: dict[str, str] | None = Field(
        default=None, description="Extracted entities from Intent Classifier"
    )

    # RAG context (Phase 2.2)
    rag_context: list[str] | None = Field(
        default=None, description="Retrieved documents from Knowledge Base"
    )

    # Inference parameters
    max_tokens: int = Field(default=1024, ge=1, le=4096, description="Maximum tokens in response")
    temperature: float | None = Field(
        default=0.7, ge=0.0, le=1.0, description="Sampling temperature (cannot use with top_p)"
    )
    top_p: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling parameter (cannot use with temperature)",
    )

    # Optional overrides
    system_prompt_override: str | None = Field(
        default=None, description="Override default system prompt"
    )


class BedrockResponse(BaseModel):
    """Response payload from Bedrock Handler Lambda.

    This model represents the output from the Bedrock Handler, containing
    the AI-generated response and associated metadata for observability.
    """

    # Core response
    conversation_id: str = Field(..., description="Conversation identifier (echo from request)")
    response_text: str = Field(..., description="AI-generated response text")

    # Model information
    model_id: str = Field(..., description="Bedrock model ID used for inference")

    # Token usage (for cost tracking)
    input_tokens: int = Field(..., ge=0, description="Number of input tokens consumed")
    output_tokens: int = Field(..., ge=0, description="Number of output tokens generated")

    # Performance metrics
    latency_ms: int = Field(..., ge=0, description="End-to-end invocation latency in milliseconds")

    # Response metadata
    stop_reason: str = Field(
        ..., description="Reason for response completion (e.g., end_turn, max_tokens)"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp of response generation")

    # Optional fields for debugging/observability
    request_id: str | None = Field(default=None, description="AWS request ID for tracing")


# =============================================================================
# Escalation Models
# =============================================================================


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


# =============================================================================
# Context Builder Models
# =============================================================================


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
