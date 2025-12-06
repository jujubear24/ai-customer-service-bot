"""Tests for prompt_builder module."""

from prompt_builder import (
    build_messages_payload,
    build_system_prompt,
    build_user_message,
    format_message_history,
    format_rag_context,
)
from prompts.guidelines import CUSTOMER_SERVICE_GUIDELINES
from prompts.safety import SAFETY_RULES
from prompts.system import BASE_SYSTEM_PROMPT
from shared.types import ConversationContext, MessageContext


class TestBuildSystemPrompt:
    """Tests for build_system_prompt function."""

    def test_build_system_prompt_default(self) -> None:
        """Test default system prompt includes all components."""
        result = build_system_prompt()

        assert BASE_SYSTEM_PROMPT in result
        assert CUSTOMER_SERVICE_GUIDELINES in result
        assert SAFETY_RULES in result

    def test_build_system_prompt_without_guidelines(self) -> None:
        """Test system prompt without guidelines."""
        result = build_system_prompt(include_guidelines=False)

        assert BASE_SYSTEM_PROMPT in result
        assert CUSTOMER_SERVICE_GUIDELINES not in result
        assert SAFETY_RULES in result

    def test_build_system_prompt_without_safety(self) -> None:
        """Test system prompt without safety rules."""
        result = build_system_prompt(include_safety=False)

        assert BASE_SYSTEM_PROMPT in result
        assert CUSTOMER_SERVICE_GUIDELINES in result
        assert SAFETY_RULES not in result

    def test_build_system_prompt_minimal(self) -> None:
        """Test minimal system prompt."""
        result = build_system_prompt(include_guidelines=False, include_safety=False)

        assert BASE_SYSTEM_PROMPT in result
        assert CUSTOMER_SERVICE_GUIDELINES not in result
        assert SAFETY_RULES not in result

    def test_build_system_prompt_with_custom_instructions(self) -> None:
        """Test system prompt with custom instructions."""
        custom = "Always respond in Spanish."
        result = build_system_prompt(custom_instructions=custom)

        assert BASE_SYSTEM_PROMPT in result
        assert "Additional Instructions" in result
        assert custom in result


class TestFormatMessageHistory:
    """Tests for format_message_history function."""

    def test_format_empty_history(self) -> None:
        """Test formatting empty message history."""
        result = format_message_history([])
        assert result == []

    def test_format_user_message(self) -> None:
        """Test formatting user message."""
        messages = [
            MessageContext(
                message_id="msg-1",
                role="USER",
                content="Hello",
                timestamp="2025-01-15T10:00:00Z",
            )
        ]
        result = format_message_history(messages)

        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "Hello"}

    def test_format_assistant_message(self) -> None:
        """Test formatting assistant message."""
        messages = [
            MessageContext(
                message_id="msg-1",
                role="ASSISTANT",
                content="Hi there!",
                timestamp="2025-01-15T10:00:00Z",
            )
        ]
        result = format_message_history(messages)

        assert len(result) == 1
        assert result[0] == {"role": "assistant", "content": "Hi there!"}

    def test_format_system_message_as_assistant(self) -> None:
        """Test that system messages are formatted as assistant."""
        messages = [
            MessageContext(
                message_id="msg-1",
                role="SYSTEM",
                content="System note",
                timestamp="2025-01-15T10:00:00Z",
            )
        ]
        result = format_message_history(messages)

        assert len(result) == 1
        assert result[0] == {"role": "assistant", "content": "System note"}

    def test_format_conversation_history(self) -> None:
        """Test formatting multi-turn conversation."""
        messages = [
            MessageContext(
                message_id="msg-1",
                role="USER",
                content="What's your return policy?",
                timestamp="2025-01-15T10:00:00Z",
            ),
            MessageContext(
                message_id="msg-2",
                role="ASSISTANT",
                content="Our return policy allows returns within 30 days.",
                timestamp="2025-01-15T10:00:05Z",
            ),
            MessageContext(
                message_id="msg-3",
                role="USER",
                content="What about damaged items?",
                timestamp="2025-01-15T10:00:10Z",
            ),
        ]
        result = format_message_history(messages)

        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"


class TestFormatRagContext:
    """Tests for format_rag_context function."""

    def test_format_empty_rag_context(self) -> None:
        """Test formatting empty RAG context."""
        result = format_rag_context([])
        assert result == ""

    def test_format_none_rag_context(self) -> None:
        """Test formatting None RAG context."""
        result = format_rag_context([])
        assert result == ""

    def test_format_single_document(self) -> None:
        """Test formatting single RAG document."""
        docs = ["Return Policy: Items can be returned within 30 days."]
        result = format_rag_context(docs)

        assert "Relevant Knowledge Base Articles" in result
        assert "Document 1" in result
        assert "Return Policy" in result

    def test_format_multiple_documents(self) -> None:
        """Test formatting multiple RAG documents."""
        docs = [
            "Return Policy: 30 days.",
            "Shipping: Standard and express options.",
            "Contact: support@example.com",
        ]
        result = format_rag_context(docs)

        assert "Document 1" in result
        assert "Document 2" in result
        assert "Document 3" in result
        assert "Return Policy" in result
        assert "Shipping" in result
        assert "Contact" in result


class TestBuildUserMessage:
    """Tests for build_user_message function."""

    def test_build_simple_message(self) -> None:
        """Test building simple user message."""
        result = build_user_message("What is your return policy?")
        assert result == "What is your return policy?"

    def test_build_message_with_intent(self) -> None:
        """Test that intent doesn't modify message (used for logging only)."""
        result = build_user_message(
            "What is your return policy?",
            intent="question",
        )
        # Intent is for context, not included in prompt
        assert result == "What is your return policy?"

    def test_build_message_with_rag_context(self) -> None:
        """Test building message with RAG context."""
        rag_docs = ["Return Policy: 30 days for full refund."]
        result = build_user_message(
            "What is your return policy?",
            rag_context=rag_docs,
        )

        assert "Relevant Knowledge Base Articles" in result
        assert "Return Policy" in result
        assert "What is your return policy?" in result
        assert "Using the above information" in result


class TestBuildMessagesPayload:
    """Tests for build_messages_payload function."""

    def test_build_payload_simple(self) -> None:
        """Test building simple message payload."""
        result = build_messages_payload("Hello")

        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "Hello"}

    def test_build_payload_with_context(self) -> None:
        """Test building payload with conversation context."""
        context = ConversationContext(
            conversation_id="conv-123",
            messages=[
                MessageContext(
                    message_id="msg-1",
                    role="USER",
                    content="Hi",
                    timestamp="2025-01-15T10:00:00Z",
                ),
                MessageContext(
                    message_id="msg-2",
                    role="ASSISTANT",
                    content="Hello!",
                    timestamp="2025-01-15T10:00:05Z",
                ),
            ],
        )
        result = build_messages_payload(
            "What's your return policy?",
            conversation_context=context,
        )

        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hi"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "Hello!"
        assert result[2]["role"] == "user"
        assert result[2]["content"] == "What's your return policy?"

    def test_build_payload_with_rag(self) -> None:
        """Test building payload with RAG context."""
        result = build_messages_payload(
            "How do I return an item?",
            rag_context=["Return items within 30 days."],
        )

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "Relevant Knowledge Base Articles" in result[0]["content"]
        assert "How do I return an item?" in result[0]["content"]

    def test_build_payload_empty_context(self) -> None:
        """Test building payload with empty conversation context."""
        context = ConversationContext(
            conversation_id="conv-123",
            messages=[],
        )
        result = build_messages_payload(
            "Hello",
            conversation_context=context,
        )

        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "Hello"}
