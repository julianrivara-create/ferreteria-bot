#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Offline Mock Data Service
Provides realistic fake data for the dashboard when offline
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

class MockDataService:
    """Service to generate mock analytics data"""
    
    def __init__(self):
        self.products = self._generate_products()
        self.sales = self._generate_recent_sales()
    
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get main dashboard KPI summary"""
        today_sales = sum(s['total'] for s in self.sales if s['is_today'])
        month_sales = sum(s['total'] for s in self.sales)
        
        return {
            'revenue_today': today_sales,
            'revenue_month': month_sales,
            'active_chats': random.randint(3, 15),
            'conversion_rate': random.uniform(2.5, 4.8),
            'pending_orders': random.randint(1, 8),
            'low_stock_items': random.randint(0, 5)
        }
        
    def get_daily_sales_stats(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily sales stats for analytics API"""
        stats = []
        base_date = datetime.now()
        for i in range(days):
            date = base_date - timedelta(days=days-1-i)
            # Random daily stats
            count = random.randint(0, 5)
            revenue = count * random.randint(50000, 200000)
            
            stats.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': count,
                'revenue': revenue
            })
        return stats

    def get_top_products_stats(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top products for analytics API"""
        return [
            {
                'product_sku': p['name'],
                'sales_count': p['sold'],
                'total_revenue': p['revenue']
            }
            for p in sorted(self.products, key=lambda x: x['revenue'], reverse=True)[:limit]
        ]

    def get_sales_chart_data(self, period: str = 'week') -> Dict[str, List]:
        """Get mock data for sales chart"""
        days = 7 if period == 'week' else 30
        labels = []
        values = []
        
        base_date = datetime.now()
        for i in range(days):
            date = base_date - timedelta(days=days-1-i)
            labels.append(date.strftime('%d/%m'))
            # Generate trend with some noise
            base_val = 500000 + (i * 10000) 
            noise = random.randint(-200000, 300000)
            values.append(max(0, base_val + noise))
            
        return {
            'labels': labels,
            'values': values
        }
    
    def get_product_performance(self) -> List[Dict[str, Any]]:
        """Get product sales performance"""
        return sorted(self.products, key=lambda p: p['revenue'], reverse=True)[:5]
        
    def _generate_products(self) -> List[Dict[str, Any]]:
        """Generate mock products"""
        products = [
            ("Producto Premium", 1800000),
            ("Producto Intermedio", 1400000),
            ("Accesorio Plus", 450000),
            ("Producto Profesional", 1900000),
            ("Producto Entrada", 950000),
        ]
        
        return [
            {
                'name': name,
                'price': price,
                'sold': random.randint(10, 100),
                'revenue': price * random.randint(10, 100),
                'stock': random.randint(0, 50)
            }
            for name, price in products
        ]
        
    def _generate_recent_sales(self) -> List[Dict[str, Any]]:
        """Generate recent sales transactions"""
        data = []
        now = datetime.now()
        
        # Today's sales
        for _ in range(random.randint(2, 8)):
            data.append({
                'date': now.isoformat(),
                'total': random.randint(450000, 2000000),
                'is_today': True
            })
            
        # Past sales
        for i in range(1, 30):
            date = now - timedelta(days=i)
            for _ in range(random.randint(1, 10)):
                data.append({
                    'date': date.isoformat(),
                    'total': random.randint(450000, 2000000),
                    'is_today': False
                })
        return data

    def get_sales_list(self, limit: int = 50, status: str = 'all') -> List[Dict[str, Any]]:
        """Get mock sales list"""
        mock_sales = []
        statuses = ['completed', 'pending', 'cancelled']
        
        for i in range(min(limit, 30)):
            product = random.choice(self.products)
            is_today = i < 5
            date = datetime.now() if is_today else datetime.now() - timedelta(days=random.randint(1, 10))
            
            mock_sales.append({
                'id': f'MOCK-{1000+i}',
                'timestamp': date.strftime('%Y-%m-%d %H:%M:%S'),
                'product_sku': product['name'],
                'total_ars': product['price'],
                'status': random.choice(statuses) if status == 'all' else status,
                'customer_email': f'user{i}@example.com',
                'payment_method': random.choice(['mercadopago', 'transfer', 'cash'])
            })
            
        return sorted(mock_sales, key=lambda x: x['timestamp'], reverse=True)

    def get_conversations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get mock conversation history"""
        conversations = []
        for i in range(min(limit, 15)):
            date = datetime.now() - timedelta(minutes=random.randint(5, 120))
            conversations.append({
                'session_id': f'mock-session-{i}',
                'last_message': date.strftime('%Y-%m-%d %H:%M:%S'),
                'message_count': random.randint(5, 50),
                'preview': "Hola, quería consultar disponibilidad y precio..."
            })
        return sorted(conversations, key=lambda x: x['last_message'], reverse=True)

mock_data = MockDataService()
