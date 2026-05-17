#!/usr/bin/env python3
"""Tests for email card collapse/expand feature.

TDD: Tests written FIRST to define expected behavior, then implementation added.
"""

import sys
import unittest
from pathlib import Path


class TestCollapseExpand(unittest.TestCase):
    """Test that email cards support collapse/expand with smooth animation."""

    def _read_html(self):
        html_path = Path(__file__).resolve().parent / "index.html"
        return html_path.read_text()

    def test_card_has_collapse_toggle_button(self):
        """Each card should have a collapse toggle button in the header."""
        html = self._read_html()
        self.assertIn('toggleCard', html,
            "Cards should have a toggleCard function for collapse/expand")

    def test_toggle_card_function_exists(self):
        """There should be a toggleCard JavaScript function defined."""
        html = self._read_html()
        self.assertIn('function toggleCard', html,
            "toggleCard function must be defined in the HTML")

    def test_toggle_card_uses_css_class(self):
        """toggleCard should toggle a CSS class (e.g., 'collapsed') on the card."""
        html = self._read_html()
        has_collapsed = '.collapsed' in html
        has_toggle = 'classList.toggle' in html
        self.assertTrue(has_collapsed and has_toggle,
            "toggleCard should use classList.toggle with a collapsed class")

    def test_summary_and_actions_are_collapsible(self):
        """Summary section and action buttons should be hidden when card is collapsed."""
        html = self._read_html()
        has_collapsed_selector = (
            '.email-card.collapsed' in html or
            '.collapsed .summary-section' in html
        )
        self.assertTrue(has_collapsed_selector,
            "CSS should hide summary/actions when card is collapsed")

    def test_smooth_animation_on_collapse(self):
        """Collapse/expand transition should use smooth animation (CSS transition)."""
        html = self._read_html()
        self.assertIn('transition', html,
            "Collapsible sections should have CSS transition for smooth animation")

    def test_chevron_indicator_in_header(self):
        """Card header should show a chevron indicator that rotates on collapse."""
        html = self._read_html()
        has_chevron_class = 'card-chevron' in html
        has_chevron_symbol = '▼' in html
        has_arrow_text = 'arrow' in html.lower()
        self.assertTrue(has_chevron_class or has_chevron_symbol or has_arrow_text,
            "Card header should have a chevron/arrow indicator for collapse state")


if __name__ == "__main__":
    unittest.main()
