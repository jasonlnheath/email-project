"""Email Clustering Engine — Phase 3: Aggregation & Routing (Tier 3)

Clusters Tier 2 email summaries by topic using TF-IDF + KMeans, then generates
cluster-level summaries for the aggregated tier.

Dependencies: ONLY scikit-learn + numpy. No heavy model downloads.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Graceful dependency handling
# ---------------------------------------------------------------------------
try:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics import silhouette_score
except ImportError as exc:  # pragma: no cover
    print(
        f"ERROR: Required ML dependency not found — {exc.name}. "
        f"Install with: pip install scikit-learn numpy",
        file=sys.stderr,
    )
    sys.exit(1)


class EmailClusteringEngine:
    """Cluster email summaries by topic and generate cluster-level summaries.

    Pipeline
    --------
    1. Load Tier-2 JSONL summaries
    2. Compute TF-IDF vectors (lightweight, no model download)
    3. Cluster via KMeans (auto-detect optimal k if not specified)
    4. Generate human-readable cluster summaries
    5. Save to JSONL
    """

    def __init__(
        self,
        n_clusters: Optional[int] = None,
        max_k_for_silhouette: int = 10,
        min_k: int = 2,
        tfidf_max_features: int = 500,
        random_state: int = 42,
    ):
        """
        Parameters
        ----------
        n_clusters : int or None
            Target number of clusters.  If *None*, auto-detect via silhouette
            score over a range [min_k .. max_k_for_silhouette].
        max_k_for_silhouette : int
            Upper bound for the auto-k search.
        min_k : int
            Lower bound for the auto-k search.
        tfidf_max_features : int
            Maximum vocabulary size for TF-IDF.
        random_state : int
            Reproducibility seed for KMeans initialisation.
        """
        self.n_clusters = n_clusters
        self.max_k = max_k_for_silhouette
        self.min_k = min_k
        self.tfidf_max_features = tfidf_max_features
        self.random_state = random_state

        # Filled during run()
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._tfidf_matrix: Optional[np.ndarray] = None
        self._labels: Optional[np.ndarray] = None
        self._silhouette_score_val: float = 0.0

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def load_summaries(self, summaries_path: str) -> List[Dict]:
        """Load Tier-2 summaries from a JSONL file.

        Expected record shape (examples of accepted fields):
            {
                "id": "msg_001",
                "date": "2025-01-15T10:30:00Z",
                "sender": "Alice Chen",
                "subject": "Q1 Budget Review",
                "summary": "Alice presented Q1 budget proposal...",
                "entities": ["budget", "Q1"],
                "action_items": ["Approve by Friday"],
                ...
            }

        Returns the full list of dicts.
        """
        if not os.path.isfile(summaries_path):
            raise FileNotFoundError(f"Summaries file not found: {summaries_path}")

        records: List[Dict] = []
        with open(summaries_path, "r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        f"WARNING: Skipping malformed JSON on line {line_no}: {exc}",
                        file=sys.stderr,
                    )
                    continue
                # Ensure every record has at least an id and a text body
                if "id" not in rec:
                    rec["id"] = f"auto_{line_no}"
                records.append(rec)

        return records

    # ------------------------------------------------------------------
    # TF-IDF vectorisation
    # ------------------------------------------------------------------
    @staticmethod
    def _build_text_body(rec: Dict) -> str:
        """Build a single searchable text string from a summary record."""
        parts: List[str] = []
        for key in ("summary", "subject", "body", "text"):
            val = rec.get(key, "")
            if isinstance(val, str) and val.strip():
                parts.append(val)
        # Append entities / action items as extra signal
        for key in ("entities", "keywords", "action_items", "outcomes"):
            vals = rec.get(key)
            if isinstance(vals, list):
                parts.extend(str(v) for v in vals if isinstance(v, str))
            elif isinstance(vals, str) and vals.strip():
                parts.append(vals)
        return " ".join(parts)

    def compute_tfidf_vectors(self, summaries: List[Dict]) -> np.ndarray:
        """Compute TF-IDF vectors for all summaries.

        Parameters
        ----------
        summaries : list of dict
            Each dict must contain at minimum an ``id`` field; text is built
            from summary/subject/body/entities fields.

        Returns
        -------
        np.ndarray  (n_samples, n_features) dense TF-IDF matrix.
        """
        texts = [self._build_text_body(s) for s in summaries]
        self._vectorizer = TfidfVectorizer(
            max_features=self.tfidf_max_features,
            stop_words="english",
            sublinear_tf=True,
            ngram_range=(1, 2),
        )
        self._tfidf_matrix = self._vectorizer.fit_transform(texts)
        return self._tfidf_matrix

    # ------------------------------------------------------------------
    # Clustering
    # ------------------------------------------------------------------
    def _find_best_k(self, tfidf_matrix: np.ndarray) -> Tuple[int, float]:
        """Search k in [min_k .. max_k] and return (best_k, best_silhouette)."""
        n_samples = tfidf_matrix.shape[0]
        upper = min(self.max_k, n_samples - 1)
        if upper < self.min_k:
            return self.min_k, 0.0

        best_k, best_score = self.min_k, -1.0
        for k in range(self.min_k, upper + 1):
            km = KMeans(n_clusters=k, random_state=self.random_state, n_init=10)
            labels = km.fit_predict(tfidf_matrix)
            # silhouette_score needs at least 2 clusters and at least 2 samples per cluster
            unique_labels = set(labels)
            if len(unique_labels) < 2:
                continue
            score = silhouette_score(tfidf_matrix, labels, sample_size=min(2000, n_samples))
            if score > best_score:
                best_score = score
                best_k = k

        return best_k, best_score

    def cluster(self, tfidf_matrix: np.ndarray) -> np.ndarray:
        """Cluster emails using KMeans.

        If ``self.n_clusters`` is None, auto-detect optimal k via silhouette
        score over a configurable range.

        Returns
        -------
        np.ndarray of shape (n_samples,) with integer cluster labels.
        """
        n_samples = tfidf_matrix.shape[0]

        if self.n_clusters is None:
            # Auto-detect optimal k
            self.n_clusters, self._silhouette_score_val = self._find_best_k(tfidf_matrix)
            print(
                f"[clustering] Auto-detected optimal k={self.n_clusters} "
                f"(silhouette={self._silhouette_score_val:.3f})"
            )

        km = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init=10,
        )
        self._labels = km.fit_predict(tfidf_matrix)

        # Compute silhouette score (needs ≥ 2 samples per cluster)
        unique_labels = set(self._labels)
        if len(unique_labels) >= 2 and n_samples > len(unique_labels):
            self._silhouette_score_val = float(
                silhouette_score(
                    tfidf_matrix, self._labels, sample_size=min(2000, n_samples)
                )
            )

        print(
            f"[clustering] Using k={self.n_clusters} "
            f"(silhouette={self._silhouette_score_val:.3f})"
        )

        return self._labels

    # ------------------------------------------------------------------
    # Cluster-level summary generation
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_date(rec: Dict) -> Optional[str]:
        """Return YYYY-MM-DD string from various date formats."""
        for key in ("date", "timestamp", "datetime"):
            val = rec.get(key, "")
            if not val:
                continue
            try:
                dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _top_tfidf_terms(
        vectorizer: TfidfVectorizer,
        tfidf_matrix: np.ndarray,
        labels: np.ndarray,
        cluster_id: int,
        n_terms: int = 5,
    ) -> List[str]:
        """Extract the top-N TF-IDF terms for a given cluster."""
        mask = labels == cluster_id
        cluster_matrix = tfidf_matrix[mask]
        if cluster_matrix.sum() == 0:
            return []
        # Mean TF-IDF across all docs in this cluster
        mean_tfidf = np.asarray(cluster_matrix.mean(axis=0)).flatten()
        feature_names = vectorizer.get_feature_names_out()
        top_indices = mean_tfidf.argsort()[::-1][:n_terms]
        return [str(feature_names[i]) for i in top_indices if mean_tfidf[i] > 0]

    @staticmethod
    def _extract_people(recs: List[Dict]) -> List[str]:
        """Collect unique sender names."""
        people: set[str] = set()
        for rec in recs:
            for key in ("sender", "from", "author"):
                val = rec.get(key, "")
                if isinstance(val, str) and val.strip():
                    people.add(val.strip())
                elif isinstance(val, list):
                    people.update(str(v).strip() for v in val if isinstance(v, str))
        return sorted(people)

    @staticmethod
    def _extract_outcomes(recs: List[Dict]) -> List[str]:
        """Collect action items / outcomes / decisions."""
        outcomes: List[str] = []
        for rec in recs:
            for key in ("action_items", "outcomes", "decisions", "actions"):
                vals = rec.get(key)
                if isinstance(vals, list):
                    outcomes.extend(str(v).strip() for v in vals if isinstance(v, str) and v.strip())
                elif isinstance(vals, str) and vals.strip():
                    outcomes.append(vals.strip())
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: List[str] = []
        for o in outcomes:
            if o not in seen:
                seen.add(o)
                unique.append(o)
        return unique[:10]  # cap at 10

    def generate_cluster_summaries(
        self,
        records: List[Dict],
        labels: np.ndarray,
        tfidf_matrix: Optional[np.ndarray] = None,
    ) -> List[Dict]:
        """Generate a summary dict for each cluster.

        Returns a list of dicts, one per cluster, with keys:
            cluster_id, size, time_range, topics, people, outcomes,
            member_ids, representative_email_id
        """
        unique_labels = sorted(set(labels))
        summaries: List[Dict] = []

        for cid in unique_labels:
            mask = labels == cid
            cluster_records = [r for r, m in zip(records, mask) if m]
            if not cluster_records:
                continue

            # Time range
            dates = [self._extract_date(r) for r in cluster_records]
            valid_dates = sorted(d for d in dates if d is not None)
            time_range: Dict[str, str] = {}
            if valid_dates:
                time_range["start"] = valid_dates[0]
                time_range["end"] = valid_dates[-1]

            # Topics (top TF-IDF terms)
            topics: List[str] = []
            if tfidf_matrix is not None and self._vectorizer is not None:
                topics = self._top_tfidf_terms(
                    self._vectorizer, tfidf_matrix, labels, cid, n_terms=5
                )

            # People & outcomes
            people = self._extract_people(cluster_records)
            outcomes = self._extract_outcomes(cluster_records)

            # Member IDs
            member_ids = [r.get("id", f"unknown_{i}") for i, r in enumerate(cluster_records)]

            # Representative email — pick the one with highest mean TF-IDF
            rep_id = member_ids[0]
            if tfidf_matrix is not None and len(cluster_records) > 1:
                cluster_tfidf = tfidf_matrix[mask]
                row_sums = np.asarray(cluster_tfidf.sum(axis=1)).flatten()
                best_idx = int(row_sums.argmax())
                rep_id = member_ids[best_idx]

            summary = {
                "cluster_id": int(cid),
                "size": int(mask.sum()),
                "time_range": time_range,
                "topics": topics,
                "people": people,
                "outcomes": outcomes,
                "member_ids": member_ids,
                "representative_email_id": rep_id,
            }
            summaries.append(summary)

        return summaries

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_clusters(self, clusters: List[Dict], output_path: str):
        """Save cluster summaries to a JSONL file."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            for cluster in clusters:
                fh.write(json.dumps(cluster, ensure_ascii=False) + "\n")
        print(f"[clustering] Saved {len(clusters)} clusters to {output_path}")

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    def run(
        self,
        summaries_path: Optional[str] = None,
        output_path: Optional[str] = None,
        records: Optional[List[Dict]] = None,
    ) -> Dict:
        """Execute the full clustering pipeline.

        Parameters
        ----------
        summaries_path : str or None
            Path to Tier-2 JSONL summaries file.  Mutually exclusive with
            *records*.
        output_path : str or None
            Where to write cluster_store.jsonl.
        records : list of dict or None
            Pre-loaded summary records (bypasses file I/O).

        Returns
        -------
        dict with keys: n_clusters, silhouette_score, n_records, clusters (list)
        """
        # --- Load data ---------------------------------------------------
        if records is None:
            if summaries_path is None:
                raise ValueError("Provide either summaries_path or records")
            records = self.load_summaries(summaries_path)
        print(f"[clustering] Loaded {len(records)} summaries")

        if len(records) < 2:
            raise ValueError("Need at least 2 summaries to cluster")

        # --- TF-IDF ------------------------------------------------------
        tfidf_matrix = self.compute_tfidf_vectors(records)
        print(f"[clustering] TF-IDF matrix shape: {tfidf_matrix.shape}")

        # --- Cluster -----------------------------------------------------
        labels = self.cluster(tfidf_matrix)

        # --- Generate cluster summaries ----------------------------------
        cluster_summaries = self.generate_cluster_summaries(
            records, labels, tfidf_matrix
        )

        # --- Save --------------------------------------------------------
        if output_path:
            self.save_clusters(cluster_summaries, output_path)

        result = {
            "n_clusters": len(cluster_summaries),
            "silhouette_score": float(self._silhouette_score_val),
            "n_records": len(records),
            "clusters": cluster_summaries,
        }
        print(f"[clustering] Done — {result['n_clusters']} clusters, silhouette={result['silhouette_score']:.3f}")
        return result
