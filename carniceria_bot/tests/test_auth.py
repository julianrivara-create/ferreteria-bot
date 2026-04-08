"""
Unit Tests for Authentication Module
"""

import pytest
from bot_sales.security.auth import AuthManager, UserDatabase, get_auth_manager, get_user_database


class TestAuthManager:
    """Tests for AuthManager"""
    
    @pytest.fixture
    def auth_manager(self):
        return AuthManager()
    
    def test_hash_password(self, auth_manager):
        password = "test_password_123"
        hashed = auth_manager.hash_password(password)
        
        assert hashed != password
        assert len(hashed) > 20
    
    def test_verify_password_correct(self, auth_manager):
        password = "test_password_123"
        hashed = auth_manager.hash_password(password)
        
        assert auth_manager.verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self, auth_manager):
        password = "test_password_123"
        hashed = auth_manager.hash_password(password)
        
        assert auth_manager.verify_password("wrong_password", hashed) is False
    
    def test_generate_token(self, auth_manager):
        token = auth_manager.generate_token(user_id="user123", role="admin")
        
        assert isinstance(token, str)
        assert len(token) > 50
    
    def test_verify_valid_token(self, auth_manager):
        token = auth_manager.generate_token(user_id="user123", role="admin")
        is_valid, payload = auth_manager.verify_token(token)
        
        assert is_valid is True
        assert payload['user_id'] == "user123"
        assert payload['role'] == "admin"
    
    def test_verify_invalid_token(self, auth_manager):
        is_valid, payload = auth_manager.verify_token("invalid_token_string")
        
        assert is_valid is False
        assert payload is None
    
    def test_refresh_token(self, auth_manager):
        import time
        old_token = auth_manager.generate_token(user_id="user123", role="user")
        time.sleep(1.1)  # Ensure timestamp changes
        new_token = auth_manager.refresh_token(old_token)
        
        assert new_token is not None
        assert new_token != old_token
        
        # Verify new token works
        is_valid, payload = auth_manager.verify_token(new_token)
        assert is_valid is True
        assert payload['user_id'] == "user123"


class TestUserDatabase:
    """Tests for UserDatabase"""
    
    @pytest.fixture
    def user_db(self):
        return UserDatabase()
    
    def test_default_admin_exists(self, user_db):
        admin_user = user_db.authenticate('admin', 'change_me_in_production')
        
        assert admin_user is not None
        assert admin_user['role'] == 'admin'
    
    def test_authenticate_valid_credentials(self, user_db):
        # Create test user
        user_db.create_user('testuser', 'testpass123', role='user')
        
        # Authenticate
        user = user_db.authenticate('testuser', 'testpass123')
        
        assert user is not None
        assert user['username'] == 'testuser'
        assert user['role'] == 'user'
        assert 'password_hash' not in user  # Should not return password
    
    def test_authenticate_invalid_password(self, user_db):
        user_db.create_user('testuser', 'testpass123', role='user')
        user = user_db.authenticate('testuser', 'wrong_password')
        
        assert user is None
    
    def test_authenticate_nonexistent_user(self, user_db):
        user = user_db.authenticate('nonexistent', 'password')
        
        assert user is None
    
    def test_create_user(self, user_db):
        success = user_db.create_user(
            username='newuser',
            password='newpass123',
            role='agent',
            email='new@example.com'
        )
        
        assert success is True
        
        # Verify user was created
        user = user_db.authenticate('newuser', 'newpass123')
        assert user is not None
        assert user['email'] == 'new@example.com'
    
    def test_create_duplicate_user(self, user_db):
        user_db.create_user('dupuser', 'pass123')
        success = user_db.create_user('dupuser', 'pass456')
        
        assert success is False
