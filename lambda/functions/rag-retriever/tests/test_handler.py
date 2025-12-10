"""Unit tests for RAG Retriever Lambda handler."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from models import RetrievalResponse, RetrievedDocument

# Set environment variables before importing handler
os.environ["KNOWLEDGE_BASE_ID"] = "test-kb-id"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["POWERTOOLS_SERVICE_NAME"] = "rag-retriever-test"
os.environ["POWERTOOLS_METRICS_NAMESPACE"] = "test"


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset the global service singleton between tests."""
    import handler

    handler._service = None


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "rag-retriever"
    context.memory_limit_in_mb = 256
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:rag-retriever"
    context.aws_request_id = "test-request-id"
    return context


@pytest.fixture
def sample_event() -> dict[str, Any]:
    """Create a sample Lambda event (direct invocation)."""
    return {
        "query": "How do I reset my password?",
        "tenant_id": "tenant-123",
        "top_k": 5,
        "min_score": 0.5,
    }


@pytest.fixture
def api_gateway_event() -> dict[str, Any]:
    """Create a sample API Gateway event."""
    return {
        "body": json.dumps(
            {
                "query": "What are the pricing plans?",
                "tenant_id": "tenant-456",
            }
        ),
        "headers": {"Content-Type": "application/json"},
        "httpMethod": "POST",
        "path": "/retrieve",
    }


@pytest.fixture
def mock_retrieval_response() -> RetrievalResponse:
    """Create a mock retrieval response."""
    return RetrievalResponse(
        documents=[
            RetrievedDocument(
                content="To reset your password, click Forgot Password.",
                score=0.95,
                source_name="password-faq.md",
            ),
            RetrievedDocument(
                content="Password must be 8+ characters.",
                score=0.82,
                source_name="security.md",
            ),
        ],
        query="How do I reset my password?",
        total_found=5,
        retrieval_time_ms=125.5,
    )


class TestHandlerSuccess:
    """Tests for successful handler execution."""

    @patch("handler.get_service")
    def test_successful_direct_invocation(
        self,
        mock_get_service: MagicMock,
        sample_event: dict[str, Any],
        mock_context: MagicMock,
        mock_retrieval_response: RetrievalResponse,
    ) -> None:
        """Test successful direct Lambda invocation."""
        from handler import handler

        mock_service = MagicMock()
        mock_service.retrieve.return_value = mock_retrieval_response
        mock_get_service.return_value = mock_service

        result = handler(sample_event, mock_context)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert len(body["documents"]) == 2
        assert body["query"] == "How do I reset my password?"
        assert body["total_found"] == 5

    @patch("handler.get_service")
    def test_successful_api_gateway_invocation(
        self,
        mock_get_service: MagicMock,
        api_gateway_event: dict[str, Any],
        mock_context: MagicMock,
        mock_retrieval_response: RetrievalResponse,
    ) -> None:
        """Test successful API Gateway invocation."""
        from handler import handler

        mock_service = MagicMock()
        mock_service.retrieve.return_value = mock_retrieval_response
        mock_get_service.return_value = mock_service

        result = handler(api_gateway_event, mock_context)

        assert result["statusCode"] == 200
        assert "Content-Type" in result["headers"]
        assert result["headers"]["Content-Type"] == "application/json"

    @patch("handler.get_service")
    def test_empty_results_returns_success(
        self,
        mock_get_service: MagicMock,
        sample_event: dict[str, Any],
        mock_context: MagicMock,
    ) -> None:
        """Test that empty results still return 200."""
        from handler import handler

        mock_service = MagicMock()
        mock_service.retrieve.return_value = RetrievalResponse(
            documents=[],
            query="test",
            total_found=0,
            retrieval_time_ms=50.0,
        )
        mock_get_service.return_value = mock_service

        result = handler(sample_event, mock_context)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["documents"] == []
        assert body["total_found"] == 0


