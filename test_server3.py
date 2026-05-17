#!/usr/bin/env python3
"""Start server in background and test with curl."""
import subprocess
import time
import os
import signal

# Start the server
proc = subprocess.Popen(
    ['python3', '/home/jason/.hermes/dashboards/email_dashboard.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

print(f"Server PID: {proc.pid}")
print("Waiting 5s for server to start...")
time.sleep(5)

# Check if process is still alive
if proc.poll() is not None:
    output = proc.stdout.read()
    print(f"Process exited with code {proc.returncode}")
    print(output[-2000:])
else:
    print("Process is still running")
    
    # Try curl
    import urllib.request
    try:
        resp = urllib.request.urlopen('http://localhost:9999/api/stats', timeout=10)
        data = resp.read().decode()
        print(f"\n=== API response: {data[:500]} ===")
    except Exception as e:
        print(f"\nAPI error: {e}")

# Read some output
time.sleep(2)
output = proc.stdout.read()
print("\n=== Server output (last 3000 chars) ===")
print(output[-3000:] if len(output) > 3000 else output)

proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()
