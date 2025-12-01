# ADR-009: Bedrock Integration Architecture

**Date:** 2025-01-XX (Update with actual date)
**Status:** Accepted
**Deciders:** Senior Cloud Architect, Development Team

---

## Context

The AI Customer Service Bot requires integration with Amazon Bedrock to generate AI-powered responses for customer inquiries.
The Bedrock Handler Lambda will receive conversation context and produce natural language responses using Claude 3.5 Sonnet.

**Key requirements driving the design:**

1. **Stateless Execution**: Handler must integrate cleanly with future Step Functions orchestration (Phase 4)
2. **Cost Efficiency**: Select model with optimal price/performance ratio for customer service use cases
3. **Reliability**: Graceful handling of throttling, timeouts, and service errors
4. **Prompt Management**: Maintainable, version-controlled prompt construction
5. **Observability**: Token usage tracking for cost attribution and capacity planning
6. **Security**: Least-privilege IAM permissions for Bedrock model access

---

## Decision

### Model Selection

Adopt **Claude 3.5 Sonnet v2** (`anthropic.claude-3-5-sonnet-20241022-v2:0`) as the foundation model.

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Rationale |
|-------|----------------------|------------------------|-----------|
| Claude 3.5 Sonnet v2 | $3.00 | $15.00 | Best price/performance for customer service |
| Claude 3.5 Haiku | $0.80 | $4.00 | Faster but less capable for nuanced queries |
| Claude 3 Opus | $15.00 | $75.00 | Overkill; unnecessary cost for this use case |

### Stateless Handler Pattern

The Bedrock Handler will be **stateless** — it receives context, invokes Bedrock, and returns the response without persisting to DynamoDB.

```bash
┌─────────────────────────────────────────────────────────────────┐
│                    Current Flow (Phase 2)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   API Gateway → Intent Classifier → Context Builder             │
│                                          ↓                      │
│                                   Bedrock Handler               │
│                                          ↓                      │
│                                   Return Response               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Future Flow (Phase 4)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Step Functions Orchestrator                                   │
│        ├── Intent Classifier                                    │
│        ├── Context Builder                                      │
│        ├── RAG Retriever (Phase 2.2)                            │
│        ├── Bedrock Handler (stateless) ←── This ADR             │
│        ├── Response Validator (Phase 3)                         │
│        ├── Persist to DynamoDB ←── Separate step                │
│        └── Return Response                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Prompt Engineering Framework

Adopt **Python f-strings** with a structured prompt builder module. Prompts are organized as Python constants with helper functions for composition.

```bash
lambda/functions/bedrock-handler/
├── src/
│   ├── handler.py
│   ├── bedrock_client.py
│   └── prompt_builder.py
└── prompts/
    ├── __init__.py
    ├── system.py           # System prompt constants
    ├── guidelines.py       # Customer service guidelines
    └── safety.py           # Content safety rules
```

**Prompt Composition Example:**

```python
# prompts/system.py
BASE_PROMPT = """You are a helpful customer service assistant for {company_name}.
Be concise, friendly, and professional."""

# prompt_builder.py
def build_system_prompt(
    company_name: str,
    intent: str | None = None,
    rag_context: list[str] | None = None,
) -> str:
    """Build the complete system prompt."""
    parts = [
        BASE_PROMPT.format(company_name=company_name),
        CUSTOMER_SERVICE_GUIDELINES,
        SAFETY_RULES,
    ]

    if rag_context:
        parts.append(format_rag_context(rag_context))

    return "\n\n".join(parts)
```

**Rationale for f-strings over Jinja2:**

- Zero external dependencies
- Full IDE support (autocomplete, type hints, refactoring)
- Python conditionals and loops handle all current requirements including RAG context injection
- Easier to test — prompt builder is just Python functions
- Jinja2 can be adopted later if non-engineers need to edit prompts directly

### Error Handling Strategy

Implement **exponential backoff with jitter** using the `tenacity` library.

| Error Type | Retry? | Strategy |
|------------|--------|----------|
| `ThrottlingException` | Yes | Exponential backoff (1s, 2s, 4s) + jitter |
| `ModelTimeoutException` | Yes | Up to 2 retries |
| `ValidationException` | No | Fail fast, log error |
| `AccessDeniedException` | No | Fail fast, alert |
| `ServiceUnavailableException` | Yes | Exponential backoff |

### Request/Response Schema

**BedrockRequest (Input):**

```python
class BedrockRequest(BaseModel):
    conversation_id: str
    user_message: str
    conversation_context: ConversationContext
    intent: str | None = None
    entities: dict[str, str] | None = None
    rag_context: list[str] | None = None  # Phase 2.2
    max_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
