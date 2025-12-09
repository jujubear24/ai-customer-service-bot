"""Unit tests for RAG Retriever models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import (
    RetrievalError,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalType,
    RetrievedDocument,
)


class TestRetrievalRequest:
    """Tests for RetrievalRequest model."""

    def test_valid_request_minimal(self) -> None:
        """Test creating request with minimal required fields."""
        request = RetrievalRequest(
            query="How do I reset my password?",
            tenant_id="tenant-123",
        )

        assert request.query == "How do I reset my password?"
        assert request.tenant_id == "tenant-123"
        assert request.top_k == 5  # default
        assert request.min_score == 0.5  # default
        assert request.retrieval_type == RetrievalType.SEMANTIC  # default

    def test_valid_request_all_fields(self) -> None:
        """Test creating request with all fields."""
        request = RetrievalRequest(
            query="What are the pricing plans?",
            tenant_id="tenant-456",
            conversation_id="conv-789",
            top_k=10,
            min_score=0.7,
            retrieval_type=RetrievalType.HYBRID,
            include_metadata=False,
        )

        assert request.query == "What are the pricing plans?"
        assert request.tenant_id == "tenant-456"
        assert request.conversation_id == "conv-789"
        assert request.top_k == 10
        assert request.min_score == 0.7
        assert request.retrieval_type == RetrievalType.HYBRID
        assert request.include_metadata is False

    def test_query_whitespace_stripped(self) -> None:
        """Test that query whitespace is stripped."""
        request = RetrievalRequest(
            query="  How do I upgrade?  ",
            tenant_id="tenant-123",
        )

        assert request.query == "How do I upgrade?"

    def test_query_empty_raises_error(self) -> None:
        """Test that empty query raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            RetrievalRequest(query="", tenant_id="tenant-123")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("query",) for e in errors)

    def test_query_whitespace_only_raises_error(self) -> None:
        """Test that whitespace-only query raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            RetrievalRequest(query="   ", tenant_id="tenant-123")

        errors = exc_info.value.errors()
        assert any("empty" in str(e["msg"]).lower() for e in errors)

    def test_query_too_long_raises_error(self) -> None:
        """Test that query over max length raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            RetrievalRequest(
                query="x" * 4097,
                tenant_id="tenant-123",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("query",) for e in errors)

    def test_top_k_bounds(self) -> None:
        """Test top_k validation bounds."""
        # Valid minimum
        request = RetrievalRequest(query="test", tenant_id="t", top_k=1)
        assert request.top_k == 1

        # Valid maximum
        request = RetrievalRequest(query="test", tenant_id="t", top_k=20)
        assert request.top_k == 20

        # Below minimum
        with pytest.raises(ValidationError):
            RetrievalRequest(query="test", tenant_id="t", top_k=0)

        # Above maximum
        with pytest.raises(ValidationError):
            RetrievalRequest(query="test", tenant_id="t", top_k=21)

    def test_min_score_bounds(self) -> None:
        """Test min_score validation bounds."""
        # Valid minimum
        request = RetrievalRequest(query="test", tenant_id="t", min_score=0.0)
        assert request.min_score == 0.0

        # Valid maximum
        request = RetrievalRequest(query="test", tenant_id="t", min_score=1.0)
        assert request.min_score == 1.0

        # Below minimum
        with pytest.raises(ValidationError):
            RetrievalRequest(query="test", tenant_id="t", min_score=-0.1)

        # Above maximum
        with pytest.raises(ValidationError):
            RetrievalRequest(query="test", tenant_id="t", min_score=1.1)


class TestRetrievedDocument:
    """Tests for RetrievedDocument model."""

    def test_valid_document(self) -> None:
        """Test creating a valid document."""
        doc = RetrievedDocument(
            content="This is the document content.",
            score=0.85,
            source_uri="s3://bucket/docs/faq.md",
            source_name="faq.md",
            metadata={"category": "billing"},
        )

        assert doc.content == "This is the document content."
        assert doc.score == 0.85
        assert doc.source_uri == "s3://bucket/docs/faq.md"
        assert doc.source_name == "faq.md"
        assert doc.metadata == {"category": "billing"}

    def test_document_minimal(self) -> None:
        """Test creating document with minimal fields."""
        doc = RetrievedDocument(
            content="Content only",
            score=0.5,
        )

        assert doc.content == "Content only"
        assert doc.score == 0.5
        assert doc.source_uri is None
        assert doc.source_name is None
        assert doc.metadata is None

    def test_formatted_content_with_source(self) -> None:
        """Test formatted content includes source attribution."""
        doc = RetrievedDocument(
            content="How to reset password instructions.",
            score=0.9,
            source_name="password-faq.md",
        )

        assert doc.formatted_content == (
            "[Source: password-faq.md]\n" "How to reset password instructions."
        )

    def test_formatted_content_without_source(self) -> None:
        """Test formatted content without source name."""
        doc = RetrievedDocument(
            content="Plain content here.",
            score=0.7,
        )

        assert doc.formatted_content == "Plain content here."

    def test_score_bounds(self) -> None:
        """Test score validation bounds."""
        # Valid bounds
        RetrievedDocument(content="test", score=0.0)
        RetrievedDocument(content="test", score=1.0)

        # Invalid bounds
        with pytest.raises(ValidationError):
            RetrievedDocument(content="test", score=-0.1)

        with pytest.raises(ValidationError):
            RetrievedDocument(content="test", score=1.1)