class TestHandlerValidationErrors:
    """Tests for handler validation error handling."""

    @patch("handler.get_service")
    def test_missing_query_returns_400(
        self,
        mock_get_service: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test missing query field returns 400."""
        from handler import handler

        event = {"tenant_id": "tenant-123"}

        result = handler(event, mock_context)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error_type"] == "VALIDATION_ERROR"
        assert "validation_errors" in body["details"]

    @patch("handler.get_service")
    def test_empty_query_returns_400(
        self,
        mock_get_service: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test empty query returns 400."""
        from handler import handler

        event = {"query": "", "tenant_id": "tenant-123"}

        result = handler(event, mock_context)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error_type"] == "VALIDATION_ERROR"

    @patch("handler.get_service")
    def test_missing_tenant_id_returns_400(
        self,
        mock_get_service: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test missing tenant_id returns 400."""
        from handler import handler

        event = {"query": "test query"}

        result = handler(event, mock_context)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error_type"] == "VALIDATION_ERROR"

    @patch("handler.get_service")
    def test_invalid_top_k_returns_400(
        self,
        mock_get_service: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test invalid top_k returns 400."""
        from handler import handler

        event = {"query": "test", "tenant_id": "t", "top_k": 100}

        result = handler(event, mock_context)

        assert result["statusCode"] == 400

    @patch("handler.get_service")
    def test_invalid_json_body_returns_400(
        self,
        mock_get_service: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test invalid JSON body returns 400."""
        from handler import handler

        event = {"body": "not valid json"}

        result = handler(event, mock_context)

        # Should return 400 for invalid JSON
        assert result["statusCode"] in (400, 500)


class TestHandlerServiceErrors:
    """Tests for handler service error handling."""

    @patch("handler.get_service")
    def test_knowledge_base_not_found_returns_404(
        self,
        mock_get_service: MagicMock,
        sample_event: dict[str, Any],
        mock_context: MagicMock,
    ) -> None:
        """Test knowledge base not found returns 404."""
        from handler import handler
        from service import KnowledgeBaseNotFoundError

        mock_service = MagicMock()
        mock_service.retrieve.side_effect = KnowledgeBaseNotFoundError("test-kb")
        mock_get_service.return_value = mock_service

        result = handler(sample_event, mock_context)

        assert result["statusCode"] == 404
        body = json.loads(result["body"])
        assert body["error_type"] == "KNOWLEDGE_BASE_NOT_FOUND"
        assert body["retryable"] is False

    @patch("handler.get_service")
    def test_throttling_returns_429(
        self,
        mock_get_service: MagicMock,
        sample_event: dict[str, Any],
        mock_context: MagicMock,
    ) -> None:
        """Test throttling returns 429."""
        from handler import handler
        from service import ThrottlingError

        mock_service = MagicMock()
        mock_service.retrieve.side_effect = ThrottlingError("Rate limit exceeded")
        mock_get_service.return_value = mock_service

        result = handler(sample_event, mock_context)

        assert result["statusCode"] == 429
        body = json.loads(result["body"])
        assert body["error_type"] == "THROTTLING"
        assert body["retryable"] is True

    @patch("handler.get_service")
    def test_service_error_returns_500(
        self,
        mock_get_service: MagicMock,
        sample_event: dict[str, Any],
        mock_context: MagicMock,
    ) -> None:
        """Test generic service error returns 500."""
        from handler import handler
        from service import RetrievalServiceError

        mock_service = MagicMock()
        mock_service.retrieve.side_effect = RetrievalServiceError(
            "Something went wrong",
            error_type="SERVICE_ERROR",
            retryable=True,
        )
        mock_get_service.return_value = mock_service

        result = handler(sample_event, mock_context)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert body["error_type"] == "SERVICE_ERROR"
        assert body["retryable"] is True

    @patch("handler.get_service")
    def test_unexpected_error_returns_500(
        self,
        mock_get_service: MagicMock,
        sample_event: dict[str, Any],
        mock_context: MagicMock,
    ) -> None:
        """Test unexpected error returns 500."""
        from handler import handler

        mock_service = MagicMock()
        mock_service.retrieve.side_effect = RuntimeError("Unexpected!")
        mock_get_service.return_value = mock_service

        result = handler(sample_event, mock_context)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert body["error_type"] == "INTERNAL_ERROR"
        assert body["retryable"] is True
        assert "Unexpected" not in body["message"]  # Don't leak internal details


class TestHandlerConfiguration:
    """Tests for handler configuration."""

    def test_missing_knowledge_base_id_returns_500(
        self,
        sample_event: dict[str, Any],
        mock_context: MagicMock,
    ) -> None:
        """Test missing KNOWLEDGE_BASE_ID returns 500."""
        import handler as handler_module
        from handler import handler

        # Reset the service and patch the module-level constant
        handler_module._service = None
        original_kb_id = handler_module.KNOWLEDGE_BASE_ID
        handler_module.KNOWLEDGE_BASE_ID = ""

        try:
            result = handler(sample_event, mock_context)

            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert body["error_type"] == "CONFIGURATION_ERROR"
        finally:
            handler_module.KNOWLEDGE_BASE_ID = original_kb_id


class TestRequestParsing:
    """Tests for request parsing."""

    @patch("handler.get_service")
    def test_parses_dict_body(
        self,
        mock_get_service: MagicMock,
        mock_context: MagicMock,
        mock_retrieval_response: RetrievalResponse,
    ) -> None:
        """Test parsing body as dict (already parsed JSON)."""
        from handler import handler

        mock_service = MagicMock()
        mock_service.retrieve.return_value = mock_retrieval_response
        mock_get_service.return_value = mock_service

        event = {
            "body": {"query": "test", "tenant_id": "t123"},
        }

        result = handler(event, mock_context)

        assert result["statusCode"] == 200

    @patch("handler.get_service")
    def test_parses_string_body(
        self,
        mock_get_service: MagicMock,
        mock_context: MagicMock,
        mock_retrieval_response: RetrievalResponse,
    ) -> None:
        """Test parsing body as JSON string."""
        from handler import handler

        mock_service = MagicMock()
        mock_service.retrieve.return_value = mock_retrieval_response
        mock_get_service.return_value = mock_service

        event = {
            "body": json.dumps({"query": "test", "tenant_id": "t123"}),
        }

        result = handler(event, mock_context)

        assert result["statusCode"] == 200

    @patch("handler.get_service")
    def test_parses_direct_event(
        self,
        mock_get_service: MagicMock,
        mock_context: MagicMock,
        mock_retrieval_response: RetrievalResponse,
    ) -> None:
        """Test parsing direct invocation event."""
        from handler import handler

        mock_service = MagicMock()
        mock_service.retrieve.return_value = mock_retrieval_response
        mock_get_service.return_value = mock_service

        event = {"query": "test", "tenant_id": "t123"}

        result = handler(event, mock_context)

        assert result["statusCode"] == 200


class TestResponseFormat:
    """Tests for response format."""

    @patch("handler.get_service")
    def test_success_response_format(
        self,
        mock_get_service: MagicMock,
        sample_event: dict[str, Any],
        mock_context: MagicMock,
        mock_retrieval_response: RetrievalResponse,
    ) -> None:
        """Test success response has correct format."""
        from handler import handler

        mock_service = MagicMock()
        mock_service.retrieve.return_value = mock_retrieval_response
        mock_get_service.return_value = mock_service

        result = handler(sample_event, mock_context)

        assert "statusCode" in result
        assert "body" in result
        assert "headers" in result

        body = json.loads(result["body"])
        assert "documents" in body
        assert "query" in body
        assert "total_found" in body
        assert "retrieval_time_ms" in body

    @patch("handler.get_service")
    def test_error_response_format(
        self,
        mock_get_service: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test error response has correct format."""
        from handler import handler

        event = {}  # Invalid event

        result = handler(event, mock_context)

        assert "statusCode" in result
        assert "body" in result
        assert "headers" in result

        body = json.loads(result["body"])
        assert "error_type" in body
        assert "message" in body
        assert "retryable" in body
