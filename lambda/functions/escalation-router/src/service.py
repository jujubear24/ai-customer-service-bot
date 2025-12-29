"""Escalation Router service for routing conversations to human agents."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit

from models import (
    DynamoDBEscalationUpdate,
    EscalationMessage,
    EscalationPriority,
    EscalationRequest,
    EscalationResponse,
    EscalationRouterConfig,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_sns import SNSClient
    from mypy_boto3_sqs import SQSClient

logger = Logger()
tracer = Tracer()
metrics = Metrics()


class EscalationRouterError(Exception):
    """Base exception for Escalation Router errors."""

    pass


class QueueError(EscalationRouterError):
    """Error sending message to SQS queue."""

    pass


class DatabaseError(EscalationRouterError):
    """Error updating DynamoDB."""

    pass


class NotificationError(EscalationRouterError):
    """Error sending SNS notification."""

    pass


class EscalationRouterService:
    """Service for routing escalated conversations to human agents.

    Handles:
    - Priority determination based on escalation score
    - Sending messages to SQS FIFO queue
    - Updating conversation status in DynamoDB
    - Optional SNS notifications for real-time alerts
    """

    def __init__(
        self,
        config: EscalationRouterConfig | None = None,
        sqs_client: SQSClient | None = None,
        dynamodb_client: DynamoDBClient | None = None,
        sns_client: SNSClient | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            config: Service configuration. Defaults to EscalationRouterConfig().
            sqs_client: SQS client for queue operations.
            dynamodb_client: DynamoDB client for status updates.
            sns_client: SNS client for notifications.
        """
        self.config = config or EscalationRouterConfig()
        self._sqs_client = sqs_client
        self._dynamodb_client = dynamodb_client
        self._sns_client = sns_client

    @property
    def sqs_client(self) -> SQSClient:
        """Lazy-load SQS client."""
        if self._sqs_client is None:
            import boto3

            self._sqs_client = boto3.client("sqs")
        return self._sqs_client

    @property
    def dynamodb_client(self) -> DynamoDBClient:
        """Lazy-load DynamoDB client."""
        if self._dynamodb_client is None:
            import boto3

            self._dynamodb_client = boto3.client("dynamodb")
        return self._dynamodb_client

    @property
    def sns_client(self) -> SNSClient:
        """Lazy-load SNS client."""
        if self._sns_client is None:
            import boto3

            self._sns_client = boto3.client("sns")
        return self._sns_client

    @tracer.capture_method
    def route_escalation(self, request: EscalationRequest) -> EscalationResponse:
        """Route an escalated conversation to the agent queue.

        Args:
            request: Escalation request from Chat Orchestrator.

        Returns:
            EscalationResponse with routing results.
        """
        start_time = datetime.utcnow()
        escalation_id = self._generate_escalation_id()

        logger.info(
            "Processing escalation",
            extra={
                "escalation_id": escalation_id,
                "conversation_id": request.conversation_id,
                "escalation_score": request.escalation.score,
            },
        )

        # Determine priority
        priority = self.config.determine_priority(request.escalation.score)
        logger.info(f"Determined priority: {priority.value}")

        # Track metrics
        metrics.add_metric(name="EscalationsRouted", unit=MetricUnit.Count, value=1)
        metrics.add_metric(
            name=f"EscalationPriority_{priority.value}",
            unit=MetricUnit.Count,
            value=1,
        )

        # Build escalation message
        message = self._build_escalation_message(
            request=request,
            escalation_id=escalation_id,
            priority=priority,
        )

        # Initialize response tracking
        queue_message_id: str | None = None
        notification_sent = False
        error_message: str | None = None

        # Step 1: Update DynamoDB
        if self.config.enable_dynamodb_update:
            try:
                self._update_conversation_status(
                    request=request,
                    escalation_id=escalation_id,
                    priority=priority,
                )
            except Exception as e:
                logger.error(f"Failed to update DynamoDB: {e}")
                metrics.add_metric(
                    name="EscalationDynamoDBErrors",
                    unit=MetricUnit.Count,
                    value=1,
                )
                error_message = f"DynamoDB update failed: {e}"
                # Continue - queue message is more important

        # Step 2: Send to SQS queue
        if self.config.enable_queue:
            try:
                queue_message_id = self._send_to_queue(message)
            except Exception as e:
                logger.error(f"Failed to send to queue: {e}")
                metrics.add_metric(
                    name="EscalationQueueErrors",
                    unit=MetricUnit.Count,
                    value=1,
                )
                error_message = f"Queue send failed: {e}"
                # This is critical - raise the error
                raise QueueError(f"Failed to send escalation to queue: {e}") from e

        # Step 3: Send SNS notification (optional)
        if self.config.enable_sns_notifications and self.config.sns_topic_arn:
            try:
                self._send_notification(message, priority)
                notification_sent = True
            except Exception as e:
                logger.warning(f"Failed to send SNS notification: {e}")
                metrics.add_metric(
                    name="EscalationSNSErrors",
                    unit=MetricUnit.Count,
                    value=1,
                )
                # Don't fail the request for notification errors

        # Calculate processing time
        processing_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        metrics.add_metric(
            name="EscalationRoutingLatency",
            unit=MetricUnit.Milliseconds,
            value=processing_time_ms,
        )

        # Build response
        response = EscalationResponse(
            success=True,
            escalation_id=escalation_id,
            priority=priority,
            queue_message_id=queue_message_id,
            notification_sent=notification_sent,
            customer_message=self.config.get_customer_message(priority),
            estimated_wait=self._get_estimated_wait(priority),
            processed_at=datetime.utcnow(),
            error_message=error_message,
        )

        logger.info(
            "Escalation routed successfully",
            extra={
                "escalation_id": escalation_id,
                "priority": priority.value,
                "queue_message_id": queue_message_id,
                "processing_time_ms": processing_time_ms,
            },
        )

        return response

    def _generate_escalation_id(self) -> str:
        """Generate a unique escalation ID."""
        return f"esc-{uuid.uuid4().hex[:12]}"

    def _build_escalation_message(
        self,
        request: EscalationRequest,
        escalation_id: str,
        priority: EscalationPriority,
    ) -> EscalationMessage:
        """Build the escalation message for SQS."""
        return EscalationMessage(
            escalation_id=escalation_id,
            conversation_id=request.conversation_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            priority=priority,
            escalation_score=request.escalation.score,
            primary_reason=request.escalation.primary_reason,
            factors=request.escalation.factors,
            sentiment=request.sentiment.sentiment if request.sentiment else None,
            last_user_message=request.last_user_message,
            message_count=request.message_count,
            created_at=datetime.utcnow(),
            metadata={
                "intent": request.intent,
                "urgency": request.urgency,
                "intent_confidence": request.intent_confidence,
                "previous_intents": request.previous_intents,
                **request.metadata,
            },
        )

    @tracer.capture_method
    def _send_to_queue(self, message: EscalationMessage) -> str:
        """Send escalation message to SQS FIFO queue.

        Args:
            message: Escalation message to send.

        Returns:
            SQS message ID.

        Raises:
            QueueError: If sending fails.
        """
        if not self.config.queue_url:
            raise QueueError("Queue URL not configured")

        sqs_message = message.to_sqs_message()

        logger.debug(
            "Sending to SQS",
            extra={
                "queue_url": self.config.queue_url,
                "message_group_id": sqs_message["MessageGroupId"],
            },
        )

        response = self.sqs_client.send_message(
            QueueUrl=self.config.queue_url,
            MessageBody=sqs_message["MessageBody"],
            MessageGroupId=sqs_message["MessageGroupId"],
            MessageDeduplicationId=sqs_message["MessageDeduplicationId"],
        )

        message_id: str = response["MessageId"]
        logger.info(f"Message sent to queue: {message_id}")
        return message_id

    @tracer.capture_method
    def _update_conversation_status(
        self,
        request: EscalationRequest,
        escalation_id: str,
        priority: EscalationPriority,
    ) -> None:
        """Update conversation status in DynamoDB.

        Args:
            request: Original escalation request.
            escalation_id: Generated escalation ID.
            priority: Determined priority level.

        Raises:
            DatabaseError: If update fails.
        """
        update = DynamoDBEscalationUpdate(
            conversation_id=request.conversation_id,
            escalation_id=escalation_id,
            escalation_score=request.escalation.score,
            escalation_reason=request.escalation.primary_reason,
            escalation_priority=priority,
        )

        update_params = update.to_update_expression()

        logger.debug(
            "Updating DynamoDB",
            extra={
                "table": self.config.table_name,
                "conversation_id": request.conversation_id,
            },
        )

        self.dynamodb_client.update_item(
            TableName=self.config.table_name,
            Key={
                "pk": {"S": f"CONV#{request.conversation_id}"},
                "sk": {"S": "METADATA"},
            },
            UpdateExpression=update_params["UpdateExpression"],
            ExpressionAttributeNames=update_params["ExpressionAttributeNames"],
            ExpressionAttributeValues={
                k: {"S": str(v)} if v is not None else {"NULL": True}
                for k, v in update_params["ExpressionAttributeValues"].items()
            },
        )

        logger.info(f"Conversation {request.conversation_id} status updated to ESCALATED")

    @tracer.capture_method
    def _send_notification(
        self,
        message: EscalationMessage,
        priority: EscalationPriority,
    ) -> None:
        """Send SNS notification for real-time agent alerts.

        Args:
            message: Escalation message details.
            priority: Priority level for notification.

        Raises:
            NotificationError: If notification fails.
        """
        if not self.config.sns_topic_arn:
            raise NotificationError("SNS topic ARN not configured")

        subject = f"[{priority.value}] Escalation: {message.conversation_id}"

        notification_body = {
            "escalation_id": message.escalation_id,
            "conversation_id": message.conversation_id,
            "priority": priority.value,
            "score": message.escalation_score,
            "reason": message.primary_reason,
            "sentiment": message.sentiment,
            "last_message": message.last_user_message[:200],  # Truncate for notification
            "created_at": message.created_at.isoformat(),
        }

        import json

        self.sns_client.publish(
            TopicArn=self.config.sns_topic_arn,
            Subject=subject[:100],  # SNS subject limit
            Message=json.dumps(notification_body, indent=2),
            MessageAttributes={
                "priority": {
                    "DataType": "String",
                    "StringValue": priority.value,
                },
                "tenant_id": {
                    "DataType": "String",
                    "StringValue": message.tenant_id,
                },
            },
        )

        logger.info(f"SNS notification sent for escalation {message.escalation_id}")

    def _get_estimated_wait(self, priority: EscalationPriority) -> str:
        """Get estimated wait time based on priority."""
        wait_times = {
            EscalationPriority.CRITICAL: "< 2 minutes",
            EscalationPriority.HIGH: "< 5 minutes",
            EscalationPriority.NORMAL: "< 10 minutes",
        }
        return wait_times.get(priority, "< 10 minutes")


