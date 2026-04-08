#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Instagram Connector
Handles Instagram Direct Messages via Meta Graph API
"""

import os
import requests
import logging
from typing import Dict, Any, Optional
from flask import request, jsonify

logger = logging.getLogger(__name__)

class InstagramConnector:
    """Instagram messaging connector using Meta Graph API"""
    
    def __init__(self, access_token: str, verify_token: str):
        """
        Initialize Instagram connector
        
        Args:
            access_token: Instagram Graph API access token
            verify_token: Webhook verification token
        """
        self.access_token = access_token
        self.verify_token = verify_token
        self.api_version = "v18.0"
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        
    def verify_webhook(self, req) -> Optional[str]:
        """
        Verify webhook for Instagram
        
        Args:
            req: Flask request object
            
        Returns:
            Challenge string if verification succeeds, None otherwise
        """
        mode = req.args.get('hub.mode')
        token = req.args.get('hub.verify_token')
        challenge = req.args.get('hub.challenge')
        
        if mode == 'subscribe' and token == self.verify_token:
            logger.info("Instagram webhook verified successfully")
            return challenge
        
        logger.warning("Instagram webhook verification failed")
        return None
    
    def handle_webhook(self, data: Dict[str, Any], bot) -> Dict[str, str]:
        """
        Process Instagram webhook event
        
        Args:
            data: Webhook payload
            bot: SalesBot instance
            
        Returns:
            Response dict
        """
        try:
            entry = data.get('entry', [{}])[0]
            messaging = entry.get('messaging', [{}])[0]
            
            sender_id = messaging.get('sender', {}).get('id')
            message_data = messaging.get('message', {})
            message_text = message_data.get('text')
            
            # Ignore echoes (messages sent by the bot)
            if message_data.get('is_echo'):
                return {"status": "ignored_echo"}
            
            if not sender_id or not message_text:
                logger.warning("Instagram message missing sender_id or text")
                return {"status": "ignored_invalid"}
            
            logger.info(f"Instagram message from {sender_id}: {message_text}")
            
            # Process with bot (prefix session with 'ig_' to identify Instagram users)
            session_id = f"ig_{sender_id}"
            response = bot.process_message(session_id, message_text)
            
            # Send response
            self.send_message(sender_id, response)
            
            return {"status": "success"}
            
        except Exception as e:
            logger.error(f"Error handling Instagram webhook: {e}")
            return {"status": "error", "message": str(e)}
    
    def send_message(self, recipient_id: str, message: str) -> Dict[str, Any]:
        """
        Send text message via Instagram API
        
        Args:
            recipient_id: Instagram user ID
            message: Message text
            
        Returns:
            API response
        """
        url = f"{self.base_url}/me/messages"
        
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message}
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Instagram message sent to {recipient_id}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending Instagram message: {e}")
            return {"error": str(e)}
    
    def send_quick_replies(self, recipient_id: str, text: str, options: list) -> Dict[str, Any]:
        """
        Send message with quick reply buttons
        
        Args:
            recipient_id: Instagram user ID
            text: Message text
            options: List of button labels
            
        Returns:
            API response
        """
        url = f"{self.base_url}/me/messages"
        
        quick_replies = [
            {
                "content_type": "text",
                "title": option[:20],  # Max 20 chars
                "payload": option
            }
            for option in options[:13]  # Max 13 quick replies
        ]
        
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "text": text,
                "quick_replies": quick_replies
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Instagram quick replies sent to {recipient_id}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending Instagram quick replies: {e}")
            return {"error": str(e)}
    
    def send_image(self, recipient_id: str, image_url: str, caption: str = "") -> Dict[str, Any]:
        """
        Send image message
        
        Args:
            recipient_id: Instagram user ID
            image_url: URL of the image
            caption: Optional caption
            
        Returns:
            API response
        """
        url = f"{self.base_url}/me/messages"
        
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {
                        "url": image_url,
                        "is_reusable": True
                    }
                }
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Send caption as separate message if provided
            if caption:
                self.send_message(recipient_id, caption)
            
            logger.info(f"Instagram image sent to {recipient_id}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending Instagram image: {e}")
            return {"error": str(e)}
    
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get Instagram user profile information
        
        Args:
            user_id: Instagram user ID
            
        Returns:
            User profile data
        """
        url = f"{self.base_url}/{user_id}"
        params = {
            "fields": "name,username,profile_pic",
            "access_token": self.access_token
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting Instagram user profile: {e}")
            return {"error": str(e)}


def run_instagram_webhook(app, bot, connector: InstagramConnector):
    """
    Setup Instagram webhook routes
    
    Args:
        app: Flask app instance
        bot: SalesBot instance
        connector: InstagramConnector instance
    """
    
    @app.route('/webhook/instagram', methods=['GET', 'POST'])
    def instagram_webhook():
        """Instagram webhook endpoint"""
        
        if request.method == 'GET':
            # Webhook verification
            challenge = connector.verify_webhook(request)
            if challenge:
                return challenge
            return "Verification failed", 403
        
        elif request.method == 'POST':
            # Handle incoming message
            data = request.get_json()
            result = connector.handle_webhook(data, bot)
            return jsonify(result)
    
    logger.info("Instagram webhook routes configured")


# Configuration helper
def get_instagram_connector() -> Optional[InstagramConnector]:
    """
    Get Instagram connector from environment variables
    
    Returns:
        InstagramConnector instance or None if not configured
    """
    access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
    verify_token = os.getenv('INSTAGRAM_VERIFY_TOKEN', 'instagram_verify_token_123')
    
    if not access_token:
        logger.warning("Instagram not configured (missing INSTAGRAM_ACCESS_TOKEN)")
        return None
    
    return InstagramConnector(access_token, verify_token)
