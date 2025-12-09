"""Pytest configuration and fixtures for RAG Retriever tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Add src directory to the path so tests can import modules
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

# Add shared layer to path
layer_dir = Path(__file__).parent.parent.parent.parent / "layers" / "common" / "python"
if layer_dir.exists():
    sys.path.insert(0, str(layer_dir))

# Set default environment variables for tests
os.environ.setdefault("KNOWLEDGE_BASE_ID", "test-kb-id")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("POWERTOOLS_SERVICE_NAME", "rag-retriever-test")
os.environ.setdefault("POWERTOOLS_METRICS_NAMESPACE", "test")
os.environ.setdefault("LOG_LEVEL", "DEBUG")


@pytest.fixture(scope="session", autouse=True)
def aws_credentials() -> None:
    """Mock AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
