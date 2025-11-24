# API Gateway Module

This module creates a REST API Gateway that exposes Lambda functions via HTTPS endpoints.

## Features

- **REST API Gateway**: Regional API Gateway deployment
- **Lambda Integration**: AWS_PROXY integration with Lambda functions
- **Request Validation**: JSON schema validation for incoming requests
- **CORS Support**: Configured for cross-origin requests
- **CloudWatch Logging**: Detailed access logs and execution logs
- **X-Ray Tracing**: Distributed tracing enabled
- **Throttling**: Rate limiting to protect backend services
- **Automatic Deployment**: Triggers on resource changes

## Usage

```hcl
module "api_gateway" {
  source = "../../modules/api_gateway"

  project_name = var.project_name
  environment  = var.environment

  # Lambda function details
  intent_classifier_function_name = module.lambda.intent_classifier_function_name
  intent_classifier_invoke_arn    = module.lambda.intent_classifier_invoke_arn

  # CloudWatch configuration
  log_retention_days      = 7
  cloudwatch_kms_key_arn  = module.observability.cloudwatch_kms_key_arn
  api_logging_level       = "INFO"

  # Throttling
  throttle_burst_limit = 100
  throttle_rate_limit  = 50

  common_tags = var.common_tags
}
```

## Endpoints

### POST /classify-intent

Classifies user intent from a message.

**Request:**

```json
{
  "message": "I need to speak to a manager",
  "conversation_history": [  // optional
    {
      "role": "user",
      "content": "Previous message"
    }
  ]
}
```

**Response:**

```json
{
  "message": "Intent classified successfully",
  "classification": {
    "intent": "escalation",
    "confidence": 0.9,
    "requires_context": true,
    "entities": {
      "sentiment": "negative"
    }
  },
  "correlation_id": "abc-123"
}
```

**Request Validation:**

- `message`: Required, string, 1-2000 characters
- `conversation_history`: Optional, array, max 50 items

## CORS Configuration

CORS is enabled with the following settings:

- **Allowed Origins**: `*` (configure to restrict in production)
- **Allowed Methods**: `POST, OPTIONS`
- **Allowed Headers**: `Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token`

## Throttling

Default throttling limits (can be customized):

- **Burst Limit**: 100 requests
- **Rate Limit**: 50 requests per second

These limits prevent abuse and protect your Lambda functions from being overwhelmed.

## Logging

### Access Logs

Access logs are written to CloudWatch Logs and include:

- Request ID and timestamp
- Source IP and caller identity
- HTTP method and resource path
- Response status and length
- Error messages (if any)

### Execution Logs

Method-level execution logs include:

- Request/response details (dev environment only)
- Integration latency
- Lambda execution details

### View Logs

```bash
# Access logs
aws logs tail /aws/apigateway/<project-name>-<environment> --follow

# Lambda execution logs (from API Gateway calls)
aws logs tail /aws/lambda/<function-name> --follow
```

## Testing the API

### Using curl

```bash
# Get the API endpoint
ENDPOINT=$(terraform output -raw classify_intent_endpoint)

# Test the endpoint
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I need to speak to a manager"
  }'
```

### Using HTTPie

```bash
http POST $ENDPOINT message="What are your business hours?"
```

### Using Postman

1. Create a new POST request
2. URL: `<api_endpoint>/classify-intent`
3. Headers: `Content-Type: application/json`
4. Body (raw JSON):

   ```json
   {
     "message": "My order #ABC123 is delayed"
   }
   ```

## Security Considerations

### Current Setup (Development)

- ✅ HTTPS only
- ✅ Request validation
- ✅ Throttling enabled
- ✅ CloudWatch logging
- ⚠️ No authentication (API is public)
- ⚠️ CORS allows all origins

### Production Recommendations

1. **Add Authentication**: Use API Keys, Cognito, or Lambda authorizers
2. **Restrict CORS**: Limit allowed origins to your domain
3. **WAF Integration**: Add AWS WAF for additional protection
4. **Usage Plans**: Implement API keys with usage quotas
5. **Private API**: Consider VPC endpoints for internal APIs

## Monitoring

The module creates CloudWatch alarms for:

- 4XX errors (client errors)
- 5XX errors (server errors)
- Latency thresholds
- Throttling events

View metrics in the CloudWatch console or with:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Count \
  --dimensions Name=ApiName,Value=<project-name>-api-<environment> \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum
```

## Adding New Endpoints

To add a new endpoint:

1. Create the resource:

   ```hcl
   resource "aws_api_gateway_resource" "new_endpoint" {
     rest_api_id = aws_api_gateway_rest_api.main.id
     parent_id   = aws_api_gateway_rest_api.main.root_resource_id
     path_part   = "new-endpoint"
   }
   ```

2. Create the method and integration (similar to classify-intent)
3. Add Lambda permission
4. Update the deployment trigger
5. Add CORS if needed

## Outputs

- `api_endpoint`: Base URL of the API
- `classify_intent_endpoint`: Full URL for /classify-intent
- `api_id`: API Gateway ID (for reference)
- `stage_name`: Deployed stage name

<!-- BEGINNING OF PRE-COMMIT-Terraform DOCS HOOK -->
<!-- END OF PRE-COMMIT-Terraform DOCS HOOK -->
