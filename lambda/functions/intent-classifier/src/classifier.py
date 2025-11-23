"""Rule-based intent classification logic."""

import re
from typing import Any

from aws_lambda_powertools import Logger

from shared.types import IntentClassification

logger = Logger(child=True)

# Intent patterns with priority order (checked top to bottom)
INTENT_PATTERNS: list[dict[str, Any]] = [
    {
        "intent": "escalation",
        "patterns": [
            r"\b(speak to|talk to|get|want).{0,10}(manager|supervisor|human|person|representative|agent)\b",
            r"\b(escalate|urgent|emergency|critical)\b",
            r"\b(frustrated|angry|upset|disappointed|unacceptable)\b",
            r"\bnot (satisfied|happy|acceptable)\b",
        ],
        "requires_context": True,
    },
    {
        "intent": "complaint",
        "patterns": [
            r"\b(complaint|complain|problem|issue|wrong|broken|doesn'?t work|not working)\b",
            r"\b(terrible|horrible|awful|worst|poor|bad) (service|experience|quality)\b",
            r"\b(refund|money back|compensation)\b",
        ],
        "requires_context": True,
    },
    {
        "intent": "request",
        "patterns": [
            r"\b(need|want|would like|can you|could you|please).{0,30}(help|assist|send|provide|give|cancel|change|update)\b",
            r"\b(how (do|can) I|where (do|can) I|when (do|can) I)\b",
            r"\b(cancel|return|exchange|modify|update|change)\b",
        ],
        "requires_context": False,
    },
    {
        "intent": "question",
        "patterns": [
            r"^(what|when|where|who|why|how|is|are|do|does|can|could|would)\b",
            r"\b(tell me|explain|clarify|understand|wondering)\b",
            r"\?$",
        ],
        "requires_context": False,
    },
    {
        "intent": "greeting",
        "patterns": [
            r"^(hi|hello|hey|good morning|good afternoon|good evening|greetings)\b",
            r"\b(thanks|thank you|thx)\b",
            r"^(bye|goodbye|see you|talk to you later)\b",
        ],
        "requires_context": False,
    },
]


def classify_intent(
    message: str, conversation_history: list[dict[str, Any]] | None = None
) -> IntentClassification:
    """
    Classify user intent using rule-based pattern matching.

    Args:
        message: The user's message text
        conversation_history: Optional conversation history for context

    Returns:
        IntentClassification with intent, confidence, and metadata
    """
    message_lower = message.lower().strip()

    if not message_lower:
        logger.warning("Empty message received for classification")
        return IntentClassification(
            intent="question",
            confidence=0.5,
            requires_context=False,
        )

    logger.debug(f"Classifying message: {message_lower[:100]}")

    # Check patterns in priority order
    for intent_config in INTENT_PATTERNS:
        for pattern in intent_config["patterns"]:
            if re.search(pattern, message_lower, re.IGNORECASE):
                confidence = calculate_confidence(message_lower, pattern)

                result = IntentClassification(
                    intent=intent_config["intent"],
                    confidence=confidence,
                    requires_context=intent_config["requires_context"],
                    entities=extract_entities(message_lower, intent_config["intent"]),
                )

                logger.info(
                    "Intent classified",
                    extra={
                        "intent": result.intent,
                        "confidence": result.confidence,
                        "pattern": pattern,
                    },
                )

                return result

    # Default to "question" if no patterns match
    logger.info("No pattern matched, defaulting to 'question' intent")
    return IntentClassification(
        intent="question",
        confidence=0.3,
        requires_context=False,
    )


def calculate_confidence(message: str, pattern: str) -> float:
    """
    Calculate confidence score based on message characteristics.

    Args:
        message: The message text
        pattern: The matched regex pattern

    Returns:
        Confidence score between 0.0 and 1.0
    """
    base_confidence = 0.7

    # Increase confidence for longer, more specific messages
    word_count = len(message.split())
    if word_count > 10:
        base_confidence += 0.1
    elif word_count > 5:
        base_confidence += 0.05

    # Increase confidence for exact keyword matches
    if re.search(r"\b(urgent|emergency|escalate|manager)\b", message, re.IGNORECASE):
        base_confidence += 0.15

    # Cap at 0.95 (never 100% certain with rule-based)
    return min(base_confidence, 0.95)


def extract_entities(message: str, intent: str) -> dict[str, str]:
    """
    Extract relevant entities from the message based on intent.

    Args:
        message: The message text
        intent: The classified intent

    Returns:
        Dictionary of extracted entities
    """
    entities: dict[str, str] = {}

    # Extract order numbers - look for alphanumeric codes after keywords
    # Pattern: keyword + optional "number" or "#" + ID containing at least one digit
    order_match = re.search(
        r"\b(?:order|ticket|reference|confirmation)\s+(?:number\s+|#\s*)?([A-Z0-9][A-Z0-9-]{2,})\b",
        message,
        re.IGNORECASE,
    )
    if order_match:
        # Verify the captured group contains at least one digit
        captured = order_match.group(1)
        if re.search(r"\d", captured):
            entities["order_id"] = captured.upper()

    # Pattern 2: Standalone alphanumeric ID with at least one digit (fallback)
    if "order_id" not in entities:
        standalone_match = re.search(r"\b([A-Z]*\d[A-Z0-9-]{2,})\b", message, re.IGNORECASE)
        if standalone_match:
            entities["order_id"] = standalone_match.group(1).upper()

    # Extract product names (simple heuristic)
    if intent in ["complaint", "request"]:
        product_match = re.search(
            r"\b(product|item)\s+['\"]?([^'\".,]{3,20})['\"]?", message, re.IGNORECASE
        )
        if product_match:
            entities["product"] = product_match.group(2).strip()

    # Extract sentiment indicators for escalation
    if intent == "escalation":
        if re.search(r"\b(frustrated|angry|upset)\b", message, re.IGNORECASE):
            entities["sentiment"] = "negative"
        if re.search(r"\b(urgent|emergency|asap)\b", message, re.IGNORECASE):
            entities["urgency"] = "high"

    logger.debug(f"Extracted entities: {entities}")
    return entities
