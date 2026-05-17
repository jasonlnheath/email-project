#!/usr/bin/env python3
"""Authentication system for email dashboard.

Provides:
- Password hashing with bcrypt
- User registration and verification
- Session management (create, validate, expire, cleanup)
- Auth middleware for HTTP handlers
- User registry (users.json → token file mapping)
"""

import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path


# ── Password Hashing ────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password using bcrypt-style hashing.
    
    Uses SHA-256 + salt as a lightweight alternative to bcrypt when
    the bcrypt package isn't available. In production, prefer bcrypt.
    """
    try:
        import bcrypt
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=12)
        ).decode("utf-8")
    except ImportError:
        # Fallback: SHA-256 with random salt
        salt = secrets.token_hex(16)
        h = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"$fallback${salt}${h}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a stored hash."""
    if not password or not hashed:
        return False

    # Check for SHA-256 fallback format first (before trying bcrypt)
    if hashed.startswith("$fallback$"):
        parts = hashed.split("$", 3)  # $fallback$salt$hash
        if len(parts) != 4:
            return False
        _, salt, stored_hash = parts[1], parts[2], parts[3]
        computed = hashlib.sha256((password + salt).encode()).hexdigest()
        return secrets.compare_digest(computed, stored_hash)

    # Otherwise use bcrypt
    try:
        import bcrypt
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hashed.encode("utf-8")
        )
    except (ValueError, ImportError):
        return False


# ── User Manager ────────────────────────────────────────────────

class UserManager:
    """Manage user accounts with password hashing."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def create_user(self, username: str, password: str, display_name: str, email: str = None) -> bool:
        """Register a new user. Returns False if username already exists."""
        hashed = hash_password(password)
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                "INSERT INTO users (username, password_hash, display_name, email) VALUES (?, ?, ?, ?)",
                (username, hashed, display_name, email)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_user(self, username: str) -> dict | None:
        """Get user info by username. Returns None if not found."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT username, password_hash, display_name, email, created_at FROM users WHERE username = ?",
                (username,)
            ).fetchone()
            if row:
                return {
                    "username": row[0],
                    "password_hash": row[1],
                    "display_name": row[2],
                    "email": row[3],
                    "created_at": row[4],
                }
            return None
        finally:
            conn.close()

    def verify_user(self, username: str, password: str) -> bool:
        """Verify username + password. Returns False if user doesn't exist or password is wrong."""
        user = self.get_user(username)
        if not user:
            return False
        return verify_password(password, user["password_hash"])


# ── Session Manager ─────────────────────────────────────────────

class SessionManager:
    """Manage authentication sessions with expiry."""

    DEFAULT_TTL = 86400  # 24 hours in seconds

    def __init__(self, user_mgr: UserManager, db_path: str | Path):
        self.user_mgr = user_mgr
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """Create sessions table if it doesn't exist.
        
        Uses REAL (epoch seconds) for expires_at to avoid timezone issues.
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL REFERENCES users(username),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at REAL NOT NULL,
                    ip_address TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def create_session(self, username: str, ttl: int = None, ip_address: str = None) -> str | None:
        """Create a new session for a user. Returns session ID or None if user not found."""
        if not self.user_mgr.get_user(username):
            return None

        session_id = secrets.token_urlsafe(32)
        ttl = ttl or self.DEFAULT_TTL
        expires_at = time.time() + ttl

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                "INSERT INTO sessions (session_id, username, expires_at, ip_address) VALUES (?, ?, ?, ?)",
                (session_id, username, expires_at, ip_address)
            )
            conn.commit()
            return session_id
        finally:
            conn.close()

    def get_username(self, session_id: str) -> str | None:
        """Get username for a valid session. Returns None if expired or invalid."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT username, expires_at FROM sessions WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            if not row:
                return None

            username, expires_epoch = row
            # Check expiry (both are epoch seconds — no timezone issues)
            if time.time() > expires_epoch:
                return None  # Expired
            return username
        finally:
            conn.close()

    def invalidate_session(self, session_id: str):
        """Invalidate (delete) a session."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()

    def cleanup_expired(self):
        """Remove all expired sessions from the database."""
        now = time.time()
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            conn.commit()
        finally:
            conn.close()


# ── Auth Middleware ─────────────────────────────────────────────

class AuthMiddleware:
    """HTTP request middleware for authentication checks."""

    def __init__(self, session_mgr: SessionManager):
        self.session_mgr = session_mgr

    def require_auth(self, handler) -> bool:
        """Check if the request has a valid session cookie.
        
        Args:
            handler: HTTP handler with .cookies dict and .send_json() method.
            
        Returns:
            True if authenticated (handler.current_user set), False if not.
        """
        session_id = handler.cookies.get("session")
        if not session_id:
            handler.send_json({"error": "unauthorized"}, 401)
            return False

        username = self.session_mgr.get_username(session_id)
        if not username:
            handler.send_json({"error": "expired session"}, 401)
            return False

        handler.current_user = username
        return True

    def handle_login(self, handler) -> bool:
        """Handle a login request.
        
        Args:
            handler: HTTP handler with .request_body dict and .send_json() method.
            
        Returns:
            True on success, False on failure.
        """
        body = getattr(handler, "request_body", {})
        username = body.get("username", "").strip()
        password = body.get("password", "")

        if not username or not password:
            handler.send_json({"success": False, "error": "username and password required"}, 401)
            return False

        # Verify credentials
        if not self.session_mgr.user_mgr.verify_user(username, password):
            handler.send_json({"success": False, "error": "invalid credentials"}, 401)
            return False

        # Create session
        ip = None
        if hasattr(handler, "client_address"):
            ca = handler.client_address
            # Only use real tuples/lists, not mocks
            if isinstance(ca, (tuple, list)) and len(ca) > 0:
                try:
                    ip = str(ca[0])
                except (TypeError, ValueError):
                    pass
        session_id = self.session_mgr.create_session(username, ip_address=ip)

        handler.send_json({
            "success": True,
            "session_id": session_id,
            "username": username,
        })
        return True

    def handle_logout(self, handler) -> bool:
        """Handle a logout request.
        
        Args:
            handler: HTTP handler with .cookies dict.
            
        Returns:
            True on success.
        """
        session_id = handler.cookies.get("session")
        if session_id:
            self.session_mgr.invalidate_session(session_id)

        handler.send_json({"success": True})
        return True


# ── User Registry ───────────────────────────────────────────────

class UserRegistry:
    """Load user → Gmail token mapping from users.json."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._config = {}

    def load(self):
        """Load users.json into memory."""
        if not self.path.exists():
            self._config = {}
            return
        with open(self.path, "r") as f:
            data = json.load(f)
        self._config = data.get("users", {})

    def get_user_config(self, username: str) -> dict | None:
        """Get user config (name, token_file, etc.)."""
        return self._config.get(username)

    def get_token_path(self, username: str) -> str | None:
        """Get the Gmail OAuth token file path for a user."""
        config = self._config.get(username)
        if not config:
            return None
        token_file = config.get("token_file", "")
        if not token_file:
            return None
        # Resolve relative to registry file's parent directory
        base_dir = self.path.parent
        return str(base_dir / token_file)

    def list_users(self) -> list[str]:
        """List all configured usernames."""
        return list(self._config.keys())
