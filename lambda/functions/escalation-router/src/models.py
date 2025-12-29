"""Pydantic models for Escalation Router Lambda."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EscalationPriority(str, Enum):
    """Priority levels for escalation routing."""

    CRITICAL = "CRITICAL"  # Score >= 0.90
    HIGH = "HIGH"  # Score >= 0.80
    NORMAL = "NORMAL"  # Score >= 0.70


class EscalationFactors(BaseModel):
    """Individual factors contributing to escalation score."""

    explicit_intent: float = Field(default=0.0, ge=0.0, le=1.0)
    negative_sentiment: float = Field(default=0.0, ge=0.0, le=1.0)
    urgency: float = Field(default=0.0, ge=0.0, le=1.0)
    repeated_question: float = Field(default=0.0, ge=0.0, le=1.0)
    low_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class EscalationData(BaseModel):
    """Escalation data from Response Validator."""

    score: float = Field(..., ge=0.0, le=1.0)
    needs_escalation: bool
    threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    factors: EscalationFactors
    primary_reason: str | None = None


class SentimentData(BaseModel):
    """Sentiment data from Response Validator."""

    sentiment: str  # POSITIVE, NEGATIVE, NEUTRAL, MIXED
    confidence: float = Field(..., ge=0.0, le=1.0)
    negative_score: float = Field(default=0.0, ge=0.0, le=1.0)


class EscalationRequest(BaseModel):
    """Request to route an escalation.

    Sent from Chat Orchestrator when escalation is triggered.
    """

    conversation_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    user_id: str | None = None
    message_id: str | None = None

    # Escalation details from Response Validator
    escalation: EscalationData

    # Context for the agent
    sentiment: SentimentData | None = None
    last_user_message: str = Field(..., min_length=1)
    last_ai_response: str | None = None
    message_count: int = Field(default=1, ge=1)

    # Intent classification data
    intent: str | None = None
    intent_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    urgency: str | None = None  # low, medium, high, critical
    previous_intents: list[str] = Field(default_factory=list)

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class EscalationMessage(BaseModel):
    """Message sent to SQS queue for agent processing.

    This is the schema for messages in the agent-escalations.fifo queue.
    """

    escalation_id: str = Field(..., min_length=1)
    conversation_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    user_id: str | None = None

    # Priority and scoring
    priority: EscalationPriority
    escalation_score: float = Field(..., ge=0.0, le=1.0)
    primary_reason: str | None = None
    factors: EscalationFactors

    # Context for the agent
    sentiment: str | None = None  # POSITIVE, NEGATIVE, NEUTRAL, MIXED
    last_user_message: str
    message_count: int = Field(default=1, ge=1)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional context
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_sqs_message(self) -> dict[str, Any]:
        """Convert to SQS message format."""
        return {
            "MessageBody": self.model_dump_json(),
            "MessageGroupId": f"priority-{self.priority.value.lower()}",
            "MessageDeduplicationId": self.escalation_id,
        }


class DynamoDBEscalationUpdate(BaseModel):
    """Data for updating conversation status in DynamoDB."""

    conversation_id: str
    status: str = "ESCALATED"
    escalation_id: str
    escalation_score: float
    escalation_reason: str | None
    escalation_priority: EscalationPriority
    escalated_at: datetime = Field(default_factory=datetime.utcnow)

    # GSI2 for agent dashboard queries
    gsi2_pk: str = "STATUS#ESCALATED"
    gsi2_sk: str = ""  # Set in __init__

    def __init__(self, **data: Any) -> None:
        """Initialize with computed GSI2 sort key."""
        super().__init__(**data)
        if not self.gsi2_sk:
            self.gsi2_sk = f"{self.escalated_at.isoformat()}#{self.conversation_id}"

    def to_update_expression(self) -> dict[str, Any]:
        """Generate DynamoDB update expression."""
        return {
            "UpdateExpression": (
                "SET #status = :status, "
                "escalation_id = :esc_id, "
                "escalation_score = :esc_score, "
                "escalation_reason = :esc_reason, "
                "escalation_priority = :esc_priority, "
                "escalated_at = :esc_at, "
                "gsi2_pk = :gsi2_pk, "
                "gsi2_sk = :gsi2_sk"
            ),
            "ExpressionAttributeNames": {
                "#status": "status",
            },
            "ExpressionAttributeValues": {
                ":status": self.status,
                ":esc_id": self.escalation_id,
                ":esc_score": str(self.escalation_score),  # DynamoDB Number
                ":esc_reason": self.escalation_reason,
                ":esc_priority": self.escalation_priority.value,
                ":esc_at": self.escalated_at.isoformat(),
                ":gsi2_pk": self.gsi2_pk,
                ":gsi2_sk": self.gsi2_sk,
            },
        }


class EscalationResponse(BaseModel):
    """Response from Escalation Router back to Chat Orchestrator."""

    success: bool
    escalation_id: str
    priority: EscalationPriority
    queue_message_id: str | None = None  # SQS message ID
    notification_sent: bool = False  # SNS notification status

    # For customer-facing response modification
    customer_message: str = Field(
        default=(
            "I understand your concern. I've escalated this to our support team, "
            "and a human agent will assist you shortly. "
            "Is there anything else I can help clarify in the meantime?"
        )
    )
    estimated_wait: str | None = "< 5 minutes"

    # Metadata
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: str | None = None


class EscalationRouterConfig(BaseModel):
    """Configuration for Escalation Router."""

    # Queue settings
    queue_url: str = Field(default="")
    enable_queue: bool = Field(default=True)

    # SNS settings
    sns_topic_arn: str = Field(default="")
    enable_sns_notifications: bool = Field(default=False)

    # DynamoDB settings
    table_name: str = Field(default="conversations")
    enable_dynamodb_update: bool = Field(default=True)

    # Priority thresholds
    critical_threshold: float = Field(default=0.90, ge=0.0, le=1.0)
    high_threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    # Customer messages by priority
    customer_messages: dict[str, str] = Field(
        default_factory=lambda: {
            "CRITICAL": (
                "I completely understand your frustration, and I sincerely apologize. "
                "I've immediately escalated this to a senior support specialist who will "
                "contact you within the next few minutes. Your case is our top priority."
            ),
            "HIGH": (
                "I understand your concern, and I want to make sure you get the help you need. "
                "I've escalated this to our support team, and a human agent will assist you shortly."
            ),
            "NORMAL": (
                "I've noted your request and escalated this to our support team. "
                "A human agent will be with you soon. Is there anything else I can help with?"
            ),
        }
    )

    def determine_priority(self, score: float) -> EscalationPriority:
        """Determine priority tier based on escalation score."""
        if score >= self.critical_threshold:
            return EscalationPriority.CRITICAL
        elif score >= self.high_threshold:
            return EscalationPriority.HIGH
        else:
            return EscalationPriority.NORMAL

    def get_customer_message(self, priority: EscalationPriority) -> str:
        """Get customer-facing message for priority level."""
        return self.customer_messages.get(
            priority.value,
            self.customer_messages["NORMAL"],
        )


# Type alias for cleaner function signatures
EscalationMetadata = dict[str, Any]
