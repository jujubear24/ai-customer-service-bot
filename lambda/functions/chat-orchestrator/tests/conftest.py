from typing import Any

import pytest


@pytest.fixture
def valid_chat_request_data() -> dict[str, Any]:
    """Return a valid dictionary for ChatRequest initialization."""
    return {
        "message": "Hello, how do I reset my password?",
        "tenant_id": "tenant-123",
        "conversation_id": "conv-abc-123",
        "use_rag": True,
        "rag_options": {"top_k": 3, "min_score": 0.5},
    }


@pytest.fixture
def valid_source_document_data() -> dict[str, Any]:
    """Return a valid dictionary for SourceDocument initialization."""
    return {
        "name": "Reset Password Guide",
        "content": "To reset your password, go to settings...",
        "source": "https://docs.example.com/reset-password",
        "score": 0.95,
        "metadata": {"category": "auth"},
    }
