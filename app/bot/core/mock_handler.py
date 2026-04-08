import json
import logging
import random
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

class MockResponseHandler:
    """
    Handles robust mock responses based on regex patterns loaded from JSON configuration.
    Features:
    - Fuzzy matching (regex)
    - Category organization
    - Random variations of responses
    - Fallback mechanism
    """
    
    def __init__(self, config_path: str = "config/mock_responses.json"):
        self.responses_data = {}
        self.loaded = False
        self._load_config(config_path)

    def _load_config(self, config_path: str):
        """Load JSON configuration"""
        try:
            # Handle relative path from project root
            base_path = Path(__file__).parent.parent.parent
            full_path = base_path / config_path
            
            if not full_path.exists():
                # Try relative to current file if project root fails
                full_path = Path(config_path)
                
            if full_path.exists():
                with open(full_path, 'r', encoding='utf-8') as f:
                    self.responses_data = json.load(f)
                self.loaded = True
                logging.info(f"✅ Mock responses loaded from {full_path}")
            else:
                logging.warning(f"⚠️ Mock responses file not found at {full_path}")
        except Exception as e:
            logging.error(f"❌ Error loading mock responses: {e}")

    def get_response(self, text: str) -> Optional[str]:
        """
        Get the best matching response for the input text.
        Returns None if no match found (unless fallback is triggered manually).
        """
        if not self.loaded or not text:
            return None
        
        text_lower = text.lower().strip()
        
        # Priority mapping (optional, implicitly handled by JSON order if we iterate carefully)
        # We iterate through all categories
        for category, items in self.responses_data.items():
            if category == "fallback": continue # Skip fallback for now
            
            for item in items:
                patterns = item.get("patterns", [])
                matching_response = self._check_match(text_lower, patterns)
                if matching_response:
                    return self._pick_response(item["responses"])
        
        # If no match, return None to allow other logic to handle it
        return None

    def get_fallback(self) -> str:
        """Get a fallback response"""
        if "fallback" in self.responses_data:
            return self._pick_response(self.responses_data["fallback"][0]["responses"])
        return "Perdón, no entendí. (Mock fallback default)"

    def _check_match(self, text: str, patterns: List[str]) -> bool:
        """Check if text matches any of the patterns (fuzzy/regex)"""
        for pattern in patterns:
            # 1. Direct match (simple)
            if pattern in text:
                return True
                
            # 2. Regex match (if pattern looks like regex or we want partial word matches)
            # Escaping special characters but allowing wildcards if we had them.
            # For now, we treated simple strings as 'contains' in the JSON.
            # But let's add word boundary check for short words like "mp" or "15"
            if len(pattern) < 4:
                 if re.search(r'\b' + re.escape(pattern) + r'\b', text):
                     return True
            
        return False

    def _pick_response(self, responses: List[str]) -> str:
        """Pick a random response from possibilities"""
        return random.choice(responses)

# Singleton instance for easy import
mock_handler = MockResponseHandler()
