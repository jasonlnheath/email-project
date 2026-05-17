#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from gmail_fetcher import GmailFetcher

f = GmailFetcher(max_results=5)
try:
    emails = f.fetch()
    print(f'Fetched {len(emails)} emails')
    for e in emails[:3]:
        print(f'  - {e.get("subject","?")[:60]}')
except Exception as ex:
    import traceback
    print(f'Error: {ex}')
    traceback.print_exc()
