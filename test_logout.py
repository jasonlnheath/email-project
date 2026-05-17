#!/usr/bin/env python3
"""Tests for logout functionality.

TDD: Tests written FIRST to define expected behavior, then implementation fixed.
Integration tests hit the real server to verify end-to-end behavior.
"""

import json
import sys
import time
import unittest
from pathlib import Path
from http.client import HTTPConnection


class TestLogout(unittest.TestCase):
    """Test that logout properly invalidates session AND clears cookies."""

    BASE_URL = "http://localhost:9999"

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
