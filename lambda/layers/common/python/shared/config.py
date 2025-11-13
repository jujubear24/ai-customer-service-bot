"""Configuration management."""

import os
from functools import lru_cache
from typing import Any


class Config:
    """Application configuration from environment variables."""

    def __init__(self) -> None:
        """Initialize configuration from environment."""
        self.environment = os.getenv("ENVIRONMENT", "dev")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.json_logging = os.getenv("JSON_LOGGING", "true").lower() == "true"

        # Powertools configuration
        self.service_name = os.getenv("POWERTOOLS_SERVICE_NAME", "customer-service-bot")

        # Bedrock configuration
        self.bedrock_model_id = os.getenv(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
        )
        self.bedrock_max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", "1000"))
        self.bedrock_temperature = float(os.getenv("BEDROCK_TEMPERATURE", "0.7"))

        # DynamoDB configuration
        self.dynamodb_table = os.getenv("DYNAMODB_TABLE", "")

        # SQS configuration
        self.escalation_queue_url = os.getenv("ESCALATION_QUEUE_URL", "")

        # CloudWatch metrics
        self.metrics_namespace = os.getenv("METRICS_NAMESPACE", "CustomerServiceBot")

        # Redis configuration
        self.redis_endpoint = os.getenv("REDIS_ENDPOINT", "")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_auth_token = os.getenv("REDIS_AUTH_TOKEN", "")

    @classmethod
    @lru_cache(maxsize=1)
    def from_env(cls) -> "Config":
        """
        Create configuration from environment variables.

        Returns:
            Cached configuration instance
        """
        return cls()

    def to_dict(self) -> dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Configuration as dictionary (excluding sensitive values)
        """
        return {
            "environment": self.environment,
            "log_level": self.log_level,
            "region": self.region,
            "json_logging": self.json_logging,
            "service_name": self.service_name,
        }
