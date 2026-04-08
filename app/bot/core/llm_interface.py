#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified LLM Interface - Abstract base for all LLM providers
Supports tool_calls pattern with retries and circuit breaker
"""

import time
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .message_models import (
    Message, LLMRequest, LLMResponse, ToolFunction,
    convert_legacy_functions
)


logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker pattern for LLM provider failures"""
    
    def __init__(self, failure_threshold: int = 3, timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timedelta(seconds=timeout_seconds)
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    def call_failed(self):
        """Record a failed call"""
        self.failures += 1
        self.last_failure_time = datetime.now()
        
        if self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"🔥 Circuit breaker OPEN - {self.failures} consecutive failures")
    
    def call_succeeded(self):
        """Record a successful call"""
        self.failures = 0
        self.state = "closed"
        logger.info("✅ Circuit breaker CLOSED - service recovered")
    
    def can_attempt(self) -> bool:
        """Check if we can attempt a call"""
        if self.state == "closed":
            return True
        
        # Check if timeout has passed to try again (half-open)
        if self.last_failure_time and datetime.now() - self.last_failure_time > self.timeout:
            self.state = "half-open"
            logger.info("Circuit breaker HALF-OPEN - attempting recovery")
            return True
        
        return False


class LLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 800,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.circuit_breaker = CircuitBreaker()
        
    @abstractmethod
    def _send_request(self, request: LLMRequest) -> LLMResponse:
        """
        Send request to LLM provider (implementation-specific)
        
        Args:
            request: Standardized LLM request
            
        Returns:
            Standardized LLM response
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM provider is available"""
        pass
    
    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[ToolFunction]] = None,
        stream: bool = False,
        run_id: Optional[str] = None
    ) -> LLMResponse:
        """
        Unified chat interface with retry logic
        
        Args:
            messages: List of Message objects
            tools: Optional list of available tools
            stream: Whether to stream the response
            run_id: Optional run ID for tracking
            
        Returns:
            LLMResponse object
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_attempt():
            logger.error("Circuit breaker OPEN - using fallback")
            return self._fallback_response(messages, run_id)
        
        # Create request
        request = LLMRequest(
            messages=messages,
            tools=tools,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=stream,
            run_id=run_id
        )
        
        # Retry logic with exponential backoff
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"LLM request attempt {attempt + 1}/{self.max_retries}")
                
                response = self._send_request(request)
                
                # Success!
                self.circuit_breaker.call_succeeded()
                return response
                
            except Exception as e:
                last_exception = e
                logger.warning(f"LLM request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    delay = self.retry_delay * (2 ** attempt)
                    logger.debug(f"Retrying in {delay}s...")
                    # time.sleep(delay)  # Optimized: Removed artificial delay
        
        # All retries failed
        self.circuit_breaker.call_failed()
        logger.error(f"LLM request failed after {self.max_retries} attempts: {last_exception}")
        return self._fallback_response(messages, run_id)
    
    def _fallback_response(self, messages: List[Message], run_id: Optional[str] = None) -> LLMResponse:
        """Generate fallback response when LLM is unavailable"""
        content = (
            "Disculpa, estoy teniendo dificultades técnicas momentáneas. 🛠️\n"
            "¿Podrías escribirme 'asesor' para que te atienda una persona?"
        )
        
        return LLMResponse(
            message=Message.assistant(content=content),
            finish_reason="fallback",
            run_id=run_id
        )
    
    def chat_legacy(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Legacy compatibility method (function_call pattern)
        
        Args:
            messages: List of message dicts (old format)
            functions: List of function definitions (old format)
            
        Returns:
            Response dict (old format)
        """
        # Convert to new format
        msg_objects = [Message.from_legacy(m) for m in messages]
        tools = convert_legacy_functions(functions) if functions else None
        
        # Call unified interface
        response = self.chat(messages=msg_objects, tools=tools)
        
        # Convert back to legacy format
        result = {"role": "assistant"}
        
        if response.message.content:
            result["content"] = response.message.content
        
        if response.message.tool_calls and len(response.message.tool_calls) > 0:
            # Convert first tool call to legacy function_call
            tc = response.message.tool_calls[0]
            result["function_call"] = tc.function
        
        return result


