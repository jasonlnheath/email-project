"""Tests for compression module."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compression import CompressionOptimizer


def test_import_compression_module():
    """compression module can be imported without errors."""
    from compression import CompressionOptimizer  # noqa: F401
    assert CompressionOptimizer is not None


def test_compression_optimizer_init_default():
    """CompressionOptimizer initializes with default max_tokens."""
    opt = CompressionOptimizer()
    assert opt.max_tokens == 64000


def test_compression_optimizer_custom_budget():
    """CompressionOptimizer accepts custom max_tokens."""
    opt = CompressionOptimizer(max_tokens=32000)
    assert opt.max_tokens == 32000


def test_token_count():
    """_token_count returns rough token estimate from char count."""
    text = "Hello world this is a test"  # 26 chars
    tokens = CompressionOptimizer._token_count(text)
    assert tokens > 0
    assert isinstance(tokens, int)


def test_token_count_empty():
    """_token_count returns 1 for empty string (min 1)."""
    tokens = CompressionOptimizer._token_count("")
    assert tokens == 1


def test_estimate_tier1_tokens():
    """estimate_tier1_tokens calculates raw email tokens correctly."""
    emails = [
        {"content": "This is the first email body."},
        {"content": "This is the second email body with more text."},
    ]
    opt = CompressionOptimizer()
    tokens = opt.estimate_tier1_tokens(emails)
    assert tokens > 0
    assert isinstance(tokens, int)


def test_estimate_tier2_tokens():
    """estimate_tier2_tokens calculates summarized email tokens correctly."""
    summaries = [
        {"summary": "Brief summary of email 1."},
        {"summary": "Brief summary of email 2."},
    ]
    opt = CompressionOptimizer()
    tokens = opt.estimate_tier2_tokens(summaries, compression_ratio=10.0)
    assert tokens >= 0
    assert isinstance(tokens, int)


def test_estimate_tier3_tokens():
    """estimate_tier3_tokens calculates aggregated email tokens correctly."""
    clusters = [
        {"summary": "Cluster summary 1."},
        {"summary": "Cluster summary 2."},
    ]
    opt = CompressionOptimizer()
    tokens = opt.estimate_tier3_tokens(clusters, compression_ratio=100.0)
    assert tokens >= 0
    assert isinstance(tokens, int)


def test_estimate_total_context():
    """estimate_total_context sums all tier tokens plus overhead."""
    tier1 = [{"content": "Email body text here."}]
    tier2 = [{"summary": "Summary text."}]
    tier3 = [{"summary": "Aggregated summary."}]
    opt = CompressionOptimizer()
    total = opt.estimate_total_context(tier1, tier2, tier3)
    assert total > 0
    assert isinstance(total, int)


def test_allocate_context_budget():
    """allocate_context_budget distributes tokens across tiers."""
    opt = CompressionOptimizer()
    result = opt.allocate_context_budget(64000, priorities=[1, 2, 3])
    assert isinstance(result, dict)
    assert 1 in result
    assert 2 in result
    assert 3 in result


def test_allocate_context_budget_empty():
    """allocate_context_budget returns empty dict when no priorities."""
    opt = CompressionOptimizer()
    result = opt.allocate_context_budget(64000, priorities=[])
    assert result == {}


def test_tier_balance_score_perfect():
    """tier_balance_score returns 1.0 for perfectly balanced allocation."""
    opt = CompressionOptimizer()
    score = opt.tier_balance_score({1: 1000, 2: 1000, 3: 1000})
    assert score > 0.9


def test_tier_balance_score_skewed():
    """tier_balance_score returns lower score for skewed allocation."""
    opt = CompressionOptimizer()
    balanced = opt.tier_balance_score({1: 1000, 2: 1000, 3: 1000})
    skewed = opt.tier_balance_score({1: 5000, 2: 100, 3: 100})
    assert balanced > skewed


def test_tier_balance_score_empty():
    """tier_balance_score returns 0.0 for empty input."""
    opt = CompressionOptimizer()
    score = opt.tier_balance_score({})
    assert score == 0.0


def test_generate_tuning_report():
    """generate_tuning_report returns a formatted string."""
    opt = CompressionOptimizer()
    result = {
        "tier1_compression": 1,
        "tier2_compression": 10,
        "tier3_compression": 50,
        "total_tokens": 50000,
        "balance_score": 0.8,
        "quality_score": 0.7,
        "allocation": {1: 10000, 2: 25000, 3: 15000},
    }
    report = opt.generate_tuning_report(result)
    assert isinstance(report, str)
    assert "Compression Tuning Report" in report


def test_extract_claims():
    """extract_claims splits text into sentences."""
    text = "First sentence. Second sentence! Third sentence?"
    claims = CompressionOptimizer.extract_claims(text)
    assert len(claims) == 3
    assert "First sentence" in claims[0]


def test_extract_claims_empty():
    """extract_claims handles empty input."""
    claims = CompressionOptimizer.extract_claims("")
    assert claims == []


def test_compression_ratio():
    """compression_ratio calculates original/summary length ratio."""
    original = "This is a long original text with many words."
    summary = "Short summary."
    ratio = CompressionOptimizer.compression_ratio(original, summary)
    assert ratio > 1.0


def test_compression_ratio_empty_summary():
    """compression_ratio returns inf for empty summary."""
    ratio = CompressionOptimizer.compression_ratio("original", "")
    assert ratio == float("inf")


def test_extract_entities_basic():
    """extract_entities finds basic entity types."""
    text = "Meeting with Sarah on May 15th at $5,000 budget. Visit https://example.com"
    entities = CompressionOptimizer.extract_entities(text)
    assert isinstance(entities, dict)
    assert "names" in entities
    assert "amounts" in entities
    assert "dates" in entities
    assert "urls" in entities


def test_entity_preservation_rate():
    """entity_preservation_rate calculates overlap between entity sets."""
    original = {"names": ["Sarah", "Bob"], "amounts": ["$5,000"]}
    summary = {"names": ["Sarah"], "amounts": []}
    rate = CompressionOptimizer.entity_preservation_rate(original, summary)
    assert 0.0 <= rate <= 1.0
    # Sarah is preserved, Bob is not -> 1/3 names + 0/1 amounts = ~0.25


def test_entity_preservation_rate_perfect():
    """entity_preservation_rate returns 1.0 when all entities match."""
    entities = {"names": ["Sarah"], "amounts": ["$5,000"]}
    rate = CompressionOptimizer.entity_preservation_rate(entities, entities)
    assert rate == 1.0


def test_cosine_similarity_identical():
    """cosine_similarity returns 1.0 for identical vectors."""
    vec = [1.0, 2.0, 3.0]
    sim = CompressionOptimizer.cosine_similarity(vec, vec)
    assert sim == 1.0


def test_cosine_similarity_orthogonal():
    """cosine_similarity returns 0.0 for orthogonal vectors."""
    vec_a = [1.0, 0.0]
    vec_b = [0.0, 1.0]
    sim = CompressionOptimizer.cosine_similarity(vec_a, vec_b)
    assert sim == 0.0


def test_semantic_similarity_text():
    """semantic_similarity_text returns a value between 0 and 1."""
    sim = CompressionOptimizer.semantic_similarity_text("hello world", "hello world")
    assert 0.0 <= sim <= 1.0
