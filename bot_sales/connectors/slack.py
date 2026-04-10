#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack Connector
Handles Slack Direct Messages and Channel mentions via Slack Events API
"""

import os
import hmac
import hashlib
import time
import requests
import logging
from typing import Dict, Any, Optional, List
from flask import request, jsonify

logger = logging.getLogger(__name__)

class SlackConnector:
    """Slack messaging connector using Events API and Web API"""
    
    def __init__(self, bot_token: str, signing_secret: str):
        """
        Initialize Slack connector
        
        Args:
            bot_token: Slack Bot User OAuth Token (xoxb-...)
            signing_secret: Slack Signing Secret for webhook verification
        """
        self.bot_token = bot_token
        self.signing_secret = signing_secret
        self.api_base = "https://slack.com/api"
        
    def verify_signature(self, req) -> bool:
        """
        Verify Slack request signature
        
        Args:
            req: Flask request object
            
        Returns:
            True if signature is valid, False otherwise
        """
        timestamp = req.headers.get('X-Slack-Request-Timestamp', '')
        signature = req.headers.get('X-Slack-Signature', '')
        
        # Prevent replay attacks (request older than 5 minutes)
        if abs(time.time() - int(timestamp)) > 60 * 5:
            logger.warning("Slack request timestamp too old")
            return False
        
        # Compute signature
        body = req.get_data(as_text=True)
        basestring = f"v0:{timestamp}:{body}"
        
        my_signature = 'v0=' + hmac.new(
            self.signing_secret.encode(),
            basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        if not hmac.compare_digest(my_signature, signature):
            logger.warning("Slack signature verification failed")
            return False
            
        return True
    
    def handle_event(self, data: Dict[str, Any], bot) -> Dict[str, str]:
        """
        Process Slack event
        
        Args:
            data: Event payload from Slack
            bot: SalesBot instance
            
        Returns:
            Response dict
        """
        try:
            event_type = data.get('type')
            
            # URL Verification (initial webhook setup)
            if event_type == 'url_verification':
                challenge = data.get('challenge')
                logger.info("Slack webhook verification successful")
                return {"challenge": challenge}
            
            # Event Callback
            if event_type == 'event_callback':
                event = data.get('event', {})
                event_subtype = event.get('type')
                
                # Ignore bot messages (prevent loops)
                if event.get('bot_id') or event.get('subtype') == 'bot_message':
                    return {"status": "ignored_bot"}
                
                # Handle message events
                if event_subtype in ['message', 'app_mention']:
                    return self._handle_message(event, bot)
            
            return {"status": "ignored"}
            
        except Exception as e:
            logger.error(f"Error handling Slack event: {e}")
            return {"status": "error", "message": str(e)}
    
    def _handle_message(self, event: Dict, bot) -> Dict:
        """Handle incoming message event"""
        user_id = event.get('user')
        channel = event.get('channel')
        text = event.get('text', '')
        
        # Remove bot mention from text if present
        text = self._clean_message_text(text)
        
        if not user_id or not text:
            logger.warning("Slack message missing user or text")
            return {"status": "ignored_invalid"}
        
        logger.info(f"Slack message from {user_id}: {text}")
        
        # Process with bot (prefix session with 'slack_')
        session_id = f"slack_{user_id}"
        response = bot.process_message(
            session_id,
            text,
            channel="slack",
            customer_ref=str(user_id),
        )
        
        # Send response
        self.send_message(channel, response)
        
        return {"status": "success"}
    
    def _clean_message_text(self, text: str) -> str:
        """Remove bot mentions from message text"""
        # Remove <@BOTID> mentions
        import re
        text = re.sub(r'<@[A-Z0-9]+>', '', text)
        return text.strip()
    
    def send_message(self, channel: str, text: str) -> Dict[str, Any]:
        """
        Send text message via Slack API
        
        Args:
            channel: Channel or user ID
            text: Message text
            
        Returns:
            API response
        """
        url = f"{self.api_base}/chat.postMessage"
        
        payload = {
            "channel": channel,
            "text": text
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.bot_token}"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok'):
                logger.info(f"Slack message sent to {channel}")
                return data
            else:
                logger.error(f"Slack API error: {data.get('error')}")
                return {"error": data.get('error')}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending Slack message: {e}")
            return {"error": str(e)}
    
    def send_blocks(self, channel: str, text: str, blocks: List[Dict]) -> Dict[str, Any]:
        """
        Send message with Block Kit components
        
        Args:
            channel: Channel or user ID
            text: Fallback text
            blocks: List of Block Kit blocks
            
        Returns:
            API response
        """
        url = f"{self.api_base}/chat.postMessage"
        
        payload = {
            "channel": channel,
            "text": text,  # Fallback text
            "blocks": blocks
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.bot_token}"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok'):
                logger.info(f"Slack blocks sent to {channel}")
                return data
            else:
                logger.error(f"Slack API error: {data.get('error')}")
                return {"error": data.get('error')}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending Slack blocks: {e}")
            return {"error": str(e)}
    
    def send_quick_replies(self, channel: str, text: str, options: List[str]) -> Dict[str, Any]:
        """
        Send message with button options
        
        Args:
            channel: Channel or user ID
            text: Message text
            options: List of button labels
            
        Returns:
            API response
        """
        # Create buttons
        buttons = [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": option[:75]  # Max 75 chars
                },
                "value": option,
                "action_id": f"button_{i}"
            }
            for i, option in enumerate(options[:5])  # Max 5 buttons per action block
        ]
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text
                }
            },
            {
                "type": "actions",
                "elements": buttons
            }
        ]
        
        return self.send_blocks(channel, text, blocks)
    
    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get Slack user information
        
        Args:
            user_id: Slack user ID
            
        Returns:
            User info data
        """
        url = f"{self.api_base}/users.info"
        params = {"user": user_id}
        headers = {"Authorization": f"Bearer {self.bot_token}"}
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok'):
                return data.get('user', {})
            else:
                logger.error(f"Slack API error: {data.get('error')}")
                return {"error": data.get('error')}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting Slack user info: {e}")
            return {"error": str(e)}




