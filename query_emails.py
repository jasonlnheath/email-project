#!/usr/bin/env python3
"""Standalone email query tool — transparent hit/prune display with Gmail links.

Usage:
    python query_emails.py "dura-pilot thermal analysis"
    python query_emails.py "what did Sean say?" --top-k 5
    python query_emails.py "dura-pilot" --exclude msg_001
    python query_emails.py "dura-pilot" --include msg_002 --exclude msg_003
    python query_emails.py "dura-pilot" --interactive   # nudge interactively

Features:
- Shows ALL candidates found (hits + pruned) with scores
- Gmail links on every result for click-through
- Nudge support: exclude/include specific emails
- No agent loop — pure Python, fast and token-efficient
"""

import argparse
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from retrieval import RetrievalPipeline


def format_result(result, label="HIT"):
    """Format a single result record for display."""
    lines = []
    gmail_url = result.get("gmail_url") or result.get("gmail_urls", [""])[0]
    link_str = f"  Gmail: {gmail_url}" if gmail_url else "  Gmail: [no link]"
    lines.append(f"  [{label}] ID:{result['id']} | Score:{result['score']:.4f} | Tier:{result['tier']}")
    lines.append(link_str)
    # Truncate content to ~200 chars for readability
    content = result.get("content", "")[:200]
    if len(result.get("content", "")) > 200:
        content += "..."
    lines.append(f"  {content}")
    return "\n".join(lines)


def display_results(query_result, show_pruned=True):
    """Display query results with transparency."""
    print(f"\n{'='*70}")
    print(f"QUERY: {query_result['query']}")
    print(f"Intent: {query_result['intent']} | Tiers searched: {query_result['tiers_searched']}")
    meta = query_result.get("metadata", {})
    print(f"Candidates found: {meta.get('total_candidates', '?')} | "
          f"Hits: {meta.get('hits_returned', '?')} | Pruned: {meta.get('pruned_count', '?')}")
    print(f"{'='*70}\n")

    # Hits
    hits = query_result.get("hits", [])
    if hits:
        print(f"--- HITS (top {len(hits)}) ---\n")
        for i, hit in enumerate(hits, 1):
            print(f"{i}. {format_result(hit, 'HIT')}")
            print()
    else:
        print("No hits found.\n")

    # Pruned
    if show_pruned:
        pruned = query_result.get("pruned", [])
        if pruned:
            print(f"--- PRUNED ({len(pruned)} results dropped) ---\n")
            for i, p in enumerate(pruned, 1):
                print(f"{i}. {format_result(p, 'PRUNED')}")
                print()
        else:
            print("No results were pruned (all candidates shown as hits).\n")

    # Nudge options
    nudge_opts = query_result.get("nudge_options", {})
    all_ids = nudge_opts.get("exclude_ids", [])
    if all_ids:
        print(f"Nudge IDs available: {', '.join(all_ids[:10])}" +
              ("..." if len(all_ids) > 10 else ""))


def interactive_nudge(pipeline, initial_query):
    """Interactive mode: show results, let user nudge."""
    nudge = {}
    query = initial_query

    while True:
        result = pipeline.query(query, top_k=5, nudge=nudge if nudge else None)
        display_results(result)

        print("\nCommands:")
        print("  e <id>   — exclude email from hits")
        print("  i <id>   — include/force email into hits")
        print("  q        — quit")
        print("  r <query> — run new query")
        cmd = input("> ").strip()

        parts = cmd.split()
        if not parts:
            continue

        action = parts[0].lower()

        if action == "q":
            break
        elif action == "r" and len(parts) > 1:
            query = " ".join(parts[1:])
            nudge = {}  # Reset nudges for new query
        elif action in ("e", "i") and len(parts) > 1:
            eid = parts[1]
            if action == "e":
                nudge.setdefault("exclude_ids", []).append(eid)
                print(f"  Excluded: {eid}")
            else:
                nudge.setdefault("include_ids", []).append(eid)
                print(f"  Included: {eid}")
        else:
            print(f"Unknown command: {cmd}")


def main():
    parser = argparse.ArgumentParser(
        description="Query email index with transparent hit/prune display.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python query_emails.py "dura-pilot thermal analysis"
  python query_emails.py "what did Sean say?" --top-k 5
  python query_emails.py "dura-pilot" --exclude msg_001
  python query_emails.py "dura-pilot" --interactive

Nudge options:
  --exclude ID   Exclude an email ID from hits
  --include ID   Force-include an email ID in hits
  --interactive  Interactive mode for nudging
        """,
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument("--top-k", type=int, default=5, help="Number of hits to show (default: 5)")
    parser.add_argument("--exclude", action="append", default=[], help="Email IDs to exclude")
    parser.add_argument("--include", action="append", default=[], help="Email IDs to force-include")
    parser.add_argument("--interactive", action="store_true", help="Interactive nudge mode")
    parser.add_argument("--no-pruned", action="store_true", help="Hide pruned results")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted")

    args = parser.parse_args()

    # Initialize pipeline
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config = {
        "tier1_path": os.path.join(base_dir, "tier1.jsonl"),
        "tier2_path": os.path.join(base_dir, "tier2.jsonl"),
        "tier3_path": os.path.join(base_dir, "tier3.jsonl"),
    }
    pipeline = RetrievalPipeline(config)

    # Build nudge dict
    nudge = {}
    if args.exclude:
        nudge["exclude_ids"] = args.exclude
    if args.include:
        nudge["include_ids"] = args.include

    # Run query
    result = pipeline.query(args.query, top_k=args.top_k, nudge=nudge if nudge else None)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    elif args.interactive:
        interactive_nudge(pipeline, args.query)
    else:
        display_results(result, show_pruned=not args.no_pruned)


if __name__ == "__main__":
    main()
