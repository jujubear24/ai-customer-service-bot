# ADR-014: Escalation Router

**Status:** Accepted
**Date:** 2025-12-28

## Context

Phase 3.2 implemented sentiment analysis and escalation scoring in the Response Validator. When the escalation score exceeds the threshold (default 0.70),
the system identifies that the conversation should be routed to a human agent. We need a mechanism to:

1. Route escalated conversations to available human agents
2. Update conversation status in DynamoDB
3. Notify agents of pending escalations
4. Provide customers with appropriate feedback
5. Track escalation metrics for operational insights

### Requirements

- **Async Processing:** Escalation routing should not block the customer response
- **Priority Handling:** Higher escalation scores should be handled first
- **Reliability:** Messages must not be lost; at-least-once delivery
- **Observability:** Track escalation volume, wait times, resolution rates
- **Scalability:** Handle varying escalation volumes without manual intervention

### Options Considered

#### Option 1: Direct SNS Notification**

- Publish directly to SNS topic when escalation detected
- Agents subscribe to topic for notifications
- Pros: Simple, real-time notifications
- Cons: No queuing, no priority handling, messages can be lost if no subscriber

#### Option 2: SQS Standard Queue**

- Push escalations to SQS queue
- Agent service polls queue for work
- Pros: Reliable delivery, decoupled, scalable
- Cons: No strict ordering, potential duplicates

#### Option 3: SQS FIFO Queue with Priority**

- Use FIFO queue with message group ID based on priority tier
- Ensures ordered processing within priority tiers
- Pros: Ordered, exactly-once processing, priority support
- Cons: Lower throughput (3,000 msg/sec with batching)

#### Option 4: EventBridge with Rules**

- Publish to EventBridge, route based on rules
- Pros: Flexible routing, multiple targets, filtering
- Cons: More complex, higher latency, overkill for current needs

## Decision

### Chosen: Option 3 - SQS FIFO Queue with Priority Tiers**

We will implement a priority-based escalation system using:

1. **SQS FIFO Queue** for reliable, ordered message delivery
2. **Priority Tiers** based on escalation score:
   - `CRITICAL` (score ≥ 0.90): Explicit escalation + multiple factors
   - `HIGH` (score ≥ 0.80): Strong escalation signals
   - `NORMAL` (score ≥ 0.70): Threshold exceeded
3. **SNS Topic** for agent notifications (optional, real-time alerts)
4. **DynamoDB Updates** to track escalation status

### Architecture

```Bash
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Chat Orchestrator                                 │
│                                                                             │
│   Validation Result ──► needs_escalation=true ──► Escalation Router Lambda  │
│                                                              │              │
└──────────────────────────────────────────────────────────────┼──────────────┘
                                                               │
                    ┌──────────────────────────────────────────┼──────────────┐
                    │                                          ▼              │
                    │  ┌──────────────┐    ┌───────────────────────────┐     │
                    │  │   DynamoDB   │◄───│   Escalation Router       │     │
                    │  │ status=ESC   │    │        Lambda             │     │
                    │  │ escalation   │    │  • Determine priority     │     │
                    │  │ _metadata    │    │  • Update DynamoDB        │     │
                    │  └──────────────┘    │  • Send to SQS            │     │
                    │                      │  • Publish to SNS (opt)   │     │
                    │                      └─────────────┬─────────────┘     │
                    │                                    │                    │
                    │                      ┌─────────────▼─────────────┐     │
                    │                      │     SQS FIFO Queue        │     │
                    │                      │  agent-escalations.fifo   │     │
                    │                      │  • MessageGroupId=priority│     │
                    │                      │  • Deduplication          │     │
                    │                      └─────────────┬─────────────┘     │
                    │                                    │                    │
                    │                      ┌─────────────▼─────────────┐     │
                    │                      │   Agent Service (Future)  │     │
                    │                      │  • Poll queue             │     │
                    │                      │  • Assign to agent        │     │
                    │                      │  • Update status          │     │
                    │                      └───────────────────────────┘     │
                    │                                                         │
                    │                      ┌───────────────────────────┐     │
                    │                      │   SNS Topic (Optional)    │     │
                    │                      │  agent-escalation-alerts  │     │
                    │                      │  • Real-time notifications│     │
                    │                      └───────────────────────────┘     │
                    │                                                         │
                    └─────────────────────────────────────────────────────────┘
```

### Priority Tiers