def run_slack_webhook(app, bot, connector: SlackConnector):
    """
    Setup Slack webhook routes
    
    Args:
        app: Flask app instance
        bot: SalesBot instance
        connector: SlackConnector instance
    """
    from bot_sales.integrations.slack_commands import SlackCommands
    from bot_sales.integrations.slack_approvals import SlackApprovals
    from bot_sales.config import Config
    
    config = Config()
    
    # Initialize integrations
    try:
        from bot_sales.core.database import Database
        db = Database()
        slack_commands = SlackCommands(bot, db)
        slack_approvals = SlackApprovals(connector, bot, config)
    except Exception as e:
        logger.error(f"Error initializing Slack integrations: {e}")
        slack_commands = None
        slack_approvals = None
    
    @app.route('/webhook/slack', methods=['POST'])
    def slack_webhook():
        """Slack events endpoint"""
        
        # Verify signature (skip for url_verification)
        data = request.get_json()
        if data.get('type') != 'url_verification':
            if not connector.verify_signature(request):
                return jsonify({"error": "Invalid signature"}), 403
        
        # Handle event
        result = connector.handle_event(data, bot)
        
        # URL verification returns challenge directly
        if 'challenge' in result:
            return result['challenge']
        
        return jsonify(result)
    
    @app.route('/webhook/slack/commands', methods=['POST'])
    def slack_commands_endpoint():
        """Slack slash commands endpoint"""
        
        if not slack_commands:
            return jsonify({"text": "❌ Slash commands not configured"}), 500
        
        # Verify signature
        if not connector.verify_signature(request):
            return jsonify({"error": "Invalid signature"}), 403
        
        # Parse command data
        command = request.form.get('command')
        text = request.form.get('text', '')
        user_id = request.form.get('user_id')
        channel_id = request.form.get('channel_id')
        
        # Check admin whitelist
        admin_users = getattr(config, 'SLACK_ADMIN_USERS', '').split(',')
        if admin_users and user_id not in admin_users:
            return jsonify({
                "response_type": "ephemeral",
                "text": "❌ No tienes permisos para usar este comando"
            })
        
        # Handle command
        try:
            response = slack_commands.handle_command(command, text, user_id, channel_id)
            return jsonify(response)
        except Exception as e:
            logger.error(f"Error handling slash command: {e}")
            return jsonify({
                "response_type": "ephemeral",
                "text": f"❌ Error: {str(e)}"
            })
    
    @app.route('/webhook/slack/interactive', methods=['POST'])
    def slack_interactive_endpoint():
        """Slack interactive components endpoint (buttons, modals)"""
        
        if not slack_approvals:
            return jsonify({"text": "❌ Interactive components not configured"}), 500
        
        # Verify signature
        if not connector.verify_signature(request):
            return jsonify({"error": "Invalid signature"}), 403
        
        # Parse payload
        import json
        payload = json.loads(request.form.get('payload'))
        
        # Extract action data
        action_type = payload.get('type')
        
        if action_type == 'block_actions':
            actions = payload.get('actions', [])
            if not actions:
                return jsonify({"text": "❌ No action found"})
            
            action = actions[0]
            action_id = action.get('action_id')
            block_id = action.get('block_id')
            value = action.get('value')
            user_id = payload.get('user', {}).get('id')
            
            # Handle approval action
            try:
                response = slack_approvals.handle_approval_action(
                    action_id, block_id, value, user_id
                )
                
                # Update original message
                return jsonify({
                    "replace_original": True,
                    "text": response.get('text', '✅ Procesado')
                })
            except Exception as e:
                logger.error(f"Error handling interactive action: {e}")
                return jsonify({"text": f"❌ Error: {str(e)}"})
        
        return jsonify({"text": "❌ Tipo de acción no soportado"})
    
    logger.info("Slack webhook routes configured (events, commands, interactive)")



# Configuration helper
def get_slack_connector() -> Optional[SlackConnector]:
    """
    Get Slack connector from environment variables
    
    Returns:
        SlackConnector instance or None if not configured
    """
    bot_token = os.getenv('SLACK_BOT_TOKEN')
    signing_secret = os.getenv('SLACK_SIGNING_SECRET')
    
    if not bot_token or not signing_secret:
        logger.warning("Slack not configured (missing SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET)")
        return None
    
    return SlackConnector(bot_token, signing_secret)