# Convenience functions for creating service instances


def create_escalation_router(
    queue_url: str = "",
    sns_topic_arn: str = "",
    table_name: str = "conversations",
    enable_sns: bool = False,
) -> EscalationRouterService:
    """Create an escalation router service with common configuration.

    Args:
        queue_url: SQS FIFO queue URL.
        sns_topic_arn: SNS topic ARN for notifications.
        table_name: DynamoDB table name.
        enable_sns: Whether to enable SNS notifications.

    Returns:
        Configured EscalationRouterService instance.
    """
    config = EscalationRouterConfig(
        queue_url=queue_url,
        sns_topic_arn=sns_topic_arn,
        table_name=table_name,
        enable_sns_notifications=enable_sns,
    )
    return EscalationRouterService(config=config)


def create_escalation_router_from_env() -> EscalationRouterService:
    """Create an escalation router service from environment variables.

    Environment variables:
        ESCALATION_QUEUE_URL: SQS FIFO queue URL
        ESCALATION_SNS_TOPIC_ARN: SNS topic ARN
        ENABLE_SNS_NOTIFICATIONS: 'true' to enable
        DYNAMODB_TABLE_NAME: DynamoDB table name
        CRITICAL_THRESHOLD: Score for CRITICAL priority
        HIGH_THRESHOLD: Score for HIGH priority

    Returns:
        Configured EscalationRouterService instance.
    """
    import os

    config = EscalationRouterConfig(
        queue_url=os.environ.get("ESCALATION_QUEUE_URL", ""),
        sns_topic_arn=os.environ.get("ESCALATION_SNS_TOPIC_ARN", ""),
        enable_sns_notifications=os.environ.get("ENABLE_SNS_NOTIFICATIONS", "false").lower()
        == "true",
        table_name=os.environ.get("DYNAMODB_TABLE_NAME", "conversations"),
        enable_queue=os.environ.get("ENABLE_QUEUE", "true").lower() == "true",
        enable_dynamodb_update=os.environ.get("ENABLE_DYNAMODB_UPDATE", "true").lower() == "true",
        critical_threshold=float(os.environ.get("CRITICAL_THRESHOLD", "0.90")),
        high_threshold=float(os.environ.get("HIGH_THRESHOLD", "0.80")),
    )

    return EscalationRouterService(config=config)
