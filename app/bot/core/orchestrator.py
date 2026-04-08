#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Orchestrator - Central event-driven orchestrator for Jarvis-style architecture
Manages state machine, run IDs, timeouts, and interruptions
"""

import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


class State(Enum):
    """Bot states"""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    ACTING = "acting"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class Event:
    """Event in the system"""
    type: str  # user_message, tool_complete, timeout, interrupt
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    run_id: str = ""
    session_id: str = ""


@dataclass
class Run:
    """Represents a single execution run"""
    run_id: str
    session_id: str
    state: State = State.IDLE
    started_at: datetime = field(default_factory=datetime.now)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: Dict[str, Any] = field(default_factory=dict)  # tool_call_id -> result
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if run has expired"""
        return datetime.now() - self.started_at > timedelta(minutes=timeout_minutes)


class Orchestrator:
    """
    Central orchestrator for the bot
    Manages state, run IDs, timeouts, and event processing
    """
    
    def __init__(self, timeout_minutes: int = 30):
        self.timeout_minutes = timeout_minutes
        self.active_runs: Dict[str, Run] = {}  # session_id -> Run
        self.event_handlers: Dict[str, Callable] = {}
        
        logger.info(f"Orchestrator initialized (timeout: {timeout_minutes}min)")
    
    def start_run(self, session_id: str) -> str:
        """
        Start a new run for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            new run_id
        """
        run_id = f"run_{session_id}_{uuid.uuid4().hex[:8]}"
        
        # Cancel existing run if any
        if session_id in self.active_runs:
            old_run = self.active_runs[session_id]
            logger.info(f"Cancelling previous run: {old_run.run_id}")
        
        # Create new run
        run = Run(run_id=run_id, session_id=session_id, state=State.LISTENING)
        self.active_runs[session_id] = run
        
        logger.info(f"Started run: {run_id} for session: {session_id}")
        return run_id
    
    def get_current_run(self, session_id: str) -> Optional[Run]:
        """Get current active run for session"""
        return self.active_runs.get(session_id)
    
    def process_event(self, event: Event) -> Optional[Any]:
        """
        Process an event
        
        Args:
            event: Event to process
            
        Returns:
            Result of processing
        """
        session_id = event.session_id
        run = self.get_current_run(session_id)
        
        # Check if event is for current run
        if run and event.run_id and event.run_id != run.run_id:
            logger.debug(f"Ignoring event for old run_id: {event.run_id} (current: {run.run_id})")
            return None
        
        # Check timeout
        if run and run.is_expired(self.timeout_minutes):
            logger.warning(f"Run {run.run_id} expired - starting new run")
            run = None
        
        # Create new run if needed
        if not run:
            self.start_run(session_id)
            run = self.get_current_run(session_id)
        
        # Process by event type
        if event.type == "user_message":
            return self._handle_user_message(run, event)
        elif event.type == "interrupt":
            return self._handle_interrupt(run, event)
        elif event.type == "tool_complete":
            return self._handle_tool_complete(run, event)
        elif event.type == "timeout":
            return self._handle_timeout(run, event)
        else:
            logger.warning(f"Unknown event type: {event.type}")
            return None
    
    def _handle_user_message(self, run: Run, event: Event) -> Dict[str, Any]:
        """Handle user message event"""
        logger.info(f"[{run.run_id}] User message: {event.data.get('text', '')[:50]}...")
        
        # Transition to THINKING
        run.state = State.THINKING
        run.messages.append({
            "role": "user",
            "content": event.data.get("text"),
            "timestamp": event.timestamp
        })
        
        return {"status": "processing", "run_id": run.run_id}
    
    def _handle_interrupt(self, run: Run, event: Event) -> Dict[str, Any]:
        """Handle interruption (e.g., user spoke while bot was speaking)"""
        logger.info(f"[{run.run_id}] INTERRUPT - cancelling current action")
        
        # Cancel current operation
        run.state = State.LISTENING
        
        # Start new run for the interruption
        new_run_id = self.start_run(run.session_id)
        
        return {"status": "interrupted", "new_run_id": new_run_id}
    
    def _handle_tool_complete(self, run: Run, event: Event) -> Dict[str, Any]:
        """Handle tool execution completion"""
        tool_call_id = event.data.get("tool_call_id")
        result = event.data.get("result")
        
        logger.info(f"[{run.run_id}] Tool complete: {tool_call_id}")
        
        # Store result (at-most-once semantics)
        if tool_call_id not in run.tool_calls:
            run.tool_calls[tool_call_id] = result
        else:
            logger.warning(f"Tool {tool_call_id} already executed - skipping duplicate")
        
        return {"status": "recorded", "tool_call_id": tool_call_id}
    
    def _handle_timeout(self, run: Run, event: Event) -> Dict[str, Any]:
        """Handle timeout event"""
        logger.warning(f"[{run.run_id}] Timeout - cleaning up")
        
        run.state = State.ERROR
        run.metadata["timeout"] = True
        
        return {"status": "timeout", "run_id": run.run_id}
    
    def cleanup_expired_runs(self):
        """Clean up expired runs"""
        expired = []
        for session_id, run in self.active_runs.items():
            if run.is_expired(self.timeout_minutes):
                expired.append(session_id)
        
        for session_id in expired:
            run = self.active_runs.pop(session_id)
            logger.info(f"Cleaned up expired run: {run.run_id}")
        
        return len(expired)
    
    def get_run_timeline(self, run_id: str) -> List[Dict[str, Any]]:
        """Get timeline of events for a run"""
        for run in self.active_runs.values():
            if run.run_id == run_id:
                return [
                    {
                        "timestamp": msg.get("timestamp"),
                        "type": "message",
                        "role":  msg.get("role"),
                        "content": msg.get("content", "")[:100]
                    }
                    for msg in run.messages
                ]
        return []
