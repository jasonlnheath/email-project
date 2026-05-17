#!/usr/bin/env python3
"""Minimal test: start server and make a raw HTTP request."""
import subprocess
import time
import socket
import sys

# Start the server
proc = subprocess.Popen(
    [sys.executable, '/home/jason/.hermes/dashboards/email_dashboard.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

print(f"Server PID: {proc.pid}")
time.sleep(5)

# Check if process is alive
if proc.poll() is not None:
    output = proc.stdout.read()
    print(f"Process exited with code {proc.returncode}")
    print("Output:")
    print(output[-3000:])
    sys.exit(1)

print("Process still running, making raw HTTP request...")

# Make a raw HTTP request
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
try:
    sock.connect(('127.0.0.1', 9999))
    sock.sendall(b'GET /api/stats HTTP/1.1\r\nHost: localhost:9999\r\nConnection: close\r\n\r\n')
    response = b''
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response += chunk
    print(f"\nRaw response ({len(response)} bytes):")
    print(response.decode('utf-8', errors='replace'))
except Exception as e:
    print(f"Socket error: {e}")
finally:
    sock.close()

# Read server output
time.sleep(2)
output = proc.stdout.read()
print("\n=== Server output ===")
print(output[-3000:] if len(output) > 3000 else output)

proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()
