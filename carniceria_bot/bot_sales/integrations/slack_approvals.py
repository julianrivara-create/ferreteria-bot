#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack Approval System
Interactive approval buttons for discounts, holds, and special requests
"""

import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SlackApprovals:
    """Handler for Slack approval workflows"""
    
    def __init__(self, slack_connector, bot, config):
        """
        Initialize approvals handler
        
        Args:
            slack_connector: SlackConnector instance
            bot: SalesBot instance
            config: Config instance
        """
        self.slack = slack_connector
        self.bot = bot
        self.config = config
        self.approval_channel = getattr(config, 'SLACK_APPROVAL_CHANNEL', None)
        self.pending_approvals = {}  # In-memory store (use Redis in production)
    
    def request_discount_approval(self, session_id: str, product: Dict, discount_pct: float, context: Dict) -> str:
        """
        Request approval for discount
        
        Args:
            session_id: User session ID
            product: Product dict
            discount_pct: Requested discount percentage
            context: Conversation context
            
        Returns:
            Approval request ID
        """
        if not self.approval_channel:
            logger.warning("SLACK_APPROVAL_CHANNEL not configured")
            return None
        
        # Check if auto-approve
        auto_approve_threshold = getattr(self.config, 'AUTO_APPROVE_DISCOUNT_UNDER', 5)
        if discount_pct <= auto_approve_threshold:
            logger.info(f"Auto-approving discount {discount_pct}% (under threshold)")
            return "AUTO_APPROVED"
        
        # Check if requires approval
        require_approval_threshold = getattr(self.config, 'REQUIRE_APPROVAL_DISCOUNT_OVER', 10)
        if discount_pct < require_approval_threshold:
            logger.info(f"Discount {discount_pct}% does not require approval")
            return "NO_APPROVAL_NEEDED"
        
        # Generate approval request
        approval_id = f"discount_{session_id}_{int(time.time())}"
        
        # Calculate prices
        original_price = product.get('price_ars', 0)
        discount_amount = original_price * (discount_pct / 100)
        final_price = original_price - discount_amount
        
        # Build approval message
        user_name = context.get('user_name', 'Usuario Desconocido')
        
        message = f"💰 *SOLICITUD DE DESCUENTO*\n\n"
        message += f"*Cliente:* {user_name}\n"
        message += f"*Producto:* {product.get('modelo', 'N/A')} - {product.get('almacenamiento', '')}\n"
        message += f"*Precio original:* ${original_price:,.0f}\n"
        message += f"*Descuento solicitado:* {discount_pct}% (${discount_amount:,.0f})\n"
        message += f"*Precio final:* ${final_price:,.0f}\n"
        
        # Create approval buttons
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message}
            },
            {
                "type": "actions",
                "block_id": approval_id,
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Aprobar"},
                        "style": "primary",
                        "value": f"approve_{approval_id}",
                        "action_id": "approve_discount"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Rechazar"},
                        "style": "danger",
                        "value": f"reject_{approval_id}",
                        "action_id": "reject_discount"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "💬 Negociar"},
                        "value": f"negotiate_{approval_id}",
                        "action_id": "negotiate_discount"
                    }
                ]
            }
        ]
        
        # Send approval request
        try:
            self.slack.send_blocks(self.approval_channel, message, blocks)
            
            # Store pending approval
            self.pending_approvals[approval_id] = {
                'type': 'discount',
                'session_id': session_id,
                'product': product,
                'discount_pct': discount_pct,
                'original_price': original_price,
                'final_price': final_price,
                'timestamp': datetime.now(),
                'status': 'pending'
            }
            
            logger.info(f"Discount approval requested: {approval_id}")
            return approval_id
            
        except Exception as e:
            logger.error(f"Error requesting discount approval: {e}")
            return None
    
    def request_hold_approval(self, session_id: str, product: Dict, hours: int, reason: str, context: Dict) -> str:
        """
        Request approval for extended hold
        
        Args:
            session_id: User session ID
            product: Product dict
            hours: Requested hold duration in hours
            reason: Customer's reason
            context: Conversation context
            
        Returns:
            Approval request ID
        """
        if not self.approval_channel:
            logger.warning("SLACK_APPROVAL_CHANNEL not configured")
            return None
        
        # Check if requires approval
        require_approval_threshold = getattr(self.config, 'REQUIRE_APPROVAL_HOLD_OVER', 60)  # minutes
        if hours * 60 < require_approval_threshold:
            logger.info(f"Hold {hours}h does not require approval")
            return "NO_APPROVAL_NEEDED"
        
        # Generate approval request
        approval_id = f"hold_{session_id}_{int(time.time())}"
        
        # Build approval message
        user_name = context.get('user_name', 'Usuario Desconocido')
        
        message = f"⏰ *SOLICITUD DE HOLD EXTENDIDO*\n\n"
        message += f"*Cliente:* {user_name}\n"
        message += f"*Producto:* {product.get('modelo', 'N/A')}\n"
        message += f"*Tiempo solicitado:* {hours} horas\n"
        message += f"*Razón:* {reason}\n"
        
        # Create approval buttons
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message}
            },
            {
                "type": "actions",
                "block_id": approval_id,
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": f"✅ Aprobar {hours}hs"},
                        "style": "primary",
                        "value": f"approve_{approval_id}_{hours}",
                        "action_id": "approve_hold"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "⏰ Aprobar 24hs"},
                        "value": f"approve_{approval_id}_24",
                        "action_id": "approve_hold_24"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Rechazar"},
                        "style": "danger",
                        "value": f"reject_{approval_id}",
                        "action_id": "reject_hold"
                    }
                ]
            }
        ]
        
        # Send approval request
        try:
            self.slack.send_blocks(self.approval_channel, message, blocks)
            
            # Store pending approval
            self.pending_approvals[approval_id] = {
                'type': 'hold',
                'session_id': session_id,
                'product': product,
                'hours': hours,
                'reason': reason,
                'timestamp': datetime.now(),
                'status': 'pending'
            }
            
            logger.info(f"Hold approval requested: {approval_id}")
            return approval_id
            
        except Exception as e:
            logger.error(f"Error requesting hold approval: {e}")
            return None
    
    def handle_approval_action(self, action_id: str, block_id: str, value: str, user_id: str) -> Dict:
        """
        Handle approval button click
        
        Args:
            action_id: Action ID from button
            block_id: Block ID (approval_id)
            value: Button value
            user_id: Slack user who clicked
            
        Returns:
            Response dict
        """
        approval_id = block_id
        
        # Get pending approval
        approval = self.pending_approvals.get(approval_id)
        if not approval:
            return {"text": "❌ Aprobación no encontrada o expirada"}
        
        # Check timeout
        timeout_minutes = getattr(self.config, 'APPROVAL_TIMEOUT_MINUTES', 5)
        if datetime.now() - approval['timestamp'] > timedelta(minutes=timeout_minutes):
            approval['status'] = 'expired'
            return {"text": "⏱️ Aprobación expirada (timeout)"}
        
        # Handle action
        if action_id.startswith('approve'):
            return self._handle_approve(approval, value, user_id)
        elif action_id.startswith('reject'):
            return self._handle_reject(approval, user_id)
        elif action_id.startswith('negotiate'):
            return self._handle_negotiate(approval, user_id)
        else:
            return {"text": "❌ Acción desconocida"}
    
    def _handle_approve(self, approval: Dict, value: str, user_id: str) -> Dict:
        """Handle approval"""
        approval['status'] = 'approved'
        approval['approved_by'] = user_id
        approval['approved_at'] = datetime.now()
        
        session_id = approval['session_id']
        
        if approval['type'] == 'discount':
            # Apply discount
            discount_pct = approval['discount_pct']
            final_price = approval['final_price']
            
            # Notify customer
            response = f"¡Buenas noticias! Te aprobaron el {discount_pct}% de descuento. Precio final: ${final_price:,.0f}"
            self.bot.send_message(session_id, response)
            
            return {"text": f"✅ Descuento aprobado por <@{user_id}>"}
            
        elif approval['type'] == 'hold':
            # Extract hours from value
            hours = approval['hours']
            if '_24' in value:
                hours = 24
            
            # Extend hold
            response = f"¡Perfecto! Te reservamos el producto por {hours} horas."
            self.bot.send_message(session_id, response)
            
            return {"text": f"✅ Hold de {hours}hs aprobado por <@{user_id}>"}
        
        return {"text": "✅ Aprobado"}
    
    def _handle_reject(self, approval: Dict, user_id: str) -> Dict:
        """Handle rejection"""
        approval['status'] = 'rejected'
        approval['rejected_by'] = user_id
        approval['rejected_at'] = datetime.now()
        
        session_id = approval['session_id']
        
        # Notify customer
        response = "Lo siento, no pudimos aprobar tu solicitud en este momento."
        self.bot.send_message(session_id, response)
        
        return {"text": f"❌ Rechazado por <@{user_id}>"}
    
    def _handle_negotiate(self, approval: Dict, user_id: str) -> Dict:
        """Handle negotiate"""
        approval['status'] = 'negotiating'
        
        # This would trigger a handoff to human agent
        return {"text": f"💬 <@{user_id}> iniciará negociación con el cliente"}
