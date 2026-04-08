#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack Alerts & Handoff System
Automatically notify admins when human intervention is needed
Supports multi-channel notifications (Slack + Email + WhatsApp)
"""

import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class SlackAlerts:
    """Handler for Slack alerts and handoff system with multi-channel notifications"""
    
    def __init__(self, slack_connector, bot, config):
        """
        Initialize alerts handler
        
        Args:
            slack_connector: SlackConnector instance
            bot: SalesBot instance
            config: Config instance
        """
        self.slack = slack_connector
        self.bot = bot
        self.config = config
        self.admin_channel = getattr(config, 'SLACK_ADMIN_CHANNEL', None)
        
        # Multi-channel notification settings
        self.enable_email_alerts = getattr(config, 'SLACK_ALERT_EMAIL_ENABLED', False)
        self.enable_whatsapp_alerts = getattr(config, 'SLACK_ALERT_WHATSAPP_ENABLED', False)
        self.admin_email = getattr(config, 'SLACK_ALERT_EMAIL', None)
        self.admin_whatsapp = getattr(config, 'SLACK_ALERT_WHATSAPP', None)
    
    def check_handoff_triggers(self, session_id: str, message: str, context: Dict) -> bool:
        """
        Check if message triggers handoff to human
        
        Args:
            session_id: User session ID
            message: User message
            context: Conversation context
            
        Returns:
            True if handoff triggered, False otherwise
        """
        if not self.admin_channel:
            logger.warning("SLACK_ADMIN_CHANNEL not configured, skipping handoff")
            return False
        
        # Trigger 1: Explicit request for human
        if self._detect_human_request(message):
            self._send_handoff_alert(session_id, "Cliente solicita hablar con humano", context)
            return True
        
        # Trigger 2: Negative sentiment
        if self._detect_negative_sentiment(message):
            self._send_handoff_alert(session_id, "Sentimiento negativo detectado", context)
            return True
        
        # Trigger 3: High-value order
        if self._detect_high_value_order(context):
            amount = context.get('cart_total', 0)
            self._send_handoff_alert(session_id, f"Pedido de alto valor: ${amount:,.0f}", context)
            return True
        
        # Trigger 4: Multiple cart abandonments
        if self._detect_cart_abandonment(session_id, context):
            self._send_handoff_alert(session_id, "Cliente abandonó carrito múltiples veces", context)
            return True
        
        return False
    
    def _detect_human_request(self, message: str) -> bool:
        """Detect if user is requesting human agent"""
        patterns = [
            r'\b(hablar|contactar|comunicar)\s+(con\s+)?(alguien|persona|humano|agente|vendedor)\b',
            r'\b(quiero|necesito|puedo)\s+(hablar|contactar)\b',
            r'\batenci[oó]n\s+(personal|humana)\b',
            r'\b(asesor|representante|operador)\b'
        ]
        
        message_lower = message.lower()
        return any(re.search(pattern, message_lower) for pattern in patterns)
    
    def _detect_negative_sentiment(self, message: str) -> bool:
        """Detect negative sentiment in message"""
        negative_keywords = [
            'enojado', 'molesto', 'furioso', 'indignado', 'frustrado',
            'reclamo', 'queja', 'mal servicio', 'pésimo', 'horrible',
            'estafa', 'fraude', 'robo', 'engaño'
        ]
        
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in negative_keywords)
    
    def _detect_high_value_order(self, context: Dict) -> bool:
        """Detect if order value exceeds threshold"""
        threshold = getattr(self.config, 'HANDOFF_AMOUNT_THRESHOLD', 5000)
        cart_total = context.get('cart_total', 0)
        return cart_total >= threshold
    
    def _detect_cart_abandonment(self, session_id: str, context: Dict) -> bool:
        """Detect multiple cart abandonments"""
        # This would require tracking in database
        # Simplified version for now
        return False
    
    def _send_handoff_alert(self, session_id: str, reason: str, context: Dict):
        """Send handoff alert to admin channel (multi-channel: Slack + Email + WhatsApp)"""
        try:
            # Extract user info
            user_name = context.get('user_name', 'Usuario Desconocido')
            channel_type = self._get_channel_type(session_id)
            channel_id = self._get_channel_id(session_id)
            
            # Generate conversation summary
            summary = self._generate_summary(context)
            
            # Build alert message (Slack format)
            slack_alert = f"🚨 *HANDOFF REQUERIDO*\n\n"
            slack_alert += f"*Cliente:* {user_name}\n"
            slack_alert += f"*Canal:* {channel_type} ({channel_id})\n"
            slack_alert += f"*Razón:* {reason}\n\n"
            slack_alert += f"📝 *RESUMEN CONVERSACIÓN:*\n{summary}\n\n"
            slack_alert += f"_Última interacción: {datetime.now().strftime('%H:%M')}_"
            
            # 1. Send to Slack (primary)
            self.slack.send_message(self.admin_channel, slack_alert)
            logger.info(f"✅ Slack alert sent for {session_id}")
            
            # 2. Send Email notification (if enabled)
            if self.enable_email_alerts and self.admin_email:
                self._send_email_notification(user_name, reason, summary, channel_type)
            
            # 3. Send WhatsApp notification (if enabled)
            if self.enable_whatsapp_alerts and self.admin_whatsapp:
                self._send_whatsapp_notification(user_name, reason, channel_type)
            
            logger.info(f"Handoff alert sent for {session_id}: {reason}")
            
        except Exception as e:
            logger.error(f"Error sending handoff alert: {e}")
    
    def _send_email_notification(self, user_name: str, reason: str, summary: str, channel_type: str):
        """Send email notification to admin"""
        try:
            from app.bot.integrations.email import EmailSender
            
            email_sender = EmailSender()
            
            subject = f"🚨 Alerta Slack: {reason}"
            body = f"""
