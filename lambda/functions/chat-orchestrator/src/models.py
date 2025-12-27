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


class ChatMetadata(BaseModel):
    """Metadata for the chat response."""

    model: str
    rag_documents_used: int = 0
    rag_skipped: bool = False
    latency: LatencyMetrics = Field(default_factory=LatencyMetrics)
    validation: ValidationMetrics | None = Field(
        default=None, description="Response validation metrics"
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
    ) -> "ChatResponse":
        """Factory method to create a ChatResponse."""
        # Build validation metrics from result
        validation_metrics = None
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
            ),
        )


class ChatError(BaseModel):
    """Error response model."""

    error_type: str = Field(..., description="Error type identifier")
    message: str = Field(..., description="Human-readable error message")
    retryable: bool = Field(default=False, description="Whether the request can be retried")
    conversation_id: str | None = Field(default=None, description="Conversation ID if available")
    details: dict[str, Any] | None = Field(default=None, description="Error details")
