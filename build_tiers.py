#!/usr/bin/env python3
"""Build tier JSONL files from Gmail data.

This script:
1. Fetches emails from Gmail using gmail_fetcher
2. Classifies them into tiers (tier1/tier2/tier3)
3. Writes them to tier1.jsonl, tier2.jsonl, tier3.jsonl with correct schema

Usage:
    python3 build_tiers.py [--max-results N] [--summarize] [--cluster]

The --summarize flag runs LLM summarization for tier2 emails.
The --cluster flag clusters tier2 emails into tier3 groups.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

# Add project dir to path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from gmail_fetcher import GmailFetcher
from compression import CompressionOptimizer
from clustering import EmailClusteringEngine
from resummarize import ResummarizationEngine


def fetch_emails(max_results=500):
    """Fetch emails from Gmail and return parsed records."""
    print(f"[build_tiers] Fetching up to {max_results} emails...")
    fetcher = GmailFetcher(max_results=max_results)
    emails = fetcher.fetch()
    print(f"[build_tiers] Fetched {len(emails)} emails")
    return emails


def classify_tiers(emails, tier2_threshold=500, tier3_threshold=1000):
    """Classify emails into tiers based on recency.

    Tier 1: Most recent emails (raw, full content)
    Tier 2: Next batch (summarized)
    Tier 3: Oldest emails (clustered/aggregated)
    """
    # Sort by date descending (newest first)
    sorted_emails = sorted(
        emails,
        key=lambda e: e.get("date", ""),
        reverse=True,
    )

    tier1 = []
    tier2 = []
    tier3 = []

    for i, email in enumerate(sorted_emails):
        if i < tier2_threshold:
            tier1.append(email)
        elif i < tier3_threshold:
            tier2.append(email)
        else:
            tier3.append(email)

    print(f"[build_tiers] Tier classification:")
    print(f"  Tier 1 (raw): {len(tier1)} emails")
    print(f"  Tier 2 (summarize): {len(tier2)} emails")
    print(f"  Tier 3 (cluster): {len(tier3)} emails")

    return {"tier1": tier1, "tier2": tier2, "tier3": tier3}


def atomic_write(path: str, records: list):
    """Write JSONL records atomically using temp file + rename.
    
    Prevents data loss if the process crashes mid-write — the original
    file is only replaced after the full write succeeds.
    """
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        shutil.move(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_tier_files(tiers, output_dir=PROJECT_DIR):
    """Write tier data to JSONL files with correct schema."""
    # Tier 1: raw emails with body content and gmail_url
    tier1_records = []
    for email in tiers["tier1"]:
        record = {
            "email_id": email.get("id", ""),
            "subject": email.get("subject", ""),
            "sender": email.get("sender", ""),
            "date": email.get("date", ""),
            "content": email.get("body", ""),  # ← This is the key field!
            "gmail_url": email.get("gmail_url", ""),  # ← Gmail link
            "snippet": email.get("snippet", ""),
            "attachments": email.get("attachments", []),
            "has_action_required": False,
            "tier": "tier1",
        }
        tier1_records.append(record)

    # Tier 2: will be populated after summarization
    tier2_records = []

    # Tier 3: will be populated after clustering
    tier3_records = []

    # Write tier1
    tier1_path = os.path.join(output_dir, "tier1.jsonl")
    atomic_write(tier1_path, tier1_records)
    print(f"[build_tiers] Wrote {len(tier1_records)} records to {tier1_path}")

    # Write empty tier2/tier3 (will be filled if --summarize/--cluster)
    tier2_path = os.path.join(output_dir, "tier2.jsonl")
    atomic_write(tier2_path, tier2_records)
    print(f"[build_tiers] Wrote {len(tier2_records)} records to {tier2_path}")

    tier3_path = os.path.join(output_dir, "tier3.jsonl")
    atomic_write(tier3_path, tier3_records)
    print(f"[build_tiers] Wrote {len(tier3_records)} records to {tier3_path}")

    return tier1_records, tier2_records, tier3_records


def summarize_tier2(tier2_emails, output_dir=PROJECT_DIR):
    """Summarize tier2 emails and write to tier2.jsonl."""
    if not tier2_emails:
        print("[build_tiers] No tier2 emails to summarize.")
        return []

    print(f"[build_tiers] Summarizing {len(tier2_emails)} tier2 emails...")

    # Use the compression optimizer for summarization
    optimizer = CompressionOptimizer()

    # Build prompts for each email
    prompts = []
    for email in tier2_emails:
        body = email.get("body", "")
        subject = email.get("subject", "")
        sender = email.get("sender", "")
        date = email.get("date", "")

        prompt = f"""Summarize this email concisely. Include:
