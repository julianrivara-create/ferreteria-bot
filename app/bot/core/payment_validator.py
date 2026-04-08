#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Payment Validation Module
Validates payment receipts and detects fraud using AI image analysis
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from app.bot.security.image_fraud_detector import image_fraud_detector, FraudRiskLevel

logger = logging.getLogger(__name__)


class PaymentValidator:
    """
    Validates payment receipts with fraud detection
    """
    
    def __init__(self):
        """Initialize payment validator"""
        self.fraud_detector = image_fraud_detector
        logger.info("PaymentValidator initialized")
    
    def validate_payment_receipt(
        self,
        image_url: str,
        expected_amount: Optional[float] = None,
        customer_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate a payment receipt image
        
        Args:
            image_url: URL or path to the receipt image
            expected_amount: Expected payment amount (optional)
            customer_id: Customer identifier for logging
        
        Returns:
            Dictionary with validation results:
            {
                'valid': bool,
                'risk_level': str,
                'should_block': bool,
                'should_escalate': bool,
                'message': str,
                'details': dict
            }
        """
        logger.info(f"Validating payment receipt for customer {customer_id}")
        
        # Analyze image for fraud
        risk_level, details = self.fraud_detector.analyze_image(image_url)
        
        # Determine action based on risk level
        should_block = False
        should_escalate = False
        valid = True
        message = ""
        
        if risk_level == FraudRiskLevel.CLEAN:
            valid = True
            message = "Comprobante verificado correctamente. Procesando pago..."
            logger.info(f"Payment receipt validated successfully for {customer_id}")
        
        elif risk_level == FraudRiskLevel.SUSPICIOUS:
            valid = False
            should_escalate = True
            message = (
                "⚠️ Tu comprobante necesita verificación manual.\n"
                "Un humano lo revisará en breve. Gracias por tu paciencia."
            )
            logger.warning(f"Suspicious payment receipt from {customer_id}: {details}")
        
        elif risk_level == FraudRiskLevel.HIGH_RISK:
            valid = False
            should_block = True
            should_escalate = True
            message = (
                "🚨 No pudimos verificar tu comprobante automáticamente.\n"
                "Por favor, contactá con un vendedor para continuar."
            )
            logger.error(f"HIGH RISK payment receipt from {customer_id}: {details}")
        
        else:  # ERROR
            valid = False
            should_escalate = True
            message = (
                "Hubo un problema al verificar tu comprobante.\n"
                "Un vendedor lo revisará manualmente."
            )
            logger.error(f"Error validating receipt for {customer_id}: {details}")
        
        # Build result
        result = {
            'valid': valid,
            'risk_level': risk_level.value,
            'should_block': should_block,
            'should_escalate': should_escalate,
            'message': message,
            'details': details,
            'timestamp': datetime.utcnow().isoformat(),
            'customer_id': customer_id,
            'expected_amount': expected_amount
        }
        
        # Log for audit trail
        self._log_validation(result)
        
        return result
    
    def _log_validation(self, result: Dict[str, Any]):
        """
        Log validation result for audit trail
        
        Args:
            result: Validation result dictionary
        """
        log_entry = {
            'timestamp': result['timestamp'],
            'customer_id': result['customer_id'],
            'risk_level': result['risk_level'],
            'valid': result['valid'],
            'escalated': result['should_escalate'],
            'blocked': result['should_block']
        }
        
        # Log to file or database (implement as needed)
        logger.info(f"Payment validation logged: {log_entry}")
    
    def get_fraud_statistics(self) -> Dict[str, Any]:
        """
        Get fraud detection statistics
        
        Returns:
            Dictionary with stats
        """
        # TODO: Implement statistics tracking
        return {
            'total_validations': 0,
            'clean': 0,
            'suspicious': 0,
            'high_risk': 0,
            'blocked': 0
        }


# Singleton instance
payment_validator = PaymentValidator()


# Function calling interface for LLM
def validate_payment_image(image_url: str, expected_amount: Optional[float] = None) -> str:
    """
    Function for LLM to validate payment receipt images
    
    Args:
        image_url: URL of the payment receipt image
        expected_amount: Expected payment amount
    
    Returns:
        Human-readable validation result
    """
    result = payment_validator.validate_payment_receipt(
        image_url=image_url,
        expected_amount=expected_amount
    )
    
    return result['message']
