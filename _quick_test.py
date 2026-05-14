#!/usr/bin/env python3
"""Quick test of Gmail fetcher auth and API call."""
import sys, time
sys.path.insert(0, '/home/jason/.hermes/emails')
from gmail_fetcher import GmailFetcher

start = time.time()
f = GmailFetcher(max_results=3)
print("Fetching 3 emails...")
try:
    emails = f.fetch(max_results=3)
    elapsed = time.time() - start
    print(f"Fetched {len(emails)} emails in {elapsed:.1f}s")
    if emails:
        for e in emails[:2]:
            print(f"  [{e['id']}] {e.get('subject', '?')[:60]}")
except Exception as e:
    elapsed = time.time() - start
    print(f"Error after {elapsed:.1f}s: {type(e).__name__}: {e}")
