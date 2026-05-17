#!/usr/bin/env python3
"""Test email fetching and enrichment."""
import sys
sys.path.insert(0, '/home/jason/.hermes/dashboards')

from email_dashboard import fetch_emails, full_enrich, load_vip_contacts

try:
    print("Loading VIP contacts...")
    vip_map = load_vip_contacts()
    print(f"  Loaded {len(vip_map)} VIP contacts")
except Exception as e:
    print(f"  VIP error: {e}", file=sys.stderr)
    import traceback; traceback.print_exc()

try:
    print("Fetching emails...")
    raw = fetch_emails(username="jason")
    print(f"  Fetched {len(raw)} emails")
    
    print("Enriching...")
    enriched = full_enrich(raw)
    print(f"  Enriched {len(enriched)} emails")
    for e in enriched[:3]:
        print(f"    - {e.get('from','?')} | {e.get('subject','?')[:60]} | tier={e.get('tier','?')}")
except Exception as e:
    print(f"  Error: {e}", file=sys.stderr)
    import traceback; traceback.print_exc()
