"""Multi-tier email retrieval pipeline with BM25, TF-IDF, and cluster matching."""

import json
import math
import os
import re
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


# ---------------------------------------------------------------------------
# Helpers: JSONL I/O
# ---------------------------------------------------------------------------

def _read_jsonl(path):
    """Read a JSONL file; return empty list if missing or empty."""
    if not path or not os.path.isfile(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# BM25 (simplified Okapi BM25)
# ---------------------------------------------------------------------------

class SimpleBM25:
    """Minimal BM25 scorer — no external library needed."""

    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.docs = []          # list of token lists
        self.avgdl = 0
        self.idf = {}
        self.doc_freq = Counter()

    def fit(self, documents):
        n = len(documents)
        total_tokens = 0
        for doc in documents:
            tokens = self._tokenize(doc)
            self.docs.append(tokens)
            total_tokens += len(tokens)
            for t in set(tokens):
                self.doc_freq[t] += 1
        self.avgdl = total_tokens / max(n, 1)
        for term, df in self.doc_freq.items():
            self.idf[term] = math.log((n - df + 0.5) / (df + 0.5) + 1)

    def _tokenize(self, text):
        return re.findall(r"[a-zA-Z0-9_]+", str(text).lower())

    def score(self, query, top_k=5):
        tokens = self._tokenize(query)
        scores = []
        for i, doc_tokens in enumerate(self.docs):
            s = 0.0
            dl = len(doc_tokens)
            for t in set(tokens):
                tf = doc_tokens.count(t)
                idf = self.idf.get(t, 0)
                num = tf * (self.k1 + 1)
                den = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                s += idf * num / den
            scores.append((i, s))
        scores.sort(key=lambda x: x[1], reverse=True)
        # Always return ALL docs with scores; caller decides how many to keep
        return scores


# ---------------------------------------------------------------------------
# QueryRouter
# ---------------------------------------------------------------------------

class QueryRouter:
    """Route natural-language queries across three email tiers."""

    # Intent keyword maps
    _RECENT_KW = {"recent", "last", "yesterday", "today", "newest", "latest", "last few"}
    _SPECIFIC_KW = {"from", "sent by", "sent from", "sender", "by "}
    # aggregated keywords are anything that isn't recent/specific/topic
    _TOPIC_KW = {"about", "regarding", "topic", "concerning", "subject", "re:"}

    def __init__(self, tier1_path=None, tier2_path=None, tier3_path=None):
        base = os.path.join(os.path.dirname(__file__) or ".")
        self.tier1_path = tier1_path or os.path.join(base, "tier1.jsonl")
        self.tier2_path = tier2_path or os.path.join(base, "tier2.jsonl")
        self.tier3_path = tier3_path or os.path.join(base, "tier3.jsonl")

        # Load tiers
        self.tier1 = _read_jsonl(self.tier1_path)   # raw emails
        self.tier2 = _read_jsonl(self.tier2_path)    # summaries
        self.tier3 = _read_jsonl(self.tier3_path)    # cluster summaries

        # BM25 index on tier1 content
        self.bm25 = SimpleBM25()
        if self.tier1:
            self.bm25.fit([e.get("content", "") for e in self.tier1])

        # TF-IDF index on tier2 summaries
        self._tfidf = TfidfVectorizer(
            lowercase=True, stop_words="english",
            ngram_range=(1, 2), max_features=5000,
        )
        if self.tier2:
            texts = []
            for s in self.tier2:
                # Try standard fields first, then fall back to structured fields
                text = s.get("summary") or s.get("content", "")
                if not text:
                    # Reconstruct from structured summary fields
                    purpose = s.get("summary_purpose", "")
                    details = s.get("summary_key_details", [])
                    if isinstance(details, list):
                        details_text = " ".join(str(d) for d in details[:10])
                    else:
                        details_text = str(details)
                    entities = s.get("summary_entities", {})
                    if isinstance(entities, dict):
                        names = entities.get("names", [])
                        if isinstance(names, list):
                            names_text = " ".join(str(n) for n in names[:5])
                        else:
                            names_text = ""
                        locations = entities.get("locations", [])
                        if isinstance(locations, list):
                            loc_text = " ".join(str(l) for l in locations[:3])
                        else:
                            loc_text = ""
                        text = f"{purpose} {details_text} {names_text} {loc_text}"
                    else:
                        text = purpose + " " + details_text
                texts.append(text.strip())
            # Only fit if we have non-empty texts with actual content
            non_empty = [t for t in texts if len(t) > 0 and len(t.split()) > 1]
            if non_empty:
                self._tfidf.fit(non_empty)
                self._tfidf_matrix = self._tfidf.transform(texts)
                nn = NearestNeighbors(n_neighbors=min(len(texts), 50), metric="cosine")
                nn.fit(self._tfidf_matrix)
                self._nn = nn
            else:
                self._nn = None
        else:
            self._nn = None

    # ---- query decomposition -------------------------------------------

    def decompose_query(self, query: str) -> dict:
        q = query.lower().strip()
        entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", query)
        dates = re.findall(r"(?:20\d{2}|Q[1-4]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\S*", q)
        senders = []
        for kw in self._SPECIFIC_KW:
            if kw in q:
                idx = q.index(kw) + len(kw)
                tail = q[idx:].strip().split()[0]
                # Only treat as sender if it looks like a name (starts with letter, not a year/number)
                if tail and tail[0].isalpha() and not re.match(r"^\d{4}", tail):
                    senders.append(tail)
        topics = [t for t in re.findall(r"\b\w+\b", q) if t not in self._RECENT_KW and t not in self._TOPIC_KW and len(t) > 2]

        # Intent
        if any(k in q for k in self._RECENT_KW):
            intent = "recent"
        elif senders:
            intent = "specific_email"
        elif any(k in q for k in self._TOPIC_KW):
            intent = "topic_search"
        else:
            intent = "aggregated"

        return {"entities": entities, "dates": dates, "senders": senders,
                "topics": topics, "intent": intent}

    # ---- tier searches -------------------------------------------------

    def search_tier1(self, query, top_k=5):
        results = []
        for idx, score in self.bm25.score(query, top_k=top_k * 3):
            e = self.tier1[idx]
            results.append({
                "tier": 1,
                "id": e.get("email_id", str(idx)),
                "content": e.get("content", ""),
                "score": round(score, 4),
                "gmail_url": e.get("gmail_url", ""),
            })
        return results[:top_k]

    def search_tier2(self, query, top_k=5):
        if not getattr(self, "_nn", None):
            return []
        vec = self._tfidf.transform([query])
        n_neighbors = max(1, min(top_k, len(self.tier2)))
        dists, indices = self._nn.kneighbors(vec, n_neighbors=n_neighbors)
        results = []
        for d, i in zip(dists[0], indices[0]):
            s = self.tier2[i]
            results.append({
                "tier": 2,
                "id": s.get("email_id") or s.get("id", str(i)),
                "subject": s.get("subject", ""),
                "content": s.get("summary", ""),
                "score": round(1 - d, 4),
                "gmail_url": s.get("gmail_url", ""),
            })
        return results

    def search_tier3(self, query, top_k=3):
        parts = self.decompose_query(query)
        results = []
        for idx, c in enumerate(self.tier3):
            score = 0.0
            # topic overlap
            for t in parts["topics"]:
                if t.lower() in c.get("summary", "").lower():
                    score += 1.0
            # sender match
            for s in parts["senders"]:
                if s.lower() in c.get("summary", "").lower():
                    score += 2.0
            # date proximity (simple heuristic)
            for d in parts["dates"]:
                if d.lower() in c.get("summary", "").lower():
                    score += 1.5
            if score > 0:
                results.append({
                    "tier": 3,
                    "id": c.get("cluster_id", str(idx)),
                    "content": c.get("summary", ""),
                    "score": round(score, 4),
                    "gmail_urls": c.get("gmail_urls", []),
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ---- routing -------------------------------------------------------

    def route_query(self, query, top_k=10, nudge=None):
        """Route a query across tiers with transparency and nudge support.

        Parameters
        ----------
        query : str
            Natural-language search query.
        top_k : int
            Number of results to keep in 'hits' after pruning.
        nudge : dict, optional
            User overrides:
              - exclude_ids: list of email IDs to remove from hits
              - include_ids: list of email IDs to force into hits

        Returns
        -------
        dict with keys: query, intent, tiers_searched, hits, pruned,
                        nudge_options, metadata
        """
        parts = self.decompose_query(query)
        all_candidates = []  # every candidate found across tiers
        tiers_searched = set()

        if parts["intent"] == "recent":
            all_candidates.extend(self.search_tier1(query, top_k=top_k * 3))
            tiers_searched.add(1)
        elif parts["intent"] == "specific_email":
            all_candidates.extend(self.search_tier1(query, top_k=top_k * 3))
            all_candidates.extend(self.search_tier2(query, top_k=top_k // 2))
            tiers_searched.update([1, 2])
        elif parts["intent"] == "topic_search":
            all_candidates.extend(self.search_tier2(query, top_k=top_k))
            all_candidates.extend(self.search_tier3(query, top_k=3))
            tiers_searched.update([2, 3])
        else:  # aggregated
            # Try tier3 and tier2 first, fall back to tier1 if empty
            tier3_hits = self.search_tier3(query, top_k=3)
            tier2_hits = self.search_tier2(query, top_k=top_k // 2)
            if tier3_hits or tier2_hits:
                all_candidates.extend(tier3_hits)
                all_candidates.extend(tier2_hits)
                tiers_searched.update([2, 3])
            else:
                # Fall back to tier1 for aggregated queries when no summaries/clusters exist
                all_candidates.extend(self.search_tier1(query, top_k=top_k))
                tiers_searched.add(1)

        # Deduplicate by id, preserve order (first occurrence wins)
        seen = set()
        unique = []
        for c in all_candidates:
            if c["id"] not in seen:
                seen.add(c["id"])
                unique.append(c)
        unique.sort(key=lambda x: x["score"], reverse=True)

        # Apply nudge filters
        exclude_ids = set(nudge.get("exclude_ids", []) if nudge else [])
        include_ids = set(nudge.get("include_ids", []) if nudge else [])

        # Force-include requested IDs (add back if they were excluded or missing)
        forced_in = []
        for cid in include_ids:
            found = next((c for c in unique if c["id"] == cid), None)
            if found and found["id"] not in exclude_ids:
                forced_in.append(found)

        # Apply exclusions
        hits = [c for c in unique if c["id"] not in exclude_ids] + forced_in
        # Deduplicate again after forcing includes
        seen2 = set()
        deduped_hits = []
        for h in hits:
            if h["id"] not in seen2:
                seen2.add(h["id"])
                deduped_hits.append(h)
        hits = deduped_hits

        # Pruned = everything that was excluded or dropped below top_k
        hit_ids = {h["id"] for h in hits[:top_k]}
        pruned = [c for c in unique if c["id"] not in hit_ids]

        # Sort hits by score descending
        hits.sort(key=lambda x: x["score"], reverse=True)

        # Build nudge options (show what IDs are available to nudge)
        all_ids_in_results = [c["id"] for c in unique]
        nudge_options = {
            "exclude_ids": all_ids_in_results,
            "include_ids": [],  # everything is already included
        }

        return {
            "query": query,
            "intent": parts["intent"],
            "tiers_searched": sorted(tiers_searched),
            "hits": hits[:top_k],
            "pruned": pruned,
            "nudge_options": nudge_options,
            "metadata": {
                "tier1_count": len(self.tier1),
                "tier2_count": len(self.tier2),
                "tier3_count": len(self.tier3),
                "total_candidates": len(unique),
                "hits_returned": len(hits[:top_k]),
                "pruned_count": len(pruned),
            },
        }

    def on_demand_decompress(self, email_id):
        """Stub for retrieving the original raw email body.

        TODO: Replace mock with Gmail API call.
        Example integration point:
            from googleapiclient.discovery import build
            service = build("gmail", "v1", credentials=creds)
            msg = service.users().messages().get(userId="me", id=email_id).execute()
            # decode payload, return body text
        """
        return (f"[MOCK DECOMPRESS — Gmail API stub]\n"
                f"email_id={email_id}\n"
                f"--- Original body would be fetched here via Gmail API ---")


# ---------------------------------------------------------------------------
# RetrievalPipeline
# ---------------------------------------------------------------------------

class RetrievalPipeline:
    """High-level interface wrapping QueryRouter with caching & context formatting."""

    def __init__(self, config=None):
        self.router = QueryRouter(
            tier1_path=config.get("tier1_path") if config else None,
            tier2_path=config.get("tier2_path") if config else None,
            tier3_path=config.get("tier3_path") if config else None,
        )
        self._cache = {}  # query_string -> result dict

    def query(self, question, top_k=10, nudge=None):
        if question in self._cache:
            return self._cache[question]
        result = self.router.route_query(question, top_k=top_k, nudge=nudge)
        self._cache[question] = result
        return result

    @staticmethod
    def _token_count(text):
        """Rough token count: ~4 chars per token (English avg)."""
        return max(1, len(text) // 4)

    def build_context_window(self, results, max_tokens=64000):
        """Build a context string from results, respecting token budget.

        Priority order: Tier 1 raw > Tier 2 summaries > Tier 3 clusters.
        Includes Gmail links for each result.
        """
        # Sort by priority then score
        priority = {1: 0, 2: 1, 3: 2}
        sorted_results = sorted(results,
                                key=lambda r: (priority.get(r["tier"], 9), -r["score"]))

        parts = []
        tokens_used = 0
        for r in sorted_results:
            tier_label = f"[Tier {r['tier']}]"
            gmail_link = r.get("gmail_url") or r.get("gmail_urls", [""])[0]
            link_line = f"\n[Gmail: {gmail_link}]" if gmail_link else ""
            header = f"## {tier_label} ID:{r['id']} ##{link_line}\n"
            body = r.get("content", "")
            snippet_len = max_tokens - tokens_used - len(header)
            if snippet_len <= 0:
                break
            # Truncate to budget
            if self._token_count(body) > snippet_len:
                body = body[:snippet_len * 4] + "..."
            parts.append(header + body)
            tokens_used += self._token_count(header + body)

        return "\n\n".join(parts)
