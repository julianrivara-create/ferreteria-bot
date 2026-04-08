#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PII Encryption Module
Encrypts sensitive personally identifiable information at rest
"""

import os
import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class PIIEncryption:
    """
    Handles encryption/decryption of PII data
    Uses Fernet (symmetric encryption)
    """
    
    def __init__(self):
        self.fernet = self._init_fernet()
    
    def _init_fernet(self) -> Optional[Fernet]:
        """
        Initialize Fernet cipher with key from environment
        
        Returns:
            Fernet instance or None if encryption disabled
        """
        encryption_key = os.getenv('ENCRYPTION_KEY')
        
        if not encryption_key:
            # Generate key from password + salt
            password = os.getenv('ENCRYPTION_PASSWORD')
            if not password:
                raise ValueError(
                    "Encryption is not configured. Set ENCRYPTION_KEY or ENCRYPTION_PASSWORD "
                    "environment variables before starting the application."
                )
            salt = os.getenv('ENCRYPTION_SALT', '').encode() or b'salesbot-default-salt-change-me'
            
            # Derive key using PBKDF2
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        else:
            key = encryption_key.encode()
        
        try:
            return Fernet(key)
        except Exception as e:
            logging.error(f"Failed to initialize encryption: {e}")
            return None
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext string
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            Encrypted string (base64 encoded)
        """
        if not self.fernet:
            logging.warning("Encryption not initialized - returning plaintext!")
            return plaintext
        
        if not plaintext:
            return ""
        
        try:
            encrypted = self.fernet.encrypt(plaintext.encode('utf-8'))
            return encrypted.decode('utf-8')
        except Exception as e:
            logging.error(f"Encryption failed: {e}")
            return plaintext
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt ciphertext string
        
        Args:
            ciphertext: Encrypted string
            
        Returns:
            Decrypted plaintext
        """
        if not self.fernet:
            logging.warning("Encryption not initialized - returning ciphertext as-is!")
            return ciphertext
        
        if not ciphertext:
            return ""
        
        try:
            decrypted = self.fernet.decrypt(ciphertext.encode('utf-8'))
            return decrypted.decode('utf-8')
        except Exception as e:
            logging.error(f"Decryption failed: {e}")
            # Might be plaintext stored before encryption was enabled
            return ciphertext
    
    def encrypt_dict(self, data: dict, fields_to_encrypt: list) -> dict:
        """
        Encrypt specific fields in a dictionary
        
        Args:
            data: Dictionary with data
            fields_to_encrypt: List of field names to encrypt
            
        Returns:
            Dictionary with encrypted fields
        """
        encrypted_data = data.copy()
        
        for field in fields_to_encrypt:
            if field in encrypted_data and encrypted_data[field]:
                encrypted_data[field] = self.encrypt(str(encrypted_data[field]))
        
        return encrypted_data
    
    def decrypt_dict(self, data: dict, fields_to_decrypt: list) -> dict:
        """
        Decrypt specific fields in a dictionary
        
        Args:
            data: Dictionary with encrypted data
            fields_to_decrypt: List of field names to decrypt
            
        Returns:
            Dictionary with decrypted fields
        """
        decrypted_data = data.copy()
        
        for field in fields_to_decrypt:
            if field in decrypted_data and decrypted_data[field]:
                decrypted_data[field] = self.decrypt(str(decrypted_data[field]))
        
        return decrypted_data


# Global encryption instance
_pii_encryption = None


def get_pii_encryption() -> PIIEncryption:
    """Get or create global encryption instance"""
    global _pii_encryption
    if _pii_encryption is None:
        _pii_encryption = PIIEncryption()
    return _pii_encryption


def encrypt_pii(plaintext: str) -> str:
    """
    Convenience function to encrypt PII
    
    Usage:
        encrypted_email = encrypt_pii(user_email)
    """
    encryptor = get_pii_encryption()
    return encryptor.encrypt(plaintext)


def decrypt_pii(ciphertext: str) -> str:
    """
    Convenience function to decrypt PII
    
    Usage:
        user_email = decrypt_pii(encrypted_email)
    """
    encryptor = get_pii_encryption()
    return encryptor.decrypt(ciphertext)


# Common PII fields that should be encrypted
PII_FIELDS = ['email', 'phone', 'dni', 'address', 'contacto']


def encrypt_customer_data(customer: dict) -> dict:
    """
    Encrypt all PII fields in customer data
    
    Args:
        customer: Customer dictionary
        
    Returns:
        Customer dict with encrypted PII
    """
    encryptor = get_pii_encryption()
    return encryptor.encrypt_dict(customer, PII_FIELDS)


def decrypt_customer_data(customer: dict) -> dict:
    """
    Decrypt all PII fields in customer data
    
    Args:
        customer: Customer dictionary with encrypted PII
        
    Returns:
        Customer dict with decrypted PII
    """
    encryptor = get_pii_encryption()
    return encryptor.decrypt_dict(customer, PII_FIELDS)
