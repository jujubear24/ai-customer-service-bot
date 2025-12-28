# ADR-013: Sentiment Analysis & Escalation Scoring Strategy

**Status**: Accepted
**Date**: 2025-12-28

## Context

The AI Customer Service Bot needs to identify conversations that require human intervention. While Phase 3.1 implemented content safety validation (PII, profanity, business rules), we now need to:

1. **Analyze customer sentiment** in real-time to detect frustration or dissatisfaction
2. **Calculate escalation scores** based on multiple weighted factors
3. **Flag conversations** that should be routed to human agents

This capability is critical for:

- Preventing customer churn from unresolved frustration
- Ensuring complex issues reach human agents promptly
- Maintaining service quality when AI responses are insufficient

## Decision Drivers

- **Latency**: Sentiment analysis adds API calls; must minimize impact on response time
- **Accuracy**: False positives waste human agent time; false negatives frustrate customers
- **Simplicity**: Escalation logic must be explainable and auditable
- **Cost**: Comprehend pricing is per-unit; minimize unnecessary API calls
- **Consistency**: Scoring must be deterministic for the same inputs

## Considered Options

### Option 1: Comprehend-Only Sentiment Analysis

Use Amazon Comprehend `DetectSentiment` for all sentiment analysis.

**Pros:** Consistent, well-tested, handles nuance
**Cons:** Additional API call latency (~50-100ms), cost per request

### Option 2: Keyword-Based Sentiment Detection

Use regex patterns to detect negative sentiment keywords.

**Pros:** Fast, no API cost, predictable
**Cons:** Misses context, high false positive/negative rate

### Option 3: Hybrid Approach (Selected)

Use Comprehend for sentiment but optimize with:

- Batch the sentiment call with existing PII detection where possible
- Cache sentiment for repeated messages (future enhancement)
- Use keyword detection only for explicit escalation requests

## Decision

We will implement **Option 3: Hybrid Approach** with the following design:

### Sentiment Analysis

**Service:** Amazon Comprehend `DetectSentiment` API

**Input:** User's message (not AI response)

**Output:** `SentimentResult` model with:

- Dominant sentiment: POSITIVE, NEGATIVE, NEUTRAL, MIXED
- Confidence score (0.0-1.0)
- Detailed scores for each sentiment type

**Rationale for analyzing user message:**

- User sentiment drives escalation need
- AI response sentiment is controlled (always professional)
- Reduces Comprehend calls by 50%

### Escalation Scoring Algorithm

Weighted factor model with configurable threshold:

| Factor | Weight | Source | Scoring Logic |
| -------- | -------- | -------- | --------------- |
| Explicit Intent | 0.35 | User message keywords | 1.0 if escalation keywords detected, else 0.0 |
| Negative Sentiment | 0.25 | Comprehend result | `sentiment_scores.negative` (0.0-1.0) |
| Urgency | 0.20 | Intent classifier | high=1.0, medium=0.5, low/none=0.0 |
| Repeated Question | 0.15 | Previous intents | 2+ repeats=1.0, 1 repeat=0.5, else 0.0 |
| Low Confidence | 0.05 | Intent classifier | `1.0 - intent_confidence` |

**Escalation Threshold:** 0.70 (configurable via environment variable)

**Formula:**

```bash
score = (0.35 × explicit_intent) +
        (0.25 × negative_sentiment) +
        (0.20 × urgency) +
        (0.15 × repeated_question) +
        (0.05 × low_confidence)

needs_escalation = score >= threshold
```

### Explicit Escalation Keywords

Regex patterns to detect explicit escalation requests:

```python
ESCALATION_PATTERNS = [
    r"\b(speak|talk)\s+(to|with)\s+(a\s+)?(human|person|agent|representative|someone)\b",
    r"\b(need|want|get)\s+(a\s+)?(human|person|agent|representative)\b",
    r"\b(transfer|connect|escalate)\s+(me\s+)?(to)?\b",
    r"\breal\s+person\b",
    r"\bhuman\s+(help|support|assistance)\b",
    r"\bthis\s+(isn't|isnt|is\s+not)\s+helping\b",
    r"\b(useless|worthless)\s+(bot|ai|assistant)\b",
]
```

### Urgency Mapping

The `urgency` field from Intent Classifier maps to scores:

| Urgency Value | Score | Examples |
| --------------- | ------- | ---------- |
| `"high"` | 1.0 | Payment issues, account locked, service outage |
| `"medium"` | 0.5 | Order delays, refund requests |
| `"low"` or `None` | 0.0 | General questions, product info |

### Repeated Question Detection

Based on `previous_intents` list in `ValidationRequest`:

```python
def calculate_repeated_score(current_intent: str, previous_intents: list[str]) -> float:
    if not current_intent or not previous_intents:
        return 0.0

    repeat_count = previous_intents.count(current_intent)

    if repeat_count >= 2:   # Asked 3+ times total
        return 1.0
    elif repeat_count == 1:  # Asked twice
        return 0.5
    return 0.0
```

## Integration Points

### Response Validator Service Flow

```bash
ValidationRequest
    │
    ├──► PII Detection (existing)
    │
    ├──► Business Rules (existing)
    │
    ├──► Sentiment Analysis (NEW)
    │         │
    │         └──► Comprehend DetectSentiment
    │
    ├──► Escalation Scoring (NEW)
    │         │
    │         ├──► Explicit intent detection
    │         ├──► Sentiment score
    │         ├──► Urgency mapping
    │         ├──► Repeated question check
    │         └──► Confidence inversion
    │
    └──► ValidationResponse
              │
              ├── sentiment: SentimentResult
              └── escalation: EscalationResult
```

### Chat Orchestrator Integration

The Chat Orchestrator will:

1. Receive `escalation` in validation response
2. Add escalation metadata to `ChatResponse`
3. Emit CloudWatch metrics for escalation events
4. (Future) Trigger SNS notification for immediate escalation

### Environment Variables

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `ENABLE_SENTIMENT_ANALYSIS` | `"true"` | Enable/disable sentiment analysis |
| `ENABLE_ESCALATION_SCORING` | `"true"` | Enable/disable escalation scoring |
| `ESCALATION_THRESHOLD` | `"0.70"` | Score threshold for escalation flag |

## Consequences

### Positive

- **Proactive escalation**: Frustrated customers reach humans before churning
- **Explainable scoring**: Weighted factors are auditable and tunable
- **Minimal latency impact**: Single additional Comprehend call (~50-100ms)
- **Reuses existing infrastructure**: Comprehend client already configured for PII

### Negative

- **Additional cost**: ~$0.0001 per sentiment analysis call
- **Potential false positives**: Sarcasm and context may be misinterpreted
- **Threshold tuning required**: Will need adjustment based on production data

### Risks & Mitigations

| Risk | Mitigation |
| ------ | ------------ |
| High false positive rate | Start with 0.70 threshold; tune based on metrics |
| Comprehend latency spikes | Fail-open design returns `None` sentiment on errors |
| Gaming by users | Explicit intent alone (0.35) won't trigger escalation |

## Metrics & Monitoring

### CloudWatch Metrics

| Metric | Type | Description |
| -------- | ------ | ------------- |
| `SentimentAnalysisRequests` | Count | Total sentiment analysis calls |
| `SentimentNegative` | Count | Negative sentiment detected |
| `EscalationTriggered` | Count | Escalation threshold exceeded |
| `EscalationScore` | Summary | Distribution of escalation scores |
| `SentimentAnalysisLatency` | Timer | Comprehend API latency |
| `EscalationByFactor` | Count | Breakdown by dominant factor |

### Alarms

- `EscalationRate > 20%` over 5 minutes → Alert on-call
- `SentimentAnalysisErrors > 10` in 5 minutes → Check Comprehend quota

## Future Enhancements

1. **Sentiment caching**: Cache results for duplicate messages within conversation
2. **Conversation-level sentiment**: Track sentiment trend across messages
3. **Custom escalation rules**: Per-tenant threshold configuration
4. **ML-based escalation**: Train model on historical escalation outcomes
5. **Real-time routing**: SNS → Lambda → Agent queue integration

## References

- [ADR-012: Response Validation Strategy](./ADR-012-response-validation.md)
- [Amazon Comprehend Sentiment Analysis](https://docs.aws.amazon.com/comprehend/latest/dg/how-sentiment.html)
- [Pydantic Models: SentimentResult, EscalationResult](../../lambda/functions/response-validator/src/models.py)
