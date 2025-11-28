"""
DynamoDB repository for conversation management.
"""

from datetime import datetime, timedelta
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from shared.models.dynamodb import (
    ConversationMetadata,
    MessageRecord,
    UserProfile,
)

logger = Logger(child=True)


class ConversationRepository:
    """Repository for conversation and message operations."""

    def __init__(self, table_name: str) -> None:
        """Initialize repository."""
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(table_name)

    def create_conversation(self, conversation_id: str, user_id: str) -> ConversationMetadata:
        """Create a new conversation."""
        metadata = ConversationMetadata.create(conversation_id=conversation_id, user_id=user_id)

        # Set TTL to 30 days from now
        ttl = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        item = metadata.model_dump()
        item["ttl"] = ttl

        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
            logger.info(
                "Created conversation",
                extra={"conversation_id": conversation_id, "user_id": user_id},
            )
            return metadata
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(
                    "Conversation already exists", extra={"conversation_id": conversation_id}
                )
                # Return existing conversation
                return self.get_conversation(conversation_id)  # type: ignore
            raise

    def get_conversation(self, conversation_id: str) -> ConversationMetadata | None:
        """Get conversation metadata."""
        try:
            response = self.table.get_item(Key={"pk": f"CONV#{conversation_id}", "sk": "METADATA"})
            item = response.get("Item")
            return ConversationMetadata.model_validate(item) if item else None
        except ClientError as e:
            logger.error(
                "Failed to get conversation",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )
            raise

    def update_conversation_status(
        self, conversation_id: str, status: str, escalation_reason: str | None = None
    ) -> None:
        """Update conversation status."""
        update_expr = "SET #status = :status, updated_at = :updated_at, gsi2_pk = :gsi2_pk"
        expr_attr_names = {"#status": "status"}
        expr_attr_values = {
            ":status": status,
            ":updated_at": datetime.utcnow().isoformat(),
            ":gsi2_pk": f"STATUS#{status}",
        }

        if escalation_reason:
            update_expr += ", escalation_reason = :escalation_reason"
            expr_attr_values[":escalation_reason"] = escalation_reason

        try:
            self.table.update_item(
                Key={"pk": f"CONV#{conversation_id}", "sk": "METADATA"},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
            )
            logger.info(
                "Updated conversation status",
                extra={"conversation_id": conversation_id, "status": status},
            )
        except ClientError as e:
            logger.error(
                "Failed to update conversation status",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )
            raise

    def add_message(
        self,
        conversation_id: str,
        message_id: str,
        role: str,
        content: str,
        intent: str | None = None,
        entities: dict[str, str] | None = None,
    ) -> MessageRecord:
        """Add a message to a conversation."""
        message = MessageRecord.create(
            conversation_id=conversation_id,
            message_id=message_id,
            role=role,
            content=content,
            intent=intent,
            entities=entities,
        )

        # Set TTL to 30 days from now
        ttl = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        item = message.model_dump()
        item["ttl"] = ttl

        try:
            # Add message
            self.table.put_item(Item=item)

            # Increment message count
            self.table.update_item(
                Key={"pk": f"CONV#{conversation_id}", "sk": "METADATA"},
                UpdateExpression="SET message_count = message_count + :inc, updated_at = :updated_at",
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":updated_at": datetime.utcnow().isoformat(),
                },
            )

            logger.info(
                "Added message",
                extra={
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "role": role,
                },
            )
            return message
        except ClientError as e:
            logger.error(
                "Failed to add message",
                extra={
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "error": str(e),
                },
            )
            raise

    def get_messages(self, conversation_id: str, limit: int | None = None) -> list[MessageRecord]:
        """Get messages for a conversation in chronological order."""
        query_params: dict[str, Any] = {
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :sk_prefix)",
            "ExpressionAttributeValues": {
                ":pk": f"CONV#{conversation_id}",
                ":sk_prefix": "MSG#",
            },
            "ScanIndexForward": True,  # Ascending (oldest first)
        }

        if limit:
            query_params["Limit"] = limit

        try:
            response = self.table.query(**query_params)
            items = response.get("Items", [])
            return [MessageRecord.model_validate(item) for item in items]
        except ClientError as e:
            logger.error(
                "Failed to get messages",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )
            raise

    def get_user_conversations(self, user_id: str, limit: int = 10) -> list[ConversationMetadata]:
        """Get user's recent conversations."""
        try:
            response = self.table.query(
                IndexName="GSI1",
                KeyConditionExpression="gsi1_pk = :gsi1_pk",
                ExpressionAttributeValues={":gsi1_pk": f"USER#{user_id}"},
                ScanIndexForward=False,  # Descending (newest first)
                Limit=limit,
            )
            items = response.get("Items", [])
            return [ConversationMetadata.model_validate(item) for item in items]
        except ClientError as e:
            logger.error(
                "Failed to get user conversations",
                extra={"user_id": user_id, "error": str(e)},
            )
            raise

    def get_conversations_by_status(
        self, status: str, limit: int = 100
    ) -> list[ConversationMetadata]:
        """Get conversations by status (e.g., ESCALATED)."""
        try:
            response = self.table.query(
                IndexName="GSI2",
                KeyConditionExpression="gsi2_pk = :gsi2_pk",
                ExpressionAttributeValues={":gsi2_pk": f"STATUS#{status}"},
                ScanIndexForward=False,  # Descending (newest first)
                Limit=limit,
            )
            items = response.get("Items", [])
            return [ConversationMetadata.model_validate(item) for item in items]
        except ClientError as e:
            logger.error(
                "Failed to get conversations by status",
                extra={"status": status, "error": str(e)},
            )
            raise

    def create_or_get_user_profile(self, user_id: str, email: str | None = None) -> UserProfile:
        """Create or retrieve user profile."""
        profile = UserProfile.create(user_id=user_id, email=email)
        item = profile.model_dump()

        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
            logger.info("Created user profile", extra={"user_id": user_id})
            return profile
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Profile exists, get it
                response = self.table.get_item(Key={"pk": f"USER#{user_id}", "sk": "PROFILE"})
                item = response.get("Item")
                return UserProfile.model_validate(item) if item else profile
            raise
