#!/usr/bin/env python3
"""Test tier 2 (summarization) and tier 3 (clustering) with 10 emails."""

import json
import os
import sys
from pathlib import Path

# Add project dir to path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from summarizer import Summarizer
from clustering import EmailClusteringEngine
from retrieval import QueryRouter, RetrievalPipeline


def load_tier1(path=None):
    """Load tier1.jsonl records."""
    if path is None:
        path = PROJECT_DIR / "tier1.jsonl"
    records = []
    with open(path) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def test_summarization(tier1_records, n=10):
    """Summarize n emails using LLM and write to tier2.jsonl."""
    print(f"\n{'='*60}")
    print(f"TESTING TIER 2: Summarizing {n} emails")
    print(f"{'='*60}")
    
    # Take first n emails (most recent)
    emails = tier1_records[:n]
    
    # Initialize summarizer
    summarizer = Summarizer()
    
    # Summarize each email
    summaries = []
    for i, email in enumerate(emails):
        print(f"[{i+1}/{n}] Summarizing: {email.get('subject', '')[:60]}...")
        try:
            summary = summarizer.summarize(email)
            record = {
                "email_id": email.get("email_id", ""),
                "subject": email.get("subject", ""),
                "sender": email.get("sender", ""),
                "date": email.get("date", ""),
                "summary": f"{email.get('subject', '')}: {', '.join(summary.get('key_entities', []))}",
                "content": f"{email.get('subject', '')} {' '.join(summary.get('key_entities', []))} {' '.join(summary.get('action_items', []))}",
                "gmail_url": email.get("gmail_url", ""),
                "key_entities": summary.get("key_entities", []),
                "action_items": summary.get("action_items", []),
                "sentiment": summary.get("sentiment", "neutral"),
                "has_action_required": len(summary.get("action_items", [])) > 0,
                "tier": "tier2",
            }
            summaries.append(record)
            print(f"  Entities: {summary.get('key_entities', [])}")
            print(f"  Actions: {summary.get('action_items', [])}")
        except Exception as e:
            print(f"  ERROR: {e}")
            # Fallback to simple summary
            record = {
                "email_id": email.get("email_id", ""),
                "subject": email.get("subject", ""),
                "sender": email.get("sender", ""),
                "date": email.get("date", ""),
                "summary": f"{email.get('subject', '')}: {email.get('content', '')[:200]}",
                "content": email.get("content", ""),
                "gmail_url": email.get("gmail_url", ""),
                "key_entities": [],
                "action_items": [],
                "sentiment": "neutral",
                "has_action_required": False,
                "tier": "tier2",
            }
            summaries.append(record)
    
    # Write tier2.jsonl
    tier2_path = PROJECT_DIR / "tier2.jsonl"
    with open(tier2_path, "w") as f:
        for record in summaries:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    print(f"\nWrote {len(summaries)} summaries to {tier2_path}")
    return summaries


def test_clustering(summaries):
    """Cluster summaries into tier3."""
    print(f"\n{'='*60}")
    print(f"TESTING TIER 3: Clustering {len(summaries)} summaries")
    print(f"{'='*60}")
    
    # Initialize clustering engine
    engine = EmailClusteringEngine(n_clusters=min(5, len(summaries)))
    
    # Extract texts for TF-IDF
    texts = [s.get("summary", "") or s.get("content", "") for s in summaries]
    
    # Build TF-IDF matrix
    from sklearn.feature_extraction.text import TfidfVectorizer
    vectorizer = TfidfVectorizer(
        lowercase=True, stop_words="english",
        ngram_range=(1, 2), max_features=100,
    )
    tfidf_matrix = vectorizer.fit_transform([t for t in texts if t])
    
    # Cluster
    labels = engine.cluster(tfidf_matrix)
    
    # Group by cluster
    clusters = {}
    for i, label in enumerate(labels):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(summaries[i])
    
    # Write tier3.jsonl
    tier3_path = PROJECT_DIR / "tier3.jsonl"
    with open(tier3_path, "w") as f:
        for cluster_id, emails in clusters.items():
            record = {
                "cluster_id": f"cluster_{cluster_id}",
                "summary": f"Cluster of {len(emails)} emails",
                "emails": [e.get("email_id", "") for e in emails],
                "gmail_urls": [e.get("gmail_url", "") for e in emails],
                "tier": "tier3",
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    print(f"Wrote {len(clusters)} clusters to {tier3_path}")
    return clusters


def test_retrieval():
    """Test retrieval on tier2 and tier3."""
    print(f"\n{'='*60}")
    print(f"TESTING RETRIEVAL: Querying all tiers")
    print(f"{'='*60}")
    
    pipeline = RetrievalPipeline()
    
    # Test queries
    queries = [
        "dura-pilot",
        "thermal analysis",
        "meeting tomorrow",
        "urgent deadline",
    ]
    
    for query in queries:
        print(f"\nQuery: '{query}'")
        results = pipeline.query(query, top_k=5)
        print(f"  Hits: {len(results.get('hits', []))}")
        print(f"  Pruned: {len(results.get('pruned', []))}")
        if results.get("hits"):
            for hit in results["hits"][:3]:
                print(f"    - [{hit.get('tier', '?')}] {hit.get('subject', '')[:50]}... (score: {hit.get('score', 0):.2f})")


def main():
    """Run full test."""
    # Load tier1
    tier1 = load_tier1()
    print(f"Loaded {len(tier1)} emails from tier1.jsonl")
    
    # Test tier2 summarization
    summaries = test_summarization(tier1, n=10)
    
    # Test tier3 clustering
    clusters = test_clustering(summaries)
    
    # Test retrieval
    test_retrieval()
    
    print(f"\n{'='*60}")
    print("TEST COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
