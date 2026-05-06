#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bundles Module
Manages product bundles and seasonal promotions
"""

import json
from datetime import datetime, date
from typing import Dict, Any, List, Optional


class BundleManager:
    """
    Manage product bundles and promotions
    """
    
    def __init__(self, bundles_file: str = "bundles.json", db=None):
        """
        Initialize bundle manager
        
        Args:
            bundles_file: Path to bundles JSON file
            db: Database instance for price lookups
        """
        self.bundles_file = bundles_file
        self.db = db
        self.bundles_data = self._load_bundles()
    
    def _load_bundles(self) -> Dict[str, Any]:
        """Load bundles from JSON file"""
        try:
            with open(self.bundles_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return self._get_fallback_bundles()
            
        return data if (data and (data.get("bundles_permanentes") or data.get("bundles_temporada"))) else self._get_fallback_bundles()

    def _get_fallback_bundles(self):
        """Hardcoded bundles for demo/fallback"""
        return {
            "bundles_permanentes": {
                "kit_taladrado": {
                    "name": "Kit Taladrado Completo",
                    "description": "Mechas acero rápido + tarugos nylon, todo para taladrar",
                    "active": True,
                    "discount_percent": 10,
                    "products": []
                },
                "kit_pintura": {
                    "name": "Kit Pintura Interior",
                    "description": "Látex interior + rodillo + bandeja + lija — todo para pintar",
                    "active": True,
                    "discount_percent": 8,
                    "products": []
                }
            },
            "bundles_temporada": {}
        }
    
    def _is_bundle_active(self, bundle: Dict[str, Any]) -> bool:
        """Check if a seasonal bundle is currently active"""
        if "active_from" not in bundle:
            # Permanent bundle
            return bundle.get("active", True)
        
        # Seasonal bundle - check dates
        today = date.today()
        active_from = datetime.strptime(bundle["active_from"], "%Y-%m-%d").date()
        active_until = datetime.strptime(bundle["active_until"], "%Y-%m-%d").date()
        
        return active_from <= today <= active_until
    
    def get_active_bundles(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all currently active bundles
        
        Args:
            category: Filter by category (optional)
        
        Returns:
            List of active bundles with calculated prices
        """
        active_bundles = []
        
        # Permanent bundles
        for bundle_id, bundle in self.bundles_data.get("bundles_permanentes", {}).items():
            if self._is_bundle_active(bundle):
                if category is None or bundle.get("category") == category:
                    bundle_with_price = self._calculate_bundle_price(bundle_id, bundle)
                    if bundle_with_price:
                        active_bundles.append(bundle_with_price)
        
        # Seasonal bundles
        for bundle_id, bundle in self.bundles_data.get("bundles_temporada", {}).items():
            if self._is_bundle_active(bundle):
                if category is None or bundle.get("category") == category:
                    bundle_with_price = self._calculate_bundle_price(bundle_id, bundle)
                    if bundle_with_price:
                        active_bundles.append(bundle_with_price)
        
        return active_bundles
    
    def _calculate_bundle_price(self, bundle_id: str, bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Calculate total price for a bundle with discount"""
        if not self.db:
            return None
        
        total_regular_price = 0
        products_details = []
        
        # Calculate regular price
        for product in bundle.get("products", []):
            sku = product["sku"]
            quantity = product.get("quantity", 1)
            
            # Get product from database
            db_product = self.db.get_product_by_sku(sku)
            if not db_product:
                # Product not found, skip bundle
                return None
            
            # Check stock
            if db_product["stock_qty"] < quantity:
                # Not enough stock
                return None
            
            price = db_product["price_ars"]
            total_regular_price += price * quantity
            
            products_details.append({
                "sku": sku,
                "name": db_product["model"],
                "quantity": quantity,
                "unit_price": price,
                "subtotal": price * quantity
            })
        
        # Apply discount
        discount_percent = bundle.get("discount_percent", 0)
        discount_amount = int(total_regular_price * (discount_percent / 100))
        final_price = total_regular_price - discount_amount
        
        return {
            "bundle_id": bundle_id,
            "name": bundle["name"],
            "description": bundle["description"],
            "products": products_details,
            "regular_price": total_regular_price,
            "discount_percent": discount_percent,
            "discount_amount": discount_amount,
            "final_price": final_price,
            "savings": discount_amount,
            "category": bundle.get("category", "General"),
            "is_seasonal": "active_from" in bundle
        }
    
    def get_bundle_by_id(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        """Get specific bundle by ID"""
        # Check permanent bundles
        if bundle_id in self.bundles_data["bundles_permanentes"]:
            bundle = self.bundles_data["bundles_permanentes"][bundle_id]
            if self._is_bundle_active(bundle):
                return self._calculate_bundle_price(bundle_id, bundle)
        
        # Check seasonal bundles
        if bundle_id in self.bundles_data["bundles_temporada"]:
            bundle = self.bundles_data["bundles_temporada"][bundle_id]
            if self._is_bundle_active(bundle):
                return self._calculate_bundle_price(bundle_id, bundle)
        
        return None
    
    def format_bundle_message(self, bundle: Dict[str, Any]) -> str:
        """Format bundle as user-friendly message"""
        msg = f"{bundle['name']}\n"
        msg += f"{bundle['description']}\n\n"
        
        msg += "Incluye:\n"
        for prod in bundle['products']:
            msg += f"  • {prod['quantity']}x {prod['name']}\n"
        
        msg += f"\nPrecio regular: ${bundle['regular_price']:,}\n"
        msg += f"Descuento: {bundle['discount_percent']}% (-${bundle['discount_amount']:,})\n"
        msg += f"Precio final: ${bundle['final_price']:,}\n"
        msg += f"Te ahorrás: ${bundle['savings']:,}"

        if bundle.get('is_seasonal'):
            msg += "\nPromo temporal - aprovechá ahora."
        
        return msg
