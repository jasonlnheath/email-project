"""Reranker module — cross-encoder style re-ranking using sklearn features."""

import re
from collections import Counter

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer


# ── Feature engineering helpers ───────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r'[a-zA-Z0-9_]+', text.lower())


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(_tokenize(a)), set(_tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _tfidf_cosine(query: str, doc: str) -> float:
    vec = TfidfVectorizer()
    try:
        tfidf = vec.fit_transform([query, doc])
        from sklearn.metrics.pairwise import cosine_similarity
        return cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
    except Exception:
        return 0.0


def _sender_match(query: str, doc: str) -> float:
    """Heuristic: do query and doc share meaningful words?"""
    q_tokens = set(_tokenize(query))
    d_tokens = set(_tokenize(doc))
    if not q_tokens or not d_tokens:
        return 0.0
    return len(q_tokens & d_tokens) / max(len(q_tokens), len(d_tokens))


def _date_proximity_heuristic(query: str, doc: str) -> float:
    """Heuristic: boost if both mention temporal cues."""
    date_pattern = re.compile(r'\d{1,2}[/:]\d{1,2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|yesterday|week|month|year', re.I)
    q_dates = set(date_pattern.findall(query.lower()))
    d_dates = set(date_pattern.findall(doc.lower()))
    if not q_dates or not d_dates:
        return 0.0
    return min(1.0, len(q_dates & d_dates) / max(len(q_dates), len(d_dates)))


def _extract_features(query: str, doc: str) -> list[float]:
    return [
        _jaccard(query, doc),
        _tfidf_cosine(query, doc),
        _sender_match(query, doc),
        _date_proximity_heuristic(query, doc),
    ]


# ── CrossEncoderReranker ─────────────────────────────────────────────────

class CrossEncoderReranker:
    """Re-ranker that learns relevance from labelled query-doc pairs."""

    def __init__(self):
        self.trained = False
        self._model = LogisticRegression(max_iter=1000, random_state=42)
        self._queries = []
        self._docs = []

    # ── training ────────────────────────────────────────────────────────

    def train(self, training_data: list[dict]) -> None:
        if not training_data:
            raise ValueError("Training data must not be empty")

        labels = []
        self._queries = []
        self._docs = []
        for item in training_data:
            label = item.get("label")
            if label not in (0, 1, 2, 3):
                raise ValueError(f"Invalid label {label}; must be 0-3")
            labels.append(label)
            self._queries.append(item["query"])
            self._docs.append(item["doc"])

        X = np.array([_extract_features(q, d) for q, d in zip(self._queries, self._docs)])
        y = np.array(labels)

        # LogisticRegression needs at least 2 classes; fall back to term overlap otherwise
        if len(np.unique(y)) < 2:
            self.trained = True
            return

        self._model.fit(X, y)
        self.trained = True

    def _fallback_score(self, query: str, documents: list[str]) -> np.ndarray:
        """Simple term-overlap scoring used as fallback."""
        q_tokens = set(_tokenize(query))
        scores = []
        for doc in documents:
            d_tokens = set(_tokenize(doc))
            if not q_tokens or not d_tokens:
                scores.append(0.0)
            else:
                scores.append(len(q_tokens & d_tokens) / len(q_tokens | d_tokens))
        return np.array(scores, dtype=float)

    # ── scoring ─────────────────────────────────────────────────────────

    def score_pairs(self, query: str, documents: list[str]) -> np.ndarray:
        # Use model only if it was actually fitted (has coef_); otherwise fallback
        if not self.trained or not hasattr(self._model, 'coef_'):
            return self._fallback_score(query, documents)

        X = np.array([_extract_features(query, doc) for doc in documents])
        probs = self._model.predict_proba(X)
        # Map predicted class probabilities to numeric scores using model's class order
        class_scores = {cls: float(cls) for cls in range(4)}
        scores_arr = np.zeros((len(documents), 4))
        for i, cls in enumerate(self._model.classes_):
            scores_arr[:, int(cls)] = probs[:, i]
        scores = scores_arr @ np.array([0.0, 1.0, 2.0, 3.0])
        return np.array(scores, dtype=float)

    # ── reranking ───────────────────────────────────────────────────────

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        if not results:
            return []

        docs = [r["content"] for r in results]
        scores = self.score_pairs(query, docs)

        paired = list(zip(results, scores))
        paired.sort(key=lambda x: x[1], reverse=True)

        out = []
        for r, s in paired[:top_k]:
            out.append({"id": r["id"], "content": r["content"], "score": float(s)})
        return out


# ── RerankingPipeline ─────────────────────────────────────────────────────

class RerankingPipeline:
    """High-level pipeline wrapping a reranker."""

    def __init__(self):
        self.reranker = CrossEncoderReranker()

    def query(self, question: str, top_k: int = 10) -> dict:
        # Simulated retrieval: use the question as both query and doc pool
        # In production this would call an external retriever.
        sample_docs = [
            f"Document about {question}",
            f"Related content for {question}",
            f"Unrelated material",
            f"Background on {question}",
            f"Notes regarding {question}",
        ]
        results = [
            {"id": str(i), "content": d, "initial_score": 0.5}
            for i, d in enumerate(sample_docs)
        ]
        reranked = self.reranker.rerank(question, results, top_k=top_k)
        return {"query": question, "results": reranked}
