#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Image Fraud Detection Module
Detects fake/edited payment receipts using AI-powered image analysis APIs
"""

import os
import requests
import logging
from typing import Dict, Any, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class FraudRiskLevel(Enum):
    """Risk levels for image fraud detection"""
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    HIGH_RISK = "high_risk"
    ERROR = "error"


class ImageFraudDetector:
    """
    Detects fake/edited images using multiple AI services
    Supports: Hive AI, Sightengine
    """
    
    def __init__(self):
        """Initialize fraud detector with API credentials"""
        self.hive_api_key = os.getenv('HIVE_AI_API_KEY', '')
        self.sightengine_api_user = os.getenv('SIGHTENGINE_API_USER', '')
        self.sightengine_api_secret = os.getenv('SIGHTENGINE_API_SECRET', '')
        
        # Configuration
        self.enabled = os.getenv('ENABLE_IMAGE_FRAUD_DETECTION', 'false').lower() == 'true'
        self.provider = os.getenv('IMAGE_FRAUD_PROVIDER', 'hive')  # 'hive' or 'sightengine'
        
        # Thresholds
        self.ai_generated_threshold = float(os.getenv('AI_GENERATED_THRESHOLD', '0.7'))
        self.manipulation_threshold = float(os.getenv('IMAGE_MANIPULATION_THRESHOLD', '0.6'))
        
        logger.info(f"ImageFraudDetector initialized. Enabled: {self.enabled}, Provider: {self.provider}")
    
    def analyze_image(self, image_url: str) -> Tuple[FraudRiskLevel, Dict[str, Any]]:
        """
        Analyze an image for fraud indicators
        
        Args:
            image_url: URL or local path to the image
        
        Returns:
            Tuple of (risk_level, details_dict)
        """
        if not self.enabled:
            logger.info("Image fraud detection is disabled")
            return FraudRiskLevel.CLEAN, {"enabled": False}
        
        try:
            if self.provider == 'hive':
                return self._analyze_with_hive(image_url)
            elif self.provider == 'sightengine':
                return self._analyze_with_sightengine(image_url)
            else:
                logger.error(f"Unknown provider: {self.provider}")
                return FraudRiskLevel.ERROR, {"error": "Unknown provider"}
        
        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            return FraudRiskLevel.ERROR, {"error": str(e)}
    
    def _analyze_with_hive(self, image_url: str) -> Tuple[FraudRiskLevel, Dict[str, Any]]:
        """
        Analyze image using Hive AI API
        Detects: AI-generated content, deepfakes, manipulations
        """
        if not self.hive_api_key:
            logger.warning("Hive AI API key not configured")
            return FraudRiskLevel.ERROR, {"error": "API key missing"}
        
        try:
            # Hive AI endpoint
            url = "https://api.thehive.ai/api/v2/task/sync"
            
            headers = {
                "Authorization": f"Token {self.hive_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "url": image_url,
                "classes": [
                    "ai_generated",
                    "screenshot",
                    "edited_image"
                ]
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse results
            ai_generated_score = 0.0
            manipulation_score = 0.0
            is_screenshot = False
            
            if 'status' in data and data['status'] == 'success':
                classes = data.get('classes', [])
                
                for cls in classes:
                    if cls['class'] == 'ai_generated':
                        ai_generated_score = cls['score']
                    elif cls['class'] == 'edited_image':
                        manipulation_score = cls['score']
                    elif cls['class'] == 'screenshot':
                        is_screenshot = cls['score'] > 0.7
            
            # Determine risk level
            risk_level = self._calculate_risk_level(
                ai_generated_score,
                manipulation_score,
                is_screenshot
            )
            
            details = {
                "provider": "hive",
                "ai_generated_score": ai_generated_score,
                "manipulation_score": manipulation_score,
                "is_screenshot": is_screenshot,
                "raw_response": data
            }
            
            logger.info(f"Hive analysis: {risk_level.value} - AI:{ai_generated_score:.2f}, Manip:{manipulation_score:.2f}")
            
            return risk_level, details
        
        except requests.RequestException as e:
            logger.error(f"Hive API request failed: {e}")
            return FraudRiskLevel.ERROR, {"error": f"API request failed: {str(e)}"}
    
    def _analyze_with_sightengine(self, image_url: str) -> Tuple[FraudRiskLevel, Dict[str, Any]]:
        """
        Analyze image using Sightengine API
        Detects: Manipulations, fake documents, screenshots
        """
        if not self.sightengine_api_user or not self.sightengine_api_secret:
            logger.warning("Sightengine API credentials not configured")
            return FraudRiskLevel.ERROR, {"error": "API credentials missing"}
        
        try:
            # Sightengine endpoint
            url = "https://api.sightengine.com/1.0/check.json"
            
            params = {
                'url': image_url,
                'models': 'genai,properties',
                'api_user': self.sightengine_api_user,
                'api_secret': self.sightengine_api_secret
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse results
            ai_generated_score = 0.0
            manipulation_score = 0.0
            is_screenshot = False
            
            if 'type' in data:
                # Check if it's AI-generated
                if 'ai_generated' in data.get('type', {}):
                    ai_generated_score = data['type']['ai_generated']
                
                # Check properties
                if 'properties' in data:
                    props = data['properties']
                    is_screenshot = props.get('is_screenshot', False)
            
            # Sightengine doesn't have direct manipulation score
            # We infer from metadata and properties
            if 'media' in data:
                media = data['media']
                if media.get('has_exif_manipulation', False):
                    manipulation_score = 0.8
            
            # Determine risk level
            risk_level = self._calculate_risk_level(
                ai_generated_score,
                manipulation_score,
                is_screenshot
            )
            
            details = {
                "provider": "sightengine",
                "ai_generated_score": ai_generated_score,
                "manipulation_score": manipulation_score,
                "is_screenshot": is_screenshot,
                "raw_response": data
            }
            
            logger.info(f"Sightengine analysis: {risk_level.value} - AI:{ai_generated_score:.2f}, Manip:{manipulation_score:.2f}")
            
            return risk_level, details
        
        except requests.RequestException as e:
            logger.error(f"Sightengine API request failed: {e}")
            return FraudRiskLevel.ERROR, {"error": f"API request failed: {str(e)}"}
    
    def _calculate_risk_level(
        self,
        ai_generated_score: float,
        manipulation_score: float,
        is_screenshot: bool
    ) -> FraudRiskLevel:
        """
        Calculate overall risk level based on detection scores
        
        Args:
            ai_generated_score: Probability image is AI-generated (0-1)
            manipulation_score: Probability image is edited (0-1)
            is_screenshot: Whether image is a screenshot
        
        Returns:
            FraudRiskLevel enum
        """
        # High risk conditions
        if ai_generated_score >= self.ai_generated_threshold:
            return FraudRiskLevel.HIGH_RISK
        
        if manipulation_score >= self.manipulation_threshold:
            return FraudRiskLevel.HIGH_RISK
        
        # Suspicious conditions
        if is_screenshot:
            return FraudRiskLevel.SUSPICIOUS
        
        if ai_generated_score >= 0.4 or manipulation_score >= 0.4:
            return FraudRiskLevel.SUSPICIOUS
        
        # Clean
        return FraudRiskLevel.CLEAN
    
    def get_human_readable_verdict(self, risk_level: FraudRiskLevel, details: Dict[str, Any]) -> str:
        """
        Generate human-readable verdict for logging/alerts
        
        Args:
            risk_level: Detected risk level
            details: Analysis details
        
        Returns:
            Human-readable string
        """
        if risk_level == FraudRiskLevel.CLEAN:
            return "✅ Imagen verificada - Sin señales de manipulación"
        
        elif risk_level == FraudRiskLevel.SUSPICIOUS:
            reasons = []
            if details.get('is_screenshot'):
                reasons.append("es captura de pantalla")
            if details.get('ai_generated_score', 0) > 0.4:
                reasons.append(f"posible IA ({details['ai_generated_score']:.0%})")
            
            return f"⚠️ Imagen sospechosa - {', '.join(reasons)}"
        
        elif risk_level == FraudRiskLevel.HIGH_RISK:
            reasons = []
            if details.get('ai_generated_score', 0) >= self.ai_generated_threshold:
                reasons.append(f"generada por IA ({details['ai_generated_score']:.0%})")
            if details.get('manipulation_score', 0) >= self.manipulation_threshold:
                reasons.append(f"editada digitalmente ({details['manipulation_score']:.0%})")
            
            return f"🚨 ALTO RIESGO - {', '.join(reasons)}"
        
        else:
            return f"❌ Error en análisis - {details.get('error', 'Unknown')}"


# Singleton instance
image_fraud_detector = ImageFraudDetector()
