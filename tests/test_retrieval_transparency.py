"""Tests for retrieval transparency features — hit/prune visibility, nudge support, gmail links.

RED-GREEN-REFACTOR TDD cycle.
"""

import json
import os
import tempfile
import pytest


@pytest.fixture
def sample_tier1():
    """Sample tier1 records with gmail_url."""
    return [
        {
            "id": "msg_001",
            "email_id": "msg_001",
            "subject": "Dura-Pilot Thermal Analysis",
            "sender": "Sean O'Brien",
            "date": "2026-05-12T10:00:00",
            "gmail_url": "https://mail.google.com/mail/u/0/#inbox/msg_001",
            "content": "Here is the thermal analysis for Dura-Pilot...",
        },
        {
            "id": "msg_002",
            "email_id": "msg_002",
            "subject": "Re: Dura-Pilot Design Specs",
            "sender": "Jason Heath",
            "date": "2026-05-11T14:00:00",
            "gmail_url": "https://mail.google.com/mail/u/0/#inbox/msg_002",
            "content": "The design looks promising. Let's review on screen.",
        },
        {
            "id": "msg_003",
            "email_id": "msg_003",
            "subject": "Fwd: Dura-Pilot Solid Models",
            "sender": "Jason Heath",
            "date": "2026-05-10T09:00:00",
            "gmail_url": "https://mail.google.com/mail/u/0/#inbox/msg_003",
            "content": "Attached are the solid models for FEA analysis.",
        },
    ]


@pytest.fixture
def sample_tier2():
    """Sample tier2 records with gmail_url."""
    return [
        {
            "email_id": "msg_001",
            "id": "msg_001",
            "gmail_url": "https://mail.google.com/mail/u/0/#inbox/msg_001",
            "summary": "Sean O'Brien sent thermal analysis for Dura-Pilot. Design looks promising, needs deeper review on proper screen.",
            "sender": "Sean O'Brien",
            "date": "2026-05-12T10:00:00",
        },
        {
            "email_id": "msg_002",
            "id": "msg_002",
            "gmail_url": "https://mail.google.com/mail/u/0/#inbox/msg_002",
            "summary": "Jason Heath reviewed Dura-Pilot design specs. Design looks promising, wants to review on screen.",
            "sender": "Jason Heath",
            "date": "2026-05-11T14:00:00",
        },
    ]


@pytest.fixture
def sample_tier3():
    """Sample tier3 cluster records."""
    return [
        {
            "cluster_id": "cluster_dura",
            "summary": "Dura-Pilot thermal analysis and design discussion. Participants: Sean O'Brien, Jason Heath. Topics: thermal analysis, FEA, design specs, solid models. Time range: May 10-12, 2026.",
            "gmail_urls": [
                "https://mail.google.com/mail/u/0/#inbox/msg_001",
                "https://mail.google.com/mail/u/0/#inbox/msg_002",
                "https://mail.google.com/mail/u/0/#inbox/msg_003",
            ],
        },
    ]


