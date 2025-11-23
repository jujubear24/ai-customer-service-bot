# Lambda Module

This module packages and deploys Lambda functions and shared layers for the AI Customer Service Bot.

## Features

- **Shared Layer**: Common utilities, Pydantic models, and AWS Powertools configuration
- **Intent Classifier**: Rule-based intent classification Lambda function
- **IAM Roles**: Least-privilege IAM roles for each function
- **Observability**: CloudWatch Logs, X-Ray tracing, and custom metrics
- **Packaging**: Automatic ZIP file creation with proper exclusions

## Building the Layer

Before deploying, you must build the Lambda layer with dependencies:

```bash
# From project root
./scripts/build-lambda-layer.sh
```

This script:

1. Copies the shared code from `lambda/layers/common/python/shared`
2. Installs Python dependencies (boto3, AWS-lambda-powertools, pydantic, redis)
3. Creates a ZIP file at `terraform/modules/lambda/builds/shared-layer.zip`
4. Cleans up build artifacts

The layer must be rebuilt whenever:

- Dependencies change in `lambda/layers/common/pyproject.toml`
- Shared code is modified

## Usage

```hcl
module "lambda" {
  source = "../../modules/lambda"

  project_name      = var.project_name
  environment       = var.environment
  log_level         = "INFO"
  metrics_namespace = "CustomerServiceBot"

  common_tags = var.common_tags
}
```

## Packaging Strategy

### Shared Layer Structure

```bash
shared-layer.zip
└── python/
    └── shared/
        ├── __init__.py
        ├── config.py
        ├── logger.py
        ├── metrics.py
        ├── types.py
        ├── utils.py
        ├── exceptions.py
        ├── cache_client.py
        └── tracing.py
```

### Function Package Structure

```bash
intent-classifier.zip
└── handler.py
└── classifier.py
```

The function imports from the shared layer using `from shared import ...`

## IAM Permissions

Each Lambda function has:

- **Basic Execution**: CloudWatch Logs creation and writing
- **X-Ray Tracing**: Trace segment publishing
- **CloudWatch Metrics**: Custom metrics publishing (scoped to namespace)
- **Function-specific**: Additional permissions as needed (e.g., DynamoDB, SQS)

## Environment Variables

All functions receive:

- `ENVIRONMENT`: Deployment environment (dev, staging, prod)
- `POWERTOOLS_SERVICE_NAME`: Service name for logging/tracing
- `POWERTOOLS_METRICS_NAMESPACE`: CloudWatch metrics namespace
- `POWERTOOLS_LOG_LEVEL`: Logging level
- `POWERTOOLS_TRACER_CAPTURE_RESPONSE`: Enable response capture
- `POWERTOOLS_TRACER_CAPTURE_ERROR`: Enable error capture

## Adding New Functions

To add a new Lambda function:

1. Create the function directory under `lambda/functions/`
2. Add packaging in `main.tf`:

    ```hcl
    data "archive_file" "new_function" {
        type        = "zip"
        source_dir  = "${path.module}/../../../lambda/functions/new-function/src"
        output_path = "${path.module}/builds/new-function.zip"
    }
    ```

3. Create IAM role and policies
4. Deploy with `aws_lambda_function` resource
5. Add outputs for the new function

## Build Directory

The module creates a `builds/` directory for ZIP files:

- `builds/shared-layer.zip`
- `builds/intent-classifier.zip`

These are automatically created by Terraform and should be gitignored.

## Testing

Functions should be tested locally before deployment:

```bash
cd lambda/functions/intent-classifier
uv run pytest -v
```

<!-- BEGINNING OF PRE-COMMIT-Terraform DOCS HOOK -->

<!-- END OF PRE-COMMIT-Terraform DOCS HOOK -->
