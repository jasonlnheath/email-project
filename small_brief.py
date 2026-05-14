#!/usr/bin/env python3
"""Fetch and summarize just the first 5 unread emails."""
from gmail_fetcher import GmailFetcher
from summarizer import Summarizer

fetcher = GmailFetcher(max_results=5)
summarizer = Summarizer()

print("[brief] Fetching unread emails...")
emails = fetcher.fetch('is:unread', max_results=5, format='full')
print(f"[brief] Found {len(emails)} unread emails")

for i, e in enumerate(emails):
    subject = e.get('subject', '(no subject)')
    sender = e.get('sender') or e.get('from', '(unknown)')
    date = e.get('date', '')
    print(f"\n--- Email {i+1} ---")
    print(f"  From: {sender}")
    print(f"  Subject: {subject}")
    print(f"  Date: {date}")
    
    try:
        s = summarizer.summarize(e)
        print(f"  Entities: {s.get('key_entities', [])}")
        print(f"  Actions:  {s.get('action_items', [])}")
        print(f"  Sentiment: {s.get('sentiment', 'unknown')}")
    except Exception as ex:
        print(f"  Summarization error: {ex}")
