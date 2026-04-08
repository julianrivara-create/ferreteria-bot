#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack Automated Reports
Daily/weekly reports sent to admin channel
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

class SlackReports:
    """Handler for automated Slack reports"""
    
    def __init__(self, slack_connector, bot, db, config):
        """
        Initialize reports handler
        
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
        self.reports_channel = getattr(config, 'SLACK_REPORTS_CHANNEL', None)
        self.scheduler = None
    
    def start_scheduler(self):
        """Start automated report scheduler"""
        if not self.reports_channel:
            logger.warning("SLACK_REPORTS_CHANNEL not configured, skipping scheduler")
            return
        
        enable_reports = getattr(self.config, 'SLACK_ENABLE_AUTO_REPORTS', False)
        if not enable_reports:
            logger.info("Automated reports disabled in config")
            return
        
        self.scheduler = BackgroundScheduler()
        
        # Daily report
        daily_time = getattr(self.config, 'SLACK_DAILY_REPORT_TIME', '09:00')
        hour, minute = map(int, daily_time.split(':'))
        
        self.scheduler.add_job(
            self.send_daily_report,
            CronTrigger(hour=hour, minute=minute),
            id='daily_report',
            name='Daily Slack Report'
        )
        
        # Weekly report
        weekly_day = getattr(self.config, 'SLACK_WEEKLY_REPORT_DAY', 'monday')
        
        self.scheduler.add_job(
            self.send_weekly_report,
            CronTrigger(day_of_week=weekly_day, hour=hour, minute=minute),
            id='weekly_report',
            name='Weekly Slack Report'
        )
        
        self.scheduler.start()
        logger.info(f"Slack reports scheduler started (daily: {daily_time}, weekly: {weekly_day})")
    
    def send_daily_report(self):
        """Send daily report to Slack"""
        try:
            report = self._generate_daily_report()
            self.slack.send_message(self.reports_channel, report)
            logger.info("Daily report sent to Slack")
        except Exception as e:
            logger.error(f"Error sending daily report: {e}")
    
    def send_weekly_report(self):
        """Send weekly report to Slack"""
        try:
            report = self._generate_weekly_report()
            self.slack.send_message(self.reports_channel, report)
            logger.info("Weekly report sent to Slack")
        except Exception as e:
            logger.error(f"Error sending weekly report: {e}")
    
    def _generate_daily_report(self) -> str:
        """Generate daily report"""
        now = datetime.now()
        start_date = now.replace(hour=0, minute=0, second=0)
        
        # Get sales data
        sales = self._get_sales_data(start_date, now)
        
        # Build report
        report = f"📊 *REPORTE DIARIO* - {now.strftime('%d %B %Y')}\n\n"
        
        # Sales section
        report += "💰 *VENTAS*\n"
        report += f"Total: ${sales['total']:,.0f} ({sales['count']} pedidos)\n"
        
        if sales['count'] > 0:
            report += f"Ticket promedio: ${sales['avg_ticket']:,.0f}\n"
            
            # Compare with yesterday
            yesterday_sales = self._get_sales_data(
                start_date - timedelta(days=1),
                start_date
            )
            
            if yesterday_sales['total'] > 0:
                change_pct = ((sales['total'] - yesterday_sales['total']) / yesterday_sales['total']) * 100
                emoji = "📈" if change_pct > 0 else "📉"
                report += f"vs. ayer: {change_pct:+.1f}% {emoji}\n"
        
        report += "\n"
        
        # Stock alerts
        low_stock = self.db.get_low_stock_products(threshold=5)
        if low_stock:
            report += "📦 *ALERTAS DE STOCK*\n"
            for p in low_stock[:5]:
                emoji = "⚠️" if p['stock'] > 0 else "❌"
                report += f"{emoji} {p['name']}: {p['stock']} unidades\n"
            report += "\n"
        
        # Customer stats
        report += "👥 *CLIENTES*\n"
        report += f"Nuevos: {sales.get('new_customers', 0)}\n"
        report += f"Recurrentes: {sales.get('returning_customers', 0)}\n"
        
        if sales['count'] > 0:
            retention = (sales.get('returning_customers', 0) / sales['count']) * 100
            report += f"Tasa retención: {retention:.0f}%\n"
        
        report += "\n"
        
        # Bot performance
        report += "🤖 *BOT PERFORMANCE*\n"
        report += f"Mensajes procesados: {sales.get('messages_processed', 'N/A')}\n"
        report += f"Tiempo respuesta: {sales.get('avg_response_time', 'N/A')}\n"
        report += f"Handoffs: {sales.get('handoffs', 0)}\n"
        
        return report
    
    def _generate_weekly_report(self) -> str:
        """Generate weekly report"""
        now = datetime.now()
        start_date = now - timedelta(days=7)
        
        # Get sales data
        sales = self._get_sales_data(start_date, now)
        
        # Build report
        report = f"📊 *REPORTE SEMANAL* - {start_date.strftime('%d %b')} - {now.strftime('%d %b')}\n\n"
        
        # Sales section
        report += "💰 *VENTAS*\n"
        report += f"Total: ${sales['total']:,.0f} ({sales['count']} pedidos)\n"
        report += f"Ticket promedio: ${sales['avg_ticket']:,.0f}\n"
        report += f"Conversión: {sales.get('conversion_rate', 0):.1f}%\n\n"
        
        # Top products
        if sales.get('top_products'):
            report += "*Top Productos:*\n"
            for i, p in enumerate(sales['top_products'][:5], 1):
                report += f"{i}. {p['name']} - {p['count']} ventas (${p['total']:,.0f})\n"
            report += "\n"
        
        # Best/worst days
        if sales.get('daily_breakdown'):
            best_day = max(sales['daily_breakdown'], key=lambda x: x['total'])
            worst_day = min(sales['daily_breakdown'], key=lambda x: x['total'])
            
            report += f"Mejor día: {best_day['day']} (${best_day['total']:,.0f})\n"
            report += f"Peor día: {worst_day['day']} (${worst_day['total']:,.0f})\n"
        
        return report
    
    def _get_sales_data(self, start_date: datetime, end_date: datetime) -> Dict:
        """Get sales data from database"""
        try:
            # This is a simplified version - implement based on your DB schema
            orders = self.db.get_orders_between(start_date, end_date)
            
            total = sum(o.get('total', 0) for o in orders)
            count = len(orders)
            avg_ticket = total / count if count > 0 else 0
            
            return {
                'total': total,
                'count': count,
                'avg_ticket': avg_ticket,
                'new_customers': 0,  # Implement based on your logic
                'returning_customers': 0,
                'messages_processed': 0,
                'avg_response_time': 'N/A',
                'handoffs': 0,
                'conversion_rate': 0,
                'top_products': [],
                'daily_breakdown': []
            }
        except Exception as e:
            logger.error(f"Error getting sales data: {e}")
            return {
                'total': 0,
                'count': 0,
                'avg_ticket': 0
            }
    
    def stop_scheduler(self):
        """Stop scheduler"""
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("Slack reports scheduler stopped")
