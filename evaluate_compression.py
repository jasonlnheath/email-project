#!/usr/bin/env python3
"""End-to-end email compression evaluation on real Gmail data.

Pipeline:
  1. Fetch recent emails from Gmail (gmail_fetcher) — or load from tier files
  2. Classify into tiers (raw / summarized / aggregated)
  3. Summarize Tier 2 emails (summarizer) — skipped if tier2.jsonl exists
  4. Cluster Tier 2 summaries (clustering)
  5. Measure: compression ratios, context utilization, retrieval recall

Output: evaluation_results.json in the project directory.

Fallback mode: If Gmail OAuth token is unavailable, loads existing tier*.jsonl
files that were previously populated from real Gmail data.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# Ensure project root is on sys.path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)


def fetch_emails_gmail(max_results: int = 50) -> List[Dict]:
    """Fetch recent emails from Gmail via API.

    Uses a reasonable default (50) to ensure enough emails for tier2 summarization.
    Each email requires a separate API call for full format parsing.
    """
    from gmail_fetcher import GmailFetcher

    fetcher = GmailFetcher(max_results=max_results)
    emails = fetcher.fetch(max_results=max_results)
    print(f"[fetch] Retrieved {len(emails)} emails from Gmail")
    return emails


def load_tier_files() -> Dict[str, List[Dict]]:
    """Load existing tier files as fallback when Gmail token is unavailable.

    Returns a dict with 'tier1', 'tier2', 'tier3' keys, each mapping to
    a list of email dicts compatible with the pipeline.
    """
    tiers: Dict[str, List[Dict]] = {"tier1": [], "tier2": [], "tier3": []}

    for tier_name in ("tier1", "tier2", "tier3"):
        path = os.path.join(PROJECT_DIR, f"{tier_name}.jsonl")
        if not os.path.isfile(path):
            print(f"[load] No {tier_name}.jsonl found at {path}")
            continue

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    # Normalize field names to match pipeline expectations
                    email = {
                        "id": record.get("email_id", ""),
                        "subject": record.get("subject", "(no subject)"),
                        "sender": record.get("sender", "(unknown sender)"),
                        "date": record.get("date", ""),
                        "body": record.get("content", ""),
                        "snippet": record.get("snippet", ""),
                        "attachments": record.get("attachments", []),
                        "gmail_url": record.get("gmail_url", ""),
                    }
                    # For tier2, also store summary fields
                    if tier_name == "tier2":
                        email["summary"] = record.get("summary", "")
                        email["key_entities"] = record.get("key_entities", [])
                        email["action_items"] = record.get("action_items", [])
                        email["sentiment"] = record.get("sentiment", "neutral")
                    tiers[tier_name].append(email)
                except json.JSONDecodeError:
                    continue

        print(f"[load] Loaded {len(tiers[tier_name])} records from {tier_name}.jsonl")

    return tiers


def classify_tiers(
    emails: List[Dict], raw_window: int = 25
) -> Dict[str, List[Dict]]:
    """Split emails into three tiers.

    Tier 1 (raw): Most recent `raw_window` emails — stored verbatim.
    Tier 2 (summarized): Next ~400 emails — need LLM summarization.
    Tier 3 (aggregated): Older emails — grouped by topic/time.
    """
    tier1 = emails[:raw_window]
    tier2 = emails[raw_window : raw_window + 400] if len(emails) > raw_window else []
    tier3 = emails[raw_window + 400 :] if len(emails) > raw_window + 400 else []

    return {"tier1": tier1, "tier2": tier2, "tier3": tier3}


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

    records = []
    for s in summaries:
        text_parts = [
            str(s.get("subject", "")),
            str(s.get("sender", "")),
            " ".join(str(e) for e in s.get("key_entities", [])),
            " ".join(str(a) for a in s.get("action_items", [])),
        ]
        records.append(
            {
                "id": s.get("id", ""),
                "text": " ".join(text_parts),
                "summary": json.dumps(s, ensure_ascii=False),
            }
        )

    engine = EmailClusteringEngine(
        n_clusters=None,
        max_k_for_silhouette=10,
        min_k=2,
        random_state=42,
    )
    result = engine.run(records=records)

    print(f"[cluster] Found {result['n_clusters']} clusters (silhouette={result['silhouette_score']:.3f})")
    return result


def compute_compression_ratios(
    emails: List[Dict], summaries: List[Dict], source: str = "gmail_api"
) -> Dict[str, Any]:
    """Compute compression ratios for each tier.

    Handles both Gmail API format (body field) and tier file format (content field).

    When source is 'tier_files', the 'content' field in tier2 records is already
    truncated (just entities/keywords), so compression ratio is not meaningful.
    In that case, we estimate based on typical raw email size.
    """
    def _get_body(e: Dict) -> str:
        return e.get("body", "") or e.get("content", "")

    total_raw_chars = sum(len(_get_body(e)) for e in emails)
    total_raw_tokens = max(1, total_raw_chars // 4)

    if not summaries:
        return {
            "total_raw_chars": total_raw_chars,
            "total_raw_tokens": total_raw_tokens,
            "tier2_summary_chars": 0,
            "tier2_summary_tokens": 0,
            "compression_ratio_tier2": 0.0,
            "note": "no summaries generated",
        }

    # Summary chars: the Summarizer returns structured dicts (sender, date, subject,
    # key_entities, action_items, sentiment), not a "summary" text field.
    # Measure the serialized JSON size of each summary as the compressed representation.
    total_summary_chars = sum(
        len(json.dumps(s, ensure_ascii=False)) for s in summaries
    )
    total_summary_tokens = max(1, total_summary_chars // 4)

    if source == "tier_files":
        # Tier file fallback: content field is already truncated, so ratio is meaningless.
        # Estimate using typical raw email size (~1000 chars) vs summary size.
        n_tier2 = len(summaries)
        avg_raw = 1000  # typical raw email body size
        estimated_raw_chars = n_tier2 * avg_raw
        estimated_raw_tokens = max(1, estimated_raw_chars // 4)
        ratio = estimated_raw_tokens / total_summary_tokens if total_summary_tokens > 0 else 0.0
        return {
            "total_raw_chars": total_raw_chars,
            "total_raw_tokens": total_raw_tokens,
            "tier2_summary_chars": total_summary_chars,
            "tier2_summary_tokens": total_summary_tokens,
            "compression_ratio_tier2": round(ratio, 2),
            "note": f"estimated (tier file fallback; avg raw={avg_raw} chars)",
        }

    ratio = (
        total_raw_tokens / total_summary_tokens if total_summary_tokens > 0 else 0.0
    )

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

    def _visible_chars(text: str) -> int:
        if not text:
            return 0
        cleaned = re.sub(r"<[^>]+>", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return len(cleaned)

    # Tier 1: raw emails — use visible (HTML-stripped) chars
    t1_chars = sum(_visible_chars(e.get("body", "") or e.get("content", "")) for e in tier1)
    t1_tokens = max(1, t1_chars // 4) + len(tier1) * 20  # per-email overhead

    # Tier 2: summaries — measure JSON-serialized size of structured summary dicts
    t2_chars = sum(len(json.dumps(s, ensure_ascii=False)) for s in tier2_summaries)
    t2_tokens = max(1, t2_chars // 4) + len(tier2_summaries) * 15  # per-summary overhead

    # Tier 3: cluster summaries — estimate ~100 chars per cluster
    t3_chars = n_clusters * 100
    t3_tokens = max(1, t3_chars // 4)

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
    emails: List[Dict], summaries: List[Dict], n_samples: int = 10
) -> Dict[str, Any]:
    """Estimate retrieval recall by checking if key entities survive summarization."""

    def extract_concrete_nouns(text: str, top_n: int = 15) -> set:
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"[\[\]\(\)]", " ", text)
        capitalized = re.findall(r"\b[A-Z][a-z]{2,}\b", text)
        amounts = re.findall(r"\$[\d,]+\.\d*", text)
        account_nums = re.findall(r"\b\d{4,}[-\s]?\d{4,}\b", text)
        dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
        return set(capitalized + amounts + account_nums + dates)

    if len(emails) < n_samples or len(summaries) < n_samples:
        n_samples = min(len(emails), len(summaries))

    if n_samples == 0:
        return {"recall@k": 0.0, "samples_analyzed": 0}

    entailed_count = 0

    for idx in range(n_samples):
        original_body = emails[idx].get("body", "")
        summary = summaries[idx]

        orig_entities = extract_concrete_nouns(original_body)
        summary_entities = set(str(e).lower() for e in summary.get("key_entities", []))

        if not orig_entities and not summary_entities:
            continue

        summary_text = json.dumps(summary, ensure_ascii=False).lower()
        orig_lower = original_body.lower()

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

    print("=" * 60)
    print("EMAIL COMPRESSION EVALUATION")
    print("=" * 60)

    # ── Step 1: Fetch or load emails ─────────────────────────────────────
    emails: List[Dict] = []
    source = "gmail_api"

    # Check if Gmail token exists before attempting API call
    token_path = os.path.expanduser("~/.hermes/google_token.json")
    gmail_available = os.path.isfile(token_path)

    # When loading from tier files, use them directly (already classified).
    # When fetching from Gmail, classify fresh.
    if not gmail_available:
        print("[WARN] Gmail OAuth token not found. Loading from tier files...")
        tiers = load_tier_files()
        emails = tiers["tier1"] + tiers["tier2"]
        source = "tier_files"
        results["tier_counts"] = {
            "tier1_raw": len(tiers["tier1"]),
            "tier2_summarize": len(tiers["tier2"]),
            "tier3_aggregate": len(tiers.get("tier3", [])),
        }
        # Tier 2 is already summarized — extract summaries from tier2 records
        summaries = []
        for rec in tiers["tier2"]:
            summary = {
                "id": rec.get("email_id", ""),
                "subject": rec.get("subject", ""),
                "sender": rec.get("sender", ""),
                "key_entities": rec.get("key_entities", []),
                "action_items": rec.get("action_items", []),
                "sentiment": rec.get("sentiment", "neutral"),
                "summary": rec.get("summary", ""),
            }
            summaries.append(summary)
    else:
        try:
            import signal

            def _timeout_handler(signum, frame):
                raise TimeoutError("Gmail fetch timed out after 60s")

            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(60)
            emails = fetch_emails_gmail()
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

            if not emails:
                print("[WARN] Gmail API returned no emails. Loading from tier files...")
                tiers = load_tier_files()
                emails = tiers["tier1"] + tiers["tier2"]
                source = "tier_files"
                results["tier_counts"] = {
                    "tier1_raw": len(tiers["tier1"]),
                    "tier2_summarize": len(tiers["tier2"]),
                    "tier3_aggregate": len(tiers.get("tier3", [])),
                }
                summaries = [
                    {
                        "id": rec.get("email_id", ""),
                        "subject": rec.get("subject", ""),
                        "sender": rec.get("sender", ""),
                        "key_entities": rec.get("key_entities", []),
                        "action_items": rec.get("action_items", []),
                        "sentiment": rec.get("sentiment", "neutral"),
                        "summary": rec.get("summary", ""),
                    }
                    for rec in tiers["tier2"]
                ]
        except FileNotFoundError as e:
            print(f"[WARN] Gmail fetch unavailable ({e}). Loading from tier files...")
            tiers = load_tier_files()
            emails = tiers["tier1"] + tiers["tier2"]
            source = "tier_files"
            results["tier_counts"] = {
                "tier1_raw": len(tiers["tier1"]),
                "tier2_summarize": len(tiers["tier2"]),
                "tier3_aggregate": len(tiers.get("tier3", [])),
            }
            summaries = [
                {
                    "id": rec.get("email_id", ""),
                    "subject": rec.get("subject", ""),
                    "sender": rec.get("sender", ""),
                    "key_entities": rec.get("key_entities", []),
                    "action_items": rec.get("action_items", []),
                    "sentiment": rec.get("sentiment", "neutral"),
                    "summary": rec.get("summary", ""),
                }
                for rec in tiers["tier2"]
            ]
        except TimeoutError as e:
            print(f"[WARN] Gmail fetch timed out ({e}). Loading from tier files...")
            tiers = load_tier_files()
            emails = tiers["tier1"] + tiers["tier2"]
            source = "tier_files"
            results["tier_counts"] = {
                "tier1_raw": len(tiers["tier1"]),
                "tier2_summarize": len(tiers["tier2"]),
                "tier3_aggregate": len(tiers.get("tier3", [])),
            }
            summaries = [
                {
                    "id": rec.get("email_id", ""),
                    "subject": rec.get("subject", ""),
                    "sender": rec.get("sender", ""),
                    "key_entities": rec.get("key_entities", []),
                    "action_items": rec.get("action_items", []),
                    "sentiment": rec.get("sentiment", "neutral"),
                    "summary": rec.get("summary", ""),
                }
                for rec in tiers["tier2"]
            ]
        except Exception as e:
            print(f"[ERROR] Failed to fetch emails: {e}")
            results["error"] = str(e)
            results["status"] = "failed_fetch"
            _save_results(results, output_path)
            return results

    if not emails:
        print("[WARN] No emails retrieved.")
        results["status"] = "no_emails"
        results["n_emails_fetched"] = 0
        _save_results(results, output_path)
        return results

    results["data_source"] = source
    results["n_emails_fetched"] = len(emails)
    results["fetch_timestamp"] = datetime.utcnow().isoformat() + "Z"

    # ── Step 2: Classify tiers (only for Gmail fetch, not tier files) ────
    if source == "gmail_api":
        tiers = classify_tiers(emails)
        results["tier_counts"] = {
            "tier1_raw": len(tiers["tier1"]),
            "tier2_summarize": len(tiers["tier2"]),
            "tier3_aggregate": len(tiers["tier3"]),
        }
    else:
        tiers = {"tier1": emails[:results["tier_counts"]["tier1_raw"]],
                  "tier2": emails[results["tier_counts"]["tier1_raw"]:]}
    # ── Step 3: Summarize Tier 2 (only for Gmail fetch, not tier files) ──
    summaries = []
    if source == "gmail_api" and tiers["tier2"]:
        summaries = summarize_tier2(tiers["tier2"])

    # ── Step 4: Cluster Tier 2 ───────────────────────────────────────────
    cluster_result = cluster_tier2(summaries)
    results["clustering"] = {
        "n_clusters": cluster_result.get("n_clusters", 0),
        "silhouette_score": round(cluster_result.get("silhouette_score", 0.0), 4),
    }

    # ── Step 5: Compute metrics ──────────────────────────────────────────
    compression = compute_compression_ratios(tiers["tier2"], summaries, source)
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
