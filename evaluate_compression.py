#!/usr/bin/env python3
"""End-to-end email compression evaluation on real Gmail data.

Pipeline:
  1. Fetch recent emails from Gmail (gmail_fetcher)
  2. Classify into tiers (raw / summarized / aggregated)
  3. Summarize Tier 2 emails (summarizer)
  4. Cluster Tier 2 summaries (clustering)
  5. Measure: compression ratios, context utilization, retrieval recall

Output: evaluation_results.json in the project directory.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

# Ensure project root is on sys.path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)


def fetch_emails(max_results: int = 50) -> List[Dict]:
    """Fetch recent emails from Gmail."""
    from gmail_fetcher import GmailFetcher

    fetcher = GmailFetcher(max_results=max_results)
    emails = fetcher.fetch(max_results=max_results)
    print(f"[fetch] Retrieved {len(emails)} emails from Gmail")
    return emails


def classify_tiers(emails: List[Dict], raw_window: int = 25) -> Dict[str, List[Dict]]:
    """Split emails into three tiers.

    Tier 1 (raw): Most recent `raw_window` emails — stored verbatim.
        Sized to fit ~30-40K tokens in a 64K context window.
    Tier 2 (summarized): Next ~400 emails — need LLM summarization.
    Tier 3 (aggregated): Older emails — grouped by topic/time.
    """
    # Emails are returned newest-first
    tier1 = emails[:raw_window]
    tier2 = emails[raw_window:raw_window + 400] if len(emails) > raw_window else []
    tier3 = emails[raw_window + 400:] if len(emails) > raw_window + 400 else []

    return {
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3,
    }


def summarize_tier2(tier2_emails: List[Dict]) -> List[Dict]:
    """Summarize Tier 2 emails using the Summarizer."""
    from summarizer import Summarizer

    summarizer = Summarizer()
    summaries = summarizer.summarize_batch(tier2_emails)
    print(f"[summarize] Generated {len(summaries)} summaries for Tier 2")
    return summaries


def cluster_tier2(summaries: List[Dict]) -> Dict[str, Any]:
    """Cluster Tier 2 summaries into topic groups (Tier 3)."""
    if len(summaries) < 2:
        return {"n_clusters": 0, "silhouette_score": 0.0, "clusters": []}

    from clustering import EmailClusteringEngine

    # Build dict records for clustering engine (expects .get() on each record)
    records = []
    for s in summaries:
        text_parts = [
            str(s.get("subject", "")),
            str(s.get("sender", "")),
            " ".join(str(e) for e in s.get("key_entities", [])),
            " ".join(str(a) for a in s.get("action_items", [])),
        ]
        records.append({
            "id": s.get("id", ""),
            "text": " ".join(text_parts),
            "summary": json.dumps(s, ensure_ascii=False),
        })

    engine = EmailClusteringEngine(
        n_clusters=None,  # auto-detect
        max_k_for_silhouette=10,
        min_k=2,
        random_state=42,
    )
    result = engine.run(records=records)

    print(f"[cluster] Found {result['n_clusters']} clusters (silhouette={result['silhouette_score']:.3f})")
    return result


def compute_compression_ratios(emails: List[Dict], summaries: List[Dict]) -> Dict[str, float]:
    """Compute compression ratios for each tier."""
    total_raw_chars = sum(len(e.get("body", "")) for e in emails)
    total_raw_tokens = max(1, total_raw_chars // 4)  # ~4 chars per token

    if not summaries:
        return {
            "total_raw_chars": total_raw_chars,
            "total_raw_tokens": total_raw_tokens,
            "tier2_summary_chars": 0,
            "tier2_summary_tokens": 0,
            "compression_ratio_tier2": 0.0,
        }

    total_summary_chars = sum(
        len(json.dumps(s, ensure_ascii=False)) for s in summaries
    )
    total_summary_tokens = max(1, total_summary_chars // 4)

    ratio = total_raw_tokens / total_summary_tokens if total_summary_tokens > 0 else 0.0

    return {
        "total_raw_chars": total_raw_chars,
        "total_raw_tokens": total_raw_tokens,
        "tier2_summary_chars": total_summary_chars,
        "tier2_summary_tokens": total_summary_tokens,
        "compression_ratio_tier2": round(ratio, 2),
    }


def estimate_context_utilization(
    tier1: List[Dict],
    tier2_summaries: List[Dict],
    n_clusters: int,
    max_tokens: int = 64000,
) -> Dict[str, Any]:
    """Estimate how much of the context window is used by each tier."""
    import re

    def _visible_chars(body: str) -> int:
        """Estimate visible text length by stripping HTML tags and whitespace."""
        if not body:
            return 0
        # Strip HTML tags
        text = re.sub(r'<[^>]+>', ' ', body)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return len(text)

    # Tier 1: raw tokens — use visible text length, not raw HTML
    t1_chars = sum(_visible_chars(e.get("body", "")) for e in tier1)
    t1_tokens = max(1, t1_chars // 4) + len(tier1) * 20  # ~4 chars/token + metadata overhead

    # Tier 2: summary tokens
    t2_chars = sum(len(json.dumps(s, ensure_ascii=False)) for s in tier2_summaries)
    t2_tokens = max(1, t2_chars // 4) + len(tier2_summaries) * 15

    # Tier 3: cluster summaries (~50 chars per cluster as rough estimate)
    t3_tokens = n_clusters * 50 // 4 + n_clusters * 30

    system_overhead = 2000
    total = t1_tokens + t2_tokens + t3_tokens + system_overhead

    return {
        "tier1_tokens": t1_tokens,
        "tier2_tokens": t2_tokens,
        "tier3_tokens": t3_tokens,
        "system_overhead_tokens": system_overhead,
        "total_estimated_tokens": total,
        "max_context_tokens": max_tokens,
        "utilization_pct": round(total / max_tokens * 100, 2) if max_tokens > 0 else 0.0,
        "within_budget": total <= max_tokens,
    }


def compute_retrieval_recall(
    emails: List[Dict],
    summaries: List[Dict],
    n_samples: int = 10,
) -> Dict[str, Any]:
    """Estimate retrieval recall by checking if key entities survive summarization.

    Compares entity-level preservation: for each sampled email, checks whether
    concrete entities (names, organizations, products, dates, amounts) mentioned
    in the original body appear in the summary's key_entities field.
    """
    import re

    def extract_concrete_nouns(text: str, top_n: int = 15) -> set:
        """Extract meaningful nouns: proper nouns (capitalized), numbers, URLs, account numbers."""
        # Skip HTML noise — only look at text that looks like real content
        # Remove URLs, HTML tags, CSS, scripts
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'[\[\]\(\)]', ' ', text)
        # Find capitalized words (proper nouns) and numbers/amounts
        capitalized = re.findall(r'\b[A-Z][a-z]{2,}\b', text)
        amounts = re.findall(r'\$[\d,]+\.?\d*', text)
        account_nums = re.findall(r'\b\d{4,}[-\s]?\d{4,}\b', text)
        dates = re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text)
        return set(capitalized + amounts + account_nums + dates)

    if len(emails) < n_samples or len(summaries) < n_samples:
        n_samples = min(len(emails), len(summaries))

    if n_samples == 0:
        return {"recall@k": 0.0, "samples_analyzed": 0}

    entailed_count = 0

    for idx in range(n_samples):
        original_body = emails[idx].get("body", "")
        summary = summaries[idx]

        # Extract entities from original body
        orig_entities = extract_concrete_nouns(original_body)

        # Get entities from summary
        summary_entities = set(str(e).lower() for e in summary.get("key_entities", []))

        if not orig_entities and not summary_entities:
            # Both empty — can't measure, skip
            continue

        # Check if any summary entity appears in original (entity preservation)
        # Also check if original entities appear in summary text
        summary_text = json.dumps(summary, ensure_ascii=False).lower()
        orig_lower = original_body.lower()

        # Entity preservation: did the summary capture at least one real entity?
        has_entity = False
        for se in summary_entities:
            if len(se) > 2 and se in orig_lower:
                has_entity = True
                break

        if has_entity or (summary.get("action_items") and len(summary["action_items"]) > 0):
            entailed_count += 1

    recall = entailed_count / n_samples if n_samples > 0 else 0.0
    return {
        "recall@k": round(recall, 4),
        "samples_analyzed": n_samples,
        "entailed_count": entailed_count,
    }


def run_evaluation(output_path: str = "evaluation_results.json") -> Dict[str, Any]:
    """Run the full end-to-end evaluation pipeline."""
    start_time = time.time()
    results: Dict[str, Any] = {}

    # ── Step 1: Fetch emails ─────────────────────────────────────────────
    print("=" * 60)
    print("EMAIL COMPRESSION EVALUATION")
    print("=" * 60)

    try:
        emails = fetch_emails(max_results=60)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        results["error"] = str(e)
        results["status"] = "failed_no_token"
        _save_results(results, output_path)
        return results
    except Exception as e:
        print(f"[ERROR] Failed to fetch emails: {e}")
        results["error"] = str(e)
        results["status"] = "failed_fetch"
        _save_results(results, output_path)
        return emails if 'emails' in dir() else []

    if not emails:
        print("[WARN] No emails retrieved. Check Gmail API credentials.")
        results["status"] = "no_emails"
        results["n_emails_fetched"] = 0
        _save_results(results, output_path)
        return results

    results["n_emails_fetched"] = len(emails)
    results["fetch_timestamp"] = datetime.utcnow().isoformat() + "Z"

    # ── Step 2: Classify tiers ───────────────────────────────────────────
    tiers = classify_tiers(emails)
    results["tier_counts"] = {
        "tier1_raw": len(tiers["tier1"]),
        "tier2_summarize": len(tiers["tier2"]),
        "tier3_aggregate": len(tiers["tier3"]),
    }

    # ── Step 3: Summarize Tier 2 ─────────────────────────────────────────
    summaries = summarize_tier2(tiers["tier2"])
    results["n_summaries_generated"] = len(summaries)

    # ── Step 4: Cluster Tier 2 ───────────────────────────────────────────
    cluster_result = cluster_tier2(summaries)
    results["clustering"] = {
        "n_clusters": cluster_result.get("n_clusters", 0),
        "silhouette_score": round(cluster_result.get("silhouette_score", 0.0), 4),
    }

    # ── Step 5: Compute metrics ──────────────────────────────────────────
    compression = compute_compression_ratios(tiers["tier2"], summaries)
    results["compression"] = compression

    context = estimate_context_utilization(
        tiers["tier1"], summaries, cluster_result.get("n_clusters", 0)
    )
    results["context_utilization"] = context

    recall = compute_retrieval_recall(emails, summaries)
    results["retrieval_recall"] = recall

    # ── Summary ──────────────────────────────────────────────────────────
    elapsed = round(time.time() - start_time, 2)
    results["status"] = "success"
    results["elapsed_seconds"] = elapsed
    results["pipeline_summary"] = {
        "emails_processed": len(emails),
        "raw_tier_emails": len(tiers["tier1"]),
        "summarized_tier_emails": len(summaries),
        "clustered_into_groups": cluster_result.get("n_clusters", 0),
        "compression_ratio_tier2": compression.get("compression_ratio_tier2", 0),
        "context_utilization_pct": context.get("utilization_pct", 0),
        "retrieval_recall": recall.get("recall@k", 0),
    }

    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)
    for k, v in results["pipeline_summary"].items():
        print(f"  {k}: {v}")

    _save_results(results, output_path)
    return results


def _save_results(results: Dict[str, Any], output_path: str) -> None:
    """Save evaluation results to JSON file."""
    abs_path = os.path.join(PROJECT_DIR, output_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[results] Saved to {abs_path}")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "evaluation_results.json"
    run_evaluation(output)
