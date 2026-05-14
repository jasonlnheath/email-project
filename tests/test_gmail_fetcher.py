"""Tests for Gmail fetcher module — follows strict TDD (tests written before implementation)."""
from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Test 1: Module importability ────────────────────────────────────────────

def test_import_gmail_fetcher():
    """gmail_fetcher module can be imported without errors."""
    from gmail_fetcher import GmailFetcher  # noqa: F401
    assert GmailFetcher is not None


# ── Test 2: OAuth authentication via token file ────────────────────────────

def test_fetcher_auth_via_google_workspace(monkeypatch):
    """GmailFetcher loads OAuth credentials from a token JSON file."""
    fake_token = {
        "access_token": "fake-oauth-token-123",
        "refresh_token": "rt_abc123",
        "client_id": "test-client-id",
        "client_secret": "test-secret",
    }

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(fake_token, f)
        token_path = f.name

    try:
        from gmail_fetcher import GmailFetcher

        fetcher = GmailFetcher(token_path=token_path)
        token = fetcher._refresh_token()

        assert token == "fake-oauth-token-123"
    finally:
        os.unlink(token_path)


def test_fetcher_missing_token_file():
    """GmailFetcher raises FileNotFoundError when token file does not exist."""
    from gmail_fetcher import GmailFetcher

    fetcher = GmailFetcher(token_path="/nonexistent/path/token.json")
    try:
        fetcher._refresh_token()
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass  # Expected


# ── Test 3: Result limiting ────────────────────────────────────────────────

def test_fetcher_limits_results(monkeypatch):
    """GmailFetcher respects max_results parameter and caps at API maximum (500)."""
    from gmail_fetcher import GmailFetcher, GMAIL_API_MAX_RESULTS

    # Test default cap — exceeding 500 should be capped
    fetcher = GmailFetcher(max_results=1000)
    assert fetcher.max_results == GMAIL_API_MAX_RESULTS

    # Test normal limit — under 500 should be preserved
    fetcher2 = GmailFetcher(max_results=25)
    assert fetcher2.max_results == 25


# ── Test 4: Email field parsing ────────────────────────────────────────────

def test_fetcher_parses_email_fields():
    """parse_email extracts id, subject, sender, date, body, snippet from raw message."""
    from gmail_fetcher import GmailFetcher

    plain_text = "Hello, this is the email body content."
    encoded_body = base64.urlsafe_b64encode(plain_text.encode()).decode()

    raw_message = {
        "id": "msg-12345",
        "snippet": "Hello, this is the ema\u2026",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test Subject Line"},
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "Date", "value": "Mon, 12 May 2026 10:30:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {
                "data": encoded_body,
                "size": len(plain_text),
            },
        },
    }

    result = GmailFetcher.parse_email(raw_message)

    assert result["id"] == "msg-12345"
    assert result["subject"] == "Test Subject Line"
    assert result["sender"] == "Alice <alice@example.com>"
    assert "Mon, 12 May 2026" in result["date"]
    assert result["body"] == plain_text
    assert result["snippet"] == "Hello, this is the ema\u2026"


def test_fetcher_parses_multipart_email():
    """parse_email extracts text/plain body from multipart MIME messages."""
    from gmail_fetcher import GmailFetcher

    plain_body = "This is a multipart email with text/plain part."
    encoded = base64.urlsafe_b64encode(plain_body.encode()).decode()

    raw_message = {
        "id": "msg-67890",
        "snippet": "This is a multipart\u2026",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Multipart Test"},
                {"name": "From", "value": "Bob <bob@example.com>"},
                {"name": "Date", "value": "Tue, 13 May 2026 14:00:00 +0000"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": "<p>HTML body</p>", "size": 15},
                },
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded, "size": len(plain_body)},
                },
            ],
        },
    }

    result = GmailFetcher.parse_email(raw_message)
    assert result["body"] == plain_body
    assert result["subject"] == "Multipart Test"


def test_fetcher_parses_html_body():
    """parse_email strips HTML tags when only text/html is available."""
    from gmail_fetcher import GmailFetcher

    html_text = "<p>Hello <b>world</b></p>"
    encoded = base64.urlsafe_b64encode(html_text.encode()).decode()

    raw_message = {
        "id": "msg-html",
        "snippet": "Hello world\u2026",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "HTML Only"},
                {"name": "From", "value": "Charlie <charlie@example.com>"},
                {"name": "Date", "value": "Wed, 14 May 2026 09:00:00 +0000"},
            ],
            "mimeType": "text/html",
            "body": {"data": encoded, "size": len(html_text)},
        },
    }

    result = GmailFetcher.parse_email(raw_message)
    assert "<" not in result["body"]
    assert "Hello world" in result["body"]


