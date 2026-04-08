#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Session Manager - Manages conversation sessions and context windows
Handles memory compression and isolation
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Represents a conversation session"""
    session_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    context_summary: Optional[str] = None
    
    def is_expired(self, timeout_minutes: int) -> bool:
        """Check if session has expired"""
        return datetime.now() - self.last_activity > timedelta(minutes=timeout_minutes)
    
    def touch(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()


class ContextWindow:
    """
    Manages context window with size limits and compression
    """
    
    def __init__(self, max_messages: int = 20, max_tokens: int = 4000):
        self.max_messages = max_messages
        self.max_tokens = max_tokens
    
    def trim(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Trim messages to fit within limits
        
        Args:
            messages: List of messages
            
        Returns:
            Trimmed list
        """
        if len(messages) <= self.max_messages:
            return messages
        
        # Keep system message if present
        system_messages = [m for m in messages if m.get("role") == "system"]
        other_messages = [m for m in messages if m.get("role") != "system"]
        
        # Keep most recent messages
        recent = other_messages[-(self.max_messages - len(system_messages)):]
        
        return system_messages + recent
    
    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Rough token estimation"""
        total = 0
        for msg in messages:
            content = str(msg.get("content", ""))
            # Rough estimate: 1 token ≈ 4 characters
            total += len(content) // 4
        return total
    
    def compress(self, messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
        """
        Compress old messages into a summary
        
        Args:
            messages: Full message history
            
        Returns:
            (summary, recent_messages)
        """
        if len(messages) <= self.max_messages // 2:
            return "", messages
        
        # Split into old and recent
        split_point = len(messages) - self.max_messages // 2
        old_messages = messages[:split_point]
        recent_messages = messages[split_point:]
        
        # Create summary
        summary = f"[Resumen de conversación previa: {len(old_messages)} mensajes]"
        
        return summary, recent_messages


class SessionManager:
    """
    Manages all active sessions
    """
    
    def __init__(
        self,
        session_timeout_minutes: int = 60,
        max_messages_per_session: int = 20
    ):
        self.session_timeout_minutes = session_timeout_minutes
        self.max_messages = max_messages_per_session
        self.sessions: Dict[str, Session] = {}
        self.context_window = ContextWindow(max_messages=max_messages_per_session)
        
        logger.info(
            f"SessionManager initialized "
            f"(timeout: {session_timeout_minutes}min, max_messages: {max_messages_per_session})"
        )
    
    def get_or_create_session(self, session_id: str) -> Session:
        """
        Get existing session or create new one
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session object
        """
        if session_id in self.sessions:
            session = self.sessions[session_id]
            
            # Check if expired
            if session.is_expired(self.session_timeout_minutes):
                logger.info(f"Session {session_id} expired - creating new one")
                del self.sessions[session_id]
                return self.get_or_create_session(session_id)
            
            session.touch()
            return session
        
        # Create new session
        session = Session(session_id=session_id)
        self.sessions[session_id] = session
        logger.info(f"Created new session: {session_id}")
        
        return session
    
    def add_message(self, session_id: str, message: Dict[str, Any]):
        """
        Add message to session
        
        Args:
            session_id: Session identifier
            message: Message dict with role and content
        """
        session = self.get_or_create_session(session_id)
        session.messages.append(message)
        session.touch()
        
        # Auto-trim if needed
        if len(session.messages) > self.max_messages:
            self._compress_session(session)
    
    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of messages
        """
        session = self.get_or_create_session(session_id)
        return session.messages.copy()
    
    def get_context(self, session_id: str, include_summary: bool = True) -> List[Dict[str, Any]]:
        """
        Get context for a session (with summary prepended if available)
        
        Args:
            session_id: Session identifier
            include_summary: Whether to include compressed summary
            
        Returns:
            List of messages for context
        """
        session = self.get_or_create_session(session_id)
        
        messages = session.messages.copy()
        
        # Prepend summary if exists
        if include_summary and session.context_summary:
            messages.insert(0, {
                "role": "system",
                "content": session.context_summary
            })
        
        return messages
    
    def _compress_session(self, session: Session):
        """Compress session history"""
        logger.info(f"Compressing session {session.session_id}")
        
        summary, recent = self.context_window.compress(session.messages)
        
        if summary:
            session.context_summary = summary
            session.messages = recent
            logger.debug(f"Compressed {session.session_id}: summary + {len(recent)} recent messages")
    
    def update_metadata(self, session_id: str, key: str, value: Any):
        """
        Update session metadata
        
        Args:
            session_id: Session identifier
            key: Metadata key
            value: Metadata value
        """
        session = self.get_or_create_session(session_id)
        session.metadata[key] = value
    
    def get_metadata(self, session_id: str, key: str, default: Any = None) -> Any:
        """
        Get session metadata
        
        Args:
            session_id: Session identifier
            key: Metadata key
            default: Default value if not found
            
        Returns:
            Metadata value
        """
        session = self.get_or_create_session(session_id)
        return session.metadata.get(key, default)
    
    def reset_session(self, session_id: str):
        """
        Reset a session (clear history)
        
        Args:
            session_id: Session identifier
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Reset session: {session_id}")
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired sessions
        
        Returns:
            Number of sessions cleaned up
        """
        expired = [
            sid for sid, session in self.sessions.items()
            if session.is_expired(self.session_timeout_minutes)
        ]
        
        for sid in expired:
            del self.sessions[sid]
            logger.info(f"Cleaned up expired session: {sid}")
        
        return len(expired)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics"""
        return {
            "active_sessions": len(self.sessions),
            "total_messages": sum(len(s.messages) for s in self.sessions.values()),
            "avg_messages_per_session": (
                sum(len(s.messages) for s in self.sessions.values()) / len(self.sessions)
                if self.sessions else 0
            )
        }
