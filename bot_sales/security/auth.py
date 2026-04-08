#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
JWT Authentication Module
Handles token generation, validation, and user session management
"""

import os
import jwt
import bcrypt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from functools import wraps
from flask import request, jsonify


class AuthManager:
    """
    JWT-based authentication manager
    """
    
    def __init__(self):
        self.secret_key = os.getenv('JWT_SECRET', '')
        self.algorithm = 'HS256'
        self.token_expiry_hours = 24

        if not self.secret_key:
            raise ValueError(
                "JWT_SECRET environment variable must be set to a secure random value. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
    
    def hash_password(self, password: str) -> str:
        """
        Hash password with bcrypt
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """
        Verify password against hash
        
        Args:
            password: Plain text password
            hashed: Hashed password
            
        Returns:
            True if password matches
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logging.error(f"Password verification error: {e}")
            return False
    
    def generate_token(
        self,
        user_id: str,
        role: str = 'user',
        extra_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate JWT token
        
        Args:
            user_id: User identifier
            role: User role (admin, manager, agent, user)
            extra_claims: Additional claims to include
            
        Returns:
            JWT token string
        """
        payload = {
            'user_id': user_id,
            'role': role,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=self.token_expiry_hours)
        }
        
        if extra_claims:
            payload.update(extra_claims)
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token
    
    def verify_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verify and decode JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            (is_valid, payload_dict or None)
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return True, payload
        except jwt.ExpiredSignatureError:
            logging.warning("Token expired")
            return False, None
        except jwt.InvalidTokenError as e:
            logging.warning(f"Invalid token: {e}")
            return False, None
    
    def refresh_token(self, old_token: str) -> Optional[str]:
        """
        Refresh an existing token
        
        Args:
            old_token: Existing JWT token
            
        Returns:
            New token or None if invalid
        """
        is_valid, payload = self.verify_token(old_token)
        
        if not is_valid or not payload:
            return None
        
        # Generate new token with same claims
        return self.generate_token(
            user_id=payload['user_id'],
            role=payload.get('role', 'user'),
            extra_claims={
                k: v for k, v in payload.items()
                if k not in ['user_id', 'role', 'iat', 'exp']
            }
        )
    
    def extract_token_from_request(self) -> Optional[str]:
        """
        Extract JWT from Flask request
        
        Returns:
            Token string or None
        """
        # Check Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            return auth_header[7:]
        
        # Check query parameter (not recommended for production)
        token = request.args.get('token')
        if token:
            return token
        
        return None


# Global auth instance
_auth_manager = None


def get_auth_manager() -> AuthManager:
    """Get or create global auth manager"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def require_auth(required_role: Optional[str] = None):
    """
    Decorator to require authentication for Flask routes
    
    Usage:
        @app.route('/admin')
        @require_auth('admin')
        def admin_dashboard():
            return "Admin area"
    
    Args:
        required_role: Required role ('admin', 'manager', 'agent') or None for any authenticated user
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            auth = get_auth_manager()
            
            # Extract token
            token = auth.extract_token_from_request()
            if not token:
                return jsonify({'error': 'No token provided'}), 401
            
            # Verify token
            is_valid, payload = auth.verify_token(token)
            if not is_valid:
                return jsonify({'error': 'Invalid or expired token'}), 401
            
            # Check role if specified
            if required_role:
                user_role = payload.get('role', 'user')
                
                # Role hierarchy: admin > manager > agent > user
                role_hierarchy = {'admin': 4, 'manager': 3, 'agent': 2, 'user': 1}
                required_level = role_hierarchy.get(required_role, 0)
                user_level = role_hierarchy.get(user_role, 0)
                
                if user_level < required_level:
                    return jsonify({'error': 'Insufficient permissions'}), 403
            
            # Add user info to request context
            request.user = payload
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


# User database mock (replace with real DB in production)
class UserDatabase:
    """
    Simple user database for demo
    In production, replace with real database
    """
    
    def __init__(self):
        self.users = {}
        # Create default admin user
        auth = get_auth_manager()
        admin_username = os.getenv('ADMIN_USERNAME', 'admin')
        admin_password = os.getenv('ADMIN_PASSWORD')
        if not admin_password:
            raise ValueError(
                "ADMIN_PASSWORD env var is required. "
                "Set a secure value before starting the application."
            )

        self.users[admin_username] = {
            'user_id': 'admin-001',
            'username': admin_username,
            'password_hash': auth.hash_password(admin_password),
            'role': 'admin',
            'email': os.getenv('ADMIN_EMAIL', 'admin@salesbot.local')
        }

        logging.info("Default admin user initialised: %s", admin_username)
    
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with username/password
        
        Returns:
            User dict or None if invalid credentials
        """
        user = self.users.get(username)
        if not user:
            return None
        
        auth = get_auth_manager()
        if auth.verify_password(password, user['password_hash']):
            # Return user info without password
            return {
                'user_id': user['user_id'],
                'username': user['username'],
                'role': user['role'],
                'email': user.get('email')
            }
        
        return None
    
    def create_user(
        self,
        username: str,
        password: str,
        role: str = 'user',
        email: Optional[str] = None
    ) -> bool:
        """
        Create new user
        
        Returns:
            True if successful
        """
        if username in self.users:
            logging.error(f"User already exists: {username}")
            return False
        
        auth = get_auth_manager()
        
        self.users[username] = {
            'user_id': f"user-{len(self.users) + 1:03d}",
            'username': username,
            'password_hash': auth.hash_password(password),
            'role': role,
            'email': email
        }
        
        logging.info(f"✅ User created: {username} (role: {role})")
        return True


# Global user database
_user_db = None


def get_user_database() -> UserDatabase:
    """Get or create global user database"""
    global _user_db
    if _user_db is None:
        _user_db = UserDatabase()
    return _user_db
