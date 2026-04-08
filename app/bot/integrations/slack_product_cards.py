#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack Product Cards
Rich product cards with images, prices, and interactive buttons
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ProductCardBuilder:
    """Builder for rich Slack product cards"""
    
    def __init__(self, config):
        """
        Initialize product card builder
        
        Args:
            config: Config instance
        """
        self.config = config
        self.default_image = "https://via.placeholder.com/300x300?text=No+Image"
    
    def build_single_card(self, product: Dict) -> List[Dict]:
        """
        Build a single product card
        
        Args:
            product: Product dict from database
            
        Returns:
            List of Slack blocks
        """
        blocks = []
        
        # Header with product name
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{product.get('modelo', 'Producto')} {product.get('almacenamiento', '')}".strip()
            }
        })
        
        # Main section with image and details
        price = product.get('price_ars', 0)
        stock = product.get('stock', 0)
        sku = product.get('sku', 'N/A')
        
        # Stock emoji
        stock_emoji = "✅" if stock > 5 else "⚠️" if stock > 0 else "❌"
        
        # Build description
        description = f"*Precio:* ${price:,.0f} ARS\n"
        description += f"*Stock:* {stock_emoji} {stock} unidades\n"
        description += f"*SKU:* {sku}\n"
        
        # Add category if available
        if product.get('categoria'):
            description += f"*Categoría:* {product['categoria']}\n"
        
        # Add condition if available
        if product.get('condicion'):
            description += f"*Condición:* {product['condicion']}\n"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": description
            },
            "accessory": {
                "type": "image",
                "image_url": product.get('image_url', self.default_image),
                "alt_text": product.get('modelo', 'Product')
            }
        })
        
        # Action buttons
        buttons = []
        
        # Add to cart button (if in stock)
        if stock > 0:
            buttons.append({
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "🛒 Agregar al Carrito"
                },
                "style": "primary",
                "value": f"add_to_cart_{sku}",
                "action_id": "add_to_cart"
            })
        
        # View details button
        buttons.append({
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "📋 Ver Detalles"
            },
            "value": f"view_details_{sku}",
            "action_id": "view_details"
        })
        
        # Request discount button
        if stock > 0:
            buttons.append({
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "💰 Pedir Descuento"
                },
                "value": f"request_discount_{sku}",
                "action_id": "request_discount"
            })
        
        if buttons:
            blocks.append({
                "type": "actions",
                "elements": buttons
            })
        
        # Divider
        blocks.append({"type": "divider"})
        
        return blocks
    
    def build_product_list(self, products: List[Dict], max_items: int = 5) -> List[Dict]:
        """
        Build a list of product cards
        
        Args:
            products: List of product dicts
            max_items: Maximum number of products to show
            
        Returns:
            List of Slack blocks
        """
        blocks = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🛍️ Productos Encontrados ({len(products)})"
            }
        })
        
        # Show products
        for product in products[:max_items]:
            blocks.extend(self.build_single_card(product))
        
        # Show "more results" if needed
        if len(products) > max_items:
            remaining = len(products) - max_items
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_Y {remaining} productos más..._"
                    }
                ]
            })
        
        return blocks
    
    def build_cart_summary(self, cart_items: List[Dict]) -> List[Dict]:
        """
        Build cart summary card
        
        Args:
            cart_items: List of cart items
            
        Returns:
            List of Slack blocks
        """
        blocks = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🛒 Tu Carrito"
            }
        })
        
        # Calculate total
        total = sum(item.get('price_ars', 0) * item.get('quantity', 1) for item in cart_items)
        
        # Items
        for item in cart_items:
            price = item.get('price_ars', 0)
            quantity = item.get('quantity', 1)
            subtotal = price * quantity
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{item.get('modelo', 'Producto')}*\n${price:,.0f} x {quantity} = ${subtotal:,.0f}"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "❌"
                    },
                    "value": f"remove_from_cart_{item.get('sku')}",
                    "action_id": "remove_from_cart"
                }
            })
        
        # Divider
        blocks.append({"type": "divider"})
        
        # Total
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Total:* ${total:,.0f} ARS"
            }
        })
        
        # Checkout button
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Finalizar Compra"
                    },
                    "style": "primary",
                    "value": "checkout",
                    "action_id": "checkout"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🗑️ Vaciar Carrito"
                    },
                    "style": "danger",
                    "value": "clear_cart",
                    "action_id": "clear_cart"
                }
            ]
        })
        
        return blocks
    
    def build_order_confirmation(self, order: Dict) -> List[Dict]:
        """
        Build order confirmation card
        
        Args:
            order: Order dict
            
        Returns:
            List of Slack blocks
        """
        blocks = []
        
        # Success header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "✅ Pedido Confirmado"
            }
        })
        
        # Order details
        order_id = order.get('order_id', 'N/A')
        total = order.get('total', 0)
        status = order.get('status', 'pending')
        
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Pedido:*\n#{order_id}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Total:*\n${total:,.0f}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Estado:*\n{status.title()}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Fecha:*\n{order.get('created_at', 'N/A')}"
                }
            ]
        })
        
        # Items
        if order.get('items'):
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Productos:*"
                }
            })
            
            for item in order['items']:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• {item.get('modelo')} x{item.get('quantity', 1)}"
                    }
                })
        
        return blocks
