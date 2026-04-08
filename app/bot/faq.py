#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FAQ Module
Handles frequently asked questions without consuming AI tokens
"""

import json
from typing import Optional, Dict, Any
from pathlib import Path

# Absolute default path: repo_root/config/faqs.json (not cwd-relative)
_DEFAULT_FAQ_PATH = str(Path(__file__).resolve().parents[2] / "config" / "faqs.json")


class FAQHandler:
    """
    Handle FAQs with keyword matching
    Saves tokens by responding without AI
    """

    def __init__(self, faq_file: str = _DEFAULT_FAQ_PATH):
        """
        Initialize FAQ handler
        
        Args:
            faq_file: Path to FAQs JSON file
        """
        self.faq_file = faq_file
        self.faqs = self._load_faqs()
    
    def _load_faqs(self) -> Dict[str, Any]:
        """Load FAQs from JSON file"""
        try:
            with open(self.faq_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("preguntas_frecuentes", {})
        except FileNotFoundError:
            return {}
    
    def detect_faq(self, message: str) -> Optional[Dict[str, str]]:
        """
        Detect if message matches an FAQ
        
        Args:
            message: User's message
        
        Returns:
            FAQ dict with 'pregunta' and 'respuesta', or None
        """
        message_lower = message.lower()
        
        # Check each FAQ's keywords
        for faq_key, faq_data in self.faqs.items():
            keywords = faq_data.get("keywords", [])
            
            # Check if any keyword matches
            for keyword in keywords:
                if keyword.lower() in message_lower:
                    return {
                        "pregunta": faq_data["pregunta"],
                        "respuesta": faq_data["respuesta"],
                        "matched_keyword": keyword
                    }
        
        return None
    
    def get_faq_by_key(self, key: str) -> Optional[Dict[str, str]]:
        """Get specific FAQ by key"""
        if key in self.faqs:
            return {
                "pregunta": self.faqs[key]["pregunta"],
                "respuesta": self.faqs[key]["respuesta"]
            }
        return None
    
    def list_all_faqs(self) -> list:
        """List all available FAQs"""
        return [
            {
                "key": key,
                "pregunta": data["pregunta"]
            }
            for key, data in self.faqs.items()
        ]
