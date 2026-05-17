#!/usr/bin/env python3
"""Test server startup step by step."""
import sys
sys.path.insert(0, '/home/jason/.hermes/dashboards')

print("Step 1: Import modules...", flush=True)
from email_dashboard import (
    UserManager, SessionManager, UserRegistry,
    AUTH_DB_PATH, USERS_JSON_PATH, HERMES_HOME,
    find_deferred_label, fetch_emails, full_enrich,
    ThreadedHTTPServer, PORT,
)
print("  Done", flush=True)

print("\nStep 2: Init auth...", flush=True)
user_mgr = UserManager(AUTH_DB_PATH)
session_mgr = SessionManager(user_mgr, AUTH_DB_PATH)
users_json = UserRegistry(USERS_JSON_PATH)
users_json.load()
print(f"  Users: {users_json.list_users()}", flush=True)

print("\nStep 3: Init per-user state...", flush=True)
USER_STATE = {}
for username in users_json.list_users():
    USER_STATE[username] = {
        "emails": [],
        "summary_queue": None,
        "deferred_label_id": None,
    }
print(f"  State for: {list(USER_STATE.keys())}", flush=True)

print("\nStep 4: Check LLM...", flush=True)
import requests
try:
    resp = requests.get("http://localhost:8033/v1/models", timeout=5)
    print(f"  LLM available: {resp.status_code == 200}", flush=True)
except Exception as e:
    print(f"  LLM unavailable: {e}", flush=True)

print("\nStep 5: Find deferred label...", flush=True)
find_deferred_label()
print(f"  Deferred label: {find_deferred_label.__globals__['DEFERRED_LABEL_ID']}", flush=True)

print("\nStep 6: Start server...", flush=True)
import socketserver
import threading

class TestHandler:
    pass

server = ThreadedHTTPServer(("0.0.0.0", PORT), None)
print(f"  Server listening on port {PORT}", flush=True)

# Now test a request in a separate thread
def make_request():
    import urllib.request
    time.sleep(1)
    try:
        resp = urllib.request.urlopen('http://localhost:9999/api/stats', timeout=5)
        print(f"  Request response: {resp.read().decode()[:200]}", flush=True)
    except Exception as e:
        print(f"  Request error: {e}", flush=True)

import time
t = threading.Thread(target=make_request, daemon=True)
t.start()

time.sleep(3)
print("\nDone!", flush=True)
server.shutdown()
