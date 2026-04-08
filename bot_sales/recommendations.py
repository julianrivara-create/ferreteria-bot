#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Recommendation Engine
Provides intelligent product recommendations based on context and history
"""

from typing import List, Dict, Any, Optional
import random

class RecommendationEngine:
    """
    Intelligent product recommendation system
    """
    
    def __init__(self, db):
        self.db = db
        self.rules = self._load_rules()
        
    def _load_rules(self) -> Dict[str, List[str]]:
        """
        Load recommendation rules dynamically based on available categories
        Format: category -> list of recommended related categories/keywords
        """
        # Get all categories from database
        try:
            categories = self.db.get_all_categories()
        except:
            categories = []
        
        # Build dynamic rules: recommend products from other categories
        rules = {}
        for category in categories:
            # For each category, recommend products from all other categories
            other_categories = [c for c in categories if c != category]
            rules[category] = other_categories
        
        return rules

    def get_recommendations(
        self, 
        current_product_sku: Optional[str] = None, 
        category: Optional[str] = None,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get product recommendations based on context
        """
        recommendations = []
        target_category = category
        
        # If SKU provided, get its category
        if current_product_sku and not target_category:
            product = self.db.get_product_by_sku(current_product_sku)
            if product:
                target_category = product.get("category")
        
        if not target_category:
            # Fallback: Trending products / Best sellers
            return self._get_trending_products(limit)
            
        # Get related categories based on rules
        related_terms = self.rules.get(target_category, [])
        if not related_terms:
            return self._get_trending_products(limit)
            
        # Search for products matching related terms
        for term in related_terms:
            # Simple search in DB (this logic assumes db has a flexible search or we filter by category)
            # Since our DB is simple, we might need a helper. 
            # For now, let's try to find products that match the term in model or category
            
            # Using keyword search logic similar to database.find_matches but broader
            products = self._find_products_by_term(term)
            
            for prod in products:
                # Avoid recommending the same product or same category main item (e.g. don't recommend another taladro for a taladro)
                if prod['sku'] == current_product_sku:
                    continue
                    
                # Add to recommendations if not present
                if not any(r['sku'] == prod['sku'] for r in recommendations):
                    recommendations.append(prod)
                    
                if len(recommendations) >= limit:
                    break
            
            if len(recommendations) >= limit:
                break
                
        return recommendations[:limit]

    def _find_products_by_term(self, term: str) -> List[Dict[str, Any]]:
        """Helper to find available products by term"""
        all_products = self.db.load_stock()
        matches = []
        for p in all_products:
            # Check availability
            if self.db.available_for_sku(p['sku']) > 0:
                if term.lower() in p['model'].lower() or term.lower() in p.get('category', '').lower():
                    matches.append(p)
        return matches

    def _get_trending_products(self, limit: int) -> List[Dict[str, Any]]:
        """Get trending/popular products (placeholder logic)"""
        # In a real app, this would use analytics data. 
        # For now, return highest-priced items (usually premium/popular)
        all_products = self.db.load_stock()
        available = [p for p in all_products if self.db.available_for_sku(p['sku']) > 0]
        
        # Sort by price (higher price = premium products)
        available.sort(key=lambda x: x.get('price_ars', 0), reverse=True)
        
        return available[:limit]

    def format_recommendation_message(self, recommendations: List[Dict[str, Any]]) -> str:
        """Format recommendations for the chat"""
        if not recommendations:
            return ""
            
        msg = "💡 También te puede interesar:\n"
        for p in recommendations:
            price = f"${p['price_ars']:,}".replace(",", ".")
            msg += f"• {p['model']} a {price}\n"
            
        return msg
