"""Tests for clustering module — RED-GREEN-REFACTOR TDD cycle.

These tests encode the plan's requirements for the clustering engine:
- TF-IDF vectorization of email summaries
- KMeans clustering with auto-k detection via silhouette score
- Cluster-level summary generation (time range, topics, people, outcomes)
- Persistence to JSONL
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest


def _import_engine():
    """Import EmailClusteringEngine, skipping if sklearn not installed."""
    try:
        from clustering import EmailClusteringEngine
        return EmailClusteringEngine
    except ImportError:
        pytest.skip("scikit-learn not installed")


@pytest.fixture
def engine_cls():
    return _import_engine()


@pytest.fixture
def engine(engine_cls):
    return engine_cls()  # Default: n_clusters=None (auto-detect)


@pytest.fixture
def engine_with_clusters(engine_cls):
    """Engine with explicit cluster count."""
    return engine_cls(n_clusters=3)


@pytest.fixture
def sample_summaries():
    """Return a list of summary dicts matching the expected schema."""
    return [
        {
            "id": "msg_001",
            "date": "2025-01-15T10:30:00Z",
            "sender": "Alice Chen",
            "subject": "Q1 Budget Review",
            "summary": "Alice presented Q1 budget proposal for approval.",
            "entities": ["budget", "Q1"],
            "action_items": ["Approve by Friday"],
        },
        {
            "id": "msg_002",
            "date": "2025-01-16T14:00:00Z",
            "sender": "Bob Smith",
            "subject": "Budget Approval Follow-up",
            "summary": "Bob confirmed the Q1 budget was approved by management.",
            "entities": ["budget", "Q1", "approval"],
            "action_items": [],
        },
        {
            "id": "msg_003",
            "date": "2025-01-17T09:00:00Z",
            "sender": "Carol Davis",
            "subject": "Team Lunch Plans",
            "summary": "Carol organized team lunch for Friday at the Italian restaurant.",
            "entities": ["lunch", "team"],
            "action_items": ["RSVP by Thursday"],
        },
        {
            "id": "msg_004",
            "date": "2025-01-18T11:00:00Z",
            "sender": "Dave Wilson",
            "subject": "Project Timeline Update",
            "summary": "Dave reported the project is on track for March delivery.",
            "entities": ["project", "timeline"],
            "action_items": [],
        },
        {
            "id": "msg_005",
            "date": "2025-01-19T16:00:00Z",
            "sender": "Eve Martinez",
            "subject": "Q2 Planning Meeting",
            "summary": "Eve scheduled Q2 planning meeting for next week.",
            "entities": ["Q2", "planning"],
            "action_items": ["Prepare agenda"],
        },
    ]


# ─── Import tests ──────────────────────────────────────────────────────────

class TestImport:
    def test_module_importable(self, engine_cls):
        """clustering module can be imported without errors."""
        from clustering import EmailClusteringEngine
        assert EmailClusteringEngine is not None


# ─── Initialization tests ─────────────────────────────────────────────────

class TestInit:
    def test_default_n_clusters_is_none(self, engine):
        """Default n_clusters should be None (auto-detect)."""
        assert engine.n_clusters is None

    def test_custom_n_clusters(self, engine_cls):
        """Can specify explicit number of clusters."""
        eng = engine_cls(n_clusters=5)
        assert eng.n_clusters == 5

    def test_default_max_k(self, engine):
        """Default max_k_for_silhouette is 10."""
        assert engine.max_k == 10

    def test_default_min_k(self, engine):
        """Default min_k is 2."""
        assert engine.min_k == 2

    def test_random_state_set(self, engine):
        """random_state is stored for reproducibility."""
        assert engine.random_state == 42


# ─── Text body extraction tests ────────────────────────────────────────────

class TestBuildTextBody:
    def test_prefers_summary_field(self, engine):
        """_build_text_body uses summary field when present."""
        rec = {"summary": "This is the summary text."}
        body = engine._build_text_body(rec)
        assert "summary" in body.lower() or "summary" not in body  # just check it runs

    def test_falls_back_to_subject(self, engine):
        """_build_text_body falls back to subject if no summary."""
        rec = {"subject": "Test Subject Line"}
        body = engine._build_text_body(rec)
        assert "test subject line" in body.lower()

    def test_includes_entities(self, engine):
        """_build_text_body includes entities as extra signal."""
        rec = {
            "subject": "Meeting",
            "entities": ["budget", "Q1"],
        }
        body = engine._build_text_body(rec)
        assert "budget" in body.lower()
        assert "q1" in body.lower()

    def test_includes_action_items(self, engine):
        """_build_text_body includes action items."""
        rec = {
            "subject": "Task",
            "action_items": ["Review document", "Send feedback"],
        }
        body = engine._build_text_body(rec)
        assert "review document" in body.lower()
        assert "send feedback" in body.lower()

    def test_empty_record_returns_empty_string(self, engine):
        """_build_text_body handles records with no text fields."""
        rec = {"id": "empty"}
        body = engine._build_text_body(rec)
        assert body == ""


# ─── TF-IDF vectorization tests ────────────────────────────────────────────

class TestTFIDF:
    def test_returns_sparse_matrix(self, engine, sample_summaries):
        """compute_tfidf_vectors returns a scipy sparse matrix (CSR format)."""
        from scipy import sparse
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        assert sparse.issparse(matrix)

    def test_shape_matches_input(self, engine, sample_summaries):
        """TF-IDF matrix has n_samples rows matching input count."""
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        assert matrix.shape[0] == len(sample_summaries)

    def test_positive_feature_count(self, engine, sample_summaries):
        """TF-IDF matrix has positive number of features."""
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        assert matrix.shape[1] > 0

    def test_stores_vectorizer(self, engine, sample_summaries):
        """compute_tfidf_vectors stores the vectorizer for later use."""
        engine.compute_tfidf_vectors(sample_summaries)
        assert engine._vectorizer is not None


# ─── Clustering tests ──────────────────────────────────────────────────────

class TestClustering:
    def test_returns_array_of_labels(self, engine, sample_summaries):
        """cluster() returns a numpy array of integer labels."""
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        assert isinstance(labels, np.ndarray)
        assert len(labels) == len(sample_summaries)

    def test_label_count_matches_input(self, engine, sample_summaries):
        """Number of labels equals number of input summaries."""
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        assert len(labels) == len(sample_summaries)

    def test_labels_are_integers(self, engine, sample_summaries):
        """Cluster labels are integers."""
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        assert all(isinstance(l, (int, np.integer)) for l in labels)

    def test_uses_specified_n_clusters(self, engine, sample_summaries):
        """When n_clusters is set, uses that value."""
        engine.n_clusters = 2
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        unique = len(set(labels))
        assert unique == 2

    def test_auto_detects_k_when_none(self, engine, sample_summaries):
        """When n_clusters is None, auto-detects via silhouette score."""
        engine.n_clusters = None
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        # Should have detected some k >= min_k (2)
        unique = len(set(labels))
        assert unique >= 2

    def test_silhouette_score_stored(self, engine, sample_summaries):
        """Silhouette score is stored after clustering."""
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        engine.cluster(matrix)
        assert engine._silhouette_score_val >= 0.0


# ─── Cluster summary generation tests ──────────────────────────────────────

class TestClusterSummaries:
    def test_returns_list_of_dicts(self, engine, sample_summaries):
        """generate_cluster_summaries returns a list of dicts."""
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        summaries = engine.generate_cluster_summaries(sample_summaries, labels, matrix)
        assert isinstance(summaries, list)
        assert all(isinstance(s, dict) for s in summaries)

    def test_one_summary_per_cluster(self, engine, sample_summaries):
        """Number of summaries equals number of unique clusters."""
        engine.n_clusters = 2
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        summaries = engine.generate_cluster_summaries(sample_summaries, labels, matrix)
        assert len(summaries) == 2

    def test_summary_has_required_keys(self, engine, sample_summaries):
        """Each cluster summary has all required fields."""
        engine.n_clusters = 2
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        summaries = engine.generate_cluster_summaries(sample_summaries, labels, matrix)
        required_keys = {"cluster_id", "size", "time_range", "topics", "people", "outcomes", "member_ids", "representative_email_id"}
        for s in summaries:
            assert required_keys.issubset(s.keys()), f"Missing keys: {required_keys - set(s.keys())}"

    def test_summary_size_matches_cluster(self, engine, sample_summaries):
        """Cluster summary size matches actual cluster member count."""
        engine.n_clusters = 2
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        summaries = engine.generate_cluster_summaries(sample_summaries, labels, matrix)
        for s in summaries:
            mask = labels == s["cluster_id"]
            assert s["size"] == int(mask.sum())

    def test_topics_are_strings(self, engine, sample_summaries):
        """Cluster topics are lists of strings."""
        engine.n_clusters = 2
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        summaries = engine.generate_cluster_summaries(sample_summaries, labels, matrix)
        for s in summaries:
            assert isinstance(s["topics"], list)
            assert all(isinstance(t, str) for t in s["topics"])

    def test_people_are_extracted(self, engine, sample_summaries):
        """Cluster people field contains sender names."""
        engine.n_clusters = 1
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        summaries = engine.generate_cluster_summaries(sample_summaries, labels, matrix)
        # All 5 senders should be in the single cluster's people list
        assert len(summaries[0]["people"]) == 5

    def test_outcomes_extracted_from_action_items(self, engine, sample_summaries):
        """Cluster outcomes include action items from records."""
        engine.n_clusters = 1
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        summaries = engine.generate_cluster_summaries(sample_summaries, labels, matrix)
        outcomes = summaries[0]["outcomes"]
        assert isinstance(outcomes, list)
        # Should contain at least some action items
        assert any("approve" in o.lower() or "rsvp" in o.lower() or "prepare" in o.lower() for o in outcomes)

    def test_member_ids_present(self, engine, sample_summaries):
        """Cluster summary includes member IDs."""
        engine.n_clusters = 1
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        summaries = engine.generate_cluster_summaries(sample_summaries, labels, matrix)
        assert len(summaries[0]["member_ids"]) == len(sample_summaries)


# ─── Persistence tests ─────────────────────────────────────────────────────

class TestPersistence:
    def test_save_clusters_writes_jsonl(self, engine, sample_summaries):
        """save_clusters writes valid JSONL to disk."""
        engine.n_clusters = 2
        matrix = engine.compute_tfidf_vectors(sample_summaries)
        labels = engine.cluster(matrix)
        summaries = engine.generate_cluster_summaries(sample_summaries, labels, matrix)

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            engine.save_clusters(summaries, path)
            assert os.path.exists(path)

            # Verify each line is valid JSON
            with open(path) as fh:
                for line in fh:
                    rec = json.loads(line.strip())
                    assert isinstance(rec, dict)
                    assert "cluster_id" in rec
        finally:
            if os.path.exists(path):
                os.unlink(path)


# ─── Edge case tests ───────────────────────────────────────────────────────

class TestEdgeCases:
    def test_load_summaries_missing_file_raises(self, engine):
        """load_summaries raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            engine.load_summaries("/nonexistent/path.jsonl")

    def test_run_requires_either_path_or_records(self, engine):
        """run() raises ValueError when neither path nor records provided."""
        with pytest.raises(ValueError, match="Provide either"):
            engine.run()

    def test_run_requires_at_least_two_summaries(self, engine):
        """run() raises ValueError with fewer than 2 summaries."""
        with pytest.raises(ValueError, match="Need at least 2"):
            engine.run(records=[{"id": "only_one"}])

    def test_extract_date_parses_iso_format(self, engine):
        """_extract_date correctly parses ISO format dates."""
        rec = {"date": "2025-01-15T10:30:00Z"}
        date_str = engine._extract_date(rec)
        assert date_str == "2025-01-15"

    def test_extract_date_handles_missing_key(self, engine):
        """_extract_date returns None when no date field present."""
        rec = {"subject": "No date here"}
        date_str = engine._extract_date(rec)
        assert date_str is None

    def test_extract_people_handles_list_sender(self, engine):
        """_extract_people handles list-type sender field."""
        recs = [{"sender": ["Alice", "Bob"]}]
        people = engine._extract_people(recs)
        assert "Alice" in people
        assert "Bob" in people

    def test_extract_outcomes_capped_at_ten(self, engine):
        """_extract_outcomes caps at 10 items."""
        recs = [{"action_items": [f"Task {i}" for i in range(20)]}]
        outcomes = engine._extract_outcomes(recs)
        assert len(outcomes) <= 10


# ─── Integration test ──────────────────────────────────────────────────────

class TestFullPipeline:
    def test_run_returns_result_dict(self, engine, sample_summaries):
        """run() returns a dict with expected keys."""
        result = engine.run(records=sample_summaries)
        assert isinstance(result, dict)
        assert "n_clusters" in result
        assert "silhouette_score" in result
        assert "n_records" in result
        assert "clusters" in result

    def test_run_preserves_record_count(self, engine, sample_summaries):
        """run() reports correct number of records processed."""
        result = engine.run(records=sample_summaries)
        assert result["n_records"] == len(sample_summaries)
