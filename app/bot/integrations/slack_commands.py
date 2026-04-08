#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack Slash Commands
Admin commands for bot management and reporting
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SlackCommands:
    """Handler for Slack slash commands"""
    
    def __init__(self, bot, db, analytics=None):
        """
        Initialize slash commands handler
        
        Args:
            bot: SalesBot instance
            db: Database instance
            analytics: Analytics instance (optional)
        """
        self.bot = bot
        self.db = db
        self.analytics = analytics
    
    def handle_command(self, command: str, text: str, user_id: str, channel_id: str) -> Dict[str, Any]:
        """
        Route slash command to appropriate handler
        
        Args:
            command: Command name (e.g., '/stock')
            text: Command arguments
            user_id: Slack user ID
            channel_id: Slack channel ID
            
        Returns:
            Response dict for Slack
        """
        # Map commands to handlers
        handlers = {
            '/stock': self._handle_stock,
            '/ventas': self._handle_ventas,
            '/reportes': self._handle_reportes,
            '/config': self._handle_config
        }
        
        handler = handlers.get(command)
        if not handler:
            return self._error_response(f"Comando desconocido: {command}")
        
        try:
            return handler(text, user_id, channel_id)
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
            return self._error_response(f"Error ejecutando comando: {str(e)}")
    
    def _handle_stock(self, text: str, user_id: str, channel_id: str) -> Dict:
        """Handle /stock [producto] command"""
        producto = text.strip() if text else None
        
        if not producto:
            # Show all stock
            stock_data = self.db.get_stock_summary()
            response = "📦 *STOCK GENERAL*\n\n"
            
            for category, items in stock_data.items():
                response += f"*{category}*\n"
                for item in items:
                    emoji = "✅" if item['stock'] > 5 else "⚠️" if item['stock'] > 0 else "❌"
                    response += f"{emoji} {item['name']}: {item['stock']} unidades\n"
                response += "\n"
            
            return {
                "response_type": "in_channel",
                "text": response
            }
        else:
            # Search specific product
            products = self.db.search_products(producto)
            
            if not products:
                return self._error_response(f"No se encontró producto: {producto}")
            
            response = f"📦 *STOCK: {producto.upper()}*\n\n"
            
            for p in products[:10]:  # Limit to 10 results
                stock = self.db.available_for_sku(p['sku'])
                emoji = "✅" if stock > 5 else "⚠️" if stock > 0 else "❌"
                response += f"{emoji} {p['modelo']} - {p['almacenamiento']}: {stock} unidades\n"
            
            response += f"\n_Última actualización: {datetime.now().strftime('%H:%M')}_"
            
            return {
                "response_type": "in_channel",
                "text": response
            }
    
    def _handle_ventas(self, text: str, user_id: str, channel_id: str) -> Dict:
        """Handle /ventas [periodo] command"""
        periodo = text.strip().lower() if text else "hoy"
        
        # Calculate date range
        now = datetime.now()
        if periodo == "hoy":
            start_date = now.replace(hour=0, minute=0, second=0)
            end_date = now
            titulo = "HOY"
        elif periodo == "ayer":
            start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
            end_date = start_date.replace(hour=23, minute=59, second=59)
            titulo = "AYER"
        elif periodo == "semana":
            start_date = now - timedelta(days=7)
            end_date = now
            titulo = "ÚLTIMOS 7 DÍAS"
        elif periodo == "mes":
            start_date = now - timedelta(days=30)
            end_date = now
            titulo = "ÚLTIMOS 30 DÍAS"
        else:
            return self._error_response(f"Periodo inválido: {periodo}. Usa: hoy, ayer, semana, mes")
        
        # Get sales data
        if self.analytics:
            sales_data = self.analytics.get_sales_summary(start_date, end_date)
        else:
            # Fallback: query database directly
            sales_data = self._get_sales_from_db(start_date, end_date)
        
        # Format response
        response = f"💰 *VENTAS {titulo}*\n\n"
        response += f"Total: ${sales_data['total']:,.0f} ({sales_data['count']} pedidos)\n"
        response += f"Ticket promedio: ${sales_data['avg_ticket']:,.0f}\n\n"
        
        if sales_data.get('top_products'):
            response += "*Top Productos:*\n"
            for i, p in enumerate(sales_data['top_products'][:5], 1):
                response += f"{i}. {p['name']} - {p['count']} ventas (${p['total']:,.0f})\n"
        
        response += f"\n*Estado:*\n"
        response += f"✅ Completados: {sales_data.get('completed', 0)}\n"
        response += f"⏳ Pendientes: {sales_data.get('pending', 0)}\n"
        response += f"❌ Cancelados: {sales_data.get('cancelled', 0)}\n"
        
        return {
            "response_type": "in_channel",
            "text": response
        }
    
    def _handle_reportes(self, text: str, user_id: str, channel_id: str) -> Dict:
        """Handle /reportes [tipo] command"""
        tipo = text.strip().lower() if text else "diario"
        
        if tipo == "diario":
            report = self._generate_daily_report()
        elif tipo == "semanal":
            report = self._generate_weekly_report()
        elif tipo == "mensual":
            report = self._generate_monthly_report()
        else:
            return self._error_response(f"Tipo inválido: {tipo}. Usa: diario, semanal, mensual")
        
        return {
            "response_type": "in_channel",
            "text": report
        }
    
    def _handle_config(self, text: str, user_id: str, channel_id: str) -> Dict:
        """Handle /config [accion] command"""
        from app.bot.config import Config
        config = Config()
        
        accion = text.strip().lower() if text else "show"
        
        if accion == "show":
            response = "⚙️ *CONFIGURACIÓN ACTUAL*\n\n"
            response += f"*Store:* {getattr(config, 'STORE_NAME', 'N/A')}\n"
            response += f"*Type:* {getattr(config, 'STORE_TYPE', 'N/A')}\n"
            response += f"*Country:* {getattr(config, 'STORE_COUNTRY', 'N/A')}\n\n"
            
            response += "*Features:*\n"
            response += f"{'✅' if getattr(config, 'ENABLE_UPSELLING', False) else '❌'} Upselling\n"
            response += f"{'✅' if getattr(config, 'ENABLE_CROSSSELLING', False) else '❌'} Cross-selling\n"
            response += f"{'✅' if getattr(config, 'ENABLE_BUNDLES', False) else '❌'} Bundles\n"
            response += f"{'✅' if getattr(config, 'ENABLE_FRAUD_DETECTION', False) else '❌'} Fraud Detection\n"
            response += f"{'✅' if getattr(config, 'ENABLE_CACHE', False) else '❌'} Cache\n"
            
            return {
                "response_type": "in_channel",
                "text": response
            }
        else:
            return self._error_response(f"Acción inválida: {accion}. Usa: show")
    
    def _generate_daily_report(self) -> str:
        """Generate daily report"""
        now = datetime.now()
        start_date = now.replace(hour=0, minute=0, second=0)
        
        sales_data = self._get_sales_from_db(start_date, now)
        
        report = f"📊 *REPORTE DIARIO* - {now.strftime('%d %B %Y')}\n\n"
        report += f"💰 *VENTAS*\n"
        report += f"Total: ${sales_data['total']:,.0f} ({sales_data['count']} pedidos)\n"
        report += f"Ticket promedio: ${sales_data['avg_ticket']:,.0f}\n\n"
        
        # Stock alerts
        low_stock = self.db.get_low_stock_products(threshold=5)
        if low_stock:
            report += f"📦 *ALERTAS DE STOCK*\n"
            for p in low_stock[:5]:
                emoji = "⚠️" if p['stock'] > 0 else "❌"
                report += f"{emoji} {p['name']}: {p['stock']} unidades\n"
            report += "\n"
        
        report += f"🤖 *BOT PERFORMANCE*\n"
        report += f"Mensajes procesados: {sales_data.get('messages', 'N/A')}\n"
        report += f"Tiempo respuesta: {sales_data.get('avg_response_time', 'N/A')}\n"
        
        return report
    
    def _generate_weekly_report(self) -> str:
        """Generate weekly report"""
        now = datetime.now()
        start_date = now - timedelta(days=7)
        
        sales_data = self._get_sales_from_db(start_date, now)
        
        report = f"📊 *REPORTE SEMANAL* - {start_date.strftime('%d %b')} - {now.strftime('%d %b')}\n\n"
        report += f"💰 *VENTAS*\n"
        report += f"Total: ${sales_data['total']:,.0f} ({sales_data['count']} pedidos)\n"
        report += f"Ticket promedio: ${sales_data['avg_ticket']:,.0f}\n"
        
        return report
    
    def _generate_monthly_report(self) -> str:
        """Generate monthly report"""
        now = datetime.now()
        start_date = now - timedelta(days=30)
        
        sales_data = self._get_sales_from_db(start_date, now)
        
        report = f"📊 *REPORTE MENSUAL* - {now.strftime('%B %Y')}\n\n"
        report += f"💰 *VENTAS*\n"
        report += f"Total: ${sales_data['total']:,.0f} ({sales_data['count']} pedidos)\n"
        report += f"Ticket promedio: ${sales_data['avg_ticket']:,.0f}\n"
        
        return report
    
    def _get_sales_from_db(self, start_date: datetime, end_date: datetime) -> Dict:
        """Get sales data from database"""
        # This is a simplified version - implement based on your DB schema
        try:
            orders = self.db.get_orders_between(start_date, end_date)
            
            total = sum(o.get('total', 0) for o in orders)
            count = len(orders)
            avg_ticket = total / count if count > 0 else 0
            
            completed = sum(1 for o in orders if o.get('status') == 'completed')
            pending = sum(1 for o in orders if o.get('status') == 'pending')
            cancelled = sum(1 for o in orders if o.get('status') == 'cancelled')
            
            return {
                'total': total,
                'count': count,
                'avg_ticket': avg_ticket,
                'completed': completed,
                'pending': pending,
                'cancelled': cancelled,
                'top_products': []
            }
        except Exception as e:
            logger.error(f"Error getting sales data: {e}")
            return {
                'total': 0,
                'count': 0,
                'avg_ticket': 0,
                'completed': 0,
                'pending': 0,
                'cancelled': 0
            }
    
    def _error_response(self, message: str) -> Dict:
        """Format error response"""
        return {
            "response_type": "ephemeral",
            "text": f"❌ {message}"
        }
