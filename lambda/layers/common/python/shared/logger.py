"""Logging configuration using AWS Lambda Powertools."""

from aws_lambda_powertools import Logger, Metrics, Tracer

# Initialize Powertools resources
# Service name will be automatically captured from POWERTOOLS_SERVICE_NAME env var
logger = Logger(utc=True)
tracer = Tracer()
metrics = Metrics()


def setup_logger(name: str | None = None, level: str = "INFO", json_format: bool = False) -> Logger:
    """
    Return the configured logger instance.
    Maintained for compatibility with existing handlers.

    Args:
        name: Logger name (ignored, uses Powertools logger)
        level: Log level (controlled via POWERTOOLS_LOG_LEVEL env var)
        json_format: Format flag (Powertools always uses JSON)

    Returns:
        Configured Logger instance
    """
    return logger


def get_logger() -> Logger:
    """Return the configured logger instance."""
    return logger


def get_tracer() -> Tracer:
    """Return the configured tracer instance."""
    return tracer


def get_metrics() -> Metrics:
    """Return the configured metrics instance."""
    return metrics