Tienes una nueva alerta en Slack que requiere tu atención.

Cliente: {user_name}
Canal: {channel_type}
Razón: {reason}

Resumen:
{summary}

Por favor revisa Slack para más detalles y acciones disponibles.
            """
            
            email_sender.send_email(
                to=self.admin_email,
                subject=subject,
                body=body
            )
            
            logger.info(f"✅ Email alert sent to {self.admin_email}")
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
    
    def _send_whatsapp_notification(self, user_name: str, reason: str, channel_type: str):
        """Send WhatsApp notification to admin"""
        try:
            from app.bot.connectors.whatsapp import WhatsAppConnector
            from app.bot.config import Config
            
            config = Config()
            
            # Initialize WhatsApp connector
            if config.WHATSAPP_PROVIDER == 'twilio':
                whatsapp = WhatsAppConnector(
                    provider='twilio',
                    account_sid=config.TWILIO_ACCOUNT_SID,
                    api_token=config.TWILIO_AUTH_TOKEN,
                    phone_number=config.TWILIO_WHATSAPP_NUMBER
                )
            elif config.WHATSAPP_PROVIDER == 'meta':
                whatsapp = WhatsAppConnector(
                    provider='meta',
                    api_token=config.META_ACCESS_TOKEN,
                    phone_number=config.META_PHONE_NUMBER_ID
                )
            else:
                logger.warning("WhatsApp not configured, skipping WhatsApp alert")
                return
            
            # Send short notification
            message = f"🚨 *Alerta Slack*\n\n"
            message += f"Cliente: {user_name}\n"
            message += f"Razón: {reason}\n"
            message += f"Canal: {channel_type}\n\n"
            message += f"Revisa Slack para más detalles."
            
            whatsapp.send_message(self.admin_whatsapp, message)
            
            logger.info(f"✅ WhatsApp alert sent to {self.admin_whatsapp}")
            
        except Exception as e:
            logger.error(f"Error sending WhatsApp notification: {e}")
    
    def _generate_summary(self, context: Dict) -> str:
        """Generate conversation summary"""
        # Get conversation history
        history = context.get('conversation_history', [])
        
        if not history:
            return "• Sin historial de conversación"
        
        # Simple summary (last 3 messages)
        summary_lines = []
        for msg in history[-3:]:
            role = "Cliente" if msg.get('role') == 'user' else "Bot"
            text = msg.get('content', '')[:100]  # Truncate
            summary_lines.append(f"• {role}: {text}")
        
        # Add cart info if available
        if context.get('cart_items'):
            cart_total = context.get('cart_total', 0)
            item_count = len(context.get('cart_items', []))
            summary_lines.append(f"• Carrito: ${cart_total:,.0f} ({item_count} items)")
        
        return "\n".join(summary_lines)
    
    def _get_channel_type(self, session_id: str) -> str:
        """Extract channel type from session ID"""
        if session_id.startswith('whatsapp_'):
            return 'WhatsApp'
        elif session_id.startswith('ig_'):
            return 'Instagram'
        elif session_id.startswith('slack_'):
            return 'Slack'
        elif session_id.startswith('web_'):
            return 'Web Chat'
        else:
            return 'Desconocido'
    
    def _get_channel_id(self, session_id: str) -> str:
        """Extract channel ID from session ID"""
        parts = session_id.split('_', 1)
        return parts[1] if len(parts) > 1 else session_id
    
    def send_stock_alert(self, product: Dict):
        """Send low stock alert"""
        if not self.admin_channel:
            return
        
        try:
            alert = f"⚠️ *ALERTA DE STOCK BAJO*\n\n"
            alert += f"*Producto:* {product['name']}\n"
            alert += f"*SKU:* {product['sku']}\n"
            alert += f"*Stock actual:* {product['stock']} unidades\n"
            alert += f"*Umbral:* {product.get('min_stock', 5)} unidades\n\n"
            alert += f"_Recomendación: Reabastecer pronto_"
            
            self.slack.send_message(self.admin_channel, alert)
            
        except Exception as e:
            logger.error(f"Error sending stock alert: {e}")
    
    def send_error_alert(self, error_type: str, details: str):
        """Send system error alert"""
        if not self.admin_channel:
            return
        
        try:
            alert = f"🔴 *ERROR DEL SISTEMA*\n\n"
            alert += f"*Tipo:* {error_type}\n"
            alert += f"*Detalles:* {details}\n"
            alert += f"*Timestamp:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            self.slack.send_message(self.admin_channel, alert)
            
        except Exception as e:
            logger.error(f"Error sending error alert: {e}")
