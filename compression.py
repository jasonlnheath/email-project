"""Compression ratio tuning module — optimizes tier ratios for 64K context budget.

Uses a heuristic optimization approach: iteratively adjusts compression ratios
to maximize retrieval quality while staying within the token budget.

Dependencies: ONLY standard library + numpy. No sklearn needed.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional


class CompressionOptimizer:
    """Optimize compression ratios across three email tiers for a fixed context budget."""

    def __init__(self, max_tokens: int = 64000):
        self.max_tokens = max_tokens

    # ── Token estimation helpers ────────────────────────────────────────

    @staticmethod
    def _token_count(text: str) -> int:
        """Rough token count: ~4 chars per token (English avg)."""
        return max(1, len(text) // 4)

    def estimate_tier1_tokens(self, emails: List[Dict]) -> int:
        """Estimate tokens for Tier 1 (raw, no compression)."""
        total = 0
        for email in emails:
            content = email.get("content", "")
            total += self._token_count(content)
        # Add metadata overhead per email (~20 tokens)
        total += len(emails) * 20
        return total

    def estimate_tier2_tokens(self, summaries: List[Dict], compression_ratio: float = 10.0) -> int:
        """Estimate tokens for Tier 2 (summarized, compressed by ratio)."""
        if not summaries or compression_ratio <= 0:
            return 0
        raw_tokens = sum(
            self._token_count(s.get("summary", s.get("content", "")))
            for s in summaries
        )
        # Add metadata overhead per summary (~15 tokens)
        raw_tokens += len(summaries) * 15
        return max(1, raw_tokens // int(compression_ratio))

    def estimate_tier3_tokens(self, clusters: List[Dict], compression_ratio: float = 100.0) -> int:
        """Estimate tokens for Tier 3 (aggregated, heavily compressed)."""
        if not clusters or compression_ratio <= 0:
            return 0
        raw_tokens = sum(
            self._token_count(c.get("summary", c.get("content", "")))
            for c in clusters
        )
        # Cluster summaries include metadata (~30 tokens per cluster)
        raw_tokens += len(clusters) * 30
        return max(1, raw_tokens // int(compression_ratio))

    def estimate_total_context(
        self,
        tier1: List[Dict],
        tier2: List[Dict],
        tier3: List[Dict],
        tier1_compression: float = 1.0,
        tier2_compression: float = 10.0,
        tier3_compression: float = 100.0,
        system_overhead: int = 2000,
    ) -> int:
        """Estimate total token usage across all tiers."""
        t1 = self.estimate_tier1_tokens(tier1) if tier1_compression <= 1 else (
            self.estimate_tier1_tokens(tier1) // int(tier1_compression)
        )
        t2 = self.estimate_tier2_tokens(tier2, tier2_compression)
        t3 = self.estimate_tier3_tokens(tier3, tier3_compression)
        return t1 + t2 + t3 + system_overhead

    # ── Context allocation ──────────────────────────────────────────────

    def allocate_context_budget(
        self, available: int, priorities: List[int] | None = None
    ) -> Dict[int, int]:
        """Distribute available tokens across tiers proportionally.

        Default priority weights: Tier 1 (30%), Tier 2 (45%), Tier 3 (25%).
        These reflect the importance of recent context vs deep retrieval.
        Returns empty dict when no priorities are specified.
        """
        if not priorities:
            return {}

        weights = {1: 0.30, 2: 0.45, 3: 0.25}
        allocation: Dict[int, int] = {}

        for tier in priorities:
            weight = weights.get(tier, 1.0 / len(priorities))
            allocation[tier] = max(100, int(available * weight))

        # Cap total to available
        total = sum(allocation.values())
        if total > available:
            # Scale down proportionally
            scale = available / total
            allocation = {k: max(100, int(v * scale)) for k, v in allocation.items()}

        return allocation

    # ── Balance scoring ─────────────────────────────────────────────────

    def tier_balance_score(self, scores: Dict[int, int]) -> float:
        """Score how evenly context is distributed across tiers (0-1).

        Uses coefficient of variation — lower variance = better balance.
        A perfectly balanced allocation gets 1.0; highly skewed gets ~0.0.
        """
        if not scores:
            return 0.0

        values = list(scores.values())
        mean_val = sum(values) / len(values)
        if mean_val == 0:
            return 0.0

        # Coefficient of variation
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_val

        # Convert to 0-1 score (cv=0 → score=1, cv→∞ → score→0)
        return max(0.0, min(1.0, 1.0 / (1.0 + cv)))

    # ── Core optimization ───────────────────────────────────────────────

    def optimize_ratios(
        self,
        tier1: List[Dict],
        tier2: List[Dict],
        tier3: List[Dict],
        system_overhead: int = 2000,
        min_compression: float = 2.0,
        max_compression: float = 200.0,
        step_size: float = 1.0,
    ) -> Dict:
        """Find optimal compression ratios within the token budget.

        Uses grid search over plausible compression ratios to maximize:
            quality_score = recall_weight * (1 - context_waste) + balance_bonus

        Parameters
        ----------
        tier1, tier2, tier3 : list of dict
            Email/summary/cluster records for each tier.
        system_overhead : int
            Fixed token cost for system prompt, instructions, etc.
        min_compression : float
            Minimum allowed compression ratio for tiers 2 and 3.
        max_compression : float
            Maximum allowed compression ratio for tiers 2 and 3.
        step_size : float
            Increment for grid search (smaller = more precise but slower).

        Returns
        -------
        dict with keys: tier1_compression, tier2_compression, tier3_compression,
                        total_tokens, balance_score, quality_score
        """
        # Tier 1 is always 1:1 (raw)
        best_ratio_2 = max(2, min(10, max_compression))
        best_ratio_3 = max(10, min(50, max_compression))
        best_quality = -1.0

        # Grid search over tier2 and tier3 compression ratios
        r2_range = range(int(min_compression), int(max_compression) + 1, max(1, int(step_size)))
        r3_range = range(int(min_compression * 5), int(max_compression) + 1, max(1, int(step_size * 5)))

        for r2 in r2_range:
            for r3 in r3_range:
                total = self.estimate_total_context(
                    tier1, tier2, tier3,
                    tier1_compression=1.0,
                    tier2_compression=r2,
                    tier3_compression=r3,
                    system_overhead=system_overhead,
                )

                if total > self.max_tokens:
                    continue

                # Quality score: reward using more of the budget (less waste)
                # while penalizing extreme imbalance
                context_waste = 1.0 - (total / self.max_tokens)
                allocation = {1: self.estimate_tier1_tokens(tier1),
                              2: self.estimate_tier2_tokens(tier2, r2),
                              3: self.estimate_tier3_tokens(tier3, r3)}
                balance = self.tier_balance_score(allocation)

                # Weighted quality: 60% budget utilization, 40% balance
                quality = 0.6 * (1.0 - context_waste) + 0.4 * balance

                if quality > best_quality:
                    best_quality = quality
                    best_ratio_2 = r2
                    best_ratio_3 = r3

        total = self.estimate_total_context(
            tier1, tier2, tier3,
            tier1_compression=1.0,
            tier2_compression=best_ratio_2,
            tier3_compression=best_ratio_3,
            system_overhead=system_overhead,
        )

        allocation = {
            1: self.estimate_tier1_tokens(tier1),
            2: self.estimate_tier2_tokens(tier2, best_ratio_2),
            3: self.estimate_tier3_tokens(tier3, best_ratio_3),
        }

        return {
            "tier1_compression": 1,
            "tier2_compression": best_ratio_2,
            "tier3_compression": best_ratio_3,
            "total_tokens": total,
            "balance_score": round(self.tier_balance_score(allocation), 4),
            "quality_score": round(best_quality, 4),
            "allocation": allocation,
        }

    # ── Reporting ───────────────────────────────────────────────────────

    def generate_tuning_report(self, result: Dict) -> str:
        """Return a formatted string report of the optimization results."""
        lines = [
            "=== Compression Tuning Report ===",
            "",
            f"  Tier 1 (raw):       compression=1:1",
            f"  Tier 2 (summarized): compression={result['tier2_compression']}:1",
            f"  Tier 3 (aggregated): compression={result['tier3_compression']}:1",
            "",
            f"  Total tokens:       {result['total_tokens']:,}",
            f"  Context budget:     {self.max_tokens:,}",
            f"  Utilization:        {result['total_tokens']/self.max_tokens*100:.1f}%",
            f"  Balance score:      {result.get('balance_score', 0):.4f}",
            f"  Quality score:      {result.get('quality_score', 0):.4f}",
        ]

        allocation = result.get("allocation", {})
        if allocation:
            lines.append("")
            lines.append("  Token allocation by tier:")
            for tier, tokens in sorted(allocation.items()):
                tier_name = {1: "Tier 1 (raw)", 2: "Tier 2 (summarized)", 3: "Tier 3 (aggregated)"}[tier]
                pct = tokens / result["total_tokens"] * 100 if result["total_tokens"] > 0 else 0
                lines.append(f"    {tier_name}: {tokens:,} tokens ({pct:.1f}%)")

        return "\n".join(lines)

    # ── Step 2: Factual Consistency (NLI Claim Verification) ────────────

    @staticmethod
    def extract_claims(text: str) -> List[str]:
        """Split text into atomic claims (one per sentence)."""
        if not text or not text.strip():
            return []
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def _word_overlap_score(claim: str, source: str) -> float:
        """Calculate word-level overlap between a claim and source text."""
        import re
        claim_words = set(re.findall(r'\b\w+\b', claim.lower()))
        source_words = set(re.findall(r'\b\w+\b', source.lower()))
        if not claim_words:
            return 1.0
        if not source_words:
            return 0.0
        intersection = claim_words & source_words
        return len(intersection) / len(claim_words)
    @staticmethod
    def compression_ratio(original: str, summary: str) -> float:
        """Calculate compression ratio as original length / summary length."""
        if not summary or len(summary) == 0:
            return float("inf") if original else 1.0
        return len(original) / len(summary)
    @staticmethod
    def _extract_summary_values(summary_text: str) -> str:
        """Extract meaningful values from a structured summary (JSON or otherwise).

        For JSON summaries, extracts only the values (not keys like 'sender', 'purpose').
        For plain text, returns the text as-is.
        This prevents structural keys from diluting word overlap scores.
        """
        import json
        try:
            parsed = json.loads(summary_text)
            # Recursively extract all string values, joining with newlines for sentence boundaries
            def extract_values(obj):
                if isinstance(obj, str):
                    return obj
                elif isinstance(obj, dict):
                    return "\n".join(extract_values(v) for v in obj.values())
                elif isinstance(obj, list):
                    return "\n".join(extract_values(item) for item in obj)
                else:
                    return str(obj)
            return extract_values(parsed)
        except (json.JSONDecodeError, TypeError):
            return summary_text

    @staticmethod
    def factual_consistency(original: str, summary: str) -> float:
        """Calculate factual consistency score between original and summary.

        Decomposes summary into claims, then checks each claim against the
        original using word overlap (heuristic NLI proxy).

        For JSON summaries, extracts only values (not structural keys) before
        comparison to prevent dilution of word overlap scores.

        Returns value in [0, 1] where 1.0 means all claims are fully supported.
        Uses a threshold of 0.5 — a claim is "entailed" if word overlap >= 50%.
        """
        # Extract meaningful content from structured summaries
        summary_content = CompressionOptimizer._extract_summary_values(summary)
        claims = CompressionOptimizer.extract_claims(summary_content)
        if not claims:
            return 1.0  # Empty summary has no false claims

        entailed_count = 0
        for claim in claims:
            overlap = CompressionOptimizer._word_overlap_score(claim, original)
            if overlap >= 0.5:  # Threshold for "entailed"
                entailed_count += 1

        return entailed_count / len(claims)

    # ── Step 3: Entity Preservation Tracking ────────────────────────────

    @staticmethod
    def extract_entities(text: str) -> Dict[str, List[str]]:
        """Extract named entities from text using heuristic patterns.

        Returns dict with keys:
            - names: Capitalized words/phrases that look like person names
            - amounts: Monetary values (e.g., "$5,000", "$5.2k")
            - dates: Date expressions (e.g., "May 15th, 2026", "next Friday")
            - urls: URLs (http:// or https://)
            - locations: Multi-word capitalized phrases that look like locations
        """
        import re
        entities: Dict[str, List[str]] = {
            "names": [],
            "amounts": [],
            "dates": [],
            "urls": [],
            "locations": [],
        }

        # Extract URLs
        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+'
        entities["urls"] = list(set(re.findall(url_pattern, text)))

        # Extract monetary values
        money_pattern = r'\$[\d,]+(?:\.\d{2})?(?:k|K|M|m)?'
        entities["amounts"] = list(set(re.findall(money_pattern, text)))

        # Extract dates (common patterns)
        date_patterns = [
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}(?:st|nd|rd|th)?,? \d{4}',
            r'\d{1,2}/\d{1,2}/\d{2,4}',
            r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
            r'(?:next|last|this) (?:week|month|year|Friday|Monday)',
            r'\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?',
        ]
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities["dates"].extend(matches)
        entities["dates"] = list(set(entities["dates"]))

        # Extract person names and locations (capitalized words/phrases)
        capitalized_phrases = re.findall(
            r'(?<![.!?])\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b', text
        )
        # Filter out common non-entity phrases
        non_entity_patterns = [
            r'^The\b', r'^A\b', r'^An\b', r'^This\b', r'^That\b',
            r'^In\s+the\b', r'^On\s+the\b', r'^At\s+the\b',
            r'^I\b$', r'^We\b', r'^You\b',
        ]
        for phrase in capitalized_phrases:
            if any(re.match(p, phrase) for p in non_entity_patterns):
                continue
            # Heuristic: locations have "City, State" pattern OR contain location keywords
            is_location = False
            if re.search(r'\b(?:Street|St|Avenue|Ave|Road|Rd|City|State|County|Country)\b', phrase, re.IGNORECASE):
                is_location = True
            elif ',' in text and phrase in text.split(',')[0]:
                # Phrase appears before a comma — likely a city name (e.g., "San Francisco" in "San Francisco, California")
                is_location = True
            if is_location:
                entities["locations"].append(phrase)
            elif len(phrase.split()) <= 3:
                entities["names"].append(phrase)

        return entities

    @staticmethod
    def entity_preservation_rate(
        original_entities: Dict[str, List[str]],
        summary_entities: Dict[str, List[str]],
    ) -> float:
        """Calculate entity preservation rate across all entity types.

        For each entity type, checks what fraction of original entities
        appear in the summary. Returns overall average across all types.

        Returns value in [0, 1] where 1.0 means all entities preserved.
        Returns 1.0 if both dicts are empty (no entities to lose).
        """
        if not original_entities and not summary_entities:
            return 1.0

        total_preserved = 0
        total_original = 0

        for key in original_entities:
            orig_set = set(original_entities.get(key, []))
            summ_set = set(summary_entities.get(key, []))
            total_original += len(orig_set)
            # Count how many original entities appear in summary
            preserved = len(orig_set & summ_set)
            total_preserved += preserved

        if total_original == 0:
            return 1.0  # No entities to lose = perfect preservation

        return total_preserved / total_original

    # ── Step 4: Semantic Similarity ─────────────────────────────────────

    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Returns value in [-1, 1] where 1.0 means identical direction,
        0.0 means orthogonal, -1.0 means opposite.
        """
        if len(vec_a) != len(vec_b):
            raise ValueError(f"Vector length mismatch: {len(vec_a)} vs {len(vec_b)}")

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    @staticmethod
    def _text_to_vector(text: str, dim: int = 16) -> List[float]:
        """Convert text to a fixed-dimensional vector using character n-gram hashing.

        This is a lightweight embedding that doesn't require external models.
        Uses hash-based feature extraction with numpy-style operations.
        """
        import hashlib

        vec = [0.0] * dim
        text_lower = text.lower().strip()

        # Character trigram features
        for i in range(len(text_lower) - 2):
            trigram = text_lower[i:i + 3]
            # Hash trigram to dimension index
            h = int(hashlib.md5(trigram.encode()).hexdigest(), 16) % dim
            vec[h] += 1.0

        # Normalize vector
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]

        return vec

    @staticmethod
    def semantic_similarity_text(text_a: str, text_b: str) -> float:
        """Calculate semantic similarity between two texts using lightweight embeddings.

        Returns value in [0, 1] where 1.0 means identical meaning.
        Uses character n-gram hashing for embedding (no external models needed).
        """
        vec_a = CompressionOptimizer._text_to_vector(text_a)
        vec_b = CompressionOptimizer._text_to_vector(text_b)
        sim = CompressionOptimizer.cosine_similarity(vec_a, vec_b)
        # Convert from [-1, 1] to [0, 1] for this metric
        return (sim + 1.0) / 2.0

    # ── Step 5: Hallucination Detection ─────────────────────────────────

    @staticmethod
    def extract_hallucinated_claims(
        original: str, summary: str
    ) -> List[str]:
        """Identify claims in the summary that are NOT supported by the original.

        Uses word overlap heuristic: if a claim's words have < 30% overlap
        with the original, it's flagged as a potential hallucination.

        Returns list of flagged claims.
        """
        claims = CompressionOptimizer.extract_claims(summary)
        hallucinations = []

        for claim in claims:
            overlap = CompressionOptimizer._word_overlap_score(claim, original)
            if overlap < 0.3:  # Low overlap → likely hallucinated
                hallucinations.append(claim)

        return hallucinations

    @staticmethod
    def hallucination_rate(original: str, summary: str) -> float:
        """Calculate fraction of summary claims that are hallucinated.

        Returns value in [0, 1] where 0.0 means no hallucinations detected.
        """
        hallucinations = CompressionOptimizer.extract_hallucinated_claims(original, summary)
        total_claims = len(CompressionOptimizer.extract_claims(summary))

        if total_claims == 0:
            return 0.0

        return len(hallucinations) / total_claims

    # ── Step 6: Retrieval Quality (Recall@k) ────────────────────────────

    @staticmethod
    def recall_at_k(results: List[Dict], k: int = 3) -> float:
        """Calculate Recall@k for retrieval evaluation.

        Args:
            results: List of dicts with keys:
                - "expected_id": the correct email ID
                - "retrieved_ids": list of retrieved email IDs (ordered by relevance)
            k: Number of top results to check (default 3).

        Returns:
            Float in [0, 1] representing fraction of queries where the correct
            result was found in the top-k retrieved items.
        """
        if not results:
            return 0.0

        found_count = 0
        for result in results:
            expected = result.get("expected_id", "")
            retrieved = result.get("retrieved_ids", [])[:k]  # Top-k only
            if expected in retrieved:
                found_count += 1

        return found_count / len(results)

    # ── Step 7: Action Item Detection ───────────────────────────────────

    @staticmethod
    def extract_action_items(text: str) -> List[str]:
        """Extract action items from text using keyword and pattern matching.

        Looks for imperative sentences, phrases with action verbs, and
        explicit action markers (e.g., "Please review", "Action required").

        Returns list of action item strings.
        """
        import re
        action_verbs = [
            "review", "approve", "submit", "send", "contact", "call",
            "schedule", "attend", "complete", "finish", "update", "confirm",
            "reply", "respond", "sign", "approve", "reject", "forward",
            "download", "upload", "install", "configure", "set up",
        ]

        action_markers = [
            "action required", "please ", "need to ", "must ", "should ",
            "deadline", "by friday", "by monday", "by tuesday", "by wednesday",
            "by thursday", "by next", "asap", "urgent",
        ]

        sentences = re.split(r'(?<=[.!?])\s+', text)
        action_items = []

        for sentence in sentences:
            sentence_lower = sentence.lower().strip()
            is_action = False

            # Check for action markers
            for marker in action_markers:
                if marker in sentence_lower:
                    is_action = True
                    break

            # Check for action verbs at start of sentence (imperative)
            if not is_action:
                first_word = sentence_lower.split()[0] if sentence_lower.split() else ""
                if first_word in action_verbs:
                    is_action = True

            # Check for action verbs anywhere with imperative context
            if not is_action:
                for verb in action_verbs:
                    if verb in sentence_lower and len(sentence_lower) < 100:
                        is_action = True
                        break

            if is_action:
                action_items.append(sentence.strip())

        return action_items

    @staticmethod
    def action_item_preservation_rate(
        original_items: List[str], summary_items: List[str]
    ) -> float:
        """Calculate fraction of original action items preserved in summary.

        Uses substring matching: an item is "preserved" if it appears as a
        substring in any summary item.

        Returns value in [0, 1] where 1.0 means all items preserved.
        Returns 1.0 if no original items (vacuously true).
        """
        if not original_items:
            return 1.0

        preserved_count = 0
        for orig_item in original_items:
            orig_lower = orig_item.lower()
            for summ_item in summary_items:
                if orig_lower in summ_item.lower():
                    preserved_count += 1
                    break

        return preserved_count / len(original_items)

    # ── Step 8: Sentiment Preservation ──────────────────────────────────

    @staticmethod
    def classify_sentiment(text: str) -> str:
        """Classify text sentiment as positive, negative, or neutral.

        Uses a simple keyword-based approach (no external NLP models needed).
        """
        positive_words = [
            "good", "great", "excellent", "amazing", "love", "happy",
            "thanks", "thank", "appreciate", "wonderful", "perfect",
            "awesome", "fantastic", "pleased", "satisfied", "positive",
        ]
        negative_words = [
            "bad", "terrible", "awful", "hate", "angry", "frustrated",
            "disappointed", "poor", "worst", "horrible", "unhappy",
            "dislike", "negative", "problem", "issue", "error", "fail",
        ]

        text_lower = text.lower()
        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)

        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        return "neutral"

    @staticmethod
    def sentiment_preservation_rate(
        original_sentiment: str, summary_sentiment: str
    ) -> float:
        """Calculate whether sentiment was preserved between original and summary.

        Returns 1.0 if sentiments match, 0.0 if they differ.
        """
        if original_sentiment == summary_sentiment:
            return 1.0
        return 0.0

    # ── Step 9: System-Level Metrics ────────────────────────────────────

    @staticmethod
    def context_utilization(tokens_used: int, total_budget: int) -> float:
        """Calculate what fraction of the context budget is used.

        Returns value in [0, 1] where 1.0 means the budget is fully utilized.
        Caps at 1.0 even if over budget.
        """
        if total_budget <= 0:
            return 0.0
        utilization = tokens_used / total_budget
        return min(utilization, 1.0)

    @staticmethod
    def compute_composite_score(scores: Dict[str, float]) -> float:
        """Compute a weighted composite score from multiple metric scores.

        Uses predefined weights for each metric type:
            - factual_consistency: 0.30 (most important)
            - entity_preservation: 0.20
            - hallucination_rate (inverted): 0.20
            - action_item_detection: 0.15
            - semantic_similarity: 0.10
            - sentiment_preservation: 0.05

        Returns value in [0, 1] representing overall compression quality.
        Returns 0.0 if no scores provided.
        """
        if not scores:
            return 0.0

        weights = {
            "factual_consistency": 0.30,
            "entity_preservation": 0.20,
            "hallucination_rate": 0.20,
            "action_item_detection": 0.15,
            "semantic_similarity": 0.10,
            "sentiment_preservation": 0.05,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        for metric, score in scores.items():
            weight = weights.get(metric, 0.05)  # Default weight for unknown metrics
            weighted_sum += score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight

    # ── Step 10: Full Evaluation Pipeline ───────────────────────────────

    @staticmethod
    def evaluate_email(
        original: str,
        summary: str,
        original_entities: Dict[str, List[str]],
        summary_entities: Dict[str, List[str]],
        original_action_items: List[str],
        summary_action_items: List[str],
    ) -> Dict[str, Any]:
        """Run all metrics on a single email compression pair.

        Returns dict with all metric scores:
            - compression_ratio: float
            - factual_consistency: float [0, 1]
            - entity_preservation_rate: float [0, 1]
            - semantic_similarity: float [0, 1]
            - hallucination_rate: float [0, 1]
            - action_item_preservation: float [0, 1]
            - sentiment_original: str
            - sentiment_summary: str
            - sentiment_preservation_rate: float [0, 1]
            - composite_score: float [0, 1]
        """
        # Individual metrics
        comp_ratio = CompressionOptimizer.compression_ratio(original, summary)
        factual = CompressionOptimizer.factual_consistency(original, summary)
        entity_rate = CompressionOptimizer.entity_preservation_rate(
            original_entities, summary_entities
        )
        semantic_sim = CompressionOptimizer.semantic_similarity_text(original, summary)
        hallucination = CompressionOptimizer.hallucination_rate(original, summary)
        action_pres = CompressionOptimizer.action_item_preservation_rate(
            original_action_items, summary_action_items
        )

        # Sentiment
        sent_orig = CompressionOptimizer.classify_sentiment(original)
        sent_summ = CompressionOptimizer.classify_sentiment(summary)
        sentiment_rate = CompressionOptimizer.sentiment_preservation_rate(
            sent_orig, sent_summ
        )

        # Composite score (invert hallucination rate so higher = better)
        scores = {
            "factual_consistency": factual,
            "entity_preservation": entity_rate,
            "hallucination_rate": 1.0 - hallucination,  # Invert: lower hallucination = higher score
            "action_item_detection": action_pres,
            "semantic_similarity": semantic_sim,
            "sentiment_preservation": sentiment_rate,
        }
        composite = CompressionOptimizer.compute_composite_score(scores)

        return {
            "compression_ratio": comp_ratio,
            "factual_consistency": factual,
            "entity_preservation_rate": entity_rate,
            "semantic_similarity": semantic_sim,
            "hallucination_rate": hallucination,
            "action_item_preservation": action_pres,
            "sentiment_original": sent_orig,
            "sentiment_summary": sent_summ,
            "sentiment_preservation_rate": sentiment_rate,
            "composite_score": composite,
        }
