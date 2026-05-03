#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import json
from typing import Dict, Any, Optional
from bot_sales.core.chatgpt import ChatGPTClient

logger = logging.getLogger(__name__)

class IntentClassifier:
    """
    Intelligent intent classifier for Ferretería Bot.
    Uses LLM to distinguish between sales, support, and conversational intents.
    """
    
    INTENTS = {
        "QUOTATION": "User is asking for products, prices, or making a new request for a quote.",
        "FOLLOW_UP": "User is responding to a previous bot question or selecting an option (A, B, C) to resolve a pending item.",
        "DETAILED_LOOKUP": "User is asking for specific technical details about a product.",
        "FAQ": "User is asking about policies (shipping, warranty, payments, schedules).",
        "GREETING_CHAT": "User is just saying hello, thank you, or making small talk.",
        "CUSTOMER_INFO": "User is providing personal data like name, phone, address, or rubro.",
        "HANDOFF_REQUEST": "User explicitly wants to talk to a human.",
        "ABANDON": "User wants to cancel, reset, or stop the conversation.",
    }

    PROMPT = """Analyze the user message and classify it into EXACTLY ONE of the following categories:
{intents_desc}

Respond ONLY with a JSON object in this format:
{{"intent": "CATEGORY_NAME", "confidence": 0.0-1.0, "reason": "short explanation"}}

Rules:
- If the user provides a name, phone, or location -> CUSTOMER_INFO.
- If the user says 'Hola', 'Gracias', 'Ok' -> GREETING_CHAT.
- If the user mentions a specific product or 'cuanto cuesta', 'tomas pedido' -> QUOTATION.
- If the user selects an option like 'La A', 'el segundo', '104-112' after being asked -> FOLLOW_UP.
- If the user asks 'donde estan', 'como envian' -> FAQ.
- Use QUOTATION if it looks like a purchase intent even if vague.
"""

    def __init__(self, chatgpt: ChatGPTClient):
        self.chatgpt = chatgpt

    def classify(self, message: str, context_summary: Optional[str] = None) -> Dict[str, Any]:
        """
        Classify human intent using LLM.
        """
        intents_desc = "\n".join([f"- {k}: {v}" for k, v in self.INTENTS.items()])
        
        user_content = f"Message: '{message}'"
        if context_summary:
            user_content = f"Context: {context_summary}\n{user_content}"

        messages = [
            {"role": "system", "content": self.PROMPT.format(intents_desc=intents_desc)},
            {"role": "user", "content": user_content}
        ]

        try:
            # Use a cheaper model if possible (e.g. gpt-3.5-turbo if the client supports it)
            # Default to the client's model
            response = self.chatgpt.send_message(messages)
            content = response.get("content", "").strip()
            
            # Extract JSON
            if "{" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                result = json.loads(content[start:end])
                return result
            
            return {"intent": "GREETING_CHAT", "confidence": 0.5, "reason": "fallback"}
        except Exception as e:
            logger.error(f"intent_classification_failed: {e}")
            return {"intent": "GREETING_CHAT", "confidence": 0.0, "reason": "error_fallback"}
