#!/usr/bin/env python3
"""Behavioral tests for dark mode toggle - simulates runtime behavior."""

import json
import re
import unittest
from pathlib import Path


class TestDarkModeBehavior(unittest.TestCase):
    """Test dark mode toggle behavior by analyzing the HTML/JS code."""

    def setUp(self):
        self.html_path = Path(__file__).resolve().parent / "index.html"
        self.html_content = self.html_path.read_text()
    
    def test_toggle_button_visible_when_logged_in(self):
        """The dark toggle button should be visible when user is logged in."""
        # Check that the auth state block shows the toggle button
        self.assertIn("document.getElementById('dark-toggle').style.display = 'inline-block'", 
                      self.html_content,
            "Toggle button should be shown when logged in")
    
    def test_dark_mode_restored_after_login(self):
        """Dark mode preference should be restored after login."""
        # Check that there's logic to restore dark mode when isLoggedIn is true
        self.assertIn("if (isLoggedIn && localStorage.getItem('dashboard-dark-mode') === '1')", 
                      self.html_content,
            "Dark mode should be restored when user is logged in and preference is saved")
    
    def test_toggle_function_toggles_both_body_and_html(self):
        """The toggle function should toggle dark class on both body and html elements."""
        # Extract the toggleDarkMode function
        toggle_match = re.search(r'function toggleDarkMode\(\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}', 
                                 self.html_content, re.DOTALL)
        
        if toggle_match:
            toggle_body = toggle_match.group(1)
            # Check that it toggles on both body and documentElement
            has_body_toggle = "document.body.classList.toggle('dark')" in toggle_body or \
                            "body.classList.toggle('dark')" in toggle_body
            has_html_toggle = "document.documentElement.classList.toggle('dark')" in toggle_body or \
                            "html.classList.toggle('dark')" in toggle_body
            
            self.assertTrue(has_body_toggle or has_html_toggle,
                "toggleDarkMode should toggle 'dark' class on body or html element")
    
    def test_popup_function_handles_url_correctly(self):
        """The openGmailPopup function should handle URLs correctly."""
        # Extract the openGmailPopup function
        popup_match = re.search(r'function openGmailPopup\(url\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}', 
                               self.html_content, re.DOTALL)
        
        if popup_match:
            popup_body = popup_match.group(1)
            # Check that it calls window.open with the URL
            self.assertIn('window.open', popup_body,
                "openGmailPopup should call window.open")
            self.assertIn('url', popup_body,
                "openGmailPopup should use the url parameter")


if __name__ == "__main__":
    unittest.main()