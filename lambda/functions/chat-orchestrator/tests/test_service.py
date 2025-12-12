import json
from unittest.mock import Mock

import pytest

# Absolute import as required by pytest path configuration
from models import ChatRequest, RAGOptions, SourceDocument
from service import BedrockHandlerClient, ChatOrchestrator, RAGRetrieverClient


@pytest.fixture
def mock_lambda_client():
    return Mock()


@pytest.fixture
def rag_client(mock_lambda_client):
    return RAGRetrieverClient("rag-fn", mock_lambda_client)


@pytest.fixture
def bedrock_client(mock_lambda_client):
    return BedrockHandlerClient("bedrock-fn", mock_lambda_client)


@pytest.fixture
def orchestrator(rag_client, bedrock_client):
    return ChatOrchestrator(rag_client, bedrock_client)


class TestRAGRetrieverClient:
    def test_retrieve_success(self, rag_client, mock_lambda_client):
        # Mock Response
        mock_payload = {
            "results": [
                {
                    "name": "Doc 1",
                    "content": "Content 1",
                    "source": "http://source1",
                    "score": 0.9,
                    "metadata": {"type": "faq"},
                }
            ]
        }
        mock_response = {"Payload": Mock(read=lambda: json.dumps(mock_payload).encode("utf-8"))}
        mock_lambda_client.invoke.return_value = mock_response

        options = RAGOptions()
        docs = rag_client.retrieve("query", "tenant", options)

        assert len(docs) == 1
        assert docs[0].content == "Content 1"
        assert docs[0].name == "Doc 1"

        # Verify call arguments
        call_args = mock_lambda_client.invoke.call_args[1]
        assert call_args["FunctionName"] == "rag-fn"
        payload = json.loads(call_args["Payload"])
        assert payload["query"] == "query"

    def test_retrieve_failure_non_fatal(self, rag_client, mock_lambda_client):
        # Simulate an exception (e.g., timeout)
        mock_lambda_client.invoke.side_effect = Exception("Lambda failed")

        docs = rag_client.retrieve("query", "tenant", RAGOptions())

        # Should return empty list, not raise
        assert docs == []

    def test_retrieve_parsing_error(self, rag_client, mock_lambda_client):
        # Result missing required fields
        mock_payload = {"results": [{"invalid": "data"}]}
        mock_response = {"Payload": Mock(read=lambda: json.dumps(mock_payload).encode("utf-8"))}
        mock_lambda_client.invoke.return_value = mock_response

        docs = rag_client.retrieve("query", "tenant", RAGOptions())

        # Should handle parsing error gracefully for that item
        assert len(docs) == 0


class TestBedrockHandlerClient:
    def test_generate_success(self, bedrock_client, mock_lambda_client):
        mock_payload = {"response": "Answer", "model": "haiku", "conversation_id": "cid"}
        mock_response = {"Payload": Mock(read=lambda: json.dumps(mock_payload).encode("utf-8"))}
        mock_lambda_client.invoke.return_value = mock_response

        result = bedrock_client.generate_response("hi", [], "cid", "tenant")

        assert result["response"] == "Answer"

    def test_generate_failure_raises(self, bedrock_client, mock_lambda_client):
        # Simulate functional error payload
        mock_payload = {"errorMessage": "AI broke"}
        mock_response = {"Payload": Mock(read=lambda: json.dumps(mock_payload).encode("utf-8"))}
        mock_lambda_client.invoke.return_value = mock_response

        with pytest.raises(RuntimeError) as exc:
            bedrock_client.generate_response("hi", [], "cid", "tenant")
        assert "AI broke" in str(exc.value)


class TestChatOrchestrator:
    def test_process_request_flow(self, orchestrator, rag_client, bedrock_client):
        # Setup Request
        request = ChatRequest(message="Help", tenant_id="t1", use_rag=True)

        # Mock RAG return (mocking the method on the instance)
        rag_doc = SourceDocument(
            name="Doc1", content="Context info", source="src", score=0.8, metadata={}
        )
        rag_client.retrieve = Mock(return_value=[rag_doc])

        # Mock Bedrock return
        bedrock_client.generate_response = Mock(
            return_value={
                "response": "Here is help based on Context info",
                "model": "claude",
                "conversation_id": "conv-new",
            }
        )

        # Execute
        response = orchestrator.process_request(request)

        # Assertions
        assert response.response == "Here is help based on Context info"
        assert response.sources[0].content == "Context info"
        assert response.metadata.rag_documents_used == 1

        # Verify flow
        rag_client.retrieve.assert_called_once()
        bedrock_client.generate_response.assert_called_once()

        # Verify context was passed to bedrock
        call_args = bedrock_client.generate_response.call_args
        assert call_args.kwargs["context"] == ["Context info"]

    def test_process_request_skip_rag(self, orchestrator, rag_client, bedrock_client):
        request = ChatRequest(message="Hi", tenant_id="t1", use_rag=False)

        # Explicitly mock retrieve so we can call assert_not_called
        rag_client.retrieve = Mock()

        bedrock_client.generate_response = Mock(
            return_value={"response": "Hello", "model": "claude"}
        )

        response = orchestrator.process_request(request)

        # Now this will work because retrieve is a Mock object
        rag_client.retrieve.assert_not_called()
        assert response.metadata.rag_skipped is True
        assert len(response.sources) == 0
