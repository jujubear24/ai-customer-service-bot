"""Prompt templates for the Bedrock Handler."""

from prompts.guidelines import CUSTOMER_SERVICE_GUIDELINES
from prompts.safety import SAFETY_RULES
from prompts.system import BASE_SYSTEM_PROMPT

__all__ = [
    "BASE_SYSTEM_PROMPT",
    "CUSTOMER_SERVICE_GUIDELINES",
    "SAFETY_RULES",
]
