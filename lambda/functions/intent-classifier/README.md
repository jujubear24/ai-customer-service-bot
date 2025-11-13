# intent-classifier

## Description

Lambda function for intent-classifier.

## Environment Variables

### Required

- `ENVIRONMENT`: Deployment environment (dev, staging, prod)
- `AWS_REGION`: AWS region
- `POWERTOOLS_SERVICE_NAME`: Service name for AWS Lambda Powertools

### Optional

- `POWERTOOLS_LOG_LEVEL`: Logging level (INFO, DEBUG, WARNING, ERROR)
- `POWERTOOLS_METRICS_NAMESPACE`: CloudWatch metrics namespace
- `POWERTOOLS_TRACER_CAPTURE_RESPONSE`: Enable response capture in traces (true/false)
- `POWERTOOLS_TRACER_CAPTURE_ERROR": Enable error capture in traces (true/false)

## Local Development

### Setup

```bash
# From the function directory
uv sync

# Or from project root
cd lambda/functions/intent-classifier
uv sync
```

### Testing

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/test_handler.py -v

# Run with type checking
uv run mypy src/

# Run linting
uv run ruff check src/
```

### Code Quality

```bash
# Format code
uv run ruff format src/ tests/

# Check types
uv run mypy src/

# Run all checks
uv run pytest && uv run mypy src/ && uv run ruff check src/
```

## Architecture Decision Records (ADRs)

See `docs/adr/` for architectural decisions related to this function.

## Deployment

This function is deployed via Terraform. See `terraform/modules/` for infrastructure configuration.

## Dependencies

- **Shared layer**: `lambda/layers/common/python/shared`
- **AWS Lambda Powertools**: Logging, tracing, and metrics
- **Pydantic**: Data validation and settings management

## Monitoring

- **CloudWatch Logs**: `/aws/lambda/intent-classifier`
- **X-Ray Traces**: View in AWS X-Ray console
- **Metrics**: Custom metrics in CloudWatch under configured namespace

## Troubleshooting

### Common Issues

1. **Cold start latency**: Consider provisioned concurrency for production
2. **Timeout errors**: Increase timeout setting in Terraform
3. **Memory errors**: Increase memory allocation in Terraform

### Debug Mode

Enable debug logging:

```bash
export POWERTOOLS_LOG_LEVEL=DEBUG
```
