import re
from typing import Literal, cast

from shared.types import IntentClassification

# Weight Multipliers: Used to prioritize one type of intent over another when
# multiple patterns match the same message.
WEIGHT_BOOST = 1.5
WEIGHT_STANDARD = 1.0


class IntentClassifier:
    """Simple rule-based classifier for customer service intents.

    This classifier uses regex patterns to score messages against known intents.
    It serves as the quick, initial classification stage of the conversational flow.
    """

    # Dictionary mapping intent names to a list of regex patterns.
    # The classification logic explicitly weights 'escalation' and 'technical_support' higher.
    INTENT_PATTERNS: dict[str, list[str]] = {
        "greeting": [
            r"\b(hi|hello|hey|good morning|good afternoon|greetings)\b",
            r"^hi there",
            r"\b(thanks|thank you|thx)\b",
            r"^(bye|goodbye|see you|talk to you later)\b",
        ],
        "complaint": [
            r"\b(angry|upset|frustrated|bad service|terrible|awful|broken|hate)\b",
            r"\b(refund|money back|chargeback)\b",
            r"\b(doesn't work|not working|failed|error)\b",
        ],
        # FIX for Test 2 (Shipping): Stronger, more specific keywords
        "shipping": [
            r"\b(shipping|delivery|shipment|tracking)\b",
            r"\b(order status|where is my order|when will it arrive)\b",
            r"\b(track|arrived|late|delayed|lost)\b",
        ],
        # FIX for Test 4 (Technical Support): Stronger, more specific keywords
        "technical_support": [
            r"\b(login|password|reset|account|access|cant log in)\b",
            r"\b(bug|glitch|crash|screen|update|configuration|api|database|system)\b",
            r"\b(install|software|hardware|compatibility)\b",
        ],
        "escalation": [
            r"\b(speak to a human|talk to a person|representative|agent|manager)\b",
            r"\b(emergency|urgent)\b",
        ],
        # General Request is classified as 'question' in the end state
        "general_request": [
            r"\b(what is|how do i|can you tell me|i want to)\b",
            r"\b(information|details|request|inquire)\b",
        ],
    }

    def classify(self, message: str) -> IntentClassification:
        """
        Classify the user's message into a predefined intent using rule-based scoring.

        Args:
            message: The user's raw message string.

        Returns:
            IntentClassification model with the detected intent and confidence.
        """
        message_lower = message.lower()

        scores: dict[str, float] = dict.fromkeys(self.INTENT_PATTERNS, 0.0)

        # 1. Calculate scores based on pattern matching
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    # Apply weight multiplier
                    weight = (
                        WEIGHT_BOOST
                        if intent in ["technical_support", "escalation"]
                        else WEIGHT_STANDARD
                    )
                    scores[intent] += weight

        # 2. Determine the best matching intent
        best_intent = "question"  # Default fallback if no match is found
        max_score = 0.0

        for intent, score in scores.items():
            if score > max_score:
                max_score = score
                best_intent = intent
            elif score == max_score and score > 0:
                # Tie-breaker: prefer the current best_intent unless the new intent
                # is more specific (i.e., not a generic request/question)
                if best_intent in ["question", "general_request"]:
                    best_intent = intent

        # 3. Finalize intent and confidence

        # Unify 'general_request' into 'question' for external systems
        if best_intent == "general_request":
            best_intent = "question"

        # Type assertion for mypy - ensure best_intent is a valid literal
        valid_intent = cast(
            Literal[
                "greeting",
                "question",
                "complaint",
                "request",
                "escalation",
                "shipping",
                "technical_support",
            ],
            best_intent,
        )

        # Simple confidence heuristic: scales base on number/weight of matches
        confidence = min(1.0, max(0.5, max_score * 0.5)) if max_score > 0 else 0.5

        # Determine if conversation context is required (all intents except greetings/escalations)
        requires_context = valid_intent not in ["greeting", "escalation"]

        return IntentClassification(
            intent=valid_intent,
            confidence=confidence,
            requires_context=requires_context,
            entities={},
        )
