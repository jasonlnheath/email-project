#!/usr/bin/env python3
"""Test the DashboardHandler directly."""
import sys
sys.path.insert(0, '/home/jason/.hermes/dashboards')

from email_dashboard import DashboardHandler, AUTH_DB_PATH
import socketserver
import threading
import time
import urllib.request

# Create a test server
class TestServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

# Start server in background
server = TestServer(("127.0.0.1", 9998), DashboardHandler)
t = threading.Thread(target=server.serve_forever, daemon=True)
t.start()

print("Test server started on port 9998")
time.sleep(1)

# Make a request
try:
    resp = urllib.request.urlopen('http://127.0.0.1:9998/api/stats', timeout=5)
    print(f"Response: {resp.read().decode()[:500]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

server.shutdown()
