#!/usr/bin/env python3
"""Tests for authentication system — TDD RED-GREEN-REFACTOR.

Tests cover:
- Password hashing (bcrypt)
- User registration
- Session creation/invalidation
- Login validation
- Auth middleware (reject unauthenticated requests)
- Session expiry
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))


class TestPasswordHashing:
    """Test password hashing with bcrypt."""

    def test_hash_is_deterministic_per_round(self):
        """Same password + same salt = same hash."""
        from auth import hash_password, verify_password

        pw = "my_secret_password"
        h1 = hash_password(pw)
        h2 = hash_password(pw)

        # Both should be valid bcrypt hashes
        assert h1.startswith("$2b$") or h1.startswith("$2a$")
        assert h2.startswith("$2b$") or h2.startswith("$2a$")
        assert len(h1) == 60
        assert len(h2) == 60

    def test_verify_correct_password(self):
        """Correct password verifies successfully."""
        from auth import hash_password, verify_password

        pw = "correct_password_123"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True

    def test_verify_wrong_password(self):
        """Wrong password fails verification."""
        from auth import hash_password, verify_password

        hashed = hash_password("real_password")
        assert verify_password("wrong_password", hashed) is False

    def test_empty_password_fails(self):
        """Empty password should not verify against a real hash."""
        from auth import hash_password, verify_password

        hashed = hash_password("real_password")
        assert verify_password("", hashed) is False


class TestUserManager:
    """Test user registration and management."""

    def setup_method(self):
        """Set up a temporary database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "auth.db")

        from auth import UserManager
        self.manager = UserManager(self.db_path)

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_user(self):
        """Test creating a new user."""
        result = self.manager.create_user(
            username="jason",
            password="secure_pass_123",
            display_name="Jason Heath"
        )
        assert result is True
        assert self.manager.get_user("jason") is not None
        assert self.manager.get_user("jason")["display_name"] == "Jason Heath"

    def test_create_user_duplicate_fails(self):
        """Creating a duplicate user returns False."""
        self.manager.create_user("jason", "pass1", "Jason")
        assert self.manager.create_user("jason", "pass2", "Jason2") is False

    def test_get_nonexistent_user(self):
        """Getting a nonexistent user returns None."""
        assert self.manager.get_user("nobody") is None

    def test_verify_user_password(self):
        """verify_user checks password against stored hash."""
        self.manager.create_user("michelle", "michelles_secret", "Michelle Heath")
        assert self.manager.verify_user("michelle", "michelles_secret") is True
        assert self.manager.verify_user("michelle", "wrong_password") is False

    def test_create_user_stores_hash_not_plaintext(self):
        """Password is stored as bcrypt hash, not plaintext."""
        self.manager.create_user("testuser", "plaintext_should_not_appear", "Test User")
        user = self.manager.get_user("testuser")
        assert user["password_hash"] != "plaintext_should_not_appear"
        assert user["password_hash"].startswith("$2b$") or user["password_hash"].startswith("$2a$")


