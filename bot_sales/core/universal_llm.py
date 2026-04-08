#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Universal LLM Client - Wrapper for Multi-Backend Support
Drop-in replacement for ChatGPTClient with support for open source models
"""

import logging
import os
from typing import List, Dict, Any, Optional
from .llm_backend import create_llm_backend, LLMBackend


class UniversalLLMClient:
    """
    Universal LLM client supporting multiple backends
    Compatible API with ChatGPTClient but works with Ollama, LM Studio, etc.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 800,
        backend: Optional[str] = None
    ):
        """
        Initialize Universal LLM client
        
        Args:
            api_key: API key (for OpenAI backend)
            model: Model name (backend-specific)
            temperature: Response randomness (0-1)
            max_tokens: Max tokens in response
            backend: Backend type ('openai', 'ollama', 'lmstudio', or None for auto)
        """
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.mock_mode = False
        
        # Determine backend from environment or parameter
        backend_type = backend or os.getenv('LLM_BACKEND', 'auto')
        
        try:
            # Create backend
            self.backend: LLMBackend = create_llm_backend(
                backend_type,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key
            )
            
            logging.info(
                f"✅ Universal LLM initialized: "
                f"{self.backend.config.backend} ({self.backend.config.model})"
            )
            
            # Check if backend is available
            if not self.backend.is_available():
                logging.warning(
                    f"⚠️  {self.backend.config.backend} backend not available. "
                    f"Falling back to mock mode."
                )
                self.mock_mode = True
                
        except Exception as e:
            logging.error(f"Failed to initialize LLM backend: {e}")
            logging.info("Falling back to mock mode")
            self.mock_mode = True
            self.backend = None
    
    def send_message(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Send message to LLM backend
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            functions: Optional list of available functions (for function calling)
            
        Returns:
            Response dict with 'role' and 'content', optionally 'function_call'
        """
        if self.mock_mode:
            logging.info("MOCK MODE: Using simplified fallback response")
            return self._mock_response(messages)
        
        try:
            # CHECKPOINT: Circuit Breaker for potential connection issues
            if not self.backend or (hasattr(self.backend, 'is_available') and not self.backend.is_available()):
                 logging.warning("LLM Backend reported unavailable before request")
                 return self._mock_response(messages)

            # Send to backend
            content = self.backend.chat_completion(
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            result = {
                "role": "assistant",
                "content": content
            }
            
            # TODO: Function calling support for open source models
            # Currently most don't support it natively, but we could parse output
            
            return result
            
        except Exception as e:
            logging.error(f"LLM backend CRITICAL error: {e}")
            logging.info("🔥 Circuit Breaker Activated: Falling back to Safe Mode")
            return self._mock_response(messages)
    
    def _mock_response(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generate mock response when no backend available
        
        Args:
            messages: Conversation messages
            
        Returns:
            Mock response dict
        """
        # Get last user message
        user_msg = ""
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                user_msg = msg.get('content', '').lower()
                break
        
        # Simple keyword-based responses
        # Enhanced SAFE MODE responses
        user_msg_lower = user_msg.lower()
        
        # 1. IMMEDIATE HANDOFF triggers
        handoff_keywords = ['asesor', 'humano', 'persona', 'alguien', 'error', 'problema', 'queja']
        if any(w in user_msg_lower for w in handoff_keywords):
            content = "Entendido. Para darte una mejor atención, te voy a derivar con un asesor humano ahora mismo. 👤"
            # We add a hidden flag that the Bot orchestrator can see to trigger actual handoff
            return {
                "role": "assistant",
                "content": content,
                "function_call": {
                    "name": "derivar_humano",
                    "arguments": "{\"razon\": \"Solicitud en Safe Mode\", \"nombre\": \"Cliente\"}"
                }
            }

        # 2. Simple keyword-based responses
        if any(word in user_msg_lower for word in ['hola', 'buenos', 'buen día', 'buenas']):
            content = "¡Hola! 👋 Estoy operando en modo de respaldo. ¿En qué puedo ayudarte? (Escribe 'asesor' si necesitas hablar con un humano)"
        elif any(word in user_msg_lower for word in ['producto', 'modelo', 'celular', 'teléfono', 'talle', 'medida', 'categoria']):
            content = "Puedo ayudarte con el catálogo, pero ahora estoy en mantenimiento. Te sugiero hablar con un asesor para confirmar detalles exactos."
        elif any(word in user_msg_lower for word in ['precio', 'cuesta', 'vale']):
            content = "Los precios cambian diariamente. Por favor pedí hablar con un 'asesor' para cotización exacta."
        elif any(word in user_msg_lower for word in ['stock', 'hay', 'tienen']):
            content = "Por el momento no puedo verificar el stock en tiempo real. ¿Querés que un humano te contacte?"
        else:
            content = "Disculpa, estoy teniendo dificultades técnicas momentáneas. 🛠️\n¿Podrías escribirme 'asesor' para que te atienda una persona?"
        
        return {
            "role": "assistant",
            "content": content + "\n\n⚠️ NOTA: Bot en modo MOCK (sin LLM backend configurado)"
        }
    
    def get_backend_info(self) -> Dict[str, Any]:
        """
        Get information about current backend
        
        Returns:
            Backend configuration dict
        """
        if self.mock_mode or not self.backend:
            return {
                'backend': 'mock',
                'model': 'none',
                'available': False
            }
        
        return {
            'backend': self.backend.config.backend,
            'model': self.backend.config.model,
            'available': self.backend.is_available(),
            'base_url': self.backend.config.base_url
        }


# Backwards compatibility alias
ChatGPTClient = UniversalLLMClient


def create_llm_client(**kwargs) -> UniversalLLMClient:
    """
    Factory function to create LLM client
    
    Usage:
        # Auto-detect backend
        client = create_llm_client()
        
        # Specific backend
        client = create_llm_client(backend='ollama', model='glm4:9b')
        client = create_llm_client(backend='openai', api_key='sk-...')
    """
    return UniversalLLMClient(**kwargs)
