# ADR-012: Response Validation Strategy

**Date:** December 17th, 2025
**Status:** Accepted
**Deciders:** Engineering Team

---

## Context

With the Chat Orchestrator (Phase 2.3) generating AI responses via Amazon Bedrock, we need a mechanism to validate responses before returning them to customers. This addresses several concerns:

1. **Content Safety** — AI-generated responses may occasionally contain inappropriate content, profanity, or off-topic material
2. **PII Exposure** — Responses might inadvertently include personally identifiable information
3. **Business Compliance** — Responses must adhere to company policies (no medical/legal advice, topic restrictions)
4. **Response Quality** — Ensure responses meet minimum quality standards (length, relevance)
5. **Escalation Routing** — Identify conversations that require human intervention

### Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| Block profane/inappropriate content | P0 | Hard block with fallback |
| Detect and redact PII | P0 | Comprehend + custom patterns |
| Enforce response length limits | P1 | 20-2000 characters |
| Deflect restricted topics | P1 | Medical, legal, competitor |
| Calculate escalation score | P1 | Weighted composite score |
| Analyze customer sentiment | P2 | Comprehend sentiment API |

### Options Considered

#### Option A: Inline validation in Chat Orchestrator

- Pros: Lower latency, simpler deployment
- Cons: Violates single-responsibility, harder to test, tightly coupled

#### Option B: Separate Response Validator Lambda

- Pros: Single responsibility, reusable, independently testable, Step Functions ready
- Cons: Additional Lambda invocation latency (~100-200ms)

#### Option C: API Gateway response transformation

- Pros: Centralized, no code changes to Lambdas
- Cons: Limited logic capability, no access to Comprehend, poor observability

---

## Decision

**We will implement Option B: Separate Response Validator Lambda.**

This aligns with our architecture principles:

- **Separation of Concerns** — Each Lambda has a single responsibility
- **Stateless Handlers** — Validator is pure function (input → output)
- **Observability by Default** — Dedicated metrics and logging for validation

The Response Validator will be invoked by the Chat Orchestrator as an optional final step, controlled by a `validate_response` flag (default: `true`).

### Architecture

```bash
┌─────────────────────┐
│  Chat Orchestrator  │
└─────────┬───────────┘
          │
          ├──► RAG Retriever ──► documents
          │
          ├──► Bedrock Handler ──► raw response
          │
          └──► Response Validator ──► validated response
                    │
                    ├── Content Safety (profanity, topics)
                    ├── PII Detection (Comprehend + regex)
                    ├── Business Rules (length, policies)
                    ├── Sentiment Analysis (Comprehend)
                    └── Escalation Scoring (weighted)
```

### PII Detection: Hybrid Approach

We will use a hybrid approach combining AWS Comprehend and custom regex patterns:

**Amazon Comprehend PII Detection:**

- Social Security Numbers
- Credit card numbers
- Bank account numbers
- Phone numbers
- Email addresses
- Physical addresses
- Dates of birth
- Driver's license numbers

**Custom Regex Patterns:**

- Order IDs (e.g., `ABC-12345`, `ORD-[A-Z0-9]+`)
- Internal account codes
- Customer reference numbers
- Product SKUs (if sensitive)

**PII Handling Strategy:**

| PII Type | Action | Rationale |
|----------|--------|-----------|
| SSN, Credit Card, Bank | Block + fallback | High risk, never expose |
| Phone, Email, Address | Redact + warn | May be legitimate in context |
| Order ID, Account Code | Log only | Business identifiers, low risk |

### Business Rules Engine

Rules are evaluated in priority order. First failure determines response handling.

| Rule | Priority | Action on Violation |
|------|----------|---------------------|
| Profanity detection | P0 | Block → fallback response |
| High-risk PII | P0 | Block → fallback response |
| Response too short (<20 chars) | P1 | Block → fallback response |
| Response too long (>2000 chars) | P1 | Truncate + warning |
| Medical advice detected | P1 | Append disclaimer |
| Legal advice detected | P1 | Append disclaimer |
| Competitor mention | P2 | Log + allow |

### Escalation Scoring Algorithm

A weighted composite score determines if human intervention is needed:

```python
escalation_score = (
    0.35 * explicit_escalation_intent +  # From intent classifier
    0.25 * negative_sentiment_score +     # From Comprehend (0-1)
    0.20 * urgency_factor +               # From intent metadata
    0.15 * repeated_question_factor +     # Same topic 2+ times
    0.05 * low_confidence_factor          # Bedrock uncertainty signals
)

needs_escalation = escalation_score >= 0.70
```

