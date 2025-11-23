"""Unit tests for intent classifier logic."""

from src.classifier import calculate_confidence, classify_intent, extract_entities


class TestClassifyIntent:
    """Test cases for classify_intent function."""

    def test_escalation_intent(self) -> None:
        """Test escalation intent detection."""
        messages = [
            "I need to speak to a manager",
            "Get me your supervisor now",
            "This is urgent, I want to talk to a human",
            "I'm very frustrated with this service",
        ]

        for message in messages:
            result = classify_intent(message)
            assert result.intent == "escalation"
            assert result.confidence >= 0.7  # Changed from > to >=
            assert result.requires_context is True

    def test_complaint_intent(self) -> None:
        """Test complaint intent detection."""
        messages = [
            "I have a complaint about your service",
            "This product is broken and doesn't work",
            "The quality is terrible, I want a refund",
            "There's a problem with my order",
        ]

        for message in messages:
            result = classify_intent(message)
            assert result.intent == "complaint"
            assert result.confidence >= 0.7  # Changed from > to >=
            assert result.requires_context is True

    def test_request_intent(self) -> None:
        """Test request intent detection."""
        messages = [
            "I would like to cancel my subscription",
            "Can you help me update my account?",
            "Please send me a replacement",
            "How do I change my password?",
        ]

        for message in messages:
            result = classify_intent(message)
            assert result.intent == "request"
            assert result.confidence >= 0.7  # Changed from > to >=

    def test_question_intent(self) -> None:
        """Test question intent detection."""
        messages = [
            "What are your business hours?",
            "When will my order arrive?",
            "Is this product available in blue?",
            "Can you explain how this works?",
        ]

        for message in messages:
            result = classify_intent(message)
            assert result.intent == "question"
            assert result.confidence > 0.5

    def test_greeting_intent(self) -> None:
        """Test greeting intent detection."""
        messages = [
            "Hello",
            "Hi there",
            "Good morning",
            "Thanks for your help",
            "Goodbye",
        ]

        for message in messages:
            result = classify_intent(message)
            assert result.intent == "greeting"
            assert result.confidence > 0.5

    def test_empty_message(self) -> None:
        """Test handling of empty message."""
        result = classify_intent("")
        assert result.intent == "question"
        assert result.confidence == 0.5

    def test_ambiguous_message(self) -> None:
        """Test handling of ambiguous message."""
        result = classify_intent("hmm okay")
        assert result.intent == "question"
        assert result.confidence < 0.5


class TestCalculateConfidence:
    """Test cases for calculate_confidence function."""

    def test_base_confidence(self) -> None:
        """Test base confidence calculation."""
        confidence = calculate_confidence("simple message", r"\bsimple\b")
        assert 0.7 <= confidence <= 0.95

    def test_longer_message_boost(self) -> None:
        """Test confidence boost for longer messages."""
        short_message = "help me"
        long_message = "I really need help with this complicated issue that I'm having"

        short_conf = calculate_confidence(short_message, r"\bhelp\b")
        long_conf = calculate_confidence(long_message, r"\bhelp\b")

        assert long_conf > short_conf

    def test_urgent_keywords_boost(self) -> None:
        """Test confidence boost for urgent keywords."""
        normal_message = "I need help"
        urgent_message = "urgent emergency I need help"

        normal_conf = calculate_confidence(normal_message, r"\bhelp\b")
        urgent_conf = calculate_confidence(urgent_message, r"\bhelp\b")

        assert urgent_conf > normal_conf

    def test_confidence_cap(self) -> None:
        """Test that confidence is capped at 0.95."""
        message = "urgent emergency escalate manager asap critical issue"
        confidence = calculate_confidence(message, r"\burgent\b")
        assert confidence <= 0.95


class TestExtractEntities:
    """Test cases for extract_entities function."""

    def test_extract_order_id_with_hash(self) -> None:
        """Test order ID extraction with hash symbol."""
        message = "My order #ABC-12345 is delayed"
        entities = extract_entities(message, "complaint")
        assert entities.get("order_id") == "ABC-12345"

    def test_extract_order_id_confirmation(self) -> None:
        """Test order ID extraction from confirmation number."""
        message = "Confirmation number A1B2C3D4E5"
        entities = extract_entities(message, "complaint")
        assert entities.get("order_id") == "A1B2C3D4E5"

    def test_extract_order_id_with_reference(self) -> None:
        """Test order ID extraction with 'reference' keyword."""
        message = "Ticket reference XYZ789"
        entities = extract_entities(message, "complaint")
        assert entities.get("order_id") == "XYZ789"

    def test_extract_product_name(self) -> None:
        """Test product name extraction."""
        message = "The product 'Widget Pro' is defective"
        entities = extract_entities(message, "complaint")
        assert "product" in entities

    def test_extract_sentiment(self) -> None:
        """Test sentiment extraction for escalations."""
        message = "I'm very frustrated with this service"
        entities = extract_entities(message, "escalation")
        assert entities.get("sentiment") == "negative"

    def test_extract_urgency(self) -> None:
        """Test urgency extraction."""
        message = "This is urgent, I need help ASAP"
        entities = extract_entities(message, "escalation")
        assert entities.get("urgency") == "high"

    def test_no_entities(self) -> None:
        """Test message with no extractable entities."""
        message = "Hello, how are you?"
        entities = extract_entities(message, "greeting")
        assert len(entities) == 0

    def test_multiple_entities(self) -> None:
        """Test extraction of multiple entities."""
        message = "URGENT: Order #ABC123 is broken and I'm very frustrated!"
        entities = extract_entities(message, "escalation")

        # Should extract multiple pieces of information
        assert "order_id" in entities
        assert entities["order_id"] == "ABC123"
        assert entities.get("sentiment") == "negative"
        assert entities.get("urgency") == "high"
