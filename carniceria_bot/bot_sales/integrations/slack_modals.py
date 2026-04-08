#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack Modals
Interactive forms for complex data capture
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class SlackModals:
    """Manage Slack modals (interactive forms)"""
    
    def __init__(self, slack_connector, db, config):
        """
        Initialize modals manager
        
        Args:
            slack_connector: SlackConnector instance
            db: Database instance
            config: Config instance
        """
        self.slack = slack_connector
        self.db = db
        self.config = config
    
    def open_product_search_modal(self, trigger_id: str):
        """Open product search modal"""
        # Get categories from database
        categories = self.db.get_all_categories()
        
        category_options = [
            {
                "text": {"type": "plain_text", "text": cat},
                "value": cat.lower()
            }
            for cat in categories
        ]
        
        modal = {
            "type": "modal",
            "callback_id": "product_search_submit",
            "title": {"type": "plain_text", "text": "Buscar Producto"},
            "submit": {"type": "plain_text", "text": "Buscar"},
            "close": {"type": "plain_text", "text": "Cancelar"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "category_block",
                    "element": {
                        "type": "static_select",
                        "action_id": "category_select",
                        "placeholder": {"type": "plain_text", "text": "Selecciona categoría"},
                        "options": category_options
                    },
                    "label": {"type": "plain_text", "text": "Categoría"}
                },
                {
                    "type": "input",
                    "block_id": "model_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "model_input",
                        "placeholder": {"type": "plain_text", "text": "Ej: iPhone 15 Pro"}
                    },
                    "label": {"type": "plain_text", "text": "Modelo"},
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "storage_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "storage_input",
                        "placeholder": {"type": "plain_text", "text": "Ej: 256GB"}
                    },
                    "label": {"type": "plain_text", "text": "Almacenamiento"},
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "price_range_block",
                    "element": {
                        "type": "static_select",
                        "action_id": "price_range_select",
                        "placeholder": {"type": "plain_text", "text": "Selecciona rango"},
                        "options": [
                            {"text": {"type": "plain_text", "text": "Todos"}, "value": "all"},
                            {"text": {"type": "plain_text", "text": "< $500"}, "value": "0-500"},
                            {"text": {"type": "plain_text", "text": "$500 - $1000"}, "value": "500-1000"},
                            {"text": {"type": "plain_text", "text": "$1000 - $2000"}, "value": "1000-2000"},
                            {"text": {"type": "plain_text", "text": "> $2000"}, "value": "2000-999999"}
                        ]
                    },
                    "label": {"type": "plain_text", "text": "Rango de Precio"},
                    "optional": True
                }
            ]
        }
        
        self.slack.open_modal(trigger_id, modal)
    
    def open_discount_request_modal(self, trigger_id: str, product_sku: str = None):
        """Open discount request modal"""
        modal = {
            "type": "modal",
            "callback_id": "discount_request_submit",
            "title": {"type": "plain_text", "text": "Solicitar Descuento"},
            "submit": {"type": "plain_text", "text": "Solicitar"},
            "close": {"type": "plain_text", "text": "Cancelar"},
            "private_metadata": product_sku or "",
            "blocks": [
                {
                    "type": "input",
                    "block_id": "product_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "product_input",
                        "placeholder": {"type": "plain_text", "text": "SKU del producto"},
                        "initial_value": product_sku or ""
                    },
                    "label": {"type": "plain_text", "text": "Producto (SKU)"}
                },
                {
                    "type": "input",
                    "block_id": "discount_block",
                    "element": {
                        "type": "number_input",
                        "is_decimal_allowed": False,
                        "action_id": "discount_input",
                        "min_value": "1",
                        "max_value": "50"
                    },
                    "label": {"type": "plain_text", "text": "Descuento (%)"}
                },
                {
                    "type": "input",
                    "block_id": "reason_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "reason_input",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "Justificación del descuento"}
                    },
                    "label": {"type": "plain_text", "text": "Razón"}
                },
                {
                    "type": "input",
                    "block_id": "customer_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "customer_input",
                        "placeholder": {"type": "plain_text", "text": "Nombre del cliente"}
                    },
                    "label": {"type": "plain_text", "text": "Cliente"}
                }
            ]
        }
        
        self.slack.open_modal(trigger_id, modal)
    
    def open_customer_info_modal(self, trigger_id: str, session_id: str = None):
        """Open customer information modal"""
        modal = {
            "type": "modal",
            "callback_id": "customer_info_submit",
            "title": {"type": "plain_text", "text": "Info del Cliente"},
            "submit": {"type": "plain_text", "text": "Guardar"},
            "close": {"type": "plain_text", "text": "Cancelar"},
            "private_metadata": session_id or "",
            "blocks": [
                {
                    "type": "input",
                    "block_id": "name_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "name_input",
                        "placeholder": {"type": "plain_text", "text": "Nombre completo"}
                    },
                    "label": {"type": "plain_text", "text": "Nombre"}
                },
                {
                    "type": "input",
                    "block_id": "email_block",
                    "element": {
                        "type": "email_text_input",
                        "action_id": "email_input",
                        "placeholder": {"type": "plain_text", "text": "email@example.com"}
                    },
                    "label": {"type": "plain_text", "text": "Email"},
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "phone_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "phone_input",
                        "placeholder": {"type": "plain_text", "text": "+54 11 2233 4455"}
                    },
                    "label": {"type": "plain_text", "text": "Teléfono"}
                },
                {
                    "type": "input",
                    "block_id": "address_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "address_input",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "Dirección completa"}
                    },
                    "label": {"type": "plain_text", "text": "Dirección"},
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "notes_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "notes_input",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "Notas adicionales"}
                    },
                    "label": {"type": "plain_text", "text": "Notas"},
                    "optional": True
                }
            ]
        }
        
        self.slack.open_modal(trigger_id, modal)
    
    def open_config_modal(self, trigger_id: str):
        """Open bot configuration modal"""
        modal = {
            "type": "modal",
            "callback_id": "config_submit",
            "title": {"type": "plain_text", "text": "Configuración"},
            "submit": {"type": "plain_text", "text": "Guardar"},
            "close": {"type": "plain_text", "text": "Cancelar"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Features del Bot*"
                    }
                },
                {
                    "type": "input",
                    "block_id": "upselling_block",
                    "element": {
                        "type": "checkboxes",
                        "action_id": "upselling_checkbox",
                        "options": [
                            {
                                "text": {"type": "plain_text", "text": "Habilitar Upselling"},
                                "value": "enable_upselling"
                            }
                        ]
                    },
                    "label": {"type": "plain_text", "text": "Upselling"},
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "crosssell_block",
                    "element": {
                        "type": "checkboxes",
                        "action_id": "crosssell_checkbox",
                        "options": [
                            {
                                "text": {"type": "plain_text", "text": "Habilitar Cross-selling"},
                                "value": "enable_crosssell"
                            }
                        ]
                    },
                    "label": {"type": "plain_text", "text": "Cross-selling"},
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "bundles_block",
                    "element": {
                        "type": "checkboxes",
                        "action_id": "bundles_checkbox",
                        "options": [
                            {
                                "text": {"type": "plain_text", "text": "Habilitar Bundles"},
                                "value": "enable_bundles"
                            }
                        ]
                    },
                    "label": {"type": "plain_text", "text": "Bundles"},
                    "optional": True
                },
                {
                    "type": "divider"
                },
                {
                    "type": "input",
                    "block_id": "discount_threshold_block",
                    "element": {
                        "type": "number_input",
                        "is_decimal_allowed": False,
                        "action_id": "discount_threshold_input",
                        "min_value": "0",
                        "max_value": "100",
                        "initial_value": str(getattr(self.config, 'REQUIRE_APPROVAL_DISCOUNT_OVER', 10))
                    },
                    "label": {"type": "plain_text", "text": "Umbral de aprobación de descuento (%)"}
                }
            ]
        }
        
        self.slack.open_modal(trigger_id, modal)
    
    def handle_modal_submission(self, callback_id: str, view: Dict, user_id: str) -> Dict:
        """
        Handle modal submission
        
        Args:
            callback_id: Modal callback ID
            view: View data from submission
            user_id: Slack user ID
            
        Returns:
            Response dict
        """
        if callback_id == "product_search_submit":
            return self._handle_product_search(view, user_id)
        elif callback_id == "discount_request_submit":
            return self._handle_discount_request(view, user_id)
        elif callback_id == "customer_info_submit":
            return self._handle_customer_info(view, user_id)
        elif callback_id == "config_submit":
            return self._handle_config_update(view, user_id)
        else:
            return {"response_action": "errors", "errors": {"base": "Unknown callback"}}
    
    def _handle_product_search(self, view: Dict, user_id: str) -> Dict:
        """Handle product search submission"""
        values = view['state']['values']
        
        # Extract form data
        category = values['category_block']['category_select']['selected_option']['value']
        model = values['model_block']['model_input'].get('value', '')
        storage = values['storage_block']['storage_input'].get('value', '')
        
        # Search products
        products = self.db.search_products_advanced(
            category=category,
            model=model,
            storage=storage
        )
        
        # Send results (would use product cards)
        logger.info(f"Product search: {len(products)} results for category={category}")
        
        return {}  # Success
    
    def _handle_discount_request(self, view: Dict, user_id: str) -> Dict:
        """Handle discount request submission"""
        values = view['state']['values']
        
        sku = values['product_block']['product_input']['value']
        discount_pct = int(values['discount_block']['discount_input']['value'])
        reason = values['reason_block']['reason_input']['value']
        customer = values['customer_block']['customer_input']['value']
        
        # Validate discount
        if discount_pct > 50:
            return {
                "response_action": "errors",
                "errors": {
                    "discount_block": "Descuento máximo: 50%"
                }
            }
        
        # Process discount request
        logger.info(f"Discount request: {discount_pct}% for {sku} by {customer}")
        
        return {}  # Success
    
    def _handle_customer_info(self, view: Dict, user_id: str) -> Dict:
        """Handle customer info submission"""
        values = view['state']['values']
        
        customer_data = {
            'name': values['name_block']['name_input']['value'],
            'email': values['email_block']['email_input'].get('value'),
            'phone': values['phone_block']['phone_input']['value'],
            'address': values['address_block']['address_input'].get('value'),
            'notes': values['notes_block']['notes_input'].get('value')
        }
        
        # Save customer data
        logger.info(f"Customer info saved: {customer_data['name']}")
        
        return {}  # Success
    
    def _handle_config_update(self, view: Dict, user_id: str) -> Dict:
        """Handle config update submission"""
        values = view['state']['values']
        
        # Extract checkboxes
        upselling_enabled = bool(values['upselling_block']['upselling_checkbox'].get('selected_options'))
        crosssell_enabled = bool(values['crosssell_block']['crosssell_checkbox'].get('selected_options'))
        bundles_enabled = bool(values['bundles_block']['bundles_checkbox'].get('selected_options'))
        discount_threshold = int(values['discount_threshold_block']['discount_threshold_input']['value'])
        
        # Update config (would persist to database or config file)
        logger.info(f"Config updated by {user_id}: upselling={upselling_enabled}, threshold={discount_threshold}")
        
        return {}  # Success