class TestRetrievalResponse:
    """Tests for RetrievalResponse model."""

    def test_empty_response(self) -> None:
        """Test creating an empty response."""
        response = RetrievalResponse(
            documents=[],
            query="test query",
            total_found=0,
            retrieval_time_ms=50.5,
        )

        assert response.documents == []
        assert response.query == "test query"
        assert response.total_found == 0
        assert response.retrieval_time_ms == 50.5
        assert response.has_results is False
        assert response.average_score == 0.0
        assert response.rag_context == []

    def test_response_with_documents(self) -> None:
        """Test response with multiple documents."""
        docs = [
            RetrievedDocument(content="Doc 1", score=0.9, source_name="a.md"),
            RetrievedDocument(content="Doc 2", score=0.8, source_name="b.md"),
            RetrievedDocument(content="Doc 3", score=0.7),
        ]

        response = RetrievalResponse(
            documents=docs,
            query="test",
            total_found=10,
            retrieval_time_ms=123.45,
        )

        assert len(response.documents) == 3
        assert response.has_results is True
        assert response.total_found == 10

    def test_average_score_calculation(self) -> None:
        """Test average score is calculated correctly."""
        docs = [
            RetrievedDocument(content="a", score=0.9),
            RetrievedDocument(content="b", score=0.8),
            RetrievedDocument(content="c", score=0.7),
        ]

        response = RetrievalResponse(
            documents=docs,
            query="test",
        )

        expected_avg = (0.9 + 0.8 + 0.7) / 3
        assert response.average_score == pytest.approx(expected_avg, rel=1e-6)

    def test_rag_context_property(self) -> None:
        """Test rag_context returns formatted content list."""
        docs = [
            RetrievedDocument(content="Content 1", score=0.9, source_name="a.md"),
            RetrievedDocument(content="Content 2", score=0.8),
        ]

        response = RetrievalResponse(documents=docs, query="test")
        context = response.rag_context

        assert len(context) == 2
        assert context[0] == "[Source: a.md]\nContent 1"
        assert context[1] == "Content 2"


class TestRetrievalError:
    """Tests for RetrievalError model."""

    def test_error_minimal(self) -> None:
        """Test creating error with minimal fields."""
        error = RetrievalError(
            error_type="VALIDATION_ERROR",
            message="Invalid query",
        )

        assert error.error_type == "VALIDATION_ERROR"
        assert error.message == "Invalid query"
        assert error.details is None
        assert error.retryable is False

    def test_error_full(self) -> None:
        """Test creating error with all fields."""
        error = RetrievalError(
            error_type="THROTTLING",
            message="Rate limit exceeded",
            details={"retry_after": 30},
            retryable=True,
        )

        assert error.error_type == "THROTTLING"
        assert error.message == "Rate limit exceeded"
        assert error.details == {"retry_after": 30}
        assert error.retryable is True

    def test_error_serialization(self) -> None:
        """Test error serializes to JSON correctly."""
        error = RetrievalError(
            error_type="TEST",
            message="Test message",
            retryable=True,
        )

        json_str = error.model_dump_json()
        assert "TEST" in json_str
        assert "Test message" in json_str
        assert '"retryable":true' in json_str.lower().replace(" ", "")


class TestRetrievalType:
    """Tests for RetrievalType enum."""

    def test_enum_values(self) -> None:
        """Test enum has expected values."""
        assert RetrievalType.SEMANTIC.value == "SEMANTIC"
        assert RetrievalType.HYBRID.value == "HYBRID"

    def test_enum_in_request(self) -> None:
        """Test enum works in request model."""
        request = RetrievalRequest(
            query="test",
            tenant_id="t",
            retrieval_type=RetrievalType.HYBRID,
        )
        assert request.retrieval_type == RetrievalType.HYBRID

    def test_enum_from_string(self) -> None:
        """Test enum can be created from string."""
        request = RetrievalRequest(
            query="test",
            tenant_id="t",
            retrieval_type="HYBRID",  # type: ignore[arg-type]
        )
        assert request.retrieval_type == RetrievalType.HYBRID
