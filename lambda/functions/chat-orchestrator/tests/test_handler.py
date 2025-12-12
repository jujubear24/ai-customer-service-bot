import json
import os
from unittest.mock import MagicMock, patch

import pytest
from aws_lambda_powertools.utilities.typing import LambdaContext

# Set env vars before importing handler to avoid initialization errors if strict
os.environ["RAG_FUNCTION_NAME"] = "test-rag"
os.environ["BEDROCK_FUNCTION_NAME"] = "test-bedrock"
os.environ["POWERTOOLS_METRICS_NAMESPACE"] = "TestNamespace"

from handler import lambda_handler
from models import ChatResponse


@pytest.fixture
def lambda_context():
    context = MagicMock(spec=LambdaContext)
    context.aws_request_id = "test-request-id"
    context.function_name = "test-function"
    context.memory_limit_in_mb = 128
    return context


@pytest.fixture
def mock_orchestrator():
    with patch("handler.orchestrator") as mock:
        yield mock


def test_handler_success(lambda_context, mock_orchestrator, valid_chat_request_data):
    # Setup Mock Response
    expected_response = ChatResponse.create(
        conversation_id="conv-123", response_text="Test response", model="test-model"
    )
    mock_orchestrator.process_request.return_value = expected_response

    # Create Event
    event = {"body": json.dumps(valid_chat_request_data)}

    # Execute
    response = lambda_handler(event, lambda_context)

    # Verify
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["conversation_id"] == "conv-123"
    assert body["response"] == "Test response"

    mock_orchestrator.process_request.assert_called_once()


def test_handler_invalid_json(lambda_context, mock_orchestrator):
    event = {"body": "{invalid-json"}

    response = lambda_handler(event, lambda_context)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Invalid JSON" in body["error"]
    mock_orchestrator.process_request.assert_not_called()


def test_handler_validation_error(lambda_context, mock_orchestrator):
    # Missing required 'message'
    event = {"body": json.dumps({"tenant_id": "t1"})}

    response = lambda_handler(event, lambda_context)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Validation Error" in body["error"]
    mock_orchestrator.process_request.assert_not_called()


def test_handler_empty_body(lambda_context, mock_orchestrator):
    event = {"body": None}

    response = lambda_handler(event, lambda_context)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Missing request body" in body["error"]


def test_handler_internal_error(lambda_context, mock_orchestrator, valid_chat_request_data):
    # Simulate service failure
    mock_orchestrator.process_request.side_effect = RuntimeError("Service crashed")

    event = {"body": json.dumps(valid_chat_request_data)}

    response = lambda_handler(event, lambda_context)

    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "Internal Server Error" in body["error"]
    assert "Service crashed" in body["message"]
