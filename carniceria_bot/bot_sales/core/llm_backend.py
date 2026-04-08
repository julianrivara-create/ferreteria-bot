#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LLM Backend Abstraction Layer
Supports multiple LLM backends: OpenAI, Ollama, LM Studio, vLLM
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import os
import logging
import requests
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """LLM configuration"""
    backend: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 800
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class LLMBackend(ABC):
    """Abstract base class for LLM backends"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Send chat completion request
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max tokens
            **kwargs: Additional backend-specific parameters
            
        Returns:
            Response text
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend is available"""
        pass


class OpenAIBackend(LLMBackend):
    """OpenAI GPT backend"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=config.api_key or os.getenv('OPENAI_API_KEY'))
            self.logger.info(f"✅ OpenAI backend initialized with model: {config.model}")
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Send chat completion to OpenAI"""
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                **kwargs
            )
            
            content = response.choices[0].message.content
            
            # Log token usage
            usage = response.usage
            self.logger.info(
                f"OpenAI API call: {usage.prompt_tokens} prompt + "
                f"{usage.completion_tokens} completion = {usage.total_tokens} tokens"
            )
            
            return content
            
        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}")
            raise
    
    def is_available(self) -> bool:
        """Check if OpenAI is available"""
        return bool(self.config.api_key or os.getenv('OPENAI_API_KEY'))