Weights are configurable via environment variables for tuning.

### Response Format

**ValidationRequest:**

```json
{
  "response_text": "Here's how to reset your password...",
  "user_message": "How do I reset my password?",
  "conversation_id": "conv-123",
  "tenant_id": "acme-corp",
  "intent": "question",
  "intent_confidence": 0.92,
  "urgency": "low",
  "message_count": 3,
  "options": {
    "check_pii": true,
    "check_profanity": true,
    "analyze_sentiment": true,
    "calculate_escalation": true
  }
}
```

**ValidationResponse:**

```json
{
  "is_valid": true,
  "validated_response": "Here's how to reset your password...",
  "original_response": "Here's how to reset your password...",
  "validation_results": {
    "profanity": {"passed": true},
    "pii": {"passed": true, "detections": []},
    "length": {"passed": true, "char_count": 245},
    "business_rules": {"passed": true, "violations": []}
  },
  "sentiment": {
    "sentiment": "NEUTRAL",
    "score": 0.85,
    "scores": {
      "positive": 0.10,
      "negative": 0.05,
      "neutral": 0.85,
      "mixed": 0.00
    }
  },
  "escalation": {
    "score": 0.32,
    "needs_escalation": false,
    "factors": {
      "explicit_intent": 0.0,
      "negative_sentiment": 0.05,
      "urgency": 0.0,
      "repeated_question": 0.0,
      "low_confidence": 0.08
    }
  },
  "metadata": {
    "validation_time_ms": 180,
    "rules_evaluated": 6,
    "fallback_used": false
  }
}
```

### Fallback Responses

When validation fails with a blocking rule, return a safe fallback:

```python
FALLBACK_RESPONSES = {
    "default": "I apologize, but I'm unable to provide a response to that. "
               "Please let me know if you have another question, or I can "
               "connect you with a support agent.",
    "pii_blocked": "I apologize, but I cannot include certain information in "
                   "my response for security reasons. Please contact our "
                   "support team directly for assistance with sensitive data.",
    "topic_restricted": "I'm not able to provide advice on that topic. "
                        "For {topic} matters, please consult a qualified "
                        "professional. Is there something else I can help with?"
}
```

---

## Consequences

### Positive

- **Safety:** AI responses are validated before reaching customers
- **Compliance:** PII detection helps meet data protection requirements
- **Observability:** Dedicated metrics for validation failures, PII detections, escalations
- **Flexibility:** Rules and thresholds are configurable without code changes
- **Reusability:** Validator can be used by future services or Step Functions
- **Testability:** Isolated component with clear inputs/outputs

### Negative

- **Latency:** Additional ~150-300ms per request (Comprehend API calls)
- **Cost:** Comprehend API charges (~$0.0001 per unit for PII, ~$0.0001 for sentiment)
- **Complexity:** Additional Lambda to maintain and monitor
- **False Positives:** Rules may occasionally block legitimate responses

### Mitigations

| Risk | Mitigation |
|------|------------|
| Latency impact | Parallel Comprehend calls; optional validation flag |
| Cost growth | Batch requests where possible; monitor usage |
| False positives | Tunable thresholds; logging for review; easy rule disable |
| Comprehend failures | Graceful degradation; continue without PII check if unavailable |

---

## Implementation Plan

| Phase | Deliverable |
|-------|-------------|
| 3.1.2 | Pydantic models |
| 3.1.3 | Business rules engine |
| 3.1.4 | PII detection service |
| 3.1.5 | Validation service layer |
| 3.1.6 | Lambda handler |
| 3.1.7 | Unit tests (80%+) |
| 3.1.8 | Terraform configuration |
| 3.1.9 | Chat Orchestrator integration |
| 3.1.10 | E2E tests & documentation |

---

## References

- [ADR-011: Orchestrator Pattern](./ADR-011-orchestrator-pattern.md)
- [Amazon Comprehend PII Detection](https://docs.aws.amazon.com/comprehend/latest/dg/how-pii.html)
- [Amazon Comprehend Sentiment Analysis](https://docs.aws.amazon.com/comprehend/latest/dg/how-sentiment.html)
- [AWS Lambda Powertools](https://docs.powertools.aws.dev/lambda/python/latest/)
