"""Pytest configuration and shared fixtures."""

import os
from unittest.mock import patch

import pytest

# Set environment variables BEFORE any imports
os.environ["POWERTOOLS_SERVICE_NAME"] = "intent-classifier"
os.environ["POWERTOOLS_METRICS_NAMESPACE"] = "CustomerServiceBot"
os.environ["POWERTOOLS_LOG_LEVEL"] = "INFO"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["ENVIRONMENT"] = "test"
os.environ["AWS_EXECUTION_ENV"] = "AWS_Lambda_python3.12"  # Trick Powertools into Lambda mode


@pytest.fixture(autouse=True)
def mock_lambda_context() -> None:
    """Mock Lambda context for Powertools."""
    # Powertools checks for Lambda environment
    with patch.dict(
        os.environ,
        {
            "AWS_LAMBDA_FUNCTION_NAME": "intent-classifier",
            "AWS_LAMBDA_FUNCTION_VERSION": "$LATEST",
            "_X_AMZN_TRACE_ID": "Root=1-5759e988-bd862e3fe1be46a994272793;Parent=53995c3f42cd8ad8;Sampled=1",
        },
    ):
        yield


@pytest.fixture(autouse=True)
def reset_powertools() -> None:
    """Reset Powertools state between tests."""
    # Import here to ensure env vars are set first
    from shared.logger import logger
    from shared.metrics import metrics

    # Clear metrics
    if hasattr(metrics, "_metrics"):
        metrics._metrics.clear()
    if hasattr(metrics, "_dimensions"):
        metrics._dimensions.clear()

    # Reset logger context
    if hasattr(logger, "_default_log_keys"):
        logger._default_log_keys.clear()

    yield

    # Cleanup after test
    if hasattr(metrics, "_metrics"):
        metrics._metrics.clear()
    if hasattr(metrics, "_dimensions"):
        metrics._dimensions.clear()
