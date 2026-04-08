#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LLM Client Factory
Permite elegir fácilmente entre ChatGPT (OpenAI) y modelos open source (Ollama/LM Studio)
"""

import os
import logging
from typing import Optional


def create_llm_client(
    backend: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
):
    """
    Crea cliente LLM según configuración
    
    Args:
        backend: 'chatgpt', 'openai', 'ollama', 'lmstudio', 'auto', or None
        api_key: API key (para OpenAI/ChatGPT)
        model: Nombre del modelo
        **kwargs: Parámetros adicionales (temperature, max_tokens, etc.)
    
    Returns:
        Cliente LLM (ChatGPTClient o UniversalLLMClient)
    
    Examples:
        # Opción 1: ChatGPT original (solo OpenAI)
        client = create_llm_client(backend='chatgpt', api_key='sk-...')
        
        # Opción 2: Universal (auto-detect: Ollama → OpenAI)
        client = create_llm_client(backend='auto')
        
        # Opción 3: Ollama específicamente
        client = create_llm_client(backend='ollama', model='glm4:9b')
        
        # Opción 4: Desde environment variable
        client = create_llm_client()  # Lee LLM_CLIENT de .env
    """
    # Determinar backend desde parámetro o environment
    if backend is None:
        backend = os.getenv('LLM_CLIENT', 'auto')
    
    backend = backend.lower()
    logger = logging.getLogger('LLMFactory')
    
    # OPCIÓN 1: ChatGPT Original (solo OpenAI)
    if backend in ['chatgpt', 'openai-only', 'gpt']:
        logger.info("🤖 Usando ChatGPT Client (solo OpenAI)")
        from .chatgpt import ChatGPTClient
        
        if not api_key:
            api_key = os.getenv('OPENAI_API_KEY')
        
        if not model:
            model = os.getenv('OPENAI_MODEL', 'gpt-4')
        
        return ChatGPTClient(
            api_key=api_key,
            model=model,
            **kwargs
        )
    
    # OPCIÓN 2: Universal (multi-backend con auto-detect)
    else:
        logger.info("🌐 Usando Universal LLM Client (multi-backend)")
        from .universal_llm import UniversalLLMClient
        
        # Si backend es 'auto', el UniversalLLMClient se encarga
        if backend in ['auto', 'universal']:
            backend = 'auto'
        
        return UniversalLLMClient(
            backend=backend,
            api_key=api_key,
            model=model,
            **kwargs
        )


def get_llm_info():
    """
    Muestra información sobre backends disponibles
    
    Returns:
        Dict con info de backends
    """
    from .llm_backend import LLMFactory
    
    info = {
        'available_backends': [],
        'recommended': None
    }
    
    backends = LLMFactory.list_available_backends()
    
    for name, available in backends:
        status = "✅ Disponible" if available else "❌ No disponible"
        info['available_backends'].append({
            'name': name,
            'available': available,
            'status': status
        })
        
        # Recommend first available
        if available and not info['recommended']:
            info['recommended'] = name
    
    return info


def print_llm_options():
    """
    Imprime opciones disponibles de LLM para el usuario
    """
    print("\n" + "=" * 60)
    print("🤖 OPCIONES DE LLM DISPONIBLES")
    print("=" * 60)
    
    info = get_llm_info()
    
    print("\n📋 Backends:")
    for backend in info['available_backends']:
        print(f"  {backend['status']} - {backend['name']}")
    
    if info['recommended']:
        print(f"\n✨ Recomendado usar: {info['recommended']}")
    
    print("\n📝 Configuración:")
    print("  Opción 1: Editar .env")
    print("    LLM_CLIENT=chatgpt    # Solo OpenAI")
    print("    LLM_CLIENT=auto       # Auto-detect (Ollama → OpenAI)")
    print("    LLM_CLIENT=ollama     # Forzar Ollama")
    
    print("\n  Opción 2: Código Python")
    print("    from bot_sales.core.client_factory import create_llm_client")
    print("    client = create_llm_client(backend='chatgpt')  # OpenAI")
    print("    client = create_llm_client(backend='ollama')   # Ollama")
    
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    # Demo
    print_llm_options()
