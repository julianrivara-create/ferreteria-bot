#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack Conversation Threading
Track and manage conversation threads for better organization
"""

import logging
from typing import Dict, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class ThreadTracker:
    """Track Slack conversation threads"""
    
    def __init__(self, storage_backend='memory'):
        """
        Initialize thread tracker
        
        Args:
            storage_backend: 'memory', 'redis', or 'database'
        """
        self.storage_backend = storage_backend
        self.threads = {}  # In-memory storage: {session_id: thread_ts}
        self.thread_metadata = {}  # {thread_ts: metadata}
    
    def create_thread(self, session_id: str, channel_id: str, initial_message_ts: str, metadata: Dict = None) -> str:
        """
        Create a new thread
        
        Args:
            session_id: User session ID
            channel_id: Slack channel ID
            initial_message_ts: Timestamp of initial message
            metadata: Optional metadata
            
        Returns:
            Thread timestamp
        """
        self.threads[session_id] = initial_message_ts
        
        self.thread_metadata[initial_message_ts] = {
            'session_id': session_id,
            'channel_id': channel_id,
            'created_at': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        
        logger.info(f"Created thread {initial_message_ts} for session {session_id}")
        return initial_message_ts
    
    def get_thread(self, session_id: str) -> Optional[str]:
        """
        Get thread timestamp for session
        
        Args:
            session_id: User session ID
            
        Returns:
            Thread timestamp or None
        """
        return self.threads.get(session_id)
    
    def update_thread_metadata(self, thread_ts: str, metadata: Dict):
        """
        Update thread metadata
        
        Args:
            thread_ts: Thread timestamp
            metadata: Metadata to update
        """
        if thread_ts in self.thread_metadata:
            self.thread_metadata[thread_ts]['metadata'].update(metadata)
            self.thread_metadata[thread_ts]['updated_at'] = datetime.now().isoformat()
    
    def close_thread(self, session_id: str):
        """
        Close a thread
        
        Args:
            session_id: User session ID
        """
        if session_id in self.threads:
            thread_ts = self.threads[session_id]
            self.update_thread_metadata(thread_ts, {'status': 'closed'})
            del self.threads[session_id]
            logger.info(f"Closed thread for session {session_id}")
    
    def get_active_threads(self) -> Dict:
        """
        Get all active threads
        
        Returns:
            Dict of active threads
        """
        return self.threads.copy()
    
    def get_thread_info(self, thread_ts: str) -> Optional[Dict]:
        """
        Get thread metadata
        
        Args:
            thread_ts: Thread timestamp
            
        Returns:
            Thread metadata or None
        """
        return self.thread_metadata.get(thread_ts)


class ThreadedMessaging:
    """Send messages in threads"""
    
    def __init__(self, slack_connector, thread_tracker: ThreadTracker):
        """
        Initialize threaded messaging
        
        Args:
            slack_connector: SlackConnector instance
            thread_tracker: ThreadTracker instance
        """
        self.slack = slack_connector
        self.tracker = thread_tracker
    
    def send_in_thread(self, session_id: str, channel_id: str, message: str, blocks: list = None) -> Dict:
        """
        Send message in thread (create if doesn't exist)
        
        Args:
            session_id: User session ID
            channel_id: Slack channel ID
            message: Message text
            blocks: Optional Slack blocks
            
        Returns:
            Slack API response
        """
        # Get existing thread
        thread_ts = self.tracker.get_thread(session_id)
        
        if not thread_ts:
            # Send initial message (creates thread)
            response = self.slack.send_message(channel_id, message, blocks=blocks)
            thread_ts = response.get('ts')
            
            # Track thread
            self.tracker.create_thread(session_id, channel_id, thread_ts)
            
            return response
        else:
            # Reply in existing thread
            return self.slack.send_message(
                channel_id,
                message,
                blocks=blocks,
                thread_ts=thread_ts
            )
    
    def send_thread_summary(self, session_id: str, channel_id: str, summary: str):
        """
        Send summary message in thread
        
        Args:
            session_id: User session ID
            channel_id: Slack channel ID
            summary: Summary text
        """
        thread_ts = self.tracker.get_thread(session_id)
        
        if thread_ts:
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📝 *Resumen de Conversación*\n\n{summary}"
                    }
                }
            ]
            
            self.slack.send_message(
                channel_id,
                summary,
                blocks=blocks,
                thread_ts=thread_ts
            )
    
    def send_thread_update(self, session_id: str, channel_id: str, update_type: str, data: Dict):
        """
        Send status update in thread
        
        Args:
            session_id: User session ID
            channel_id: Slack channel ID
            update_type: Type of update (e.g., 'cart_updated', 'order_placed')
            data: Update data
        """
        thread_ts = self.tracker.get_thread(session_id)
        
        if not thread_ts:
            return
        
        # Format update based on type
        if update_type == 'cart_updated':
            message = f"🛒 Cliente agregó {data.get('product_name')} al carrito"
        elif update_type == 'order_placed':
            message = f"✅ Pedido #{data.get('order_id')} confirmado - ${data.get('total'):,.0f}"
        elif update_type == 'discount_requested':
            message = f"💰 Cliente solicitó {data.get('discount_pct')}% de descuento"
        elif update_type == 'handoff_requested':
            message = f"🚨 Cliente solicitó hablar con humano"
        else:
            message = f"ℹ️ {update_type}: {json.dumps(data)}"
        
        self.slack.send_message(
            channel_id,
            message,
            thread_ts=thread_ts
        )
    
    def close_thread_with_summary(self, session_id: str, channel_id: str, outcome: str, summary: str):
        """
        Close thread with final summary
        
        Args:
            session_id: User session ID
            channel_id: Slack channel ID
            outcome: Outcome (e.g., 'completed', 'abandoned', 'escalated')
            summary: Final summary
        """
        thread_ts = self.tracker.get_thread(session_id)
        
        if not thread_ts:
            return
        
        # Outcome emoji
        emoji_map = {
            'completed': '✅',
            'abandoned': '❌',
            'escalated': '🚨',
            'pending': '⏳'
        }
        emoji = emoji_map.get(outcome, 'ℹ️')
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *Thread Cerrado - {outcome.title()}*\n\n{summary}"
                }
            }
        ]
        
        self.slack.send_message(
            channel_id,
            f"Thread cerrado: {outcome}",
            blocks=blocks,
            thread_ts=thread_ts
        )
        
        # Close thread
        self.tracker.close_thread(session_id)
