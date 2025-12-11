import pytest
from pydantic import ValidationError

from models import ChatError, ChatRequest, ChatResponse, RAGOptions, SourceDocument

# --- RAGOptions Tests ---


def test_rag_options_defaults():
    """Test that RAGOptions instantiates with correct defaults."""
    options = RAGOptions()
    assert options.top_k == 3
    assert options.min_score == 0.5


def test_rag_options_constraints():
    """Test min/max constraints on RAGOptions."""
    # Test top_k bounds (assuming max is 10 based on snippet)
    with pytest.raises(ValidationError):
        RAGOptions(top_k=11)

    with pytest.raises(ValidationError):
        RAGOptions(top_k=0)

    # Test min_score bounds
    with pytest.raises(ValidationError):
        RAGOptions(min_score=1.1)

    with pytest.raises(ValidationError):
        RAGOptions(min_score=-0.1)


# --- ChatRequest Tests ---


def test_chat_request_valid(valid_chat_request_data):
    """Test successful creation of ChatRequest."""
    request = ChatRequest(**valid_chat_request_data)
    assert request.message == valid_chat_request_data["message"]
    assert request.tenant_id == valid_chat_request_data["tenant_id"]
    assert request.use_rag is True


def test_chat_request_validation_message_empty():
    """Test that empty or whitespace-only messages raise ValidationError."""
    with pytest.raises(ValidationError) as exc:
        ChatRequest(message="   ", tenant_id="t1")
    assert "Message cannot be empty" in str(exc.value)


def test_chat_request_validation_tenant_id_empty():
    """Test that empty tenant_id raises ValidationError."""
    with pytest.raises(ValidationError):
        ChatRequest(message="valid message", tenant_id="   ")


def test_chat_request_defaults():
    """Test that optional fields use correct defaults."""
    request = ChatRequest(message="Hello", tenant_id="t1")
    assert request.use_rag is True
    assert request.rag_options.top_k == 3
    assert request.conversation_id is None


# --- ChatResponse Tests ---


def test_chat_response_create_factory(valid_source_document_data):
    """Test the factory method for creating responses."""
    sources = [SourceDocument(**valid_source_document_data)]

    response = ChatResponse.create(
        conversation_id="conv-123",
        response_text="Here is the answer.",
        model="claude-haiku",
        sources=sources,
        rag_documents_used=1,
        rag_latency_ms=150.5,
        bedrock_latency_ms=500.0,
        total_latency_ms=655.0,
    )

    assert response.conversation_id == "conv-123"
    assert response.response == "Here is the answer."
    assert len(response.sources) == 1
    assert response.sources[0].score == 0.95

    # Check generated fields
    assert response.message_id.startswith("msg-")

    # Check metadata
    meta = response.metadata
    assert meta.model == "claude-haiku"
    assert meta.rag_documents_used == 1
    assert meta.latency.rag_ms == 150.5
    assert meta.latency.bedrock_ms == 500.0
    assert meta.latency.total_ms == 655.0


def test_chat_response_create_without_sources():
    """Test factory method works without sources (e.g. general chat)."""
    response = ChatResponse.create(
        conversation_id="conv-123", response_text="Hello there.", model="claude-haiku"
    )
    assert response.sources == []
    assert response.metadata.rag_skipped is False  # Default is False in factory arg


# --- ChatError Tests ---


def test_chat_error_creation():
    """Test ChatError model."""
    error = ChatError(
        error_type="ServiceError",
        message="Something went wrong",
        retryable=True,
        details={"status_code": 503},
    )
    assert error.error_type == "ServiceError"
    assert error.retryable is True
    assert error.details["status_code"] == 503
