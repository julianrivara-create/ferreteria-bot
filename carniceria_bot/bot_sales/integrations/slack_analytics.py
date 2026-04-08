#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack Analytics Dashboard
Interactive analytics with charts and metrics
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
import io
import base64

logger = logging.getLogger(__name__)

class SlackAnalyticsDashboard:
    """Generate analytics dashboards for Slack"""
    
    def __init__(self, slack_connector, db, config):
        """
        Initialize analytics dashboard
        
        Args:
            slack_connector: SlackConnector instance
            db: Database instance
            config: Config instance
        """
        self.slack = slack_connector
        self.db = db
        self.config = config
    
    def generate_dashboard(self, period='today', channel_id=None) -> List[Dict]:
        """
        Generate analytics dashboard
        
        Args:
            period: 'today', 'week', 'month'
            channel_id: Optional channel to send to
            
        Returns:
            List of Slack blocks
        """
        # Get date range
        start_date, end_date = self._get_date_range(period)
        
        # Get metrics
        metrics = self._get_metrics(start_date, end_date)
        
        # Build blocks
        blocks = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 Analytics Dashboard - {period.title()}"
            }
        })
        
        # Key Metrics
        blocks.extend(self._build_key_metrics(metrics))
        
        # Divider
        blocks.append({"type": "divider"})
        
        # Sales Chart
        chart_url = self._generate_sales_chart(metrics)
        if chart_url:
            blocks.append({
                "type": "image",
                "image_url": chart_url,
                "alt_text": "Sales Chart"
            })
        
        # Divider
        blocks.append({"type": "divider"})
        
        # Top Products
        blocks.extend(self._build_top_products(metrics))
        
        # Divider
        blocks.append({"type": "divider"})
        
        # Conversion Funnel
        blocks.extend(self._build_conversion_funnel(metrics))
        
        # Export button
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "📥 Exportar CSV"
                    },
                    "value": f"export_{period}",
                    "action_id": "export_analytics"
                }
            ]
        })
        
        # Send to channel if specified
        if channel_id:
            self.slack.send_blocks(channel_id, "Analytics Dashboard", blocks)
        
        return blocks
    
    def _get_date_range(self, period: str) -> tuple:
        """Get date range for period"""
        now = datetime.now()
        
        if period == 'today':
            start = now.replace(hour=0, minute=0, second=0)
            end = now
        elif period == 'week':
            start = now - timedelta(days=7)
            end = now
        elif period == 'month':
            start = now - timedelta(days=30)
            end = now
        else:
            start = now.replace(hour=0, minute=0, second=0)
            end = now
        
        return start, end
    
    def _get_metrics(self, start_date: datetime, end_date: datetime) -> Dict:
        """Get analytics metrics"""
        try:
            orders = self.db.get_orders_between(start_date, end_date)
            
            total_revenue = sum(o.get('total', 0) for o in orders)
            total_orders = len(orders)
            avg_ticket = total_revenue / total_orders if total_orders > 0 else 0
            
            # Calculate conversion (would need session data)
            total_sessions = 100  # Placeholder
            conversion_rate = (total_orders / total_sessions * 100) if total_sessions > 0 else 0
            
            # Top products
            product_sales = {}
            for order in orders:
                for item in order.get('items', []):
                    sku = item.get('sku')
                    if sku:
                        if sku not in product_sales:
                            product_sales[sku] = {
                                'name': item.get('modelo', 'Unknown'),
                                'count': 0,
                                'revenue': 0
                            }
                        product_sales[sku]['count'] += item.get('quantity', 1)
                        product_sales[sku]['revenue'] += item.get('price_ars', 0) * item.get('quantity', 1)
            
            top_products = sorted(
                product_sales.values(),
                key=lambda x: x['revenue'],
                reverse=True
            )[:5]
            
            return {
                'revenue': total_revenue,
                'orders': total_orders,
                'avg_ticket': avg_ticket,
                'conversion_rate': conversion_rate,
                'top_products': top_products,
                'daily_breakdown': []  # Would calculate daily sales
            }
            
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return {
                'revenue': 0,
                'orders': 0,
                'avg_ticket': 0,
                'conversion_rate': 0,
                'top_products': []
            }
    
    def _build_key_metrics(self, metrics: Dict) -> List[Dict]:
        """Build key metrics section"""
        return [{
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*💰 Revenue:*\n${metrics['revenue']:,.0f}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*📦 Orders:*\n{metrics['orders']}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*🎯 Avg Ticket:*\n${metrics['avg_ticket']:,.0f}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*📈 Conversion:*\n{metrics['conversion_rate']:.1f}%"
                }
            ]
        }]
    
    def _build_top_products(self, metrics: Dict) -> List[Dict]:
        """Build top products section"""
        blocks = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*🏆 Top Products*"
            }
        }]
        
        for i, product in enumerate(metrics['top_products'], 1):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{i}. *{product['name']}*\n{product['count']} ventas • ${product['revenue']:,.0f}"
                }
            })
        
        return blocks
    
    def _build_conversion_funnel(self, metrics: Dict) -> List[Dict]:
        """Build conversion funnel"""
        # Placeholder data
        funnel_data = [
            ("Visitantes", 100, "100%"),
            ("Consultaron Producto", 75, "75%"),
            ("Agregaron al Carrito", 45, "45%"),
            ("Iniciaron Checkout", 30, "30%"),
            ("Completaron Compra", 20, "20%")
        ]
        
        blocks = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*🔄 Conversion Funnel*"
            }
        }]
        
        for stage, count, percentage in funnel_data:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"• {stage}: {count} ({percentage})"
                }
            })
        
        return blocks
    
    def _generate_sales_chart(self, metrics: Dict) -> Optional[str]:
        """Generate sales chart"""
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            
            # Sample data (would use real daily breakdown)
            days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            sales = [1200, 1500, 1800, 1400, 2200, 2500, 1900]
            
            # Create chart
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(days, sales, marker='o', linewidth=2, markersize=8)
            ax.set_title('Daily Sales', fontsize=16, fontweight='bold')
            ax.set_xlabel('Day')
            ax.set_ylabel('Sales ($)')
            ax.grid(True, alpha=0.3)
            
            # Save to bytes
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
            buf.seek(0)
            plt.close()
            
            # Upload to Slack or return base64
            # For now, return placeholder
            return "https://via.placeholder.com/800x400?text=Sales+Chart"
            
        except Exception as e:
            logger.error(f"Error generating chart: {e}")
            return None
    
    def export_to_csv(self, period: str) -> str:
        """Export analytics to CSV"""
        start_date, end_date = self._get_date_range(period)
        metrics = self._get_metrics(start_date, end_date)
        
        # Generate CSV
        csv_data = "Metric,Value\n"
        csv_data += f"Revenue,{metrics['revenue']}\n"
        csv_data += f"Orders,{metrics['orders']}\n"
        csv_data += f"Avg Ticket,{metrics['avg_ticket']}\n"
        csv_data += f"Conversion Rate,{metrics['conversion_rate']}%\n"
        
        return csv_data
