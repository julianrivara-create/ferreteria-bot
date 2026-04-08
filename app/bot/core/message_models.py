#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Message Models - Standardized message and tool models
Pydantic models for type-safe LLM interactions
"""

from typing import List, Dict, Any, Optional, Literal, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime
import json


class ToolParameter(BaseModel):
    """Tool function parameter definition"""
    type: str
    description: str
    enum: Optional[List[str]] = None
    items: Optional[Dict[str, Any]] = None  # For array types


class ToolFunction(BaseModel):
    """Tool function definition"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema format
    
    @classmethod
    def from_legacy_function(cls, func_def: Dict[str, Any]) -> "ToolFunction":
        """Convert legacy function definition to ToolFunction"""
        return cls(
            name=func_def["name"],
            description=func_def["description"],
            parameters=func_def.get("parameters", {})
        )


class ToolCall(BaseModel):
    """Tool call made by the model"""
    id: str = Field(default_factory=lambda: f"call_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    type: Literal["function"] = "function"
    function: Dict[str, Any]  # {name: str, arguments: str}
    
    @validator('function')
    def validate_function(cls, v):
        """Ensure function has required fields"""
        if 'name' not in v:
            raise ValueError("function must have 'name' field")
        if 'arguments' not in v:
            v['arguments'] = "{}"
        return v
    
    def get_arguments(self) -> Dict[str, Any]:
        """Parse arguments from JSON string"""
        try:
            args_str = self.function.get('arguments', '{}')
            if isinstance(args_str, dict):
                return args_str
            return json.loads(args_str)
        except json.JSONDecodeError:
            return {}


class Message(BaseModel):
    """Standardized message format"""
    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Optional[str] = None
    name: Optional[str] = None  # For function/tool messages
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None  # For tool response messages
    function_call: Optional[Dict[str, Any]] = None  # Legacy support
    
    class Config:
        extra = "allow"  # Allow extra fields for provider-specific data
    
    @classmethod
    def system(cls, content: str) -> "Message":
        """Create system message"""
        return cls(role="system", content=content)
    
    @classmethod
    def user(cls, content: str) -> "Message":
        """Create user message"""
        return cls(role="user", content=content)
    
    @classmethod
    def assistant(cls, content: Optional[str] = None, tool_calls: Optional[List[ToolCall]] = None) -> "Message":
        """Create assistant message"""
        return cls(role="assistant", content=content, tool_calls=tool_calls)
    
    @classmethod
    def tool(cls, content: str, tool_call_id: str, name: Optional[str] = None) -> "Message":
        """Create tool response message"""
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)
    
    @classmethod
    def from_legacy(cls, msg: Dict[str, Any]) -> "Message":
        """Convert legacy message format to Message model"""
        # Handle legacy function_call
        tool_calls = None
        if "function_call" in msg and msg["function_call"]:
            tool_calls = [ToolCall(
                function={
                    "name": msg["function_call"]["name"],
                    "arguments": msg["function_call"]["arguments"]
                }
            )]
        
        return cls(
            role=msg.get("role", "user"),
            content=msg.get("content"),
            name=msg.get("name"),
            tool_calls=tool_calls,
            function_call=msg.get("function_call")
        )
    
    def to_openai(self) -> Dict[str, Any]:
        """Convert to OpenAI API format"""
        result = {"role": self.role}
        
        if self.content is not None:
            result["content"] = self.content
        
        if self.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": tc.function
                }
                for tc in self.tool_calls
            ]
        
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        
        if self.name:
            result["name"] = self.name
        
        return result
    
    def to_gemini(self) -> Dict[str, Any]:
        """Convert to Gemini API format"""
        # Gemini uses 'user' and 'model' roles
        role_map = {
            "system": "user",  # System messages converted to user context
            "user": "user",
            "assistant": "model",
            "function": "function",
            "tool": "function"
        }
        
        result = {
            "role": role_map.get(self.role, "user"),
            "parts": []
        }
        
        if self.content:
            result["parts"].append({"text": self.content})
        
        # Gemini function calling format different from OpenAI
        if self.tool_calls:
            for tc in self.tool_calls:
                result["parts"].append({
                    "functionCall": {
                        "name": tc.function["name"],
                        "args": tc.get_arguments()
                    }
                })
        
        return result


class LLMRequest(BaseModel):
    """Standardized LLM request"""
    messages: List[Message]
    tools: Optional[List[ToolFunction]] = None
    temperature: float = 0.7
    max_tokens: int = 800
    stream: bool = False
    run_id: Optional[str] = None  # For tracking


class LLMResponse(BaseModel):
    """Standardized LLM response"""
    message: Message
    usage: Optional[Dict[str, int]] = None  # {prompt_tokens, completion_tokens, total_tokens}
    finish_reason: Optional[str] = None
    run_id: Optional[str] = None
    
    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls"""
        return bool(self.message.tool_calls)
    
    @property
    def text(self) -> Optional[str]:
        """Get response text content"""
        return self.message.content


# Helper functions

def validate_tool_schema(tool: ToolFunction) -> bool:
    """Validate tool schema before execution"""
    try:
        # Check required fields
        if not tool.name or not tool.description:
            return False
        
        # Check parameters schema
        params = tool.parameters
        if "type" not in params or params["type"] != "object":
            return False
        
        return True
    except Exception:
        return False


def convert_legacy_functions(functions: List[Dict[str, Any]]) -> List[ToolFunction]:
    """Convert legacy function definitions to ToolFunction models"""
    return [ToolFunction.from_legacy_function(f) for f in functions]