class OpenAIClient(LLMClient):
    """OpenAI-specific implementation"""
    
    def __init__(self, api_key: str, model: str = "gpt-4", **kwargs):
        super().__init__(model=model, **kwargs)
        self.api_key = api_key
        
        try:
            import openai
            self.openai = openai
            self.openai.api_key = api_key
            logger.info(f"✅ OpenAI client initialized: {model}")
        except ImportError:
            logger.error("OpenAI package not installed")
            self.openai = None
    
    def is_available(self) -> bool:
        """Check if OpenAI is available"""
        return self.openai is not None and bool(self.api_key)
    
    def _send_request(self, request: LLMRequest) -> LLMResponse:
        """Send request to OpenAI API"""
        if not self.is_available():
            raise RuntimeError("OpenAI not available")
        
        # Convert messages to OpenAI format
        messages_dict = [m.to_openai() for m in request.messages]
        
        # Prepare arguments
        kwargs = {
            "model": self.model,
            "messages": messages_dict,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        
        # Add tools if provided
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters
                    }
                }
                for tool in request.tools
            ]
            kwargs["tool_choice"] = "auto"
        
        # Make API call
        response = self.openai.ChatCompletion.create(**kwargs)
        
        # Parse response
        choice = response['choices'][0]
        message_data = choice['message']
        
        # Convert to Message object
        message = Message.from_legacy(message_data)
        
        return LLMResponse(
            message=message,
            usage=response.get('usage'),
            finish_reason=choice.get('finish_reason'),
            run_id=request.run_id
        )


class GeminiClient(LLMClient):
    """Google Gemini-specific implementation"""
    
    def __init__(self, api_key: str, model: str = "gemini-1.5-pro", **kwargs):
        super().__init__(model=model, **kwargs)
        self.api_key = api_key
        
        try:
            import google.generativeai as genai
            self.genai = genai
            genai.configure(api_key=api_key)
            self.model_obj = genai.GenerativeModel(model)
            logger.info(f"✅ Gemini client initialized: {model}")
        except ImportError:
            logger.error("Google GenerativeAI package not installed")
            self.genai = None
            self.model_obj = None
    
    def is_available(self) -> bool:
        """Check if Gemini is available"""
        return self.genai is not None and self.model_obj is not None
    
    def _send_request(self, request: LLMRequest) -> LLMResponse:
        """Send request to Gemini API"""
        if not self.is_available():
            raise RuntimeError("Gemini not available")
        
        # Convert messages to Gemini format
        # Gemini requires alternating user/model messages
        gemini_messages = []
        for msg in request.messages:
            if msg.role == "system":
                # Prepend system message to first user message
                continue
            gemini_messages.append(msg.to_gemini())
        
        # Gemini chat format
        # TODO: Implement proper Gemini function calling
        # For now, simple text chat
        
        # Extract just the user messages
        chat_history = []
        prompt = ""
        
        for i, msg in enumerate(request.messages):
            if msg.role == "user":
                prompt = msg.content
            elif msg.role == "assistant" and msg.content:
                chat_history.append({
                    "role": "user" if i == 0 else "model",
                    "parts": [msg.content]
                })
        
        # Generate response
        response = self.model_obj.generate_content(
            prompt,
            generation_config={
                "temperature": request.temperature,
                "max_output_tokens": request.max_tokens,
            }
        )
        
        # Parse response
        content = response.text if hasattr(response, 'text') else ""
        
        return LLMResponse(
            message=Message.assistant(content=content),
            finish_reason="stop",
            run_id=request.run_id
        )


def create_llm_client(
    provider: str = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> LLMClient:
    """
    Factory function to create LLM client
    
    Args:
        provider: Provider name ("openai", "gemini")
        api_key: API key for the provider
        model: Model name
        **kwargs: Additional arguments
        
    Returns:
        LLMClient instance
    """
    if provider.lower() == "openai":
        return OpenAIClient(
            api_key=api_key or "",
            model=model or "gpt-4",
            **kwargs
        )
    elif provider.lower() == "gemini":
        return GeminiClient(
            api_key=api_key or "",
            model=model or "gemini-1.5-pro",
            **kwargs
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")