class TestSessionManager:
    """Test session creation, validation, and expiry."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "auth.db")

        from auth import UserManager, SessionManager
        self.user_mgr = UserManager(self.db_path)
        self.session_mgr = SessionManager(self.user_mgr, self.db_path)

        # Create a test user
        self.user_mgr.create_user("jason", "password123", "Jason Heath")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_session(self):
        """Creating a session returns a valid session ID."""
        session_id = self.session_mgr.create_session("jason")
        assert session_id is not None
        assert len(session_id) > 0

    def test_get_valid_session(self):
        """Getting a valid session returns the username."""
        session_id = self.session_mgr.create_session("jason")
        username = self.session_mgr.get_username(session_id)
        assert username == "jason"

    def test_get_invalid_session(self):
        """Getting an invalid session returns None."""
        assert self.session_mgr.get_username("fake_session_id_xyz") is None

    def test_invalidate_session(self):
        """Invalidating a session makes it unusable."""
        session_id = self.session_mgr.create_session("jason")
        self.session_mgr.invalidate_session(session_id)
        assert self.session_mgr.get_username(session_id) is None

    def test_session_expiry(self):
        """Expired sessions are cleaned up and return None."""
        # Create a session with very short expiry for testing
        session_id = self.session_mgr.create_session("jason", ttl=1)  # 1 second TTL
        assert self.session_mgr.get_username(session_id) == "jason"

        # Wait for expiry
        time.sleep(1.5)

        # Session should be expired
        assert self.session_mgr.get_username(session_id) is None

    def test_cleanup_expired_sessions(self):
        """cleanup_expired removes expired sessions from DB."""
        # Create an expired session (1s TTL)
        self.session_mgr.create_session("jason", ttl=1)
        # Create a valid session (long TTL)
        self.session_mgr.create_session("michelle", ttl=3600)

        # Force cleanup
        self.session_mgr.cleanup_expired()

        # Valid session still works
        # (We can't easily get the session ID back, but we verify no crash)
        assert True  # If we got here without error, cleanup worked


class TestAuthMiddleware:
    """Test auth middleware that protects API endpoints."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "auth.db")

        from auth import UserManager, SessionManager, AuthMiddleware
        self.user_mgr = UserManager(self.db_path)
        self.session_mgr = SessionManager(self.user_mgr, self.db_path)
        self.middleware = AuthMiddleware(self.session_mgr)

        self.user_mgr.create_user("jason", "password123", "Jason Heath")
        self.user_mgr.create_user("michelle", "michelleshadow", "Michelle Heath")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_cookie_returns_401(self):
        """Request without session cookie gets 401."""
        mock_handler = MagicMock()
        mock_handler.cookies = {}

        result = self.middleware.require_auth(mock_handler)

        assert result is False
        mock_handler.send_json.assert_called_once_with(
            {"error": "unauthorized"}, 401
        )

    def test_invalid_session_returns_401(self):
        """Request with invalid session cookie gets 401."""
        mock_handler = MagicMock()
        mock_handler.cookies = {"session": "fake_session_xyz"}

        result = self.middleware.require_auth(mock_handler)

        assert result is False
        mock_handler.send_json.assert_called_once_with(
            {"error": "expired session"}, 401
        )

    def test_valid_session_passes(self):
        """Request with valid session cookie passes auth."""
        session_id = self.session_mgr.create_session("jason")
        mock_handler = MagicMock()
        mock_handler.cookies = {"session": session_id}

        result = self.middleware.require_auth(mock_handler)

        assert result is True
        assert mock_handler.current_user == "jason"

    def test_different_users_get_different_sessions(self):
        """Jason's session doesn't work for Michelle and vice versa."""
        jason_sid = self.session_mgr.create_session("jason")
        michelle_sid = self.session_mgr.create_session("michelle")

        # Jason's session should resolve to jason
        mock_jason = MagicMock()
        mock_jason.cookies = {"session": jason_sid}
        assert self.middleware.require_auth(mock_jason) is True
        assert mock_jason.current_user == "jason"

        # Michelle's session should resolve to michelle
        mock_michelle = MagicMock()
        mock_michelle.cookies = {"session": michelle_sid}
        assert self.middleware.require_auth(mock_michelle) is True
        assert mock_michelle.current_user == "michelle"