- Sender: {sender}
- Date: {date}
- Subject: {subject}
- Key points and action items

Email body:
{body[:2000]}  # Truncate very long bodies

Return JSON with fields: summary, key_entities, action_items, sentiment"""
        prompts.append((email, prompt))

    # For now, use a simple summarization approach
    # In production, this would call the LLM
    summaries = []
    for email, prompt in prompts:
        # Placeholder: use subject + first line of body as summary
        body = email.get("body", "")
        summary = f"{email.get('subject', '')}: {body.split(chr(10))[0] if body else 'No content'}"

        record = {
            "email_id": email.get("id", ""),
            "subject": email.get("subject", ""),
            "sender": email.get("sender", ""),
            "date": email.get("date", ""),
            "summary": summary,
            "content": summary,  # Also put in content for search
            "gmail_url": email.get("gmail_url", ""),
            "key_entities": [],
            "action_items": [],
            "sentiment": "neutral",
            "has_action_required": False,
            "tier": "tier2",
        }
        summaries.append(record)

    # Write tier2
    tier2_path = os.path.join(output_dir, "tier2.jsonl")
    atomic_write(tier2_path, summaries)
    print(f"[build_tiers] Wrote {len(summaries)} summaries to {tier2_path}")

    return summaries


def cluster_tier2(summaries, output_dir=PROJECT_DIR):
    """Cluster tier2 summaries and write to tier3.jsonl."""
    if not summaries:
        print("[build_tiers] No summaries to cluster.")
        return []

    print(f"[build_tiers] Clustering {len(summaries)} summaries...")

    # Use the clustering engine
    engine = EmailClusteringEngine(n_clusters=10)
    clusters = engine.cluster(summaries)

    # Write tier3
    tier3_path = os.path.join(output_dir, "tier3.jsonl")
    atomic_write(tier3_path, clusters)
    print(f"[build_tiers] Wrote {len(clusters)} clusters to {tier3_path}")

    return clusters


def main():
    parser = argparse.ArgumentParser(description="Build tier JSONL files from Gmail")
    parser.add_argument(
        "--max-results",
        type=int,
        default=500,
        help="Maximum number of emails to fetch (default: 500)",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Run LLM summarization for tier2 emails",
    )
    parser.add_argument(
        "--cluster",
        action="store_true",
        help="Cluster tier2 emails into tier3 groups",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=PROJECT_DIR,
        help="Output directory for tier files (default: project dir)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("BUILDING EMAIL TIERS")
    print("=" * 60)

    # Step 1: Fetch emails
    emails = fetch_emails(max_results=args.max_results)

    if not emails:
        print("[ERROR] No emails fetched. Check Gmail API credentials.")
        sys.exit(1)

    # Step 2: Classify tiers
    tiers = classify_tiers(emails)

    # Step 3: Write tier files
    tier1_records, tier2_records, tier3_records = write_tier_files(tiers, args.output_dir)

    # Step 4: Summarize tier2 (optional)
    if args.summarize:
        tier2_records = summarize_tier2(tiers["tier2"], args.output_dir)

    # Step 5: Cluster tier2 (optional)
    if args.cluster and args.summarize:
        cluster_tier2(tier2_records, args.output_dir)

    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print(f"Tier 1: {len(tier1_records)} raw emails")
    print(f"Tier 2: {len(tier2_records)} summaries")
    print(f"Tier 3: {len(tier3_records)} clusters")


if __name__ == "__main__":
    main()