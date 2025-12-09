"""
Pydantic models for RAG Retriever Lambda.

Defines request/response schemas and domain models for knowledge base retrieval.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RetrievalType(str, Enum):
    """Type of retrieval operation."""

    SEMANTIC = "SEMANTIC"
    HYBRID = "HYBRID"


class RetrievalRequest(BaseModel):
    """Request model for RAG retrieval."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="The search query to find relevant documents",
    )
    tenant_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Tenant identifier for multi-tenant filtering",
    )
    conversation_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional conversation ID for context",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of documents to retrieve",
    )
    min_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score threshold (0-1)",
    )
    retrieval_type: RetrievalType = Field(
        default=RetrievalType.SEMANTIC,
        description="Type of retrieval (SEMANTIC or HYBRID)",
    )
    include_metadata: bool = Field(
        default=True,
        description="Whether to include document metadata in response",
    )

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        """Ensure query is not just whitespace."""
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        return v.strip()


class RetrievedDocument(BaseModel):
    """A single document retrieved from the knowledge base."""

    content: str = Field(
        ...,
        description="The text content of the retrieved chunk",
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score (0-1)",
    )
    source_uri: str | None = Field(
        default=None,
        description="S3 URI or source location of the document",
    )
    source_name: str | None = Field(
        default=None,
        description="Human-readable name of the source document",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional metadata from the document",
    )

    @property
    def formatted_content(self) -> str:
        """Format content with source attribution for prompt injection."""
        if self.source_name:
            return f"[Source: {self.source_name}]\n{self.content}"
        return self.content


class RetrievalResponse(BaseModel):
    """Response model for RAG retrieval."""

    documents: list[RetrievedDocument] = Field(
        default_factory=list,
        description="List of retrieved documents",
    )
    query: str = Field(
        ...,
        description="The original query",
    )
    total_found: int = Field(
        default=0,
        ge=0,
        description="Total number of documents found before filtering",
    )
    retrieval_time_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Time taken for retrieval in milliseconds",
    )

    @property
    def has_results(self) -> bool:
        """Check if any documents were retrieved."""
        return len(self.documents) > 0

    @property
    def rag_context(self) -> list[str]:
        """Get formatted context list for Bedrock Handler injection."""
        return [doc.formatted_content for doc in self.documents]

    @property
    def average_score(self) -> float:
        """Calculate average relevance score of retrieved documents."""
        if not self.documents:
            return 0.0
        return sum(doc.score for doc in self.documents) / len(self.documents)


class RetrievalError(BaseModel):
    """Error response model."""

    error_type: str = Field(
        ...,
        description="Type/category of the error",
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Additional error details for debugging",
    )
    retryable: bool = Field(
        default=False,
        description="Whether the request can be retried",
    )
