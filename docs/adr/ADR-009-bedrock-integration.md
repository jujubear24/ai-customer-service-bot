# ADR-009: Bedrock Integration Architecture

**Date:** 2025-11-30
**Status:** Accepted
**Deciders:** Senior Cloud Architect, Development Team

---

## Context

The AI Customer Service Bot requires integration with Amazon Bedrock to generate AI-powered responses for customer inquiries.
The Bedrock Handler Lambda will receive conversation context and produce natural language responses using Claude Haiku 4.5.

**Key requirements driving the design:**

1. **Stateless Execution**: Handler must integrate cleanly with future Step Functions orchestration (Phase 4)
2. **Cost Efficiency**: Select model with optimal price/performance ratio for customer service use cases
3. **Low Latency**: Customer service requires fast response times
4. **Reliability**: Graceful handling of throttling, timeouts, and service errors
5. **Prompt Management**: Maintainable, version-controlled prompt construction
6. **Observability**: Token usage tracking for cost attribution and capacity planning
7. **Security**: Least-privilege IAM permissions for Bedrock model access

---

## Decision

### Model Selection

Adopt **Claude Haiku 4.5** (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) as the foundation model.

| Model | Model ID | Input (per 1M) | Output (per 1M) | Rationale |
|-------|----------|----------------|-----------------|-----------|
| **Claude Haiku 4.5** | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | ~$1.00 | ~$5.00 | ⭐ Fastest, most cost-effective, designed for customer service |
| Claude Sonnet 4 | `us.anthropic.claude-sonnet-4-20250514-v1:0` | $3.00 | $15.00 | More capable but 3x cost |
| Claude Sonnet 4.5 | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | $3.00 | $15.00 | Best for complex coding/agents |
| ~~Claude 3.5 Sonnet v2~~ | — | — | — | ❌ Legacy model |

**Why Claude Haiku 4.5:**

- **Speed**: Fastest response times in the Claude 4.5 family — critical for customer service chatbots
- **Cost**: Most cost-effective option (~$1/$5 vs $3/$15 for Sonnet)
- **Capability**: Matches Claude Sonnet 4 performance on agent tasks and customer service use cases
- **Design Fit**: Anthropic specifically optimized Haiku 4.5 for "customer service agents and chatbots where response time is critical"

**Note on Model ID Format:**

Newer Bedrock models require a regional prefix. For us-east-1, use `us.anthropic.claude-haiku-4-5-20251001-v1:0`.
Without the prefix, Bedrock returns a `ValidationException`.

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
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0"
      ]
    }
  ]
}
```

---

## Consequences

### Positive

- **Fast Response Times**: Haiku 4.5 provides lowest latency in the Claude 4.5 family
- **Cost Efficient**: ~70% cheaper than Sonnet models ($1/$5 vs $3/$15 per 1M tokens)
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

- **Model Capability**: Haiku 4.5 may produce slightly less nuanced responses than Sonnet on edge cases; monitor escalation rates
- **Future Flexibility**: Can upgrade to Sonnet 4 if complex queries require stronger reasoning; model ID is configurable via environment variable

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

### Option 3: Claude Sonnet 4 / Sonnet 4.5 for Stronger Reasoning

Use Sonnet ($3/$15 per 1M tokens) instead of Haiku (~$1/$5).

**Why not chosen:** Customer service queries are typically straightforward — order status, FAQs, basic troubleshooting.
Haiku 4.5 matches Sonnet 4 on agent tasks and is specifically optimized for customer service chatbots.
The 3x cost increase isn't justified for this use case. Can upgrade to Sonnet if escalation analysis shows Haiku struggling.

### Option 4: Claude 3.5 Sonnet v2 (Legacy)

Use the previous generation Claude 3.5 Sonnet v2 model.

**Why not chosen:** Model is now legacy with "Extended Access" status. The Claude 4.5 family offers better performance,
and Haiku 4.5 specifically matches or exceeds Claude 3.5 Sonnet capabilities at a fraction of the cost.
Using current-generation models ensures longer support runway.

### Option 5: No Retry Logic (Fail Fast)

Let all Bedrock errors propagate immediately without retries.

**Why not chosen:** Bedrock throttling is common under load. Transient errors would cause unnecessary customer-facing failures.
Exponential backoff with 3 retries handles most transient issues transparently. Step Functions can add additional retry layers in Phase 4.

---

## References

- [Amazon Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
- [Anthropic Claude on Bedrock](https://aws.amazon.com/bedrock/claude/)
- [Claude Haiku 4.5 Announcement](https://aws.amazon.com/about-aws/whats-new/2025/10/claude-4-5-haiku-anthropic-amazon-bedrock/)
- [ADR-008: DynamoDB Schema Design](./008-dynamodb-schema-design.md)
- Implementation: `lambda/functions/bedrock-handler/src/handler.py`
- Infrastructure: `terraform/modules/bedrock/main.tf`
