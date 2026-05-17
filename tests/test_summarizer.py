"""Tests for summarization engine — follows TDD (tests written before implementation)."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Test 1: Module importability ────────────────────────────────────────────

def test_import_summarizer():
    """summarizer module can be imported without errors."""
    from summarizer import Summarizer  # noqa: F401
    assert Summarizer is not None


# ── Test 2: Prompt format ──────────────────────────────────────────────────

def test_summarizer_prompt_format():
    """build_prompt generates a prompt with FROM/SUBJECT/DATE/BODY sections and JSON instructions."""
    from summarizer import Summarizer

    summarizer = Summarizer()
    email = {
        "sender": "Alice <alice@example.com>",
        "subject": "Meeting Tomorrow",
        "date": "Mon, 12 May 2026 10:00:00 +0000",
        "body": "Let's meet at 3pm to discuss the Q2 budget.",
    }

    prompt = summarizer.build_prompt(email)

    assert "FROM:" in prompt
    assert "SUBJECT:" in prompt
    assert "DATE:" in prompt
    assert "BODY:" in prompt
    assert "Alice <alice@example.com>" in prompt
    assert "Meeting Tomorrow" in prompt
    assert "Let's meet at 3pm" in prompt
    # Must contain JSON output instructions
    assert "JSON" in prompt.upper() or "json" in prompt
    # Must mention key_entities, action_items, sentiment
    assert "key_entities" in prompt
    assert "action_items" in prompt
    assert "sentiment" in prompt


def test_summarizer_prompt_default_values():
    """build_prompt uses sensible defaults for missing email fields."""
    from summarizer import Summarizer

    summarizer = Summarizer()
    email = {}  # No fields at all

    prompt = summarizer.build_prompt(email)

    assert "Unknown" in prompt
    assert "(no subject)" in prompt


# ── Test 3: Structured output ──────────────────────────────────────────────

def test_summarizer_structured_output(monkeypatch):
    """summarize returns a dict with sender, date, subject, key_entities, action_items, sentiment."""
    from summarizer import Summarizer

    summarizer = Summarizer()
    email = {
        "sender": "Alice <alice@example.com>",
        "subject": "Project Update",
        "date": "Mon, 12 May 2026 10:00:00 +0000",
        "body": "Please review the attached report by Friday.",
    }

    # Mock the LLM call to return a deterministic JSON response
    mock_response = json.dumps({
        "sender": "Alice <alice@example.com>",
        "date": "Mon, 12 May 2026 10:00:00 +0000",
        "subject": "Project Update",
        "key_entities": ["Q2 budget", "report", "Friday"],
        "action_items": ["Review attached report by Friday"],
        "sentiment": "neutral",
    })

    def fake_call(prompt, timeout=3):
        return mock_response

    monkeypatch.setattr(summarizer, "_call_llama_cpp", fake_call)

    result = summarizer.summarize(email)

    assert isinstance(result, dict)
    assert "sender" in result
    assert "date" in result
    assert "subject" in result
    assert "key_entities" in result
    assert "action_items" in result
    assert "sentiment" in result
    assert isinstance(result["key_entities"], list)
    assert isinstance(result["action_items"], list)
    assert result["sentiment"] in ("positive", "negative", "neutral")


def test_summarizer_structured_output_missing_fields(monkeypatch):
    """summarize fills in missing fields from the email when LLM response omits them."""
    from summarizer import Summarizer

    summarizer = Summarizer()
    email = {
        "sender": "Bob <bob@example.com>",
        "subject": "Quick Question",
        "date": "Tue, 13 May 2026 14:00:00 +0000",
        "body": "Can you send me the files?",
    }

    # LLM returns partial JSON (missing action_items and sentiment)
    mock_response = json.dumps({
        "sender": "Bob <bob@example.com>",
        "subject": "Quick Question",
        "key_entities": ["files"],
    })

    def fake_call(prompt, timeout=3):
        return mock_response

    monkeypatch.setattr(summarizer, "_call_llama_cpp", fake_call)

    result = summarizer.summarize(email)

    assert result["action_items"] == []
    assert result["sentiment"] == "neutral"


# ── Test 4: Batch processing ───────────────────────────────────────────────

def test_summarizer_batch_processing(monkeypatch):
    """summarize_batch processes multiple emails and returns a list of summaries."""
    from summarizer import Summarizer

    summarizer = Summarizer()
    emails = [
        {
            "sender": "Alice <alice@example.com>",
            "subject": "Email 1",
            "date": "Mon, 12 May 2026 10:00:00 +0000",
            "body": "First email body.",
        },
        {
            "sender": "Bob <bob@example.com>",
            "subject": "Email 2",
            "date": "Tue, 13 May 2026 14:00:00 +0000",
            "body": "Second email body.",
        },
        {
            "sender": "Charlie <charlie@example.com>",
            "subject": "Email 3",
            "date": "Wed, 14 May 2026 09:00:00 +0000",
            "body": "Third email body.",
        },
    ]

    call_count = [0]

    def fake_call(prompt, timeout=3):
        call_count[0] += 1
        return json.dumps({
            "sender": "Unknown",
            "date": "Unknown",
            "subject": f"Summary for call {call_count[0]}",
            "key_entities": [],
            "action_items": [],
            "sentiment": "neutral",
        })

    monkeypatch.setattr(summarizer, "_call_llama_cpp", fake_call)

    results = summarizer.summarize_batch(emails)

    assert isinstance(results, list)
    assert len(results) == 3
    assert call_count[0] == 3  # One LLM call per email


def test_summarizer_batch_empty():
    """summarize_batch returns empty list for empty input."""
    from summarizer import Summarizer

    summarizer = Summarizer()
    results = summarizer.summarize_batch([])
    assert results == []
    assert isinstance(results, list)


# ── Test 5: Empty content handling ─────────────────────────────────────────

def test_summarizer_empty_content_handling(monkeypatch):
    """summarize handles emails with no body gracefully (fallback to defaults)."""
    from summarizer import Summarizer

    summarizer = Summarizer()
    email = {
        "sender": "Alice <alice@example.com>",
        "subject": "Empty Email",
        "date": "Mon, 12 May 2026 10:00:00 +0000",
        "body": "",
    }

    # Simulate LLM failure (e.g., empty body causes error)
    def fake_call(prompt, timeout=3):
        raise ConnectionError("LLM service unavailable")

    monkeypatch.setattr(summarizer, "_call_llama_cpp", fake_call)

    result = summarizer.summarize(email)

    assert isinstance(result, dict)
    assert result["sender"] == "Alice <alice@example.com>"
    assert result["subject"] == "Empty Email"
    assert result["key_entities"] == []
    assert result["action_items"] == []
    assert result["sentiment"] == "neutral"


def test_summarizer_llm_failure_fallback():
    """summarize returns default summary when LLM call raises an exception."""
    from summarizer import Summarizer

    summarizer = Summarizer()
    email = {
        "sender": "Dave <dave@example.com>",
        "subject": "Test",
        "date": "Thu, 15 May 2026 12:00:00 +0000",
        "body": "Some content.",
    }

    # Mock _call_llama_cpp to raise an exception
    def fake_call(prompt, timeout=3):
        raise ConnectionError("Connection refused")

    import unittest.mock
    with unittest.mock.patch.object(summarizer, "_call_llama_cpp", fake_call):
        result = summarizer.summarize(email)

    assert result["sender"] == "Dave <dave@example.com>"
    assert result["subject"] == "Test"
    assert result["key_entities"] == []
    assert result["action_items"] == []
    assert result["sentiment"] == "neutral"


# ── Test 6: Long email truncation ──────────────────────────────────────────

def test_summarizer_long_email_truncation():
    """_truncate cuts very long bodies to max_body_length with beginning and end context."""
    from summarizer import Summarizer

    summarizer = Summarizer(max_body_length=100)
    long_body = "A" * 500  # 500 chars, well over the 100 char limit

    truncated = summarizer._truncate(long_body)

    assert len(truncated) <= 100
    assert "[truncated]" in truncated
    # Should contain beginning and end
    assert truncated.startswith("AAA")
    assert truncated.endswith("AAA")


def test_summarizer_short_email_no_truncation():
    """_truncate returns body unchanged when under max_body_length."""
    from summarizer import Summarizer

    summarizer = Summarizer(max_body_length=100)
    short_body = "Short email body"

    result = summarizer._truncate(short_body)
    assert result == short_body


def test_summarizer_default_max_body_length():
    """Summarizer uses DEFAULT_MAX_BODY_LENGTH (3000) as default."""
    from summarizer import Summarizer, DEFAULT_MAX_BODY_LENGTH

    summarizer = Summarizer()
    assert summarizer.max_body_length == DEFAULT_MAX_BODY_LENGTH
    assert DEFAULT_MAX_BODY_LENGTH == 3000


# ── Test: Prompt includes truncated content ────────────────────────────────

def test_summarizer_prompt_includes_truncation_marker(monkeypatch):
    """build_prompt truncates long bodies and includes [truncated] marker in prompt."""
    from summarizer import Summarizer

    summarizer = Summarizer(max_body_length=50)
    long_body = "X" * 1000

    email = {
        "sender": "Test",
        "subject": "Long Email",
        "date": "Mon, 12 May 2026 10:00:00 +0000",
        "body": long_body,
    }

    prompt = summarizer.build_prompt(email)

    assert "[truncated]" in prompt
    # The body portion should be truncated (not 1000 chars of X)
    body_section = prompt.split("BODY:")[1].split("\n\n")[0] if "BODY:" in prompt else ""
    assert len(body_section) <= 50


# ── Test: Summarizer configuration ─────────────────────────────────────────

def test_summarizer_custom_config():
    """Summarizer accepts custom max_body_length, base_url, and model."""
    from summarizer import Summarizer

    s = Summarizer(
        max_body_length=2000,
        base_url="http://localhost:9999",
        model="custom-model",
    )
    assert s.max_body_length == 2000
    assert s.base_url == "http://localhost:9999"
    assert s.model == "custom-model"


def test_summarizer_base_url_strips_trailing_slash():
    """Summarizer strips trailing slash from base_url."""
    from summarizer import Summarizer

    s = Summarizer(base_url="http://localhost:8033/")
    assert s.base_url == "http://localhost:8033"
