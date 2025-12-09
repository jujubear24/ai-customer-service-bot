"""
RAG Retrieval Service for Amazon Bedrock Knowledge Base.

Handles document retrieval from Bedrock Knowledge Base with:
- Semantic search
- Relevance score filtering
- Source attribution
- Retry logic for transient failures
"""

from __future__ import annotations

import time
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from botocore.config import Config
from botocore.exceptions import ClientError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from models import (
    RetrievalRequest,
    RetrievalResponse,
    RetrievalType,
    RetrievedDocument,
)

logger = Logger()


class RetrievalServiceError(Exception):
    """Base exception for retrieval service errors."""

    def __init__(
        self,
        message: str,
        error_type: str = "RETRIEVAL_ERROR",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable
        self.details = details or {}


class KnowledgeBaseNotFoundError(RetrievalServiceError):
    """Raised when knowledge base doesn't exist."""

    def __init__(self, knowledge_base_id: str) -> None:
        super().__init__(
            message=f"Knowledge base not found: {knowledge_base_id}",
            error_type="KNOWLEDGE_BASE_NOT_FOUND",
            retryable=False,
        )


class ThrottlingError(RetrievalServiceError):
    """Raised when API is throttled."""

    def __init__(self, message: str = "Request throttled") -> None:
        super().__init__(
            message=message,
            error_type="THROTTLING",
            retryable=True,
        )


class RetrievalService:
    """
    Service for retrieving documents from Bedrock Knowledge Base.

    Handles:
    - Bedrock Agent Runtime API calls
    - Response parsing and formatting
    - Score-based filtering
    - Retry logic for transient failures
    """

    def __init__(
        self,
        knowledge_base_id: str,
        region: str | None = None,
        client: Any | None = None,
    ) -> None:
        """
        Initialize the retrieval service.

        Args:
            knowledge_base_id: ID of the Bedrock Knowledge Base
            region: AWS region (defaults to boto3 default)
            client: Optional pre-configured client for testing
        """
        self.knowledge_base_id = knowledge_base_id
        self.region = region

        if client is not None:
            self._client: Any = client
        else:
            config = Config(
                retries={"max_attempts": 3, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=30,
            )
            self._client = boto3.client(
                "bedrock-agent-runtime",
                region_name=region,
                config=config,
            )

    @retry(
        retry=retry_if_exception_type(ThrottlingError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        """
        Retrieve relevant documents from the knowledge base.

        Args:
            request: Retrieval request parameters

        Returns:
            RetrievalResponse with matching documents

        Raises:
            KnowledgeBaseNotFoundError: If KB doesn't exist
            ThrottlingError: If request is throttled (will retry)
            RetrievalServiceError: For other errors
        """
        start_time = time.perf_counter()

        try:
            # Build retrieval configuration
            retrieval_config = self._build_retrieval_config(request)

            logger.info(
                "Retrieving from knowledge base",
                knowledge_base_id=self.knowledge_base_id,
                query_length=len(request.query),
                top_k=request.top_k,
                min_score=request.min_score,
            )

            # Call Bedrock Agent Runtime API
            response = self._client.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": request.query},
                retrievalConfiguration=retrieval_config,
            )

            # Parse response
            documents = self._parse_retrieval_results(
                response.get("retrievalResults", []),
                min_score=request.min_score,
                include_metadata=request.include_metadata,
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "Retrieval completed",
                documents_found=len(response.get("retrievalResults", [])),
                documents_returned=len(documents),
                elapsed_ms=round(elapsed_ms, 2),
            )

            return RetrievalResponse(
                documents=documents,
                query=request.query,
                total_found=len(response.get("retrievalResults", [])),
                retrieval_time_ms=elapsed_ms,
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            logger.error(
                "Bedrock API error",
                error_code=error_code,
                error_message=error_message,
            )

            if error_code == "ResourceNotFoundException":
                raise KnowledgeBaseNotFoundError(self.knowledge_base_id) from e
            elif error_code in ("ThrottlingException", "TooManyRequestsException"):
                raise ThrottlingError(error_message) from e
            else:
                raise RetrievalServiceError(
                    message=f"Bedrock API error: {error_message}",
                    error_type=error_code,
                    retryable=error_code in ("ServiceException", "InternalServerError"),
                    details={"error_code": error_code},
                ) from e

    def _build_retrieval_config(self, request: RetrievalRequest) -> dict[str, Any]:
        """Build the retrieval configuration for the API call."""
        config: dict[str, Any] = {
            "vectorSearchConfiguration": {
                "numberOfResults": request.top_k,
            }
        }

        # Add hybrid search if requested
        if request.retrieval_type == RetrievalType.HYBRID:
            config["vectorSearchConfiguration"]["overrideSearchType"] = "HYBRID"

        return config

    def _parse_retrieval_results(
        self,
        results: list[dict[str, Any]],
        min_score: float,
        include_metadata: bool,
    ) -> list[RetrievedDocument]:
        """
        Parse and filter retrieval results from the API response.

        Args:
            results: Raw results from Bedrock API
            min_score: Minimum score threshold
            include_metadata: Whether to include metadata

        Returns:
            List of RetrievedDocument objects above the score threshold
        """
        documents: list[RetrievedDocument] = []

        for result in results:
            score = result.get("score", 0.0)

            # Filter by minimum score
            if score < min_score:
                logger.debug(
                    "Skipping low-score result",
                    score=score,
                    min_score=min_score,
                )
                continue

            # Extract content
            content = result.get("content", {}).get("text", "")
            if not content:
                continue

            # Extract location/source info
            location = result.get("location", {})
            source_uri = None
            source_name = None

            if location.get("type") == "S3":
                s3_location = location.get("s3Location", {})
                source_uri = s3_location.get("uri")
                # Extract filename from S3 URI
                if source_uri:
                    source_name = source_uri.split("/")[-1]

            # Extract metadata if requested
            metadata = None
            if include_metadata:
                metadata = result.get("metadata", {})

            documents.append(
                RetrievedDocument(
                    content=content,
                    score=score,
                    source_uri=source_uri,
                    source_name=source_name,
                    metadata=metadata,
                )
            )

        # Sort by score descending
        documents.sort(key=lambda d: d.score, reverse=True)

        return documents

    def health_check(self) -> bool:
        """
        Perform a health check on the knowledge base.

        Returns:
            True if the knowledge base is accessible
        """
        try:
            # Perform a minimal retrieval to check connectivity
            self._client.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": "health check"},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {"numberOfResults": 1}
                },
            )
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.warning(
                "Health check failed",
                error_code=error_code,
            )
            return False
