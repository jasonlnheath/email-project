#!/usr/bin/env python3
"""Tests for login/logout functionality.

TDD: Tests written FIRST to define expected behavior, then implementation fixed.
Integration tests hit the real server to verify end-to-end behavior.
"""

import json
import sys
import time
import unittest
from pathlib import Path
from http.client import HTTPConnection


class TestLoginLogout(unittest.TestCase):
    """Test that login and logout work correctly."""

    BASE_URL = "http://localhost:9999"

    def test_login_form_exists(self):
        """The login form should be present in the HTML."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        self.assertIn('id="login-container"', html_content,
            "Login container should exist")
        self.assertIn('id="username"', html_content,
            "Username input should exist")
        self.assertIn('id="password"', html_content,
            "Password input should exist")
        self.assertIn('handleLogin', html_content,
            "handleLogin function should be called on form submit")

    def test_logout_function_exists(self):
        """The logout function should call /api/logout."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        self.assertIn('async function logout()', html_content,
            "logout function should be defined")
        self.assertIn("'/api/logout'", html_content,
            "logout should call /api/logout endpoint")

    def test_logout_clears_cookie_in_response(self):
        """Logout response MUST include Set-Cookie header to clear the browser cookie.
        
        This is the critical bug: without clearing the cookie, the browser
        keeps sending the old session ID on subsequent requests.
        """
        # Hit the logout endpoint with a fake session cookie
        conn = HTTPConnection("localhost", 9999)
        conn.request("GET", "/api/logout", headers={"Cookie": "session=fake_session_id"})
        resp = conn.getresponse()
        body = resp.read().decode()
        
        # Verify response
        self.assertEqual(resp.status, 200)
        data = json.loads(body)
        self.assertTrue(data["success"])
        
        # CRITICAL: Set-Cookie header must be present to clear browser cookie
        set_cookie = resp.getheader("Set-Cookie")
        self.assertIsNotNone(set_cookie, 
            "Logout MUST return Set-Cookie header to clear browser cookie")
        self.assertIn("Max-Age=0", set_cookie,
            "Set-Cookie must have Max-Age=0 to expire the cookie immediately")
        conn.close()

    def test_logout_returns_json(self):
        """Logout should return JSON with success field."""
        conn = HTTPConnection("localhost", 9999)
        conn.request("GET", "/api/logout")
        resp = conn.getresponse()
        body = resp.read().decode()
        
        data = json.loads(body)
        self.assertIn("success", data)
        self.assertTrue(data["success"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
