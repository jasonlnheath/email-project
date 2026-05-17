#!/usr/bin/env python3
"""Full test of email dashboard flow."""
import sys
sys.path.insert(0, '/home/jason/.hermes/dashboards')

from email_dashboard import fetch_emails, full_enrich, load_vip_contacts, get_service, find_deferred_label

print("=== Testing get_service ===")
try:
    svc = get_service("jason")
    print(f"  Service created: {type(svc)}")
except Exception as e:
    print(f"  Error: {e}")
    import traceback; traceback.print_exc()

print("\n=== Testing find_deferred_label ===")
try:
    find_deferred_label()
    print(f"  Deferred label: {find_deferred_label.__globals__['DEFERRED_LABEL_ID']}")
except Exception as e:
    print(f"  Error: {e}")
    import traceback; traceback.print_exc()

print("\n=== Testing fetch_emails ===")
try:
    raw = fetch_emails(username="jason", max_results=5)
    print(f"  Fetched {len(raw)} emails")
except Exception as e:
    print(f"  Error: {e}")
    import traceback; traceback.print_exc()

print("\n=== Testing full_enrich ===")
try:
    raw = fetch_emails(username="jason", max_results=5)
    enriched = full_enrich(raw)
    print(f"  Enriched {len(enriched)} emails")
    for e in enriched[:3]:
        print(f"    - {e.get('from','?')[:40]} | {e.get('subject','?')[:50]} | tier={e.get('tier')}")
except Exception as e:
    print(f"  Error: {e}")
    import traceback; traceback.print_exc()
