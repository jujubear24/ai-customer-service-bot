# ADR-007: API Gateway Integration and Request Validation

**Date:** 2025-11-23
**Status:** Accepted
**Deciders:** Senior Cloud Architect, Development Team

---

## Context

We need to expose the core Intent Classification logic through a public REST API endpoint while maintaining foundational security, validation, and observability for a public-facing service.
The design must balance simplicity for initial development with a path toward production-hardening.

---

## Decision

### Integration Type

Use **AWS_PROXY** integration for the `/classify-intent` API Gateway resource. This approach forwards the entire HTTP request to the Lambda function without requiring custom transformation logic.
It simplifies the integration and offloads JSON parsing and validation to the Lambda function.

### Request Validation

Deploy an `aws_api_gateway_request_validator` to enforce the structure and presence of required request body parameters (e.g., `message`).
This prevents unnecessary Lambda invocations—including cold starts—from invalid client requests and reduces risk by failing early at the edge.

### CORS

Configure a dedicated `OPTIONS` method using **MOCK** integration to support CORS preflight requests. An initial wildcard (`*`) origin is permitted for development purposes;
however, this must be restricted to specific domains prior to production deployment.

### Observability

Enable **X-Ray tracing** and **CloudWatch access logs** on the API Gateway stage. Logging uses an IAM role defined at the account level and managed by Terraform to ensure consistent, centralized observability.

---

## Consequences

### Positive

- **Security (Early Fail):** Request validation limits the API's attack surface by blocking malformed payloads before Lambda execution.
- **Simplicity:** AWS_PROXY integration avoids the overhead of mapping templates, keeping the API Gateway configuration minimal.
- **Tracing:** Provides full tracing coverage from the client, through API Gateway, and into Lambda for debugging and monitoring.

### Negative

- **Authentication:** The API is currently configured with no authorization (`authorization = "NONE"`).
A follow-up task (Phase 6/7) is required to integrate Cognito or Lambda authorizers before advancing beyond the development stage.

### Neutral

- **Resource Count:** Enabling request validation, CORS support, and model definitions increases the number of Terraform resources.
This introduces some complexity compared to a pure proxy-only approach but provides clearer validation and frontend compatibility.

---

## Alternatives Considered

### Option 1: AWS Integration with VTL Mapping

**Why not chosen:** Using Velocity Template Language (VTL) mapping templates increases brittleness, makes transformations harder to debug, and introduces additional operational overhead.
AWS_PROXY integration shifts all request-handling logic into the Python Lambda function, which is easier to test, maintain, and evolve over time.
