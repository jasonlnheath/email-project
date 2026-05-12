#!/usr/bin/env python3
"""Tests for retrieval recall computation in evaluate_compression.

Validates entity-level preservation: checks whether concrete entities
(names, organizations, products, dates, amounts) mentioned in original
email bodies appear in the summary's key_entities field.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evaluate_compression import compute_retrieval_recall


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_emails():
    """Return sample email dicts."""
    return [
        {
            "id": "test1",
            "subject": "Meeting rescheduled to Tuesday 10am",
            "sender": "alice@example.com",
            "date": "2025-05-08T14:30:00Z",
            "body": "Hi team,\n\nThe meeting has been rescheduled to Tuesday at 10am. Please confirm your availability by end of day.\n\nBest regards,\nAlice",
            "snippet": "The meeting has been rescheduled...",
            "attachments": [],
        },
        {
            "id": "test2",
            "subject": "Q3 budget approval needed",
            "sender": "bob@corp.com",
            "date": "2025-05-09T09:00:00Z",
            "body": "Please review the attached Q3 budget proposal ($2.5M total) and approve by Friday. Contact Sarah if you have questions about the marketing allocation.",
            "snippet": "Budget approval needed...",
            "attachments": [{"filename": "q3_budget.xlsx", "type": "application/xlsx"}],
        },
        {
            "id": "test3",
            "subject": "Welcome to the team!",
            "sender": "hr@company.com",
            "date": "2025-05-10T08:00:00Z",
            "body": "We're excited to welcome you! Your start date is Monday, May 15th. Please complete the onboarding forms at https://onboarding.company.com and bring your ID to the front desk.",
            "snippet": "Welcome to the team...",
            "attachments": [],
        },
    ]


@pytest.fixture
def good_summaries():
    """Return summaries that preserve entities from sample_emails."""
    return [
        {
            "sender": "alice@example.com",
            "date": "2025-05-08T14:30:00Z",
            "subject": "Meeting rescheduled to Tuesday 10am",
            "key_entities": ["Tuesday", "10am", "meeting"],
            "action_items": ["confirm availability by end of day"],
            "sentiment": "neutral",
        },
        {
            "sender": "bob@corp.com",
            "date": "2025-05-09T09:00:00Z",
            "subject": "Q3 budget approval needed",
            "key_entities": ["Q3", "$2.5M", "Sarah", "marketing allocation"],
            "action_items": ["approve budget by Friday", "contact Sarah for questions"],
            "sentiment": "neutral",
        },
        {
            "sender": "hr@company.com",
            "date": "2025-05-10T08:00:00Z",
            "subject": "Welcome to the team!",
            "key_entities": ["Monday", "May 15th", "onboarding forms"],
            "action_items": ["complete onboarding forms", "bring ID to front desk"],
            "sentiment": "positive",
        },
    ]


@pytest.fixture
def poor_summaries():
    """Return summaries that don't preserve entities."""
    return [
        {"sender": "unknown", "date": "", "subject": "", "key_entities": [], "action_items": [], "sentiment": "neutral"},
        {"sender": "unknown", "date": "", "subject": "", "key_entities": [], "action_items": [], "sentiment": "neutral"},
        {"sender": "unknown", "date": "", "subject": "", "key_entities": [], "action_items": [], "sentiment": "neutral"},
    ]


# ── Tests ──────────────────────────────────────────────────────────────────

class TestComputeRetrievalRecall:
    """Tests for the improved retrieval recall computation."""

    def test_good_summaries_yields_positive_recall(self, sample_emails, good_summaries):
        """Good summaries that preserve entities should yield recall > 0."""
        result = compute_retrieval_recall(sample_emails, good_summaries, n_samples=3)
        assert result["recall@k"] > 0.0, f"Expected positive recall, got {result['recall@k']}"
        assert result["entailed_count"] > 0

    def test_poor_summaries_yields_low_recall(self, sample_emails, poor_summaries):
        """Poor summaries with no entity preservation should yield low recall."""
        result = compute_retrieval_recall(sample_emails, poor_summaries, n_samples=3)
        # With empty summaries, recall should be 0 or very low
        assert result["recall@k"] <= 0.5

    def test_empty_input_returns_zero(self):
        """Empty email/summary lists return 0.0 recall."""
        result = compute_retrieval_recall([], [], n_samples=10)
        assert result["recall@k"] == 0.0
        assert result["samples_analyzed"] == 0

    def test_fewer_summaries_than_emails(self):
        """Handles case where fewer summaries than emails."""
        emails = [
            {"id": "1", "body": "Hello world meeting Tuesday", "subject": "Test"},
            {"id": "2", "body": "Another email body here", "subject": "Test2"},
            {"id": "3", "body": "Third email", "subject": "Test3"},
        ]
        summaries = [
            {"sender": "a", "date": "", "subject": "", "key_entities": ["meeting", "Tuesday"], "action_items": [], "sentiment": "neutral"},
        ]
        result = compute_retrieval_recall(emails, summaries, n_samples=10)
        assert result["samples_analyzed"] == 1  # capped at len(summaries)

    def test_action_items_count_as_preservation(self):
        """Emails with action items in summary count as entailed."""
        emails = [
            {"id": "1", "body": "Please review the document by Friday and send feedback.", "subject": "Review needed"},
        ]
        summaries = [
            {"sender": "test@example.com", "date": "", "subject": "Review needed", "key_entities": [], "action_items": ["review document by Friday"], "sentiment": "neutral"},
        ]
        result = compute_retrieval_recall(emails, summaries, n_samples=1)
        assert result["recall@k"] > 0.0

    def test_entity_preservation_detection(self):
        """Entity preservation: summary entities found in original body."""
        emails = [
            {
                "id": "1",
                "body": "The meeting with Sarah on May 15th at 2pm requires Q2 budget approval of $50,000.",
                "subject": "Meeting",
            },
        ]
        summaries = [
            {
                "sender": "test@example.com",
                "date": "",
                "subject": "Meeting",
                "key_entities": ["Sarah", "May 15th", "$50,000"],
                "action_items": [],
                "sentiment": "neutral",
            },
        ]
        result = compute_retrieval_recall(emails, summaries, n_samples=1)
        assert result["recall@k"] > 0.0, f"Expected entity preservation detected, got recall={result['recall@k']}"

    def test_html_body_handled(self):
        """HTML in body doesn't break entity extraction."""
        emails = [
            {
                "id": "1",
                "body": "<html><body><p>Please review the <b>Q3 budget</b> by Friday. Contact <i>Sarah</i>.</p></body></html>",
                "subject": "Budget",
            },
        ]
        summaries = [
            {"sender": "a", "date": "", "subject": "Budget", "key_entities": ["Q3 budget", "Sarah"], "action_items": [], "sentiment": "neutral"},
        ]
        result = compute_retrieval_recall(emails, summaries, n_samples=1)
        assert 0.0 <= result["recall@k"] <= 1.0

    def test_unicode_body_handled(self):
        """Unicode characters in body don't break extraction."""
        emails = [
            {
                "id": "1",
                "body": "The café meeting is at noon. Bring your résumé.",
                "subject": "Café",
            },
        ]
        summaries = [
            {"sender": "a", "date": "", "subject": "Café", "key_entities": ["café", "noon"], "action_items": [], "sentiment": "neutral"},
        ]
        result = compute_retrieval_recall(emails, summaries, n_samples=1)
        assert 0.0 <= result["recall@k"] <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
