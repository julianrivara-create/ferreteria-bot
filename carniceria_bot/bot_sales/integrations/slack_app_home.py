#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack App Home
Personalized dashboard with metrics, approval center, and quick actions
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SlackAppHome:
    """Manage Slack App Home tab"""
    
    def __init__(self, slack_connector, bot, db, config):
        """
        Initialize App Home manager
        
        Args:
            slack_connector: SlackConnector instance
            bot: SalesBot instance
            db: Database instance
            config: Config instance
        """
        self.slack = slack_connector
        self.bot = bot
        self.db = db
        self.config = config
    
    def publish_home_view(self, user_id: str, approvals_manager=None, alerts_manager=None):
        """
        Publish App Home view for user
        
        Args:
            user_id: Slack user ID
            approvals_manager: SlackApprovals instance (optional)
            alerts_manager: SlackAlerts instance (optional)
        """
        blocks = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🤖 Sales Bot Dashboard"
            }
        })
        
        # Metrics section
        blocks.extend(self._build_metrics_section())
        
        # Divider
        blocks.append({"type": "divider"})
        
        # Approval Center (NEW - user's idea!)
        if approvals_manager:
            blocks.extend(self._build_approval_center(approvals_manager))
            blocks.append({"type": "divider"})
        
        # Active Alerts section
        if alerts_manager:
            blocks.extend(self._build_alerts_section(alerts_manager))
            blocks.append({"type": "divider"})
        
        # Quick Actions
        blocks.extend(self._build_quick_actions())
        
        # Divider
        blocks.append({"type": "divider"})
        
        # Recent Activity
        blocks.extend(self._build_recent_activity())
        
        # Publish view
        try:
            self.slack.publish_home_view(user_id, blocks)
            logger.info(f"Published App Home for user {user_id}")
        except Exception as e:
            logger.error(f"Error publishing App Home: {e}")
    
    def _build_metrics_section(self) -> List[Dict]:
        """Build metrics section"""
        blocks = []
        
        # Get today's metrics
        today_start = datetime.now().replace(hour=0, minute=0, second=0)
        today_sales = self._get_sales_metrics(today_start, datetime.now())
        
        # Get yesterday's metrics for comparison
        yesterday_start = today_start - timedelta(days=1)
        yesterday_sales = self._get_sales_metrics(yesterday_start, today_start)
        
        # Calculate change
        sales_change = 0
        if yesterday_sales['total'] > 0:
            sales_change = ((today_sales['total'] - yesterday_sales['total']) / yesterday_sales['total']) * 100
        
        change_emoji = "📈" if sales_change > 0 else "📉" if sales_change < 0 else "➡️"
        
        # Get stock alerts
        low_stock_count = len(self.db.get_low_stock_products(threshold=5))
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*📊 Métricas de Hoy*"
            }
        })
        
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*💰 Ventas:*\n${today_sales['total']:,.0f} ({today_sales['count']} pedidos)"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*📊 vs. Ayer:*\n{change_emoji} {sales_change:+.1f}%"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*📦 Stock Crítico:*\n{'⚠️' if low_stock_count > 0 else '✅'} {low_stock_count} productos"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*🎯 Ticket Promedio:*\n${today_sales['avg_ticket']:,.0f}"
                }
            ]
        })
        
        return blocks
    
    def _build_approval_center(self, approvals_manager) -> List[Dict]:
        """
        Build Approval Center section (NEW FEATURE!)
        Central place to view and act on all pending approvals
        """
        blocks = []
        
        # Get pending approvals
        pending = approvals_manager.pending_approvals
        pending_list = [
            (approval_id, data) 
            for approval_id, data in pending.items() 
            if data.get('status') == 'pending'
        ]
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"✋ Centro de Aprobaciones ({len(pending_list)} pendientes)"
            }
        })
        
        if not pending_list:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "✅ _No hay aprobaciones pendientes_"
                }
            })
        else:
            # Show each pending approval
            for approval_id, data in pending_list[:5]:  # Show max 5
                approval_type = data.get('type')
                session_id = data.get('session_id', 'N/A')
                timestamp = data.get('timestamp')
                
                # Calculate time elapsed
                if timestamp:
                    elapsed = datetime.now() - timestamp
                    elapsed_str = f"{int(elapsed.total_seconds() / 60)} min ago"
                else:
                    elapsed_str = "N/A"
                
                if approval_type == 'discount':
                    # Discount approval
                    product = data.get('product', {})
                    discount_pct = data.get('discount_pct', 0)
                    final_price = data.get('final_price', 0)
                    
                    text = f"*💰 Descuento {discount_pct}%*\n"
                    text += f"Producto: {product.get('modelo', 'N/A')}\n"
                    text += f"Precio final: ${final_price:,.0f}\n"
                    text += f"_{elapsed_str}_"
                    
                elif approval_type == 'hold':
                    # Hold approval
                    product = data.get('product', {})
                    hours = data.get('hours', 0)
                    reason = data.get('reason', 'N/A')
                    
                    text = f"*⏰ Hold {hours}hs*\n"
                    text += f"Producto: {product.get('modelo', 'N/A')}\n"
                    text += f"Razón: {reason}\n"
                    text += f"_{elapsed_str}_"
                else:
                    text = f"*Aprobación {approval_type}*\n_{elapsed_str}_"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": text
                    }
                })
                
                # Action buttons
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Aprobar"
                            },
                            "style": "primary",
                            "value": f"approve_{approval_id}",
                            "action_id": f"home_approve_{approval_type}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "❌ Rechazar"
                            },
                            "style": "danger",
                            "value": f"reject_{approval_id}",
                            "action_id": f"home_reject_{approval_type}"
                        }
                    ]
                })
                
                blocks.append({"type": "divider"})
            
            # Show "more" if needed
            if len(pending_list) > 5:
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"_Y {len(pending_list) - 5} aprobaciones más..._"
                        }
                    ]
                })
        
        return blocks
    
    def _build_alerts_section(self, alerts_manager) -> List[Dict]:
        """Build active alerts section"""
        blocks = []
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*🚨 Alertas Activas*"
            }
        })
        
        # This would need to track active handoffs
        # For now, placeholder
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "✅ _No hay alertas activas_"
            }
        })
        
        return blocks
    
    def _build_quick_actions(self) -> List[Dict]:
        """Build quick actions section"""
        blocks = []
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*⚡ Acciones Rápidas*"
            }
        })
        
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "📦 Ver Stock"
                    },
                    "value": "view_stock",
                    "action_id": "quick_view_stock"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "💰 Ver Ventas"
                    },
                    "value": "view_sales",
                    "action_id": "quick_view_sales"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "📊 Analytics"
                    },
                    "value": "view_analytics",
                    "action_id": "quick_view_analytics"
                }
            ]
        })
        
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "⚙️ Configuración"
                    },
                    "value": "view_config",
                    "action_id": "quick_view_config"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🔄 Actualizar"
                    },
                    "value": "refresh",
                    "action_id": "quick_refresh"
                }
            ]
        })
        
        return blocks
    
    def _build_recent_activity(self) -> List[Dict]:
        """Build recent activity section"""
        blocks = []
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*📋 Actividad Reciente*"
            }
        })
        
        # Get recent orders/events
        recent_events = self._get_recent_events(limit=5)
        
        if not recent_events:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_No hay actividad reciente_"
                }
            })
        else:
            for event in recent_events:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• {event['emoji']} {event['description']} _{event['time_ago']}_"
                    }
                })
        
        return blocks
    
    def _get_sales_metrics(self, start_date: datetime, end_date: datetime) -> Dict:
        """Get sales metrics for period"""
        try:
            orders = self.db.get_orders_between(start_date, end_date)
            
            total = sum(o.get('total', 0) for o in orders)
            count = len(orders)
            avg_ticket = total / count if count > 0 else 0
            
            return {
                'total': total,
                'count': count,
                'avg_ticket': avg_ticket
            }
        except Exception as e:
            logger.error(f"Error getting sales metrics: {e}")
            return {'total': 0, 'count': 0, 'avg_ticket': 0}
    
    def _get_recent_events(self, limit: int = 5) -> List[Dict]:
        """Get recent events"""
        # This would query recent orders, messages, etc.
        # Placeholder for now
        return [
            {
                'emoji': '✅',
                'description': 'Juan completó compra de iPhone 15',
                'time_ago': '5 min'
            },
            {
                'emoji': '💰',
                'description': 'María pidió descuento en MacBook',
                'time_ago': '12 min'
            },
            {
                'emoji': '🛒',
                'description': 'Carlos agregó AirPods al carrito',
                'time_ago': '18 min'
            }
        ]
    
    def handle_home_action(self, action_id: str, value: str, user_id: str, approvals_manager=None) -> Dict:
        """
        Handle action from App Home
        
        Args:
            action_id: Action ID
            value: Action value
            user_id: Slack user ID
            approvals_manager: SlackApprovals instance
            
        Returns:
            Response dict
        """
        # Handle approval actions from home
        if action_id.startswith('home_approve_') or action_id.startswith('home_reject_'):
            if not approvals_manager:
                return {"text": "❌ Approvals manager not available"}
            
            # Extract approval_id from value
            parts = value.split('_', 1)
            if len(parts) < 2:
                return {"text": "❌ Invalid value"}
            
            approval_id = parts[1]
            
            # Handle approval
            if action_id.startswith('home_approve_'):
                response = approvals_manager.handle_approval_action(
                    'approve_discount' if 'discount' in action_id else 'approve_hold',
                    approval_id,
                    value,
                    user_id
                )
            else:
                response = approvals_manager.handle_approval_action(
                    'reject_discount' if 'discount' in action_id else 'reject_hold',
                    approval_id,
                    value,
                    user_id
                )
            
            # Refresh home view
            self.publish_home_view(user_id, approvals_manager)
            
            return response
        
        # Handle quick actions
        elif action_id == 'quick_view_stock':
            # Would show stock modal or message
            return {"text": "📦 Abriendo vista de stock..."}
        
        elif action_id == 'quick_view_sales':
            return {"text": "💰 Abriendo vista de ventas..."}
        
        elif action_id == 'quick_view_analytics':
            return {"text": "📊 Abriendo analytics..."}
        
        elif action_id == 'quick_view_config':
            return {"text": "⚙️ Abriendo configuración..."}
        
        elif action_id == 'quick_refresh':
            # Refresh home view
            self.publish_home_view(user_id, approvals_manager)
            return {"text": "🔄 Dashboard actualizado"}
        
        return {"text": "❌ Acción no reconocida"}
