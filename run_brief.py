#!/usr/bin/env python3
"""Run the brief logic directly."""
import json
import sys
import time
import urllib.request
import urllib.error

SERVER_URL = "http://localhost:9999"

def log(msg):
    print(f"[brief] {msg}", flush=True)

def http_get(url, timeout=15):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return None

log("Starting email brief...")

# Check if server is running
data = http_get(f"{SERVER_URL}/api/stats")
if data and "total_emails" in data:
    log(f"Server already running ({data['total_emails']} emails)")
else:
    log("ERROR: Server not running. Start it first.")
    sys.exit(1)

# Refresh emails
log("Refreshing emails...")
result = http_get(f"{SERVER_URL}/api/reload")
if result:
    count = result.get("count", "?")
    log(f"Reload triggered (count={count})")
else:
    log("WARNING: Reload failed")

# Wait for VIP/HIGH summaries
log("Waiting for VIP/HIGH summaries...")
for i in range(90):
    stats = http_get(f"{SERVER_URL}/api/stats")
    if not stats:
        time.sleep(2)
        continue
    
    total = stats.get("total_emails", 0)
    vip_high_count = stats.get("vip_high_count", 0)
    with_summaries = stats.get("with_summaries", 0)
    
    if total == 0:
        if i % 10 == 0:
            log(f"  Waiting for emails to load... ({i}s)")
        time.sleep(2)
        continue
    
    if vip_high_count == 0:
        log(f"No VIP/HIGH emails. {total} emails loaded.")
        break
    
    if with_summaries >= vip_high_count:
        log(f"All {vip_high_count} VIP/HIGH emails have summaries ✓")
        break
    
    if i % 10 == 0:
        log(f"  {with_summaries}/{vip_high_count} VIP/HIGH summaries ready...")
    
    time.sleep(2)

# Get final stats and build message
final_stats = http_get(f"{SERVER_URL}/api/stats") or {}
emails = final_stats.get("emails", [])
total = final_stats.get("total_emails", len(emails))

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

# Show VIP/HIGH emails with summaries
vip_high = [e for e in emails if e.get("tier") in ("VIP_HIGH", "HIGH")]
if vip_high:
    lines.append("*Urgent emails:*")
    for e in vip_high[:5]:
        sender = e.get("sender", e.get("from", "?"))
        subject = e.get("subject", "(no subject)")
        summary = e.get("summary", "")
        
        if summary:
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

message = "\n".join(lines)
print(message)
