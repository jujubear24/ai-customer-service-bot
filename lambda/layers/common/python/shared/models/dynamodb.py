"""
DynamoDB single-table design for AI Customer Service Bot.

Access Patterns:
1. Get conversation by conversation_id
2. Get all messages for a conversation (chronological)
3. Get recent conversations for a user
4. Get conversations by status (for escalation)
5. Query conversations by date range
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """DynamoDB entity types."""

    CONVERSATION = "CONVERSATION"
    MESSAGE = "MESSAGE"
    USER_PROFILE = "USER_PROFILE"


class ConversationStatus(str, Enum):
    """Conversation status types."""

    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    ABANDONED = "ABANDONED"


class MessageRole(str, Enum):
    """Message role types."""

    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


# Primary Key Structure:
# PK = CONV#{conversation_id} or USER#{user_id}
# SK = METADATA or MSG#{timestamp} or CONV#{timestamp}


class ConversationMetadata(BaseModel):
    """Conversation metadata record."""

    pk: str = Field(..., description="PK: CONV#{conversation_id}")
    sk: str = Field(default="METADATA", description="SK: METADATA")
    entity_type: str = Field(default=EntityType.CONVERSATION)
    conversation_id: str
    user_id: str
    status: ConversationStatus = ConversationStatus.ACTIVE
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    message_count: int = Field(default=0)
    last_intent: str | None = None
    escalation_reason: str | None = None
    sentiment_score: float | None = None
    # GSI-1: For querying by user
    gsi1_pk: str = Field(..., description="USER#{user_id}")
    gsi1_sk: str = Field(..., description="CONV#{created_at}")
    # GSI-2: For querying by status
    gsi2_pk: str = Field(..., description="STATUS#{status}")
    gsi2_sk: str = Field(..., description="{updated_at}")
    ttl: int | None = Field(default=None, description="Unix timestamp for auto-deletion (30 days)")

    @classmethod
    def create(cls, conversation_id: str, user_id: str) -> "ConversationMetadata":
        """Create a new conversation metadata record."""
        now = datetime.utcnow().isoformat()
        return cls(
            pk=f"CONV#{conversation_id}",
            sk="METADATA",
            conversation_id=conversation_id,
            user_id=user_id,
            gsi1_pk=f"USER#{user_id}",
            gsi1_sk=f"CONV#{now}",
            gsi2_pk=f"STATUS#{ConversationStatus.ACTIVE}",
            gsi2_sk=now,
        )


class MessageRecord(BaseModel):
    """Individual message record in a conversation."""

    pk: str = Field(..., description="PK: CONV#{conversation_id}")
    sk: str = Field(..., description="SK: MSG#{timestamp}#{message_id}")
    entity_type: str = Field(default=EntityType.MESSAGE)
    conversation_id: str
    message_id: str
    role: MessageRole
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    intent: str | None = None
    entities: dict[str, str] | None = None
    sentiment: str | None = None
    tokens_used: int | None = None
    model_version: str | None = None
    ttl: int | None = Field(default=None, description="Unix timestamp for auto-deletion (30 days)")

    @classmethod
    def create(
        cls,
        conversation_id: str,
        message_id: str,
        role: MessageRole,
        content: str,
        intent: str | None = None,
        entities: dict[str, str] | None = None,
    ) -> "MessageRecord":
        """Create a new message record."""
        timestamp = datetime.utcnow().isoformat()
        return cls(
            pk=f"CONV#{conversation_id}",
            sk=f"MSG#{timestamp}#{message_id}",
            conversation_id=conversation_id,
            message_id=message_id,
            role=role,
            content=content,
            timestamp=timestamp,
            intent=intent,
            entities=entities,
        )


class UserProfile(BaseModel):
    """User profile for preference storage."""

    pk: str = Field(..., description="PK: USER#{user_id}")
    sk: str = Field(default="PROFILE", description="SK: PROFILE")
    entity_type: str = Field(default=EntityType.USER_PROFILE)
    user_id: str
    email: str | None = None
    name: str | None = None
    total_conversations: int = Field(default=0)
    avg_sentiment: float | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @classmethod
    def create(cls, user_id: str, email: str | None = None) -> "UserProfile":
        """Create a new user profile."""
        return cls(
            pk=f"USER#{user_id}",
            sk="PROFILE",
            user_id=user_id,
            email=email,
        )


# Example query patterns:
"""
1. Get conversation metadata:
   Query: PK = "CONV#{conversation_id}" AND SK = "METADATA"

2. Get all messages for conversation (chronological):
   Query: PK = "CONV#{conversation_id}" AND SK begins_with "MSG#"
   ScanIndexForward = True (ascending by timestamp)

3. Get user's conversations (most recent first):
   Query GSI-1: PK = "USER#{user_id}" AND SK begins_with "CONV#"
   ScanIndexForward = False (descending by timestamp)

4. Get conversations by status:
   Query GSI-2: PK = "STATUS#{status}" AND SK > "{timestamp}"
   For escalated conversations needing attention

5. Get recent messages (last N):
   Query: PK = "CONV#{conversation_id}" AND SK begins_with "MSG#"
   Limit = N, ScanIndexForward = False (descending)
"""