| Tier | Score Range | MessageGroupId | Use Case |
| ------ | ------------- | ---------------- | ---------- |
| CRITICAL | ≥ 0.90 | `priority-critical` | Angry customer explicitly demanding agent |
| HIGH | ≥ 0.80 | `priority-high` | Strong negative sentiment + urgency |
| NORMAL | ≥ 0.70 | `priority-normal` | Threshold exceeded |

### Message Schema

```json
{
  "escalation_id": "esc-uuid-here",
  "conversation_id": "conv-123",
  "tenant_id": "tenant-456",
  "user_id": "user-789",
  "priority": "HIGH",
  "escalation_score": 0.85,
  "primary_reason": "Explicit escalation request",
  "factors": {
    "explicit_intent": 1.0,
    "negative_sentiment": 0.75,
    "urgency": 1.0,
    "repeated_question": 0.5,
    "low_confidence": 0.0
  },
  "sentiment": "NEGATIVE",
  "last_user_message": "I want to speak to a manager!",
  "message_count": 5,
  "created_at": "2025-12-29T10:30:00Z",
  "metadata": {
    "intent": "complaint",
    "urgency": "high"
  }
}
```

### DynamoDB Updates

When escalation is triggered:

```python
# Update conversation status
{
    "pk": "CONV#conv-123",
    "sk": "METADATA",
    "status": "ESCALATED",
    "escalation_id": "esc-uuid",
    "escalation_score": 0.85,
    "escalation_reason": "Explicit escalation request",
    "escalation_priority": "HIGH",
    "escalated_at": "2025-12-29T10:30:00Z",
    "gsi2_pk": "STATUS#ESCALATED",  # For agent dashboard queries
    "gsi2_sk": "2025-12-29T10:30:00Z#conv-123"
}
```

### Customer Response

When escalation is triggered, the Chat Orchestrator modifies the response:

```json
{
  "response": "I understand your concern. I've escalated this to our support team, and a human agent will assist you shortly. In the meantime, is there anything else I can help clarify?",
  "metadata": {
    "escalation": {
      "triggered": true,
      "priority": "HIGH",
      "estimated_wait": "< 5 minutes"
    }
  }
}
```

### Configuration

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `ESCALATION_QUEUE_URL` | - | SQS FIFO queue URL |
| `ESCALATION_SNS_TOPIC_ARN` | - | SNS topic ARN (optional) |
| `ENABLE_SNS_NOTIFICATIONS` | `false` | Enable real-time SNS alerts |
| `CRITICAL_THRESHOLD` | `0.90` | Score for CRITICAL priority |
| `HIGH_THRESHOLD` | `0.80` | Score for HIGH priority |

### Lambda Specification

| Attribute | Value |
| ----------- | ------- |
| Runtime | Python 3.12 |
| Memory | 256 MB |
| Timeout | 10 seconds |
| Trigger | Direct invocation (from Chat Orchestrator) |
| Layer | shared-layer |

### IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:*:*:agent-escalations.fifo"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": "arn:aws:sns:*:*:agent-escalation-alerts"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:UpdateItem"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/conversations"
    }
  ]
}
```

## Consequences

### Positive

- **Reliable Delivery:** SQS FIFO ensures no escalations are lost
- **Priority Handling:** Critical issues surface first
- **Decoupled:** Agent service can scale independently
- **Observable:** CloudWatch metrics for queue depth, processing time
- **Auditable:** DynamoDB stores complete escalation history
- **Extensible:** Easy to add routing rules, skill-based routing later

### Negative

- **Throughput Limit:** FIFO queues limited to 3,000 msg/sec (sufficient for current scale)
- **Additional Infrastructure:** SQS queue, optional SNS topic
- **Latency:** Small overhead for queue operations (~50-100ms)
- **Agent Service Required:** Need separate service to process queue (future work)

### Neutral

- **Cost:** SQS FIFO ~$0.50/million requests, minimal impact
- **Complexity:** Moderate increase, but well-isolated

## Metrics

| Metric | Unit | Description |
| -------- | ------ | ------------- |
| EscalationsRouted | Count | Total escalations sent to queue |
| EscalationsByPriority | Count | Escalations by priority tier |
| EscalationRoutingLatency | Milliseconds | Time to process escalation |
| EscalationQueueDepth | Count | Messages waiting in queue |
| EscalationRoutingErrors | Count | Failed routing attempts |

## References

- [ADR-012: Response Validation Strategy](./ADR-012-response-validation.md)
- [ADR-013: Sentiment Analysis & Escalation Scoring](./ADR-013-sentiment-escalation.md)
- [AWS SQS FIFO Queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues.html)
- [DynamoDB GSI for Status Queries](./ADR-008-dynamodb-schema-design.md)
