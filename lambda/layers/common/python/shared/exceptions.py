"""Custom exception classes."""


class LambdaError(Exception):
    """Base exception for Lambda functions."""

    pass


class ValidationError(LambdaError):
    """Raised when input validation fails."""

    pass


class ConfigurationError(LambdaError):
    """Raised when configuration is invalid."""

    pass


class ExternalServiceError(LambdaError):
    """Raised when external service call fails."""

    pass


class BedrockError(ExternalServiceError):
    """Raised when Bedrock API call fails."""

    pass


class DynamoDBError(ExternalServiceError):
    """Raised when DynamoDB operation fails."""

    pass


class CacheError(ExternalServiceError):
    """Raised when cache operation fails."""

    pass