```

**BedrockResponse (Output):**

```python
class BedrockResponse(BaseModel):
    conversation_id: str
    response_text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    stop_reason: str
    timestamp: str
```

### Observability

CloudWatch metrics emitted by the handler:

| Metric | Unit | Description |
|--------|------|-------------|
| `BedrockInvocations` | Count | Total model invocations |
| `BedrockLatency` | Milliseconds | End-to-end invocation latency |
| `BedrockInputTokens` | Count | Input tokens consumed |
| `BedrockOutputTokens` | Count | Output tokens generated |
| `BedrockErrors` | Count | Errors by type (dimension) |
| `BedrockThrottles` | Count | Throttling events |

### IAM Permissions

Least-privilege policy restricting access to the specific model:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInvokeModel",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
      ]
    }
  ]
}
```

---

## Consequences

### Positive

- **Decoupled Architecture**: Bedrock Handler can be tested, deployed, and scaled independently of storage concerns
- **Cost Visibility**: Token metrics enable accurate cost attribution per conversation
- **Zero Prompt Dependencies**: Python f-strings require no external libraries
- **Full IDE Support**: Type hints, autocomplete, and refactoring work seamlessly with prompt code
- **Future-Ready**: Stateless design integrates seamlessly with Step Functions orchestration
- **Reliability**: Retry logic handles transient Bedrock failures gracefully

### Negative

- **Prompts in Code**: Prompt changes require code deployment (acceptable for current team structure)
- **No Immediate Persistence**: Caller is responsible for storing responses; failure after Bedrock success loses the response
- **Additional Dependency**: Requires `tenacity` package in Lambda layer for retry logic

### Neutral

- **Model Lock-in**: Tightly coupled to Claude message format; mitigated by abstracting via `bedrock_client.py`
- **Future Flexibility**: If non-engineers need to edit prompts, can migrate to Jinja2 or AWS Bedrock Prompt Management

---

## Alternatives Considered

### Option 1: Stateful Handler (Write to DynamoDB)

Handler persists AI responses directly to DynamoDB after generation.

**Why not chosen:** Violates single responsibility principle. Creates partial state issues if Bedrock succeeds but DynamoDB fails.
Step Functions (Phase 4) provides better orchestration with per-step retry/catch logic. Stateless handlers are more testable and reusable.

### Option 2: Jinja2 Templates

Use Jinja2 templates stored as `.j2` files for prompt construction.

**Why not chosen:** Adds external dependency without clear benefit for current requirements.
Python f-strings handle variable substitution, conditionals, and loops (for RAG context) adequately.
Jinja2's value emerges when non-engineers need to edit prompts or when managing 10+ prompt variants — neither applies currently.
Can be adopted later if requirements change.

### Option 3: Claude 3.5 Haiku for Lower Cost

Use Haiku ($0.80/$4.00 per 1M tokens) instead of Sonnet ($3.00/$15.00).

**Why not chosen:** Customer service requires nuanced understanding of context, intent, and tone.
Haiku's reduced capability increases risk of poor responses requiring escalation. Sonnet provides better first-contact resolution,
which offsets the higher per-token cost with fewer escalations.

### Option 4: AWS Bedrock Prompt Management

Store and version prompts in AWS Bedrock console using Prompt Management feature.

**Why not chosen:** Adds AWS console dependency for prompt changes. Harder to test locally and integrate with CI/CD.
Better suited for teams where non-engineers manage prompts via UI. Can be evaluated for future phases if team structure changes.

### Option 5: No Retry Logic (Fail Fast)

Let all Bedrock errors propagate immediately without retries.

**Why not chosen:** Bedrock throttling is common under load. Transient errors would cause unnecessary customer-facing failures.
Exponential backoff with 3 retries handles most transient issues transparently. Step Functions can add additional retry layers in Phase 4.

---

## References

- [Amazon Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
- [Anthropic Claude Messages API](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages.html)
- [ADR-008: DynamoDB Schema Design](./008-dynamodb-schema-design.md)
- Implementation: `lambda/functions/bedrock-handler/src/handler.py`
- Infrastructure: `terraform/modules/bedrock/main.tf`
