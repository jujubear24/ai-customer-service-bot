# ADR-008: DynamoDB Schema Design

**Date:** 2025-11-27
**Status:** Accepted
**Deciders:** Senior Cloud Architect, Development Team

---

## Context

The AI Customer Service Bot requires persistent storage for conversation history to enable context-aware responses from the Bedrock (Claude) model.
The Context Builder Lambda needs to retrieve previous messages in a conversation to construct an appropriate context window for the LLM.

**Key requirements driving the design:**

1. **Conversation Retrieval**: Fetch all messages for a given conversation in chronological order
2. **User History**: Query a user's recent conversations for continuity across sessions
3. **Escalation Management**: Quickly identify conversations by status (e.g., ESCALATED) for agent routing
4. **Token Management**: Support efficient retrieval for context window construction (8000 token limit)
5. **Cost Efficiency**: Minimize storage costs while maintaining performance for a serverless architecture
6. **Automatic Cleanup**: Remove stale conversations to manage storage growth

---

## Decision

### Single-Table Design

Adopt a **single-table design** with composite primary keys (`pk`/`sk`) to store all entity types: conversations, messages, and user profiles.

### Primary Key Structure

| Entity Type | PK Pattern | SK Pattern |
|-------------|------------|------------|
| Conversation Metadata | `CONV#{conversation_id}` | `METADATA` |
| Message | `CONV#{conversation_id}` | `MSG#{timestamp}#{message_id}` |
| User Profile | `USER#{user_id}` | `PROFILE` |

### Global Secondary Indexes

**GSI1 - User Queries:**

- Hash Key: `gsi1_pk` = `USER#{user_id}`
- Sort Key: `gsi1_sk` = `CONV#{created_at}`
- Purpose: Retrieve a user's conversations ordered by creation date

**GSI2 - Status Queries:**

- Hash Key: `gsi2_pk` = `STATUS#{status}`
- Sort Key: `gsi2_sk` = `{updated_at}`
- Purpose: Query conversations by status for escalation routing and operational dashboards

### Data Access Patterns

| Access Pattern | Key Condition | Index |
|----------------|---------------|-------|
| Get conversation metadata | `pk = CONV#{id}` AND `sk = METADATA` | Table |
| Get messages (chronological) | `pk = CONV#{id}` AND `sk begins_with MSG#` | Table |
| Get user's conversations | `gsi1_pk = USER#{id}` | GSI1 |
| Get conversations by status | `gsi2_pk = STATUS#{status}` | GSI2 |

### TTL Strategy

- **Retention Period**: 30 days from creation/last update
- **Implementation**: Unix timestamp stored in `ttl` attribute
- **Scope**: Applied to both conversation metadata and individual messages
- **Rationale**: Balances storage costs with reasonable history retention for customer service context

### Token Estimation

The Context Builder uses a simple heuristic for token estimation: **4 characters ≈ 1 token**.
This provides a fast, compute-free approximation suitable for context window management without requiring tokenizer dependencies.

### Billing Mode

- **Development**: On-demand (`PAY_PER_REQUEST`) for cost efficiency with unpredictable traffic
- **Production**: Evaluate provisioned capacity with auto-scaling based on observed patterns

---

## Consequences

### Positive

- **Flexible Querying**: Single-table design with GSIs supports all required access patterns efficiently
- **Cost-Effective**: On-demand billing eliminates idle capacity costs; TTL automates cleanup
- **Scalable**: DynamoDB scales automatically; no connection pooling or capacity planning required
- **Low Latency**: Single-digit millisecond response times for all access patterns
- **Serverless Alignment**: Complements Lambda-based architecture with no connection management overhead
- **Future-Ready**: DynamoDB Streams enabled for future event-driven features (e.g., analytics, notifications)

### Negative

- **Learning Curve**: Single-table design requires understanding of DynamoDB access patterns and key design
- **Query Complexity**: Application code must construct composite keys correctly; no ad-hoc querying
- **GSI Maintenance**: GSI attributes must be kept in sync during updates (e.g., `gsi2_pk` when status changes)

### Neutral

- **Token Estimation Accuracy**: The 4-char heuristic is approximate; actual token counts may vary by ~10-20% depending on content.
This is acceptable for context window management where exact precision is unnecessary.
- **No Cross-Partition Queries**: Cannot efficiently query across all conversations without a scan; mitigated by GSIs for known access patterns.

---

## Alternatives Considered

### Option 1: Multi-Table Design

Separate tables for conversations, messages, and users with foreign key relationships.

**Why not chosen:** Increases operational complexity, requires multiple queries for related data, and doesn't leverage DynamoDB's strengths.
Single-table design provides better performance for known access patterns and reduces the number of AWS resources to manage.

### Option 2: Simple Primary Key (conversation_id only)

Use `conversation_id` as a simple primary key without composite keys.

**Why not chosen:** Cannot efficiently store multiple entity types (metadata, messages) in the same table. Would require separate tables or inefficient filtering, losing the benefits of single-table design.

### Option 3: Relational Database (Aurora Serverless)

Use Aurora Serverless v2 for flexible SQL querying.

**Why not chosen:** Higher baseline costs, connection management complexity with Lambda (even with RDS Proxy), and cold start latency.
DynamoDB's serverless model aligns better with the event-driven architecture and provides more predictable performance at scale.

### Option 4: ElastiCache for Session Storage

Use Redis for in-memory conversation storage.

**Why not chosen:** Requires VPC configuration, increases infrastructure complexity, and doesn't provide durable storage.
Not suitable for conversations that may span multiple sessions or require persistence beyond immediate use.

---

## References

- [AWS DynamoDB Single-Table Design](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-general-nosql-design.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- Implementation: `lambda/layers/common/python/shared/models/dynamodb.py`
- Repository: `lambda/layers/common/python/shared/repositories/dynamodb.py`
- Infrastructure: `terraform/modules/dynamodb/main.tf`