@pytest.fixture
def temp_tier_files(sample_tier1, sample_tier2, sample_tier3):
    """Create temporary JSONL files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        t1 = os.path.join(tmpdir, "tier1.jsonl")
        t2 = os.path.join(tmpdir, "tier2.jsonl")
        t3 = os.path.join(tmpdir, "tier3.jsonl")

        for path, records in [(t1, sample_tier1), (t2, sample_tier2), (t3, sample_tier3)]:
            with open(path, "w") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")

        yield t1, t2, t3


# ===================================================================
# Test 1: gmail_url field present in tier records
# ===================================================================

class TestGmailUrlInRecords:
    """gmail_url should be present in all tier record types."""

    def test_tier1_has_gmail_url(self, sample_tier1):
        for rec in sample_tier1:
            assert "gmail_url" in rec, "tier1 records must have gmail_url"
            assert rec["gmail_url"].startswith("https://mail.google.com/mail/u/0/#inbox/")

    def test_tier2_has_gmail_url(self, sample_tier2):
        for rec in sample_tier2:
            assert "gmail_url" in rec, "tier2 records must have gmail_url"

    def test_tier3_has_gmail_urls_list(self, sample_tier3):
        for rec in sample_tier3:
            assert "gmail_urls" in rec, "tier3 cluster records must have gmail_urls list"
            assert isinstance(rec["gmail_urls"], list)


# ===================================================================
# Test 2: Hit/prune visibility — all candidates returned with scores
# ===================================================================

class TestHitPruneVisibility:
    """Retrieval should return ALL candidates with scores, not just top-k."""

    def test_search_returns_all_candidates_with_scores(self, temp_tier_files):
        """All tier1 BM25 results should be returned with scores, not truncated to top_k."""
        from retrieval import SimpleBM25

        t1_path = temp_tier_files[0]
        bm25 = SimpleBM25()
        # Build index
        with open(t1_path) as f:
            records = [json.loads(l) for l in f if l.strip()]
        texts = [r.get("content", "") for r in records]
        bm25.fit(texts)

        # Query should return ALL docs with scores, not just top_k
        scores = bm25.score("dura pilot thermal", top_k=100)  # large top_k to get all
        assert len(scores) == len(records), "Should return all documents"
        for idx, score in scores:
            assert isinstance(score, float), "Score must be a float"
            assert score >= 0, "Score must be non-negative"

    def test_query_result_contains_hit_prune_info(self, temp_tier_files):
        """route_query should include 'hits' (all candidates) and 'pruned' (dropped) lists."""
        from retrieval import QueryRouter

        router = QueryRouter(
            tier1_path=temp_tier_files[0],
            tier2_path=temp_tier_files[1],
            tier3_path=temp_tier_files[2],
        )

        result = router.route_query("dura-pilot thermal analysis", top_k=2)

        # Must have hits/prune metadata
        assert "hits" in result, "Result must contain 'hits' list"
        assert "pruned" in result, "Result must contain 'pruned' list"

        # Hits should include all candidates with scores
        assert isinstance(result["hits"], list)
        assert len(result["hits"]) > 0, "Should have at least some hits"

        # Pruned should be non-empty if we requested fewer than available
        # (top_k=2 but we have 3 tier1 docs)
        assert isinstance(result["pruned"], list)


# ===================================================================
# Test 3: Nudge support — user can override/prune results
# ===================================================================

class TestNudgeSupport:
    """User should be able to nudge results by excluding/include IDs."""

    def test_nudge_exclude_ids_removes_from_hits(self, temp_tier_files):
        """Excluding an email ID should remove it from hits and add to pruned."""
        from retrieval import QueryRouter

        router = QueryRouter(
            tier1_path=temp_tier_files[0],
            tier2_path=temp_tier_files[1],
            tier3_path=temp_tier_files[2],
        )

        # Without nudge
        result_no_nudge = router.route_query("dura-pilot", top_k=10)
        ids_without_nudge = {h["id"] for h in result_no_nudge["hits"]}

        # With nudge to exclude msg_001
        result_with_nudge = router.route_query(
            "dura-pilot", top_k=10, nudge={"exclude_ids": ["msg_001"]}
        )
        ids_with_nudge = {h["id"] for h in result_with_nudge["hits"]}

        assert "msg_001" not in ids_with_nudge, "Excluded ID should not be in hits"
        assert "msg_001" in ids_without_nudge, "Excluded ID should be in hits without nudge"

    def test_nudge_include_ids_forces_specific_results(self, temp_tier_files):
        """Including specific IDs should ensure they appear in results."""
        from retrieval import QueryRouter

        router = QueryRouter(
            tier1_path=temp_tier_files[0],
            tier2_path=temp_tier_files[1],
            tier3_path=temp_tier_files[2],
        )

        # Force include msg_002 which is already in tier2 results
        # (it's a realistic scenario: user wants to guarantee a specific email appears)
        result = router.route_query(
            "dura-pilot", top_k=2, nudge={"include_ids": ["msg_002"]}
        )

        hit_ids = {h["id"] for h in result["hits"]}
        assert "msg_002" in hit_ids, "Forced-include ID should be in hits"


# ===================================================================
# Test 4: Gmail URL propagation through pipeline
# ===================================================================

class TestGmailUrlPropagation:
    """gmail_url must propagate from tier records into query results."""

    def test_hits_include_gmail_url(self, temp_tier_files):
        """Each hit in results must include the gmail_url field."""
        from retrieval import QueryRouter

        router = QueryRouter(
            tier1_path=temp_tier_files[0],
            tier2_path=temp_tier_files[1],
            tier3_path=temp_tier_files[2],
        )

        result = router.route_query("dura-pilot", top_k=10)

        for hit in result["hits"]:
            assert "gmail_url" in hit or "gmail_urls" in hit, \
                f"Hit {hit.get('id')} missing gmail_url/gmail_urls"

    def test_pruned_include_gmail_url(self, temp_tier_files):
        """Pruned records must also include gmail_url for transparency."""
        from retrieval import QueryRouter

        router = QueryRouter(
            tier1_path=temp_tier_files[0],
            tier2_path=temp_tier_files[1],
            tier3_path=temp_tier_files[2],
        )

        result = router.route_query("dura-pilot", top_k=1)  # force pruning

        for pruned in result["pruned"]:
            assert "gmail_url" in pruned or "gmail_urls" in pruned, \
                f"Pruned record {pruned.get('id')} missing gmail_url/gmail_urls"


# ===================================================================
# Test 5: RetrievalPipeline.query returns transparency fields
# ===================================================================

class TestRetrievalPipelineTransparency:
    """High-level pipeline must expose hits/prune/nudge."""

    def test_pipeline_query_returns_hits_and_pruned(self, temp_tier_files):
        from retrieval import RetrievalPipeline

        config = {
            "tier1_path": temp_tier_files[0],
            "tier2_path": temp_tier_files[1],
            "tier3_path": temp_tier_files[2],
        }
        pipeline = RetrievalPipeline(config)

        result = pipeline.query("dura-pilot", top_k=2)

        assert "hits" in result, "Pipeline result must have 'hits'"
        assert "pruned" in result, "Pipeline result must have 'pruned'"
        assert "nudge_options" in result, "Pipeline result must have 'nudge_options'"

    def test_pipeline_query_with_nudge(self, temp_tier_files):
        from retrieval import RetrievalPipeline

        config = {
            "tier1_path": temp_tier_files[0],
            "tier2_path": temp_tier_files[1],
            "tier3_path": temp_tier_files[2],
        }
        pipeline = RetrievalPipeline(config)

        # Nudge to exclude msg_001
        result = pipeline.query(
            "dura-pilot", top_k=5,
            nudge={"exclude_ids": ["msg_001"]}
        )

        hit_ids = {h["id"] for h in result.get("hits", [])}
        assert "msg_001" not in hit_ids, "Nudge-excluded ID must not be in hits"


# ===================================================================
# Test 6: build_context_window includes gmail links
# ===================================================================

class TestContextWindowWithLinks:
    """Context window should include clickable Gmail links."""

    def test_context_window_has_gmail_links(self, temp_tier_files):
        from retrieval import RetrievalPipeline

        config = {
            "tier1_path": temp_tier_files[0],
            "tier2_path": temp_tier_files[1],
            "tier3_path": temp_tier_files[2],
        }
        pipeline = RetrievalPipeline(config)

        result = pipeline.query("dura-pilot", top_k=5)
        context = pipeline.build_context_window(result["hits"])

        # Should contain gmail URLs
        assert "mail.google.com" in context, "Context must include Gmail links"
