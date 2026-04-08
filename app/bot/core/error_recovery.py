#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Error Recovery & Clarification Helpers
Helps bot recover from errors and ask clarifying questions
"""

from typing import Dict, Any, List, Optional


class ErrorRecovery:
    """
    Handles error recovery and clarification strategies
    """
    
    @staticmethod
    def generate_clarification(
        error_type: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Generate clarification question based on error type
        
        Args:
            error_type: Type of error (no_match, ambiguous, invalid_input, etc.)
            context: Context information
            
        Returns:
            Clarification question
        """
        clarifications = {
            'no_match': [
                "No encontré ese producto. ¿Podrías darme más detalles?",
                "No tengo stock de eso. ¿Te puedo sugerir algo similar?",
                "🤔 No estoy seguro de qué producto buscás. ¿Podés ser más específico?"
            ],
            
            'ambiguous': [
                "Tengo varias opciones que coinciden. ¿Cuál te interesa?",
                "Encontré varios modelos. ¿Querés que te los muestre?",
                "Hay varias versiones. ¿Qué especificaciones buscás?"
            ],
            
            'invalid_input': [
                "No entendí bien. ¿Podrías reformular?",
                "Disculpá, ¿me lo podés explicar de otra forma?",
                "🤷 No pude procesar eso. ¿Intentás de nuevo?"
            ],
            
            'missing_info': [
                "Me falta un dato. ¿Podrías completar?",
                "Para ayudarte necesito saber: {missing_field}",
                "Casi listo! Solo falta: {missing_field}"
            ],
            
            'technical_error': [
                "Tuve un problema técnico. ¿Intentás de nuevo?",
                "Algo salió mal de mi lado. Probá en un minuto.",
                "🔧 Error temporal. ¿Reiniciamos?"
            ]
        }
        
        templates = clarifications.get(error_type, ["¿Cómo te puedo ayudar?"])
        
        # Pick first template (could be random in production)
        template = templates[0]
        
        # Fill in context if needed
        if '{missing_field}' in template and 'missing_field' in context:
            template = template.format(missing_field=context['missing_field'])
        
        return template
    
    @staticmethod
    def suggest_options(
        items: List[Dict[str, Any]],
        max_options: int = 3
    ) -> str:
        """
        Generate suggestions from list of options
        
        Args:
            items: List of items to suggest
            max_options: Maximum number to show
            
        Returns:
            Formatted suggestions
        """
        if not items:
            return "No tengo sugerencias en este momento."
        
        limited = items[:max_options]
        
        if len(limited) == 1:
            item = limited[0]
            return f"Te sugiero: {item.get('name', item.get('modelo', 'este producto'))}"
        
        suggestions = "Te sugiero:\n"
        for i, item in enumerate(limited, 1):
            name = item.get('name', item.get('modelo', f'Opción {i}'))
            suggestions += f"{i}. {name}\n"
        
        return suggestions
    
    @staticmethod
    def format_help_message() -> str:
        """
        Generate help message
        
        Returns:
            Help text
        """
        return """
🤖 **Cómo puedo ayudarte:**

🔧 **Buscar productos**: "Busco una llave allen 5mm"
💰 **Ver precios**: "Cuánto sale el tarugo Fischer 10mm?"
📦 **Consultar stock**: "Tenés mechas Ezeta disponibles?"
🚚 **Info de envío**: "Cuánto demora el envío?"
💳 **Formas de pago**: "Puedo pagar en cuotas?"

Escribí lo que necesitás y te ayudo! 😊
"""
    
    @staticmethod
    def detect_reset_intent(message: str) -> bool:
        """
        Detect if user wants to reset conversation
        
        Args:
            message: User message
            
        Returns:
            True if reset intent detected
        """
        reset_keywords = [
            'empezar de nuevo',
            'reiniciar',
            'reset',
            'cancelar todo',
            'borrar',
            'volver al inicio'
        ]
        
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in reset_keywords)
    
    @staticmethod
    def handle_timeout(last_message_time: float, timeout_minutes: int = 30) -> Optional[str]:
        """
        Handle conversation timeout
        
        Args:
            last_message_time: Timestamp of last message
            timeout_minutes: Timeout in minutes
            
        Returns:
            Timeout message or None
        """
        import time
        
        elapsed_minutes = (time.time() - last_message_time) / 60
        
        if elapsed_minutes > timeout_minutes:
            return f"⏰ Han pasado {int(elapsed_minutes)} minutos. ¿Seguimos? Escribí 'sí' para continuar o 'reset' para empezar de nuevo."
        
        return None


class ContextManager:
    """
    Manages conversation context for better error recovery
    """
    
    def __init__(self):
        self.context = {}
    
    def set(self, key: str, value: Any) -> None:
        """Set context variable"""
        self.context[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get context variable"""
        return self.context.get(key, default)
    
    def clear(self) -> None:
        """Clear all context"""
        self.context = {}
    
    def has_required_fields(self, required: List[str]) -> tuple[bool, Optional[str]]:
        """
        Check if all required fields are present
        
        Args:
            required: List of required field names
            
        Returns:
            (all_present, first_missing_field)
        """
        for field in required:
            if field not in self.context or not self.context[field]:
                return False, field
        
        return True, None
