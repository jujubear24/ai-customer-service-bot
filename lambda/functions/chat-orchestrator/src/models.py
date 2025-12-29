"""Chat Orchestrator request and response models."""

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class RAGOptions(BaseModel):
    """Options for RAG retrieval."""

    top_k: int = Field(default=3, ge=1, le=10, description="Max documents to retrieve")
    min_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Minimum relevance score")


class ChatRequest(BaseModel):
    """Request model for chat orchestrator."""

    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    tenant_id: str = Field(..., min_length=1, max_length=100, description="Tenant identifier")
    conversation_id: str | None = Field(
        default=None, description="Conversation ID (generated if not provided)"
    )
    use_rag: bool = Field(default=True, description="Enable RAG retrieval")
    rag_options: RAGOptions = Field(default_factory=RAGOptions)
    validate_response: bool = Field(default=True, description="Enable response validation")

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Strip whitespace and validate non-empty."""
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        return v

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        """Strip whitespace and validate non-empty."""
        v = v.strip()
        if not v:
            raise ValueError("Tenant ID cannot be empty")
        return v


class SourceDocument(BaseModel):
    """Model representing a retrieved source document."""

    source_name: str | None = Field(default=None, description="Document title or name")
    content: str = Field(..., description="Text content of the document")
    source_uri: str | None = Field(default=None, description="URI or path to the source")
    score: float = Field(..., description="Relevance score")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")


class LatencyMetrics(BaseModel):
    """Latency breakdown for the request."""

    rag_ms: float | None = None
    bedrock_ms: float | None = None
    validation_ms: float | None = None
    total_ms: float = 0.0


class ValidationMetrics(BaseModel):
    """Metrics from response validation."""

    is_valid: bool = Field(default=True, description="Whether the response passed validation")
    action: str = Field(default="PASS", description="Validation action taken")
    was_modified: bool = Field(default=False, description="Whether response was modified")
    validation_skipped: bool = Field(default=False, description="Whether validation was skipped")
    rules_evaluated: int = Field(default=0, description="Number of rules evaluated")
    fallback_used: bool = Field(default=False, description="Whether a fallback response was used")
    fallback_reason: str | None = Field(default=None, description="Reason for fallback if used")


class SentimentMetrics(BaseModel):
    """Metrics from sentiment analysis (Phase 3.2)."""

    sentiment: str = Field(
        ..., description="Dominant sentiment: POSITIVE, NEGATIVE, NEUTRAL, MIXED"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Sentiment confidence score")
    negative_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Negative sentiment score"
    )


class EscalationMetrics(BaseModel):
    """Metrics from escalation scoring (Phase 3.2)."""

    score: float = Field(..., ge=0.0, le=1.0, description="Composite escalation score")
    needs_escalation: bool = Field(..., description="Whether escalation threshold was exceeded")
    threshold: float = Field(default=0.70, ge=0.0, le=1.0, description="Escalation threshold used")
    primary_reason: str | None = Field(default=None, description="Primary reason for escalation")

    # Factor breakdown
    explicit_intent_score: float = Field(default=0.0, ge=0.0, le=1.0)
    negative_sentiment_score: float = Field(default=0.0, ge=0.0, le=1.0)
    urgency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    repeated_question_score: float = Field(default=0.0, ge=0.0, le=1.0)
    low_confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


class EscalationRoutingMetrics(BaseModel):
    """Metrics from escalation routing (Phase 3.3)."""

    routed: bool = Field(default=False, description="Whether escalation was routed to agents")
    escalation_id: str | None = Field(default=None, description="Unique escalation identifier")
    priority: str | None = Field(default=None, description="Priority tier: CRITICAL, HIGH, NORMAL")
    queue_message_id: str | None = Field(default=None, description="SQS message ID if queued")
    estimated_wait: str | None = Field(default=None, description="Estimated wait time for agent")
    routing_error: bool = Field(default=False, description="Whether routing encountered an error")
    error_message: str | None = Field(default=None, description="Error message if routing failed")


class ChatMetadata(BaseModel):
    """Metadata for the chat response."""

    model: str
    rag_documents_used: int = 0
    rag_skipped: bool = False
    latency: LatencyMetrics = Field(default_factory=LatencyMetrics)
    validation: ValidationMetrics | None = Field(
        default=None, description="Response validation metrics"
    )
    sentiment: SentimentMetrics | None = Field(
        default=None, description="Sentiment analysis metrics (Phase 3.2)"
    )
    escalation: EscalationMetrics | None = Field(
        default=None, description="Escalation scoring metrics (Phase 3.2)"
    )
    escalation_routing: EscalationRoutingMetrics | None = Field(
        default=None, description="Escalation routing metrics (Phase 3.3)"
    )


class ChatResponse(BaseModel):
    """Response model for chat orchestrator."""

    conversation_id: str
    message_id: str
    response: str
    sources: list[SourceDocument] = Field(default_factory=list)
    metadata: ChatMetadata

    @classmethod
    def create(
        cls,
        conversation_id: str,
        response_text: str,
        model: str,
        sources: list[SourceDocument] | None = None,
        rag_documents_used: int = 0,
        rag_skipped: bool = False,
        rag_latency_ms: float | None = None,
        bedrock_latency_ms: float | None = None,
        validation_latency_ms: float | None = None,
        total_latency_ms: float = 0.0,
        validation_result: dict[str, Any] | None = None,
        escalation_routing_result: dict[str, Any] | None = None,
    ) -> "ChatResponse":
        """Factory method to create a ChatResponse."""
        # Build validation metrics from result
        validation_metrics = None
        sentiment_metrics = None
        escalation_metrics = None
        escalation_routing_metrics = None

        if validation_result is not None:
            validation_metrics = ValidationMetrics(
                is_valid=validation_result.get("is_valid", True),
                action=validation_result.get("action", "PASS"),
                was_modified=validation_result.get("was_modified", False),
                validation_skipped=validation_result.get("validation_skipped", False),
                rules_evaluated=validation_result.get("metadata", {}).get("rules_evaluated", 0),
                fallback_used=validation_result.get("metadata", {}).get("fallback_used", False),
                fallback_reason=validation_result.get("metadata", {}).get("fallback_reason"),
            )

            # Extract sentiment metrics (Phase 3.2)
            sentiment_data = validation_result.get("sentiment")
            if sentiment_data is not None:
                sentiment_metrics = SentimentMetrics(
                    sentiment=sentiment_data.get("sentiment", "NEUTRAL"),
                    confidence=sentiment_data.get("confidence", 0.0),
                    negative_score=sentiment_data.get("scores", {}).get("negative", 0.0),
                )

            # Extract escalation metrics (Phase 3.2)
            escalation_data = validation_result.get("escalation")
            if escalation_data is not None:
                factors = escalation_data.get("factors", {})
                escalation_metrics = EscalationMetrics(
                    score=escalation_data.get("score", 0.0),
                    needs_escalation=escalation_data.get("needs_escalation", False),
                    threshold=escalation_data.get("threshold", 0.70),
                    primary_reason=escalation_data.get("primary_reason"),
                    explicit_intent_score=factors.get("explicit_intent", 0.0),
                    negative_sentiment_score=factors.get("negative_sentiment", 0.0),
                    urgency_score=factors.get("urgency", 0.0),
                    repeated_question_score=factors.get("repeated_question", 0.0),
                    low_confidence_score=factors.get("low_confidence", 0.0),
                )

        # Extract escalation routing metrics (Phase 3.3)
        if escalation_routing_result is not None:
            escalation_routing_metrics = EscalationRoutingMetrics(
                routed=escalation_routing_result.get("success", False),
                escalation_id=escalation_routing_result.get("escalation_id"),
                priority=escalation_routing_result.get("priority"),
                queue_message_id=escalation_routing_result.get("queue_message_id"),
                estimated_wait=escalation_routing_result.get("estimated_wait"),
                routing_error=escalation_routing_result.get("routing_error", False),
                error_message=escalation_routing_result.get("error_message"),
            )

        return cls(
            conversation_id=conversation_id,
            message_id=f"msg-{uuid4().hex[:12]}",
            response=response_text,
            sources=sources or [],
            metadata=ChatMetadata(
                model=model,
                rag_documents_used=rag_documents_used,
                rag_skipped=rag_skipped,
                latency=LatencyMetrics(
                    rag_ms=rag_latency_ms,
                    bedrock_ms=bedrock_latency_ms,
                    validation_ms=validation_latency_ms,
                    total_ms=total_latency_ms,
                ),
                validation=validation_metrics,
                sentiment=sentiment_metrics,
                escalation=escalation_metrics,
                escalation_routing=escalation_routing_metrics,
            ),
        )


class ChatError(BaseModel):
    """Error response model."""

    error_type: str = Field(..., description="Error type identifier")
    message: str = Field(..., description="Human-readable error message")
    retryable: bool = Field(default=False, description="Whether the request can be retried")
    conversation_id: str | None = Field(default=None, description="Conversation ID if available")
    details: dict[str, Any] | None = Field(default=None, description="Error details")
