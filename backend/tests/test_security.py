"""
Tests for security utility functions
"""
import pytest
from datetime import timedelta

from app.utils.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    hash_api_key,
    verify_api_key,
    validate_api_key_complexity,
)
from app.config import settings


class TestPasswordHashing:
    """Test password hashing functions"""

    def test_get_password_hash(self):
        """Test password hashing"""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 20  # bcrypt hashes are 60 chars

    def test_verify_password_correct(self):
        """Test password verification with correct password"""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password"""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert verify_password("wrong_password", hashed) is False

    def test_hash_passwords_different(self):
        """Test that same password produces different hashes (salt)"""
        password = "same_password"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2  # Different salts


class TestAPIKeyFunctions:
    """Test API key functions"""

    def test_hash_api_key(self):
        """Test API key hashing"""
        api_key = "my-secret-api-key"
        hashed = hash_api_key(api_key)

        assert hashed is not None
        assert hashed != api_key

    def test_verify_api_key_correct(self):
        """Test API key verification"""
        api_key = "my-secret-api-key"
        hashed = hash_api_key(api_key)

        assert verify_api_key(api_key, hashed) is True

    def test_verify_api_key_incorrect(self):
        """Test API key verification with wrong key"""
        api_key = "my-secret-api-key"
        hashed = hash_api_key(api_key)

        assert verify_api_key("wrong-key", hashed) is False


class TestAPIKeyComplexity:
    """Test API key complexity validation"""

    def test_valid_api_key(self):
        """Test valid API key"""
        valid, msg = validate_api_key_complexity("SecureKey123!@#")
        assert valid is True
        assert msg == ""

    def test_short_api_key(self):
        """Test API key too short"""
        valid, msg = validate_api_key_complexity("abc12")
        assert valid is False
        assert "长度至少" in msg

    def test_weak_pattern_123456(self):
        """Test API key with weak pattern 123456"""
        valid, msg = validate_api_key_complexity("abc123456xyz")
        assert valid is False
        assert "弱密钥模式" in msg

    def test_weak_pattern_password(self):
        """Test API key with weak pattern password"""
        valid, msg = validate_api_key_complexity("mypassword123")
        assert valid is False
        assert "弱密钥模式" in msg

    def test_repeated_characters(self):
        """Test API key with repeated characters"""
        valid, msg = validate_api_key_complexity("testaaaaakey")
        assert valid is False
        assert "连续相同字符" in msg

    def test_sequential_characters(self):
        """Test API key with sequential characters"""
        valid, msg = validate_api_key_complexity("test1234key")
        assert valid is False
        assert "连续顺序字符" in msg


class TestJWTokens:
    """Test JWT token functions"""

    def test_create_access_token(self):
        """Test access token creation"""
        data = {"sub": "TEST001"}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50

    def test_create_access_token_with_expiry(self):
        """Test access token with custom expiry"""
        data = {"sub": "TEST001"}
        token = create_access_token(data, expires_delta=timedelta(hours=1))

        assert token is not None

    def test_create_refresh_token(self):
        """Test refresh token creation"""
        data = {"sub": "TEST001"}
        token = create_refresh_token(data)

        assert token is not None
        assert isinstance(token, str)

    def test_verify_refresh_token_valid(self):
        """Test refresh token verification"""
        data = {"sub": "TEST001"}
        token = create_refresh_token(data)

        employee_id = verify_refresh_token(token)
        assert employee_id == "TEST001"

    def test_verify_refresh_token_invalid(self):
        """Test invalid refresh token"""
        employee_id = verify_refresh_token("invalid.token.here")
        assert employee_id is None

    def test_verify_refresh_token_wrong_type(self):
        """Test access token used as refresh token"""
        data = {"sub": "TEST001"}
        access_token = create_access_token(data)

        # Access token doesn't have "type": "refresh"
        employee_id = verify_refresh_token(access_token)
        assert employee_id is None
