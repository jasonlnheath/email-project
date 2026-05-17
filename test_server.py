#!/usr/bin/env python3
"""Test the dashboard server directly."""
import subprocess
import sys
import time
import urllib.request
import json

# Start the server
proc = subprocess.Popen(
    [sys.executable, '/home/jason/.hermes/dashboards/email_dashboard.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

# Wait for server to start
for i in range(30):
    time.sleep(1)
    try:
        resp = urllib.request.urlopen('http://localhost:9999/api/stats', timeout=5)
        data = json.loads(resp.read().decode())
        print(f"Server ready! {data}")
        break
    except Exception as e:
        if i == 29:
            print(f"Server not ready after 30s: {e}")

# Check stdout for errors
time.sleep(2)
output = proc.stdout.read()
print("\n--- Server output ---")
print(output)

proc.terminate()
proc.wait(timeout=5)