class OllamaBackend(LLMBackend):
    """Ollama local LLM backend"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.base_url = config.base_url or os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        self.session = requests.Session()
        
        if self.is_available():
            self.logger.info(f"✅ Ollama backend initialized: {self.base_url} - model: {config.model}")
            self._verify_model()
        else:
            self.logger.warning("⚠️  Ollama not running. Install: curl -fsSL https://ollama.com/install.sh | sh")
    
    def _verify_model(self) -> None:
        """Verify that model is available"""
        try:
            response = self.session.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]
                
                if self.config.model not in model_names:
                    self.logger.warning(
                        f"Model {self.config.model} not found. "
                        f"Available: {', '.join(model_names)}\n"
                        f"Download with: ollama pull {self.config.model}"
                    )
        except Exception as e:
            self.logger.debug(f"Could not verify model: {e}")
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Send chat completion to Ollama"""
        try:
            payload = {
                "model": self.config.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature or self.config.temperature,
                    "num_predict": max_tokens or self.config.max_tokens
                }
            }
            
            response = self.session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=60
            )
            
            response.raise_for_status()
            result = response.json()
            
            content = result["message"]["content"]
            
            # Log performance
            if "eval_count" in result:
                self.logger.info(
                    f"Ollama: {result.get('eval_count', 0)} tokens, "
                    f"{result.get('total_duration', 0) / 1e9:.2f}s"
                )
            
            return content
            
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}\n"
                f"Make sure Ollama is running: ollama serve"
            )
        except Exception as e:
            self.logger.error(f"Ollama error: {e}")
            raise
    
    def is_available(self) -> bool:
        """Check if Ollama is running"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False


class LMStudioBackend(LLMBackend):
    """LM Studio backend (OpenAI compatible API)"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.base_url = config.base_url or os.getenv('LMSTUDIO_HOST', 'http://localhost:1234')
        
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key="lm-studio",  # Dummy key
                base_url=f"{self.base_url}/v1"
            )
            self.logger.info(f"✅ LM Studio backend initialized: {self.base_url}")
        except ImportError:
            raise ImportError("openai package required for LM Studio")
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Send chat completion to LM Studio"""
        try:
            response = self.client.chat.completions.create(
                model=self.config.model or "local-model",
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                **kwargs
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            self.logger.error(f"LM Studio error: {e}")
            raise
    
    def is_available(self) -> bool:
        """Check if LM Studio is running"""
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=2)
            return response.status_code == 200
        except:
            return False


class LLMFactory:
    """Factory to create LLM backends"""
    
    BACKEND_MAP = {
        'openai': OpenAIBackend,
        'ollama': OllamaBackend,
        'lmstudio': LMStudioBackend
    }
    
    @classmethod
    def create(cls, backend_type: Optional[str] = None, **config_kwargs) -> LLMBackend:
        """
        Create LLM backend
        
        Args:
            backend_type: 'openai', 'ollama', 'lmstudio', or None (auto-detect)
            **config_kwargs: Configuration overrides
            
        Returns:
            LLM backend instance
        """
        # Auto-detect if not specified
        if backend_type is None or backend_type == 'auto':
            backend_type = cls._auto_detect_backend()
        
        # Get configuration
        config = cls._build_config(backend_type, **config_kwargs)
        
        # Create backend
        backend_class = cls.BACKEND_MAP.get(backend_type)
        if not backend_class:
            raise ValueError(
                f"Unknown backend: {backend_type}. "
                f"Available: {', '.join(cls.BACKEND_MAP.keys())}"
            )
        
        return backend_class(config)
    
    @classmethod
    def _auto_detect_backend(cls) -> str:
        """Auto-detect best available backend"""
        logger = logging.getLogger('LLMFactory')
        
        # Priority: Ollama (free, local) > OpenAI (paid)
        
        # Check Ollama
        if cls._is_ollama_available():
            logger.info("🔍 Auto-detected: Ollama (local, free)")
            return 'ollama'
        
        # Check LM Studio
        if cls._is_lmstudio_available():
            logger.info("🔍 Auto-detected: LM Studio (local, free)")
            return 'lmstudio'
        
        # Check OpenAI
        if os.getenv('OPENAI_API_KEY'):
            logger.info("🔍 Auto-detected: OpenAI (API key found)")
            return 'openai'
        
        # Default to Ollama with warning
        logger.warning(
            "⚠️  No LLM backend detected!\n"
            "Install Ollama: curl -fsSL https://ollama.com/install.sh | sh\n"
            "Then: ollama pull glm4:9b"
        )
        return 'ollama'
    
    @classmethod
    def _is_ollama_available(cls) -> bool:
        """Check if Ollama is running"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    @classmethod
    def _is_lmstudio_available(cls) -> bool:
        """Check if LM Studio is running"""
        try:
            response = requests.get("http://localhost:1234/v1/models", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    @classmethod
    def _build_config(cls, backend_type: str, **overrides) -> LLMConfig:
        """Build configuration for backend"""
        defaults = {
            'openai': {
                'model': os.getenv('OPENAI_MODEL', 'gpt-4'),
                'api_key': os.getenv('OPENAI_API_KEY'),
            },
            'ollama': {
                'model': os.getenv('OLLAMA_MODEL', 'glm4:9b'),
                'base_url': os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
            },
            'lmstudio': {
                'model': os.getenv('LMSTUDIO_MODEL', 'local-model'),
                'base_url': os.getenv('LMSTUDIO_HOST', 'http://localhost:1234'),
            }
        }
        
        config_dict = defaults.get(backend_type, {})
        config_dict.update(overrides)
        config_dict['backend'] = backend_type
        
        return LLMConfig(**config_dict)
    
    @classmethod
    def list_available_backends(cls) -> List[Tuple[str, bool]]:
        """
        List all backends and their availability
        
        Returns:
            List of (backend_name, is_available) tuples
        """
        return [
            ('openai', bool(os.getenv('OPENAI_API_KEY'))),
            ('ollama', cls._is_ollama_available()),
            ('lmstudio', cls._is_lmstudio_available())
        ]


# Convenience function
def create_llm_backend(backend: Optional[str] = None, **kwargs) -> LLMBackend:
    """
    Create LLM backend (convenience wrapper)
    
    Args:
        backend: Backend type or None for auto-detect
        **kwargs: Additional configuration
        
    Returns:
        LLM backend instance
    """
    return LLMFactory.create(backend, **kwargs)
