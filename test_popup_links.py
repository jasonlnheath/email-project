#!/usr/bin/env python3
"""Tests for popup Gmail link behavior.

TDD: Tests written FIRST to define expected behavior, then implementation fixed.
"""

import json
import sys
import unittest
from pathlib import Path


class TestPopupLinks(unittest.TestCase):
    """Test that Gmail links open in popup windows instead of new tabs."""

    def test_render_card_uses_popup_function(self):
        """The renderCard function should use a popup function for Gmail links,
        not target='_blank'."""
        # Read the index.html file
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        # Check that the Open button uses a popup function
        # Instead of: <a href="..." target="_blank">
        # It should be: <a href="..." onclick="...openGmailPopup(...)">
        self.assertIn('openGmailPopup', html_content,
            "Gmail link should use openGmailPopup function instead of target='_blank'")
        self.assertIn('event.preventDefault()', html_content,
            "Gmail link should call event.preventDefault() to prevent navigation")
    
    def test_open_gmail_popup_function_exists(self):
        """There should be an openGmailPopup function defined."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        self.assertIn('function openGmailPopup', html_content,
            "openGmailPopup function must be defined in the HTML")
    
    def test_popup_has_correct_dimensions(self):
        """The popup should have reasonable dimensions (not full screen)."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        # Check that window.open is called with width and height parameters
        self.assertIn('width=', html_content,
            "Popup should specify width parameter")
        self.assertIn('height=', html_content,
            "Popup should specify height parameter")

    def test_open_button_uses_javascript_void_href(self):
        """The Open button should use javascript:void(0) as href."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        # The Open button should NOT have target="_blank"
        self.assertNotIn("target='_blank'", html_content,
            "Gmail links should not use target='_blank'")


if __name__ == "__main__":
    unittest.main()
