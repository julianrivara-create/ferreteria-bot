#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A/B Testing Framework
Test different messages, offers, and flows
"""

import logging
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ABTestManager:
    """Manage A/B tests"""
    
    def __init__(self, db=None):
        """
        Initialize A/B test manager
        
        Args:
            db: Database instance (optional)
        """
        self.db = db
        self.tests = {}  # In-memory storage
    
    def create_test(self, name: str, variants: Dict[str, Dict]) -> str:
        """
        Create new A/B test
        
        Args:
            name: Test name
            variants: Dict of variants {variant_id: {config}}
            
        Returns:
            Test ID
        """
        test_id = f"test_{name}_{int(datetime.now().timestamp())}"
        
        self.tests[test_id] = {
            'name': name,
            'variants': variants,
            'results': {
                variant_id: {'shown': 0, 'converted': 0, 'revenue': 0}
                for variant_id in variants.keys()
            },
            'created_at': datetime.now().isoformat(),
            'status': 'active'
        }
        
        logger.info(f"Created A/B test: {test_id} with {len(variants)} variants")
        return test_id
    
    def get_variant(self, test_id: str, user_id: str) -> str:
        """
        Get variant for user (consistent assignment)
        
        Args:
            test_id: Test ID
            user_id: User ID
            
        Returns:
            Variant ID
        """
        if test_id not in self.tests:
            return None
        
        test = self.tests[test_id]
        variants = list(test['variants'].keys())
        
        # Consistent hash-based assignment
        hash_val = int(hashlib.md5(f"{test_id}_{user_id}".encode()).hexdigest(), 16)
        variant_index = hash_val % len(variants)
        variant_id = variants[variant_index]
        
        # Track impression
        test['results'][variant_id]['shown'] += 1
        
        return variant_id
    
    def track_conversion(self, test_id: str, variant_id: str, revenue: float = 0):
        """
        Track conversion for variant
        
        Args:
            test_id: Test ID
            variant_id: Variant ID
            revenue: Optional revenue amount
        """
        if test_id not in self.tests:
            return
        
        test = self.tests[test_id]
        if variant_id in test['results']:
            test['results'][variant_id]['converted'] += 1
            test['results'][variant_id]['revenue'] += revenue
            
            logger.info(f"Conversion tracked: {test_id}/{variant_id}")
    
    def get_results(self, test_id: str) -> Dict:
        """
        Get test results
        
        Args:
            test_id: Test ID
            
        Returns:
            Results dict
        """
        if test_id not in self.tests:
            return None
        
        test = self.tests[test_id]
        results = {}
        
        for variant_id, data in test['results'].items():
            shown = data['shown']
            converted = data['converted']
            revenue = data['revenue']
            
            conversion_rate = (converted / shown * 100) if shown > 0 else 0
            avg_revenue = (revenue / converted) if converted > 0 else 0
            
            results[variant_id] = {
                'shown': shown,
                'converted': converted,
                'conversion_rate': conversion_rate,
                'revenue': revenue,
                'avg_revenue': avg_revenue
            }
        
        return {
            'name': test['name'],
            'variants': results,
            'created_at': test['created_at'],
            'status': test['status']
        }
    
    def generate_report(self, test_id: str) -> str:
        """
        Generate Slack-formatted report
        
        Args:
            test_id: Test ID
            
        Returns:
            Formatted report
        """
        results = self.get_results(test_id)
        
        if not results:
            return "❌ Test not found"
        
        report = f"📊 *A/B Test Results: {results['name']}*\n\n"
        
        # Find winner
        best_variant = max(
            results['variants'].items(),
            key=lambda x: x[1]['conversion_rate']
        )
        
        for variant_id, data in results['variants'].items():
            is_winner = variant_id == best_variant[0]
            emoji = "🏆" if is_winner else "📈"
            
            report += f"{emoji} *Variant {variant_id}*\n"
            report += f"• Shown: {data['shown']}\n"
            report += f"• Converted: {data['converted']}\n"
            report += f"• Conversion Rate: {data['conversion_rate']:.2f}%\n"
            report += f"• Revenue: ${data['revenue']:,.0f}\n"
            report += f"• Avg Revenue: ${data['avg_revenue']:,.0f}\n\n"
        
        # Statistical significance (simplified)
        if best_variant[1]['shown'] > 100:
            report += "✅ *Statistically significant* (>100 impressions)\n"
        else:
            report += "⚠️ *Not enough data* (<100 impressions)\n"
        
        return report
    
    def stop_test(self, test_id: str):
        """Stop test"""
        if test_id in self.tests:
            self.tests[test_id]['status'] = 'stopped'
            logger.info(f"Stopped test: {test_id}")


# Example test configurations
EXAMPLE_TESTS = {
    'greeting_test': {
        'A': {'message': 'Hola! ¿Cómo puedo ayudarte?'},
        'B': {'message': '¡Bienvenido! ¿Qué producto buscas?'},
        'C': {'message': 'Hey! Estoy aquí para ayudarte a encontrar el producto perfecto'}
    },
    'discount_offer_test': {
        'A': {'discount': 5, 'message': '5% de descuento en tu primera compra'},
        'B': {'discount': 10, 'message': '10% OFF especial para ti'},
        'C': {'discount': 0, 'message': 'Envío gratis en tu primera compra'}
    },
    'cta_test': {
        'A': {'cta': 'Comprar Ahora'},
        'B': {'cta': 'Agregar al Carrito'},
        'C': {'cta': 'Lo Quiero!'}
    }
}
