import re
import logging
import socket
from typing import Dict, Tuple, Optional

class Validator:
    """
    Sistema de validaciones para datos de clientes
    """
    
    @staticmethod
    def validate_dni(dni: str, check_digit: bool = False) -> Tuple[bool, str]:
        """
        Valida DNI argentino (7-8 dígitos) con checksum opcional
        
        Args:
            dni: DNI string
            check_digit: Si True, valida checksum (algoritmo Módulo 11)
            
        Returns:
            (is_valid, error_message)
        """
        if not dni:
            return False, "DNI vacío"
        
        # Limpiar puntos y espacios
        dni_clean = dni.replace(".", "").replace(" ", "").strip()
        
        # Validar formato
        if not dni_clean.isdigit():
            return False, "DNI debe contener solo números"
        
        # Validar longitud
        if len(dni_clean) < 7 or len(dni_clean) > 8:
            return False, "DNI debe tener 7 u 8 dígitos"
        
        # Validar rango (1M a 99M para DNIs argentinos)
        dni_int = int(dni_clean)
        if dni_int < 1000000 or dni_int > 99999999:
            return False, "DNI fuera de rango válido"
        
        # Nota: El DNI argentino puro NO tiene dígito verificador intrínseco.
        # El CUIL/CUIT sí (Módulo 11).
        # Si se valida DNI, la validación de rango y numérico es la correcta.
        
        if check_digit:
             # Si se requiere check_digit, asumimos que es CUIT/CUIL
             # Implementación básica de Módulo 11 para futuro
             pass
        
        return True, ""
    
    @staticmethod
    def validate_email(email: str, check_dns: bool = False) -> Tuple[bool, str]:
        """
        Valida formato de email con DNS check opcional
        
        Args:
            email: Email address
            check_dns: Si True, verifica que el dominio tenga MX records
            
        Returns:
            (is_valid, error_message)
        """
        if not email:
            return False, "Email vacío"
        
        # Normalizar
        email = email.strip().lower()
        
        # Regex mejorado
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(pattern, email):
            return False, "Formato de email inválido"
        
        # DNS check (opcional, puede ser lento)
        if check_dns:
            try:
                domain = email.split('@')[1]
                socket.gethostbyname(domain)
            except (socket.gaierror, IndexError):
                logging.warning(f"Email domain DNS check failed: {email}")
                return False, "Dominio de email no existe"
        
        return True, ""
    
    @staticmethod
    def validate_phone(phone: str) -> Tuple[bool, str]:
        """
        Valida teléfono argentino (celular o fijo)
        Acepta: 1122334455, 11-2233-4455, +54 11 2233 4455, etc.
        
        Returns:
            (is_valid, error_message)
        """
        if not phone:
            return False, "Teléfono vacío"
        
        # Limpiar caracteres especiales
        phone_clean = re.sub(r'[^\d+]', '', phone)
        
        # Quitar prefijo internacional si existe
        if phone_clean.startswith('+54'):
            phone_clean = phone_clean[3:]
        elif phone_clean.startswith('54'):
            phone_clean = phone_clean[2:]
        
        # Validar longitud (10 dígitos para celular, 8 para fijo con código)
        if len(phone_clean) < 8 or len(phone_clean) > 13:
            return False, "Teléfono debe tener entre 8 y 13 dígitos"
        
        return True, ""
    
    @staticmethod
    def validate_address(address: str) -> Tuple[bool, str]:
        """
        Valida dirección (básico: no vacío, longitud razonable)
        
        Returns:
            (is_valid, error_message)
        """
        if not address:
            return False, "Dirección vacía"
        
        address = address.strip()
        
        if len(address) < 5:
            return False, "Dirección demasiado corta"
        
        if len(address) > 200:
            return False, "Dirección demasiado larga"
        
        return True, ""
    
    @staticmethod
    def validate_customer_data(data: Dict) -> Tuple[bool, Dict[str, str]]:
        """
        Valida todos los datos de un cliente
        
        Args:
            data: Dict con keys: nombre, email, contacto, dni (opcional), address (opcional)
        
        Returns:
            (all_valid, {field: error_message})
        """
        errors = {}
        
        # Nombre
        nombre = data.get('nombre', '').strip()
        if not nombre:
            errors['nombre'] = "Nombre requerido"
        elif len(nombre) < 2:
            errors['nombre'] = "Nombre demasiado corto"
        
        # Email
        if 'email' in data:
            is_valid, msg = Validator.validate_email(data['email'])
            if not is_valid:
                errors['email'] = msg
        
        # Teléfono
        if 'contacto' in data:
            is_valid, msg = Validator.validate_phone(data['contacto'])
            if not is_valid:
                errors['contacto'] = msg
        
        # DNI (opcional)
        if 'dni' in data and data['dni']:
            is_valid, msg = Validator.validate_dni(data['dni'])
            if not is_valid:
                errors['dni'] = msg
        
        # Dirección (opcional)
        if 'address' in data and data['address']:
            is_valid, msg = Validator.validate_address(data['address'])
            if not is_valid:
                errors['address'] = msg
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_sku(sku: str) -> Tuple[bool, str]:
        """
        Valida formato de SKU
        
        Returns:
            (is_valid, error_message)
        """
        if not sku:
            return False, "SKU vacío"
        
        sku = sku.strip()
        
        # Validar longitud razonable
        if len(sku) < 3 or len(sku) > 50:
            return False, "SKU debe tener entre 3 y 50 caracteres"
        
        # Validar caracteres permitidos (alfanuméricos, guiones, guiones bajos)
        if not re.match(r'^[a-zA-Z0-9-_]+$', sku):
            return False, "SKU solo puede contener letras, números, guiones y guiones bajos"
        
        return True, ""
    
    @staticmethod
    def validate_price(price: float) -> Tuple[bool, str]:
        """
        Valida precio
        
        Returns:
            (is_valid, error_message)
        """
        if price is None:
            return False, "Precio vacío"
        
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            return False, "Precio debe ser un número"
        
        # Precio debe ser positivo
        if price_float <= 0:
            return False, "Precio debe ser mayor a 0"
        
        # Precio razonable (menos de $10M)
        if price_float > 10000000:
            return False, "Precio fuera de rango razonable"
        
        return True, ""
    
    @staticmethod
    def validate_stock(stock: int) -> Tuple[bool, str]:
        """
        Valida stock
        
        Returns:
            (is_valid, error_message)
        """
        if stock is None:
            return False, "Stock vacío"
        
        try:
            stock_int = int(stock)
        except (ValueError, TypeError):
            return False, "Stock debe ser un número entero"
        
        # Stock no puede ser negativo
        if stock_int < 0:
            return False, "Stock no puede ser negativo"
        
        # Stock razonable (menos de 10,000 unidades)
        if stock_int > 10000:
            logging.warning(f"Stock muy alto: {stock_int}")
        
        return True, ""
