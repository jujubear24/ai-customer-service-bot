"""Unit tests for RAG Retriever service."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from models import RetrievalRequest, RetrievalType
from service import (
    KnowledgeBaseNotFoundError,
    RetrievalService,
    RetrievalServiceError,
    ThrottlingError,
)


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock Bedrock Agent Runtime client."""
    return MagicMock()


@pytest.fixture
def service(mock_client: MagicMock) -> RetrievalService:
    """Create a RetrievalService with mocked client."""
    return RetrievalService(
        knowledge_base_id="test-kb-id",
        region="us-east-1",
        client=mock_client,
    )


@pytest.fixture
def sample_request() -> RetrievalRequest:
    """Create a sample retrieval request."""
    return RetrievalRequest(
        query="How do I reset my password?",
        tenant_id="tenant-123",
        top_k=5,
        min_score=0.5,
    )


@pytest.fixture
def sample_api_response() -> dict[str, Any]:
    """Create a sample Bedrock API response."""
    return {
        "retrievalResults": [
            {
                "content": {"text": "To reset your password, click Forgot Password..."},
                "score": 0.95,
                "location": {
                    "type": "S3",
                    "s3Location": {"uri": "s3://bucket/faqs/password-faq.md"},
                },
                "metadata": {"category": "account"},
            },
            {
                "content": {"text": "Password requirements include 8+ characters..."},
                "score": 0.82,
                "location": {
                    "type": "S3",
                    "s3Location": {"uri": "s3://bucket/faqs/security.md"},
                },
            },
            {
                "content": {"text": "Unrelated low-score content"},
                "score": 0.3,  # Below min_score
                "location": {
                    "type": "S3",
                    "s3Location": {"uri": "s3://bucket/other.md"},
                },
            },
        ]
    }


class TestRetrievalServiceInit:
    """Tests for RetrievalService initialization."""

    def test_init_with_client(self, mock_client: MagicMock) -> None:
        """Test initialization with provided client."""
        service = RetrievalService(
            knowledge_base_id="kb-123",
            region="us-west-2",
            client=mock_client,
        )

        assert service.knowledge_base_id == "kb-123"
        assert service.region == "us-west-2"
        assert service._client is mock_client

    @patch("service.boto3.client")
    def test_init_creates_client(self, mock_boto_client: MagicMock) -> None:
        """Test initialization creates client when not provided."""
        mock_boto_client.return_value = MagicMock()

        service = RetrievalService(
            knowledge_base_id="kb-456",
            region="eu-west-1",
        )

        mock_boto_client.assert_called_once()
        call_kwargs = mock_boto_client.call_args
        assert call_kwargs[0][0] == "bedrock-agent-runtime"
        assert call_kwargs[1]["region_name"] == "eu-west-1"
        assert service.knowledge_base_id == "kb-456"


