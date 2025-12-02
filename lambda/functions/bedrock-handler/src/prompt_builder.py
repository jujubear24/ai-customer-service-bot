"""Prompt builder for constructing system and user prompts.

This module composes prompts using Python f-strings, avoiding external
template dependencies like Jinja2. See ADR-009 for rationale.
"""

from prompts.guidelines import CUSTOMER_SERVICE_GUIDELINES
from prompts.safety import SAFETY_RULES
from prompts.system import BASE_SYSTEM_PROMPT
from shared.types import ConversationContext, MessageContext


def build_system_prompt(
    include_guidelines: bool = True,
    include_safety: bool = True,
    custom_instructions: str | None = None,
) -> str:
    """Build the complete system prompt.

    Args:
        include_guidelines: Include customer service guidelines.
        include_safety: Include safety rules.
        custom_instructions: Optional custom instructions to append.

    Returns:
        Composed system prompt string.
    """
    parts: list[str] = [BASE_SYSTEM_PROMPT]

    if include_guidelines:
        parts.append(CUSTOMER_SERVICE_GUIDELINES)

    if include_safety:
        parts.append(SAFETY_RULES)

    if custom_instructions:
        parts.append(f"## Additional Instructions\n\n{custom_instructions}")

    return "\n\n".join(parts)


def format_message_history(messages: list[MessageContext]) -> list[dict[str, str]]:
    """Format conversation history for Bedrock Messages API.

    Args:
        messages: List of message contexts from conversation history.

    Returns:
        List of message dicts with 'role' and 'content' keys.
    """
    formatted: list[dict[str, str]] = []

    for msg in messages:
        # Map internal roles to Bedrock roles
        role = msg.role.lower()
        if role == "user":
            formatted.append({"role": "user", "content": msg.content})
        elif role in ("assistant", "system"):
            # System messages in history are treated as assistant for context
            formatted.append({"role": "assistant", "content": msg.content})

    return formatted


def format_rag_context(documents: list[str]) -> str:
    """Format RAG documents for inclusion in prompt.

    Args:
        documents: List of retrieved document contents.

    Returns:
        Formatted string with numbered documents.
    """
    if not documents:
        return ""

    sections: list[str] = ["## Relevant Knowledge Base Articles\n"]

    for i, doc in enumerate(documents, 1):
        sections.append(f"### Document {i}\n{doc}\n")

    return "\n".join(sections)


def build_user_message(
    user_message: str,
    intent: str | None = None,
    entities: dict[str, str] | None = None,
    rag_context: list[str] | None = None,
) -> str:
    """Build the user message with optional context.

    For simple queries, returns the message as-is. For complex queries
    with RAG context, prepends the relevant documents.

    Args:
        user_message: The current user message.
        intent: Classified intent (for context, not included in prompt).
        entities: Extracted entities (for context, not included in prompt).
        rag_context: Retrieved documents to include.

    Returns:
        Formatted user message string.
    """
    parts: list[str] = []

    # Add RAG context if available (Phase 2.2)
    if rag_context:
        parts.append(format_rag_context(rag_context))
        parts.append("---\n")
        parts.append("Using the above information if relevant, please respond to:\n")

    parts.append(user_message)

    return "\n".join(parts)


def build_messages_payload(
    user_message: str,
    conversation_context: ConversationContext | None = None,
    intent: str | None = None,
    entities: dict[str, str] | None = None,
    rag_context: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build the complete messages array for Bedrock.

    Args:
        user_message: Current user message.
        conversation_context: Previous conversation history.
        intent: Classified intent.
        entities: Extracted entities.
        rag_context: Retrieved RAG documents.

    Returns:
        List of messages for Bedrock Messages API.
    """
    messages: list[dict[str, str]] = []

    # Add conversation history if available
    if conversation_context and conversation_context.messages:
        messages.extend(format_message_history(conversation_context.messages))

    # Add current user message
    formatted_user_message = build_user_message(
        user_message=user_message,
        intent=intent,
        entities=entities,
        rag_context=rag_context,
    )
    messages.append({"role": "user", "content": formatted_user_message})

    return messages
