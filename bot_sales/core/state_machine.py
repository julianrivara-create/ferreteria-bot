#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Order State Machine Validator
Ensures valid state transitions for orders/holds/sales
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime


class OrderStateMachine:
    """
    State machine for order lifecycle
    
    Valid states:
    - CREATED: Hold created
    - CONFIRMED: Sale confirmed
    - PAID: Payment received
    - SHIPPED: Order shipped
    - DELIVERED: Order delivered
    - CANCELLED: Order cancelled
    - EXPIRED: Hold expired
    """
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        'CREATED': ['CONFIRMED', 'CANCELLED', 'EXPIRED'],
        'CONFIRMED': ['PAID', 'CANCELLED'],
        'PAID': ['SHIPPED', 'CANCELLED'],
        'SHIPPED': ['DELIVERED', 'CANCELLED'],
        'DELIVERED': [],  # Terminal state
        'CANCELLED': [],  # Terminal state
        'EXPIRED': []     # Terminal state
    }
    
    def __init__(self):
        self.audit_log = []
    
    def validate_transition(
        self,
        current_state: str,
        new_state: str
    ) -> tuple[bool, str]:
        """
        Validate if state transition is allowed
        
        Args:
            current_state: Current order state
            new_state: Desired new state
            
        Returns:
            (is_valid, error_message)
        """
        current_state = current_state.upper()
        new_state = new_state.upper()
        
        # Check if states are valid
        if current_state not in self.VALID_TRANSITIONS:
            return False, f"Invalid current state: {current_state}"
        
        if new_state not in self.VALID_TRANSITIONS:
            return False, f"Invalid new state: {new_state}"
        
        # Check if transition is allowed
        allowed_states = self.VALID_TRANSITIONS[current_state]
        if new_state not in allowed_states:
            return False, f"Cannot transition from {current_state} to {new_state}. Allowed: {', '.join(allowed_states)}"
        
        return True, ""
    
    def transition(
        self,
        order_id: str,
        current_state: str,
        new_state: str,
        user_id: Optional[str] = None,
        reason: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Attempt state transition and log audit trail
        
        Args:
            order_id: Order identifier
            current_state: Current state
            new_state: Desired new state
            user_id: User making the change
            reason: Reason for transition
            
        Returns:
            (success, error_message)
        """
        # Validate transition
        is_valid, error_msg = self.validate_transition(current_state, new_state)
        
        if not is_valid:
            logging.warning(f"Invalid state transition for {order_id}: {error_msg}")
            return False, error_msg
        
        # Log audit trail
        audit_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'order_id': order_id,
            'from_state': current_state.upper(),
            'to_state': new_state.upper(),
            'user_id': user_id,
            'reason': reason
        }
        
        self.audit_log.append(audit_entry)
        
        logging.info(f"State transition: {order_id} {current_state} → {new_state}")
        
        return True, ""
    
    def get_audit_log(
        self,
        order_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get audit log entries
        
        Args:
            order_id: Filter by order ID (optional)
            limit: Maximum number of entries
            
        Returns:
            List of audit entries
        """
        logs = self.audit_log
        
        if order_id:
            logs = [log for log in logs if log['order_id'] == order_id]
        
        return logs[-limit:]
    
    def get_allowed_transitions(self, current_state: str) -> List[str]:
        """
        Get list of allowed transitions from current state
        
        Args:
            current_state: Current state
            
        Returns:
            List of allowed next states
        """
        return self.VALID_TRANSITIONS.get(current_state.upper(), [])


# Global state machine instance
_state_machine = None


def get_state_machine() -> OrderStateMachine:
    """Get or create global state machine"""
    global _state_machine
    if _state_machine is None:
        _state_machine = OrderStateMachine()
    return _state_machine


def validate_order_transition(current_state: str, new_state: str) -> tuple[bool, str]:
    """
    Convenience function to validate state transition
    
    Usage:
        is_valid, error = validate_order_transition('CREATED', 'CONFIRMED')
    """
    sm = get_state_machine()
    return sm.validate_transition(current_state, new_state)