def test_fetcher_parses_missing_headers():
    """parse_email handles missing headers gracefully with defaults."""
    from gmail_fetcher import GmailFetcher

    raw_message = {
        "id": "msg-no-headers",
        "snippet": "",
        "payload": {
            "headers": [],
            "body": {},
        },
    }

    result = GmailFetcher.parse_email(raw_message)
    assert result["subject"] == "(no subject)"
    assert result["sender"] == "(unknown sender)"
    assert result["body"] == ""


def test_fetcher_parses_attachments():
    """parse_email extracts attachment metadata from payload parts."""
    from gmail_fetcher import GmailFetcher

    encoded = base64.urlsafe_b64encode(b"").decode()

    raw_message = {
        "id": "msg-attach",
        "snippet": "",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "With Attachment"},
                {"name": "From", "value": "Dave <dave@example.com>"},
                {"name": "Date", "value": "Thu, 15 May 2026 12:00:00 +0000"},
            ],
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded, "size": 0},
                },
                {
                    "filename": "report.pdf",
                    "mimeType": "application/pdf",
                    "body": {"size": 102400},
                },
            ],
        },
    }

    result = GmailFetcher.parse_email(raw_message)
    assert len(result["attachments"]) == 1
    assert result["attachments"][0]["filename"] == "report.pdf"
    assert result["attachments"][0]["type"] == "application/pdf"
    assert result["attachments"][0]["size_bytes"] == 102400


# ── Test 5: Date range filtering ───────────────────────────────────────────

def test_fetcher_date_range_filtering():
    """filter_by_date correctly filters emails by after/before date boundaries."""
    from gmail_fetcher import GmailFetcher

    fetcher = GmailFetcher()

    messages = [
        {"date": "Mon, 01 May 2026 10:00:00 +0000", "id": "early"},
        {"date": "Wed, 13 May 2026 10:00:00 +0000", "id": "middle"},
        {"date": "Fri, 29 May 2026 10:00:00 +0000", "id": "late"},
    ]

    # Filter: after May 10
    filtered = fetcher.filter_by_date(messages, after="2026-05-10")
    ids = [m["id"] for m in filtered]
    assert "early" not in ids
    assert "middle" in ids
    assert "late" in ids

    # Filter: before May 20
    filtered2 = fetcher.filter_by_date(messages, before="2026-05-20")
    ids2 = [m["id"] for m in filtered2]
    assert "early" in ids2
    assert "middle" in ids2
    assert "late" not in ids2

    # Filter: between May 10 and May 20
    filtered3 = fetcher.filter_by_date(messages, after="2026-05-10", before="2026-05-20")
    ids3 = [m["id"] for m in filtered3]
    assert ids3 == ["middle"]


def test_fetcher_date_parsing_formats():
    """_parse_date handles multiple date formats (RFC 2822, ISO 8601, date-only)."""
    from gmail_fetcher import GmailFetcher

    # RFC 2822
    dt = GmailFetcher._parse_date("Mon, 12 May 2026 10:30:00 +0000")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 5
    assert dt.day == 12

    # ISO 8601 UTC
    dt2 = GmailFetcher._parse_date("2026-05-12T10:30:00Z")
    assert dt2 is not None
    assert dt2.year == 2026

    # Date only
    dt3 = GmailFetcher._parse_date("2026-05-12")
    assert dt3 is not None
    assert dt3.year == 2026

    # Empty string
    assert GmailFetcher._parse_date("") is None


# ── Test 6: Empty inbox handling ───────────────────────────────────────────

def test_fetcher_handles_empty_inbox():
    """GmailFetcher returns empty list when no messages are found."""
    from gmail_fetcher import GmailFetcher

    fetcher = GmailFetcher()

    # _parse_messages with empty list
    result = fetcher._parse_messages([])
    assert result == []
    assert isinstance(result, list)

    # parse_email with minimal message (no body data)
    minimal_message = {
        "id": "msg-empty",
        "snippet": "",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Empty"},
                {"name": "From", "value": "nobody@example.com"},
                {"name": "Date", "value": "Mon, 01 Jan 2026 00:00:00 +0000"},
            ],
            "body": {},
        },
    }
    result = GmailFetcher.parse_email(minimal_message)
    assert result["body"] == ""
    assert isinstance(result, dict)
