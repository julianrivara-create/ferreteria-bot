#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Objection Handling Module
Provides logic to detect and respond to common customer objections.
"""

from typing import Dict, List, Optional, Any

class ObjectionHandler:
    """
    Handles customer objections (Price, Trust, Shipping, etc.)
    Provides standardized, persuasive responses.
    """
    
    def __init__(self):
        # Patterns to help identify objections (if needed for non-LLM logic)
        # In this architecture, we primarily use these to structure the response data
        self.objections_db = {
            "precio": {
                "keywords": ["caro", "precio", "charlable", "menos", "descuento", "barato"],
                "response_template": (
                    "Entiendo. Pensá que estás llevando:\n"
                    "• Garantía oficial del fabricante\n"
                    "• Producto original y validado\n"
                    "• Soporte postventa local\n\n"
                    "Además tenemos alternativas de pago según el método elegido. "
                    "¿Querés que revisemos opciones?"
                ),
                "action": "offer_payment_plans"
            },
            "confianza": {
                "keywords": ["confiable", "seguro", "estafa", "miedo", "local", "lugar"],
                "response_template": (
                    "Es normal tener dudas. Para tu tranquilidad:\n"
                    "• Tenemos oficina en Palermo (con cita previa).\n"
                    "• Más de 5 años vendiendo en el sitio.\n"
                    "• Factura A o B con tu compra.\n"
                    "Si querés, te puedo mandar foto de la caja sellada con tu nombre ahora mismo."
                ),
                "action": "offer_proof"
            },
            "competencia": {
                "keywords": ["otro lado", "vi mas barato", "publicacion", "tienda"],
                "response_template": (
                    "Ojo con precios muy bajos: a veces son equipos reacondicionados o sin garantía real.\n"
                    "Lo nuestro es nuevo, sellado y con garantía escrita. "
                    "Preferible invertir un poquito más y dormir tranquilo."
                ),
                "action": "highlight_value"
            },
            "stock": {
                "keywords": ["color", "modelo", "gb", "memoria"],
                "response_template": (
                    "Ese específico no lo tengo, pero hay opciones:\n"
                    "{alternatives}\n"
                    "A veces un color diferente o +/- memoria te salva y lo tenés ya. ¿Te va alguno?"
                ),
                "action": "suggest_alternatives"
            },
            "decision": {
                "keywords": ["pensarlo", "ver", "aviso", "luego", "despues"],
                "response_template": (
                    "¡Dale, tranqui! 🐢 Tomate tu tiempo.\n"
                    "Solo tené en cuenta que el stock vuela y los precios en pesos pueden variar por el dólar.\n"
                    "Si te decidís hoy, te puedo congelar el precio por 24hs. ¿Te reservo la unidad?"
                ),
                "action": "create_urgency"
            }
        }

    def get_objection_response(self, objection_type: str, context: Dict[str, Any] = None) -> str:
        """
        Get the canonical response for a specific objection type.
        Context can be used to fill in dynamic details (e.g. alternatives).
        """
        obj_data = self.objections_db.get(objection_type.lower())
        
        if not obj_data:
            return "Entiendo tu punto. ¿En qué más puedo ayudarte para que te sientas seguro?"
        
        response = obj_data["response_template"]
        
        # Inject context if needed
        if context and "alternatives" in context and "{alternatives}" in response:
            response = response.format(alternatives=context["alternatives"])
        elif "{alternatives}" in response:
             response = response.format(alternatives="• Variante A disponible\n• Variante B disponible") # Fallback
             
        return response

    def get_all_guidelines(self) -> str:
        """
        Returns a formatted string of guidelines to inject into the LLM system prompt.
        """
        guidelines = "GUÍA DE MANEJO DE OBJECIONES:\n"
        for key, data in self.objections_db.items():
            guidelines += f"- Si el cliente objeta sobre '{key.upper()}': {data['response_template']}\n"
        return guidelines
