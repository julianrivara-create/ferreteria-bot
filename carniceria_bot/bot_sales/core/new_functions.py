"""
New callable functions for advanced features
Append these to business_logic.py
"""

def comparar_productos(self, sku1: str, sku2: str) -> Dict[str, Any]:
    """
    Compara dos productos lado a lado
    
    Args:
        sku1: SKU del primer producto
        sku2: SKU del segundo producto
    
    Returns:
        {
            'status': str,
            'comparison_table': str,
            'recommendation': str
        }
    """
    result = self.product_comparator.compare_products(sku1, sku2)
    return result

def validar_datos_cliente(self, nombre: str, email: str = None, 
                         contacto: str = None, dni: str = None) -> Dict[str, Any]:
    """
    Valida datos del cliente
    
    Returns:
        {
            'valid': bool,
            'errors': {field: error_message}
        }
    """
    data = {
        'nombre': nombre,
        'email': email,
        'contacto': contacto,
        'dni': dni
    }
    
    is_valid, errors = self.validator.validate_customer_data(data)
    
    return {
        'valid': is_valid,
        'errors': errors,
        'message': 'Datos válidos' if is_valid else 'Hay errores en los datos'
    }

def detectar_fraude(self, email: str = None, phone: str = None, 
                   message: str = None) -> Dict[str, Any]:
    """
    Calcula risk score para transacción
    
    Returns:
        {
            'risk_score': int (0-100),
            'should_block': bool,
            'reasons': []
        }
    """
    score, reasons = self.fraud_detector.calculate_risk_score(
        email=email, phone=phone, message=message
    )
    
    should_block = self.fraud_detector.should_block(score)
    
    return {
        'risk_score': score,
        'should_block': should_block,
        'reasons': reasons,
        'action': 'block' if should_block else 'allow'
    }
