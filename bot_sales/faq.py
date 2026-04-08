#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FAQ Module
Handles frequently asked questions without consuming AI tokens
"""

import json
from typing import Optional, Dict, Any
from pathlib import Path
import yaml


class FAQHandler:
    """
    Handle FAQs with keyword matching
    Saves tokens by responding without AI
    """
    
    def __init__(self, faq_file: str = "faqs.json"):
        """
        Initialize FAQ handler
        
        Args:
            faq_file: Path to FAQs JSON file
        """
        self.faq_file = faq_file
        self._last_mtime = None
        self.faqs = self._load_faqs()

    def _resolved_path(self) -> Path:
        faq_path = Path(self.faq_file)
        if not faq_path.is_absolute():
            faq_path = Path(__file__).resolve().parent.parent / faq_path
        return faq_path

    def _maybe_reload(self) -> None:
        faq_path = self._resolved_path()
        mtime = faq_path.stat().st_mtime if faq_path.exists() else None
        if mtime != self._last_mtime:
            self.faqs = self._load_faqs()
    
    def _load_faqs(self) -> Dict[str, Any]:
        """Load FAQs from JSON file"""
        faq_path = self._resolved_path()
        try:
            with open(faq_path, 'r', encoding='utf-8') as f:
                if faq_path.suffix.lower() in {".yaml", ".yml"}:
                    data = yaml.safe_load(f) or {}
                    entries = data.get("entries", [])
                    normalized = {}
                    for entry in entries:
                        if not isinstance(entry, dict) or not entry.get("active", True):
                            continue
                        normalized[str(entry.get("id", "")).strip()] = {
                            "pregunta": entry.get("question", ""),
                            "respuesta": entry.get("answer", ""),
                            "keywords": entry.get("keywords", []),
                        }
                    self._last_mtime = faq_path.stat().st_mtime
                    return normalized
                data = json.load(f)
                self._last_mtime = faq_path.stat().st_mtime
                return data.get("preguntas_frecuentes", {})
        except FileNotFoundError:
            self._last_mtime = None
            return {}
    
    def detect_faq(self, message: str) -> Optional[Dict[str, str]]:
        """
        Detect if message matches an FAQ
        
        Args:
            message: User's message
        
        Returns:
            FAQ dict with 'pregunta' and 'respuesta', or None
        """
        self._maybe_reload()
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
        self._maybe_reload()
        if key in self.faqs:
            return {
                "pregunta": self.faqs[key]["pregunta"],
                "respuesta": self.faqs[key]["respuesta"]
            }
        return None
    
    def list_all_faqs(self) -> list:
        """List all available FAQs"""
        self._maybe_reload()
        return [
            {
                "key": key,
                "pregunta": data["pregunta"]
            }
            for key, data in self.faqs.items()
        ]