class TestRetrievalServiceRetrieve:
    """Tests for RetrievalService.retrieve method."""

    def test_successful_retrieval(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
        sample_request: RetrievalRequest,
        sample_api_response: dict[str, Any],
    ) -> None:
        """Test successful document retrieval."""
        mock_client.retrieve.return_value = sample_api_response

        response = service.retrieve(sample_request)

        # Verify API was called correctly
        mock_client.retrieve.assert_called_once()
        call_kwargs = mock_client.retrieve.call_args[1]
        assert call_kwargs["knowledgeBaseId"] == "test-kb-id"
        assert call_kwargs["retrievalQuery"]["text"] == sample_request.query

        # Verify response
        assert response.has_results is True
        assert len(response.documents) == 2  # Low-score doc filtered
        assert response.query == sample_request.query
        assert response.total_found == 3
        assert response.retrieval_time_ms > 0

        # Verify documents are sorted by score
        assert response.documents[0].score == 0.95
        assert response.documents[1].score == 0.82

    def test_retrieval_filters_low_scores(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
    ) -> None:
        """Test that documents below min_score are filtered."""
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {"content": {"text": "High score"}, "score": 0.9},
                {"content": {"text": "Medium score"}, "score": 0.6},
                {"content": {"text": "Low score"}, "score": 0.4},
            ]
        }

        request = RetrievalRequest(
            query="test",
            tenant_id="t",
            min_score=0.5,
        )

        response = service.retrieve(request)

        assert len(response.documents) == 2
        assert all(doc.score >= 0.5 for doc in response.documents)

    def test_retrieval_respects_top_k(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
        sample_request: RetrievalRequest,
    ) -> None:
        """Test that top_k is passed to API."""
        sample_request.top_k = 10
        mock_client.retrieve.return_value = {"retrievalResults": []}

        service.retrieve(sample_request)

        call_kwargs = mock_client.retrieve.call_args[1]
        vector_config = call_kwargs["retrievalConfiguration"][
            "vectorSearchConfiguration"
        ]
        assert vector_config["numberOfResults"] == 10

    def test_retrieval_hybrid_search(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
    ) -> None:
        """Test hybrid search configuration."""
        mock_client.retrieve.return_value = {"retrievalResults": []}

        request = RetrievalRequest(
            query="test",
            tenant_id="t",
            retrieval_type=RetrievalType.HYBRID,
        )

        service.retrieve(request)

        call_kwargs = mock_client.retrieve.call_args[1]
        vector_config = call_kwargs["retrievalConfiguration"][
            "vectorSearchConfiguration"
        ]
        assert vector_config["overrideSearchType"] == "HYBRID"

    def test_retrieval_extracts_source_info(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
    ) -> None:
        """Test source URI and name extraction."""
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": "Content"},
                    "score": 0.9,
                    "location": {
                        "type": "S3",
                        "s3Location": {"uri": "s3://bucket/path/to/document.md"},
                    },
                }
            ]
        }

        request = RetrievalRequest(query="test", tenant_id="t")
        response = service.retrieve(request)

        assert response.documents[0].source_uri == "s3://bucket/path/to/document.md"
        assert response.documents[0].source_name == "document.md"

    def test_retrieval_includes_metadata(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
    ) -> None:
        """Test metadata is included when requested."""
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": "Content"},
                    "score": 0.9,
                    "metadata": {"category": "billing", "version": "2.0"},
                }
            ]
        }

        request = RetrievalRequest(
            query="test",
            tenant_id="t",
            include_metadata=True,
        )
        response = service.retrieve(request)

        assert response.documents[0].metadata == {
            "category": "billing",
            "version": "2.0",
        }

    def test_retrieval_excludes_metadata_when_disabled(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
    ) -> None:
        """Test metadata is excluded when not requested."""
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": "Content"},
                    "score": 0.9,
                    "metadata": {"category": "billing"},
                }
            ]
        }

        request = RetrievalRequest(
            query="test",
            tenant_id="t",
            include_metadata=False,
        )
        response = service.retrieve(request)

        assert response.documents[0].metadata is None

    def test_retrieval_handles_empty_results(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
        sample_request: RetrievalRequest,
    ) -> None:
        """Test handling of empty results."""
        mock_client.retrieve.return_value = {"retrievalResults": []}

        response = service.retrieve(sample_request)

        assert response.has_results is False
        assert len(response.documents) == 0
        assert response.total_found == 0

    def test_retrieval_skips_empty_content(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
        sample_request: RetrievalRequest,
    ) -> None:
        """Test documents with empty content are skipped."""
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {"content": {"text": ""}, "score": 0.9},
                {"content": {"text": "Valid content"}, "score": 0.8},
                {"content": {}, "score": 0.7},
            ]
        }

        response = service.retrieve(sample_request)

        assert len(response.documents) == 1
        assert response.documents[0].content == "Valid content"


class TestRetrievalServiceErrors:
    """Tests for RetrievalService error handling."""

    def test_knowledge_base_not_found_error(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
        sample_request: RetrievalRequest,
    ) -> None:
        """Test handling of ResourceNotFoundException."""
        mock_client.retrieve.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "KB not found"}},
            "Retrieve",
        )

        with pytest.raises(KnowledgeBaseNotFoundError) as exc_info:
            service.retrieve(sample_request)

        assert "test-kb-id" in str(exc_info.value)
        assert exc_info.value.retryable is False

    def test_throttling_error(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
        sample_request: RetrievalRequest,
    ) -> None:
        """Test handling of ThrottlingException."""
        mock_client.retrieve.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Retrieve",
        )

        # Should raise after retries
        with pytest.raises(ThrottlingError) as exc_info:
            service.retrieve(sample_request)

        assert exc_info.value.retryable is True
        # Verify retries happened (3 attempts)
        assert mock_client.retrieve.call_count == 3

    def test_generic_client_error(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
        sample_request: RetrievalRequest,
    ) -> None:
        """Test handling of generic ClientError."""
        mock_client.retrieve.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Invalid params"}},
            "Retrieve",
        )

        with pytest.raises(RetrievalServiceError) as exc_info:
            service.retrieve(sample_request)

        assert exc_info.value.error_type == "ValidationException"
        assert "Invalid params" in str(exc_info.value)

    def test_internal_server_error_is_retryable(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
        sample_request: RetrievalRequest,
    ) -> None:
        """Test InternalServerError is marked as retryable."""
        mock_client.retrieve.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Server error"}},
            "Retrieve",
        )

        with pytest.raises(RetrievalServiceError) as exc_info:
            service.retrieve(sample_request)

        assert exc_info.value.retryable is True


class TestRetrievalServiceHealthCheck:
    """Tests for RetrievalService.health_check method."""

    def test_health_check_success(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
    ) -> None:
        """Test successful health check."""
        mock_client.retrieve.return_value = {"retrievalResults": []}

        result = service.health_check()

        assert result is True
        mock_client.retrieve.assert_called_once()

    def test_health_check_failure(
        self,
        service: RetrievalService,
        mock_client: MagicMock,
    ) -> None:
        """Test failed health check."""
        mock_client.retrieve.side_effect = ClientError(
            {"Error": {"Code": "ServiceException", "Message": "Service unavailable"}},
            "Retrieve",
        )

        result = service.health_check()

        assert result is False