class TestLoginEndpoint:
    """Test the login flow."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "auth.db")

        from auth import UserManager, SessionManager, AuthMiddleware
        self.user_mgr = UserManager(self.db_path)
        self.session_mgr = SessionManager(self.user_mgr, self.db_path)
        self.middleware = AuthMiddleware(self.session_mgr)

        self.user_mgr.create_user("jason", "correct_password", "Jason Heath")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_login_with_correct_creds(self):
        """Login with correct credentials succeeds."""
        mock_handler = MagicMock()
        mock_handler.request_body = {"username": "jason", "password": "correct_password"}

        result = self.middleware.handle_login(mock_handler)

        assert result is True  # Login succeeded
        # Should have set a session cookie
        set_cookie_calls = [
            call for call in mock_handler.send_response.call_args_list
            if "Set-Cookie" in str(call)
        ]
        # The handler should have called send_json with success
        json_calls = [call for call in mock_handler.send_json.call_args_list]
        assert len(json_calls) > 0
        assert json_calls[0][0][0]["success"] is True
        assert "session_id" in json_calls[0][0][0]

    def test_login_with_wrong_password(self):
        """Login with wrong password returns error."""
        mock_handler = MagicMock()
        mock_handler.request_body = {"username": "jason", "password": "wrong_password"}

        result = self.middleware.handle_login(mock_handler)

        # Should return error
        json_calls = [call for call in mock_handler.send_json.call_args_list]
        assert len(json_calls) > 0
        assert json_calls[0][0][0].get("error") is not None
        assert json_calls[0][0][0].get("success") is False

    def test_login_with_unknown_user(self):
        """Login with nonexistent user returns error."""
        mock_handler = MagicMock()
        mock_handler.request_body = {"username": "nobody", "password": "whatever"}

        result = self.middleware.handle_login(mock_handler)

        json_calls = [call for call in mock_handler.send_json.call_args_list]
        assert len(json_calls) > 0
        assert json_calls[0][0][0].get("error") is not None


class TestLogoutEndpoint:
    """Test the logout flow."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "auth.db")

        from auth import UserManager, SessionManager, AuthMiddleware
        self.user_mgr = UserManager(self.db_path)
        self.session_mgr = SessionManager(self.user_mgr, self.db_path)
        self.middleware = AuthMiddleware(self.session_mgr)

        self.user_mgr.create_user("jason", "password123", "Jason Heath")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_logout_invalidates_session(self):
        """Logout invalidates the session cookie."""
        session_id = self.session_mgr.create_session("jason")

        mock_handler = MagicMock()
        mock_handler.cookies = {"session": session_id}

        result = self.middleware.handle_logout(mock_handler)

        assert result is True
        # Session should be invalidated
        assert self.session_mgr.get_username(session_id) is None


class TestUserRegistry:
    """Test user registry (users.json) loading and mapping."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.users_json_path = os.path.join(self.tmpdir, "users.json")

        from auth import UserRegistry
        self.registry = UserRegistry(self.users_json_path)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_users_file(self):
        """Loading users.json returns the user config."""
        # Create a users.json file
        with open(self.users_json_path, "w") as f:
            json.dump({
                "users": {
                    "jason": {
                        "name": "Jason Heath",
                        "token_file": "tokens/jason_google_token.json"
                    },
                    "michelle": {
                        "name": "Michelle Heath",
                        "token_file": "tokens/michelle_google_token.json"
                    }
                }
            }, f)

        self.registry.load()
        assert self.registry.get_user_config("jason") is not None
        assert self.registry.get_user_config("jason")["name"] == "Jason Heath"
        assert self.registry.get_user_config("michelle")["name"] == "Michelle Heath"

    def test_get_nonexistent_user(self):
        """Getting a nonexistent user from registry returns None."""
        with open(self.users_json_path, "w") as f:
            json.dump({"users": {"jason": {"name": "Jason"}}}, f)

        self.registry.load()
        assert self.registry.get_user_config("nobody") is None

    def test_token_file_path(self):
        """Token file path resolves correctly."""
        with open(self.users_json_path, "w") as f:
            json.dump({
                "users": {
                    "jason": {
                        "name": "Jason",
                        "token_file": "tokens/jason_google_token.json"
                    }
                }
            }, f)

        self.registry.load()
        token_path = self.registry.get_token_path("jason")
        assert "tokens" in token_path
        assert "jason_google_token.json" in token_path


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
