"""Unit tests for enrichment and normalizer services."""

from app.services.enrichment import (
    extract_sender_email, get_priority, is_newsletter_email,
    is_school_email, enrich_batch, build_vip_map,
)
from app.services.normalizer import normalize_name, normalize_email, normalize_contact


# ── Enrichment ──────────────────────────────────────────────

def test_extract_sender_email():
    email, name = extract_sender_email("John Doe <john@example.com>")
    assert email == "john@example.com"
    assert name == "John Doe"


def test_extract_sender_bare():
    email, name = extract_sender_email("noreply@github.com")
    assert email == "noreply@github.com"


def test_get_priority_vip():
    vip_map = {"alice@company.com": {"name": "Alice", "relationship_type": "colleague"}}
    tier, order, info = get_priority({"from": "Alice <alice@company.com>", "subject": "hi", "snippet": ""}, vip_map)
    assert tier == "VIP_HIGH"
    assert info is not None


def test_get_priority_high_keyword():
    tier, order, info = get_priority(
        {"from": "bank@bank.com", "subject": "Security Alert", "snippet": "urgent login"}, {}
    )
    assert tier == "HIGH"


def test_get_priority_medium():
    tier, order, info = get_priority(
        {"from": "someone@random.com", "subject": "hello", "snippet": "just checking in"}, {}
    )
    assert tier == "MEDIUM"


def test_get_priority_promo():
    tier, order, info = get_priority(
        {"from": "deals@shop.com", "subject": "SALE", "snippet": "unsubscribe here", "labels": ["CATEGORY_PROMOTIONS"]}, {}
    )
    assert tier == "LOW"


def test_is_newsletter():
    assert is_newsletter_email({"subject": "Weekly digest", "snippet": "", "labels": []})
    assert not is_newsletter_email({"subject": "Meeting tomorrow", "snippet": "", "labels": []})


def test_enrich_batch_sorts_by_tier():
    vip_map = {"vip@test.com": {"name": "VIP"}}
    emails = [
        {"from": "random@test.com", "subject": "hi", "snippet": ""},
        {"from": "vip@test.com", "subject": "important", "snippet": ""},
    ]
    result = enrich_batch(emails, vip_map)
    assert result[0]["tier"] == "VIP_HIGH"
    assert result[1]["tier"] == "MEDIUM"


# ── Normalizer ──────────────────────────────────────────────

def test_normalize_name_first_last():
    norm, first, last = normalize_name("John Doe")
    assert first == "John"
    assert last == "Doe"
    assert norm == "Doe, John"


def test_normalize_name_comma():
    norm, first, last = normalize_name("Doe, John")
    assert first == "John"
    assert last == "Doe"


def test_normalize_email():
    result = normalize_email("John@Gmail.COM")
    assert result["address"] == "john@gmail.com"
    assert result["type"] == "personal"


def test_normalize_contact_google():
    raw = {
        "displayName": "Jane Smith",
        "emailAddresses": [{"value": "jane@example.com"}],
        "id": "people/123",
    }
    result = normalize_contact(raw, source="google")
    assert result["first_name"] == "Jane"
    assert result["last_name"] == "Smith"
    assert len(result["emails"]) == 1
    assert result["source"] == "google"


def test_build_vip_map():
    vips = [{"contact_id": "c1", "relationship_type": "family"}]
    contacts = [{"id": "c1", "normalized_name": "Mom", "emails": '[{"address": "mom@test.com"}]'}]
    vip_map = build_vip_map(vips, contacts)
    assert "mom@test.com" in vip_map
    assert "vip_name_mom" in vip_map
