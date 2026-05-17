#!/usr/bin/env python3
"""Tests for dark mode toggle functionality.

TDD: Tests written FIRST to define expected behavior, then implementation fixed.
"""

import json
import sys
import unittest
from pathlib import Path


class TestDarkModeToggle(unittest.TestCase):
    """Test that dark mode toggle works correctly."""

    def test_dark_toggle_button_exists(self):
        """The HTML should have a dark mode toggle button."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        self.assertIn('id="dark-toggle"', html_content,
            "Dark mode toggle button must exist")
    
    def test_toggle_function_exists(self):
        """There should be a toggleDarkMode function defined."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        self.assertIn('function toggleDarkMode', html_content,
            "toggleDarkMode function must be defined in the HTML")
    
    def test_dark_mode_class_toggled(self):
        """The toggle function should add/remove 'dark' class on body."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        # Check that toggleDarkMode toggles the dark class
        self.assertIn("classList.toggle('dark')", html_content,
            "toggleDarkMode should toggle 'dark' class on body")
    
    def test_dark_mode_preference_saved(self):
        """The toggle function should save preference to localStorage."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        # Check that toggleDarkMode saves to localStorage
        self.assertIn("localStorage.setItem('dashboard-dark-mode'", html_content,
            "toggleDarkMode should save preference to localStorage")
    
    def test_dark_mode_restored_on_load(self):
        """Dark mode preference should be restored when page loads."""
        html_path = Path(__file__).resolve().parent / "index.html"
        html_content = html_path.read_text()
        
        # Check that there's logic to restore dark mode on load
        self.assertIn("localStorage.getItem('dashboard-dark-mode')", html_content,
            "Page should check localStorage for dark mode preference on load")


if __name__ == "__main__":
    unittest.main()