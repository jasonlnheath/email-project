#!/usr/bin/env python3
"""Start server and test API endpoints."""
import subprocess
import sys
import time
import urllib.request
import json
import os

# Start the server with stdout visible
proc = subprocess.Popen(
    [sys.executable, '/home/jason/.hermes/dashboards/email_dashboard.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    env={**os.environ},
)

print("Waiting for server to start...")
for i in range(30):
    time.sleep(1)
    try:
        resp = urllib.request.urlopen('http://localhost:9999/api/stats', timeout=5)
        data = json.loads(resp.read().decode())
        print(f"\n=== Server ready! ===")
        print(f"Stats: {json.dumps(data, indent=2)}")
        
        # Try reload
        resp2 = urllib.request.urlopen('http://localhost:9999/api/reload', timeout=15)
        reload_data = json.loads(resp2.read().decode())
        print(f"\n=== Reload result: {reload_data} ===")
        
        time.sleep(3)
        
        # Check stats again
        resp3 = urllib.request.urlopen('http://localhost:9999/api/stats', timeout=5)
        data2 = json.loads(resp3.read().decode())
        print(f"\n=== Stats after reload: total={data2.get('total_emails')}, vip_high={data2.get('vip_high_count')}, summaries={data2.get('with_summaries')} ===")
        
        break
    except Exception as e:
        if i == 29:
            print(f"Server not ready after 30s: {e}")

# Read server output
time.sleep(2)
output = proc.stdout.read()
print("\n=== Server stdout/stderr ===")
for line in output.split('\n'):
    if line.strip():
        print(line)

proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()
