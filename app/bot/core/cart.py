#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Multi-Product Cart Implementation
Allows users to add multiple products before checkout
"""

import time
import uuid
from typing import Dict, List, Optional, Any


class ShoppingCart:
    """
    Shopping cart for multi-product purchases
    """
    
    def __init__(self, user_id: str):
        self.cart_id = f"CART-{uuid.uuid4().hex[:8].upper()}"
        self.user_id = user_id
        self.items = []
        self.created_at = time.time()
        self.updated_at = time.time()
    
    def add_item(
        self,
        sku: str,
        producto: str,
        precio: int,
        quantity: int = 1
    ) -> Dict[str, Any]:
        """
        Add item to cart
        
        Returns:
            Status dict
        """
        # Check if item already in cart
        for item in self.items:
            if item['sku'] == sku:
                item['quantity'] += quantity
                item['subtotal'] = item['quantity'] * item['precio']
                self.updated_at = time.time()
                return {
                    'status': 'updated',
                    'message': f'Cantidad aumentada a {item["quantity"]}'
                }
        
        # Add new item
        self.items.append({
            'sku': sku,
            'producto': producto,
            'precio': precio,
            'quantity': quantity,
            'subtotal': precio * quantity
        })
        
        self.updated_at = time.time()
        
        return {
            'status': 'added',
            'message': f'{producto} agregado al carrito'
        }
    
    def remove_item(self, sku: str) -> Dict[str, Any]:
        """Remove item from cart"""
        original_count = len(self.items)
        self.items = [item for item in self.items if item['sku'] != sku]
        
        if len(self.items) < original_count:
            self.updated_at = time.time()
            return {'status': 'removed', 'message': 'Producto eliminado'}
        else:
            return {'status': 'not_found', 'message': 'Producto no encontrado en carrito'}
    
    def update_quantity(self, sku: str, new_quantity: int) -> Dict[str, Any]:
        """Update item quantity"""
        if new_quantity <= 0:
            return self.remove_item(sku)
        
        for item in self.items:
            if item['sku'] == sku:
                item['quantity'] = new_quantity
                item['subtotal'] = item['precio'] * new_quantity
                self.updated_at = time.time()
                return {'status': 'updated', 'message': f'Cantidad actualizada a {new_quantity}'}
        
        return {'status': 'not_found', 'message': 'Producto no encontrado'}
    
    def get_total(self) -> int:
        """Calculate total price"""
        return sum(item['subtotal'] for item in self.items)
    
    def get_item_count(self) -> int:
        """Get total number of items"""
        return sum(item['quantity'] for item in self.items)
    
    def clear(self) -> None:
        """Clear all items"""
        self.items = []
        self.updated_at = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert cart to dictionary"""
        return {
            'cart_id': self.cart_id,
            'user_id': self.user_id,
            'items': self.items,
            'item_count': self.get_item_count(),
            'total': self.get_total(),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class CartManager:
    """
    Manages shopping carts for all users
    """
    
    def __init__(self):
        self.carts = {}  # {user_id: ShoppingCart}
    
    def get_or_create_cart(self, user_id: str) -> ShoppingCart:
        """Get existing cart or create new one"""
        if user_id not in self.carts:
            self.carts[user_id] = ShoppingCart(user_id)
        
        return self.carts[user_id]
    
    def get_cart(self, user_id: str) -> Optional[ShoppingCart]:
        """Get cart if exists"""
        return self.carts.get(user_id)
    
    def delete_cart(self, user_id: str) -> bool:
        """Delete cart after checkout"""
        if user_id in self.carts:
            del self.carts[user_id]
            return True
        return False


# Global cart manager
_cart_manager = None


def get_cart_manager() -> CartManager:
    """Get or create global cart manager"""
    global _cart_manager
    if _cart_manager is None:
        _cart_manager = CartManager()
    return _cart_manager
