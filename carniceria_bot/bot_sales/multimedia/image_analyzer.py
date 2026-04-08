import logging
from typing import Optional, Dict, Any
from openai import OpenAI
from bot_sales.config import Config

class ImageAnalyzer:
    """
    Analyzes images using OpenAI's GPT-4o Vision model to identify products.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.client = None
        
        if Config.OPENAI_API_KEY:
            try:
                self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
            except Exception as e:
                self.logger.error(f"Failed to init OpenAI client for vision: {e}")
        else:
            self.logger.warning("OpenAI API Key missing. Image analysis disabled.")

    def analyze_product(self, image_url: str) -> Optional[Dict[str, Any]]:
        """
        Analyzes a product image and returns structured data.
        
        Args:
            image_url: Public URL of the image
            
        Returns:
            Dict with 'model', 'color', 'category' or None
        """
        if not self.client:
            return None
            
        try:
            self.logger.info(f"Analyzing image: {image_url}")
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Identify the Apple product in this image. Return strictly valid JSON with keys: 'model' (specific model name), 'color' (if visible), 'category' (iPhone, Mac, iPad, etc), and 'confidence' (0-1). If not an Apple product or unsure, return {'error': 'unknown'}."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url,
                                },
                            },
                        ],
                    }
                ],
                max_tokens=300,
                response_format={ "type": "json_object" }
            )
            
            content = response.choices[0].message.content
            import json
            result = json.loads(content)
            
            self.logger.info(f"Vision result: {result}")
            return result
            
        except Exception as e:
            self.logger.error(f"Image analysis failed: {e}")
            return None
