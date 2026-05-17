#!/usr/bin/env python3
"""Email dashboard brief — starts server, refreshes emails, waits for VIP/HIGH summaries,
then sends Jason a notification with the dashboard URL and a preview."""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
import socket

DASHBOARD_DIR = "/home/jason/.hermes/dashboards"
SERVER_URL = "http://localhost:9999"
SERVER_SCRIPT = os.path.join(DASHBOARD_DIR, "email_dashboard.py")
PORT = 9999
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")


def log(msg):
    print(f"[brief] {msg}", flush=True)


def http_get(url, timeout=15, cookie=None):
    try:
        req = urllib.request.Request(url)
        if cookie:
            req.add_header("Cookie", f"session={cookie}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return None


def port_is_open(port):
    """Check if a port is open (regardless of auth)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("localhost", port))
    sock.close()
    return result == 0


def login(username="jason", password=""):
    """Login to the dashboard and return session ID."""
    if not password:
        log("No DASHBOARD_PASSWORD set — cannot authenticate")
        return None
    
    log(f"Logging in as {username}...")
    try:
        data = json.dumps({"username": username, "password": password}).encode()
        req = urllib.request.Request(
            f"{SERVER_URL}/api/login",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            # Extract session ID from Set-Cookie header
            set_cookie = resp.headers.get("Set-Cookie", "")
            session_id = ""
            if "session=" in set_cookie:
                session_id = set_cookie.split("session=")[1].split(";")[0]
            
            if result.get("success"):
                log(f"Login successful (session={session_id[:20]}...)")
                return session_id
            else:
                log(f"Login failed: {result.get('error')}")
                return None
    except Exception as e:
        log(f"Login error: {e}")
        return None


def start_server():
    """Start the dashboard server in the background if not already running."""
    # Check if port is open — server might be running but auth-protected
    if port_is_open(PORT):
        log("Port 9999 is open — server appears to be running")
        
        # Try to login and get stats
        if DASHBOARD_PASSWORD:
            session_id = login(password=DASHBOARD_PASSWORD)
            if session_id:
                data = http_get(f"{SERVER_URL}/api/stats", cookie=session_id)
                if data and "total_emails" in data:
                    log(f"Server confirmed running ({data['total_emails']} emails)")
                    return True
        
        # Server is running but we couldn't authenticate or get stats
        # Check if it's responding at all (even with auth error)
        try:
            req = urllib.request.Request(f"{SERVER_URL}/api/stats")
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode())
                if "total_emails" in body:
                    log(f"Server running ({body['total_emails']} emails)")
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 401:
                log("Server is running but requires authentication — will login before API calls")
                return True
        
        # Server is running but unresponsive — kill it and restart
        log("Port open but server unresponsive — restarting...")
        os.system(f"fuser -k {PORT}/tcp 2>/dev/null")
        time.sleep(3)
    else:
        log("Starting dashboard server...")

    proc = subprocess.Popen(
        [sys.executable, SERVER_SCRIPT],
        cwd=DASHBOARD_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    # Wait for server to be ready (up to 60s)
    for i in range(60):
        time.sleep(1)
        if port_is_open(PORT):
            # Server is up — try to login and get stats
            if DASHBOARD_PASSWORD:
                session_id = login(password=DASHBOARD_PASSWORD)
                if session_id:
                    data = http_get(f"{SERVER_URL}/api/stats", cookie=session_id)
                    if data and "total_emails" in data:
                        log(f"Server started (PID {proc.pid}, {data['total_emails']} emails)")
                        return True
            else:
                # No auth — check without cookie
                data = http_get(f"{SERVER_URL}/api/stats")
                if data and "total_emails" in data:
                    log(f"Server started (PID {proc.pid}, {data['total_emails']} emails)")
                    return True
    log("WARNING: Server may not be ready yet")
    return False


def refresh_emails(session_id=""):
    """Trigger a refresh of emails via the API."""
    log("Refreshing emails...")
    result = http_get(f"{SERVER_URL}/api/reload", cookie=session_id)
    if result:
        count = result.get("count", "?")
        log(f"Reload triggered (count={count})")
        return result
    log("WARNING: Reload failed or returned no data")
    return None


def wait_for_summaries(timeout=180, session_id=""):
    """Wait for VIP/HIGH priority emails to have summaries computed."""
    log("Waiting for VIP/HIGH summaries...")
    for i in range(timeout):
        stats = http_get(f"{SERVER_URL}/api/stats", cookie=session_id)
        if not stats:
            time.sleep(2)
            continue

        total = stats.get("total_emails", 0)
        vip_high_count = stats.get("vip_high_count", 0)
        with_summaries = stats.get("with_summaries", 0)

        if total == 0:
            # Still loading initial emails
            if i % 10 == 0:
                log(f"  Waiting for emails to load... ({i}s)")
            time.sleep(2)
            continue

        # No VIP/HIGH emails — nothing to wait for, we're done
        if vip_high_count == 0:
            log(f"No VIP/HIGH emails. {total} emails loaded.")
            return True

        if with_summaries >= vip_high_count:
            log(f"All {vip_high_count} VIP/HIGH emails have summaries ✓")
            return True

        if i % 10 == 0:
            log(f"  {with_summaries}/{vip_high_count} VIP/HIGH summaries ready...")

        time.sleep(2)

    # Timeout — report what we have
    stats = http_get(f"{SERVER_URL}/api/stats", cookie=session_id) or {}
    vip_high_count = stats.get("vip_high_count", 0)
    with_summaries = stats.get("with_summaries", 0)
    total = stats.get("total_emails", 0)
    log(f"Timeout: {total} emails, {with_summaries}/{vip_high_count} VIP/HIGH summaries ready")
    return True  # Still deliver the message even if not all summaries loaded


def build_message(stats):
    """Build a Telegram-friendly message from the dashboard stats."""
    emails = stats.get("emails", [])
    total = stats.get("total_emails", len(emails))

    # Count by tier
    counts = {}
    for e in emails:
        t = e.get("tier", "UNKNOWN")
        counts[t] = counts.get(t, 0) + 1

    lines = [f"📧 *Email Dashboard* — {total} unread"]
    lines.append("")

    if counts:
        tier_emojis = {"VIP_HIGH": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
        for tier in ["VIP_HIGH", "HIGH", "MEDIUM", "LOW"]:
            if tier in counts:
                emoji = tier_emojis.get(tier, "⚪")
                lines.append(f"{emoji} *{tier}*: {counts[tier]}")
        lines.append("")

    # Show VIP/HIGH emails with summaries (or preview)
    vip_high = [e for e in emails if e.get("tier") in ("VIP_HIGH", "HIGH")]
    if vip_high:
        lines.append("*Urgent emails:*")
        for e in vip_high[:5]:  # Top 5
            sender = e.get("sender", e.get("from", "?"))
            subject = e.get("subject", "(no subject)")
            summary = e.get("summary", "")

            if summary:
                # Truncate summary for the message
                preview = summary[:200].replace("\n", " ").strip()
                lines.append(f"🔹 *{sender}* — {subject}")
                lines.append(f"   {preview}...")
            else:
                lines.append(f"🔹 *{sender}* — {subject} *(summary loading)*")
            lines.append("")

    # Show unsubscribe opportunities
    unsub_emails = [e for e in emails if e.get("unsubscribe_url")]
    if unsub_emails and len(unsub_emails) <= 5:
        lines.append("*Quick unsubscribes:*")
        for e in unsub_emails[:3]:
            sender = e.get("from", "?")
            subject = e.get("subject", "")
            lines.append(f"↩ {sender} — {subject}")
        lines.append("")

    lines.append(f"👉 Open dashboard: http://localhost:9999")
    return "\n".join(lines)


def main():
    log("Starting email brief...")

    # 1. Start server (or confirm it's running)
    if not start_server():
        log("ERROR: Could not start server")
        print("❌ Dashboard server failed to start. Check logs.")
        return

    # 2. Login
    session_id = login(password=DASHBOARD_PASSWORD)
    if not session_id:
        log("ERROR: Authentication failed. Set DASHBOARD_PASSWORD environment variable.")
        print("❌ Dashboard authentication failed. Set DASHBOARD_PASSWORD env var.")
        return

    # 3. Refresh emails
    refresh_emails(session_id=session_id)

    # 4. Wait for VIP/HIGH summaries
    wait_for_summaries(timeout=180, session_id=session_id)

    # 5. Get final stats and build message
    final_stats = http_get(f"{SERVER_URL}/api/stats", cookie=session_id) or {}
    message = build_message(final_stats)

    print(message)


if __name__ == "__main__":
    main()
