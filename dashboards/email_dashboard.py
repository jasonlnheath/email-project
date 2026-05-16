#!/usr/bin/env python3
"""Email Action Dashboard — mobile-first, AJAX-powered, with LLM summaries & VIP priority.

Optimized: uses direct Google API client calls instead of subprocesses.
Each button click is now a pure HTTP call (~100ms) instead of spawning
a new Python process with full auth overhead (~400ms).
"""

import http.server
import json
import os
import re
import socket
import socketserver
import sys
import threading
import time
import traceback
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────
PORT = 9999
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = Path.home() / "relmgr" / "contacts.db"
LLAMA_CPP_HOST = "http://localhost:8033"
LLAMA_CPP_MODEL = "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"

# ── Async Summary Queue ────────────────────────────────────────

class SummaryQueue:
    """Priority queue for background email summarization."""
    
    def __init__(self):
        self._queue = []  # List of {msg_id, data, priority}
        self._status = {}  # msg_id -> {"state": "pending"/"processing"/"ready"/"error", "summary": str|None}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread = None
    
    def add(self, msg_id, email_data, priority=2):
        """Add email to summary queue. Skips if already queued/processed."""
        with self._lock:
            if msg_id in self._status:
                return  # Already queued or processed
            self._queue.append({
                "msg_id": msg_id,
                "data": email_data,
                "priority": priority,
            })
            self._status[msg_id] = {"state": "pending", "summary": None}
    
    def get_status(self, msg_id):
        """Get summary status for an email."""
        with self._lock:
            if msg_id not in self._status:
                return {"state": "not_found", "summary": None}
            return dict(self._status[msg_id])
    
    def set_ready(self, msg_id, summary):
        """Mark a summary as ready."""
        with self._lock:
            if msg_id in self._status:
                self._status[msg_id] = {"state": "ready", "summary": summary}
    
    def next_item(self):
        """Get next item from queue (highest priority first). Returns None if empty."""
        with self._lock:
            if not self._queue:
                return None
            # Sort by priority (lower number = higher priority)
            self._queue.sort(key=lambda x: x["priority"])
            item = self._queue.pop(0)
            self._status[item["msg_id"]] = {"state": "processing", "summary": None}
            return item
    
    def start_worker(self, summarize_func):
        """Start background worker thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return  # Already running
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker,
            args=(summarize_func,),
            daemon=True,
        )
        self._worker_thread.start()
    
    def _worker(self, summarize_func):
        """Background worker that processes summaries in priority order."""
        while not self._stop_event.is_set():
            item = self.next_item()
            if item is None:
                time.sleep(0.5)  # Wait for new items
                continue
            
            msg_id = item["msg_id"]
            email_data = item["data"]
            
            try:
                summary = summarize_func(item["data"])
                self.set_ready(msg_id, summary)
            except Exception as e:
                print(f"Summary error for {msg_id}: {e}", file=sys.stderr, flush=True)
                with self._lock:
                    self._status[msg_id] = {"state": "error", "summary": str(e)}
    
    def stop(self):
        """Signal worker to stop."""
        self._stop_event.set()


# ── Global state ───────────────────────────────────────────────
EMAILS = []
DEFERRED_LABEL_ID = None
SUMMARY_QUEUE = SummaryQueue()


# ── Google API setup (runs once at startup) ────────────────────
def _load_scopes():
    try:
        data = json.loads((HERMES_HOME / "google_token.json").read_text())
        scopes = data.get("scopes")
        if isinstance(scopes, list) and scopes:
            return scopes
    except Exception:
        pass
    return [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
    ]


def get_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as AuthRequest

    token_path = HERMES_HOME / "google_token.json"
    creds = Credentials.from_authorized_user_file(str(token_path), _load_scopes())
    if creds.expired and creds.refresh_token:
        creds.refresh(AuthRequest())
        token_path.write_text(json.dumps(json.loads(creds.to_json()), indent=2))
    if not creds.valid:
        print("Token is invalid. Re-run setup.", file=sys.stderr)
        sys.exit(1)
    return creds


def get_service():
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=get_credentials())


# ── Thread-safe Google API setup ────────────────────────────────
_thread_local = threading.local()


def get_service():
    """Get a thread-local Gmail API service."""
    from googleapiclient.discovery import build
    if not hasattr(_thread_local, 'service'):
        _thread_local.service = build("gmail", "v1", credentials=get_credentials())
    return _thread_local.service


# ── Gmail operations (direct API calls, no subprocess) ─────────

def fetch_emails(max_results=20):
    """Fetch unread emails via direct API call — optimized to only fetch new ones."""
    service = get_service()
    
    # Load existing processed IDs from the pipeline
    processed_ids = set()
    pipeline_dir = Path.home() / ".hermes" / "emails"
    processed_file = pipeline_dir / ".processed_ids.json"
    if processed_file.exists():
        try:
            with open(processed_file, "r") as f:
                data = json.load(f)
                processed_ids = set(data.get("email_ids", []))
        except Exception:
            pass
    
    # Load existing summaries from tier2.jsonl
    existing_summaries = {}
    tier2_file = pipeline_dir / "tier2.jsonl"
    if tier2_file.exists():
        try:
            with open(tier2_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        eid = record.get("email_id", "")
                        if eid:
                            existing_summaries[eid] = record
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
    
    # Fetch message IDs (limit to most recent N emails)
    results = service.users().messages().list(
        userId="me", q="is:unread", maxResults=max_results
    ).execute()
    messages = results.get("messages", [])
    
    output = []
    for msg_meta in messages:
        msg_id = msg_meta["id"]
        
        # Skip if already processed by the pipeline
        if msg_id in processed_ids:
            # Use existing summary if available
            if msg_id in existing_summaries:
                summary_record = existing_summaries[msg_id]
                output.append({
                    "id": msg_id,
                    "threadId": msg_id,  # Use email ID as thread ID for simplicity
                    "from": summary_record.get("sender", ""),
                    "to": "",
                    "subject": summary_record.get("subject", ""),
                    "date": summary_record.get("date", ""),
                    "snippet": summary_record.get("summary", ""),
                    "labels": ["UNREAD"],  # Assume unread if still in inbox
                    "gmail_link": f"https://mail.google.com/mail/mu/mp/330/#cv/Inbox/{msg_id}",
                    "unsubscribe_url": None,
                    "summary": summary_record.get("summary", ""),
                    "key_entities": summary_record.get("key_entities", []),
                    "action_items": summary_record.get("action_items", []),
                    "sentiment": summary_record.get("sentiment", "neutral"),
                    "has_action_required": summary_record.get("has_action_required", False),
                })
            # If not in existing_summaries, skip (no data to show)
            continue
        
        # Fetch metadata for new emails
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        output.append({
            "id": msg["id"],
            "threadId": msg["threadId"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "labels": msg.get("labelIds", []),
            "gmail_link": f"https://mail.google.com/mail/mu/mp/330/#cv/Inbox/{msg['threadId']}" if msg["threadId"] else "",
            "unsubscribe_url": None,
        })
    return output


def fetch_full_body(msg_id):
    """Fetch the full body of an email via direct API call."""
    service = get_service()
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full",
        metadataHeaders=["From", "To", "Subject", "Date"],
    ).execute()

    def _extract_body(payload):
        body = ""
        if payload.get("body", {}).get("data"):
            import base64
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        elif payload.get("parts"):
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    import base64
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
            if not body:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                        import base64
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                        break
        return body

    return _extract_body(msg.get("payload", {}))


def do_action(action, msg_id):
    """Modify message labels directly via API."""
    service = get_service()
    body = {}
    if action == "read":
        body = {"removeLabelIds": ["UNREAD"]}
    elif action == "delete":
        body = {"removeLabelIds": ["INBOX"]}
    elif action == "defer":
        body = {"addLabelIds": [DEFERRED_LABEL_ID], "removeLabelIds": ["UNREAD"]}
    else:
        raise ValueError(f"Unknown action: {action}")

    start = time.time()
    service.users().messages().modify(userId="me", id=msg_id, body=body).execute()
    elapsed = time.time() - start
    return f"Done ({elapsed*1000:.0f}ms)", ""


# ── VIP / Contact Lookup ───────────────────────────────────────

def load_vip_contacts():
    """Load VIP contacts from RelMgr database."""
    vip_map = {}
    if not DB_PATH.exists():
        return vip_map
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT vc.contact_id, vc.relationship_type, c.normalized_name "
            "FROM vip_contacts vc LEFT JOIN contacts c ON vc.contact_id = c.id"
        ).fetchall():
            rd = dict(row)
            contact_id = rd['contact_id']
            contact_row = conn.execute("SELECT * FROM contacts WHERE id=?", (contact_id,)).fetchone()
            if contact_row:
                rd2 = dict(contact_row)
                emails_list = json.loads(rd2['emails']) if rd2.get('emails') else []
                for e in emails_list:
                    addr = e.get('address', '').lower().strip() if isinstance(e, dict) else ''
                    if addr:
                        vip_map[addr] = {
                            'name': rd2['normalized_name'],
                            'relationship_type': rd['relationship_type'],
                        }
                if rd.get('normalized_name'):
                    vip_map[f"vip_name_{rd['normalized_name'].lower()}"] = {
                        'name': rd['normalized_name'],
                        'relationship_type': rd['relationship_type'],
                        'by_name': True
                    }
        conn.close()
    except Exception as e:
        print(f"Warning: could not load VIP contacts: {e}", file=sys.stderr)
    return vip_map


def extract_sender_email(from_field):
    """Extract email address from a From header string."""
    match = re.search(r'<([^>]+)>', from_field)
    if match:
        return match.group(1).lower().strip(), from_field.split('<')[0].strip().strip('"')
    parts = from_field.split('<')
    if len(parts) > 1:
        return parts[-1].rstrip('>').lower().strip(), parts[0].strip().strip('"')
    return from_field.lower().strip(), from_field


# ── Priority / Tier ────────────────────────────────────────────

def get_priority(email, vip_map):
    """Determine priority tier for an email."""
    from_field = email.get('from', '')
    sender_email, display_name = extract_sender_email(from_field)

    vip_info = vip_map.get(sender_email)
    if not vip_info and display_name:
        vip_info = vip_map.get(f"vip_name_{display_name.lower()}")

    if vip_info:
        return ('VIP_HIGH', 0, vip_info)

    high_keywords = ['school', 'trip', 'deadline', 'payment', 'due', 'security', 'alert',
                     'password', 'login', 'transaction', 'bank', 'financial', 'urgent']
    text = f"{email.get('subject','')} {email.get('snippet','')}".lower()
    labels = set(email.get('labels', []))
    if any(kw in text for kw in high_keywords):
        return ('HIGH', 1, None)

    if labels & {'CATEGORY_UPDATES'}:
        return ('MEDIUM', 2, None)

    if labels & {'CATEGORY_PROMOTIONS'}:
        return ('LOW', 3, None)

    newsletter_kw = ['newsletter', 'unsubscribe', 'mailing', 'campaign', 'digest', 'promo']
    if any(kw in text for kw in newsletter_kw):
        return ('LOW', 3, None)

    return ('MEDIUM', 2, None)


def is_school_email(email):
    keywords = ["school", "edu", "class", "teacher", "student", "parent",
                "heath", "andrew", "science", "reproductive", "froehli"]
    text = f"{email['from']} {email['subject']} {email['snippet']}".lower()
    return any(kw in text for kw in keywords)


def is_newsletter_email(email):
    categories = {"CATEGORY_UPDATES", "CATEGORY_PROMOTIONS"}
    keywords = ["newsletter", "subscribe", "unsubscribe", "mailing", "campaign", "digest"]
    labels = set(email.get("labels", []))
    snippet = f"{email['subject']} {email['snippet']}".lower()
    return bool(labels & categories) or any(kw in snippet for kw in keywords)


# ── LLM Summarizer ─────────────────────────────────────────────

def summarize_with_llm(email_dict):
    """Summarize an email using Qwen via llama.cpp."""
    try:
        import requests
        sender = email_dict.get('sender', 'Unknown')
        subject = email_dict.get('subject', '(no subject)')
        body = email_dict.get('body', '') or ''
        truncated = body[:2500] if len(body) > 2500 else body

        prompt = (
            f"Analyze this email and return a brief 1-3 sentence summary capturing the key points.\n\n"
            f"FROM: {sender}\n"
            f"SUBJECT: {subject}\n\n"
            f"BODY:\n{truncated}\n\n"
            "Return ONLY the summary text. No JSON, no markdown, no extra text."
        )
        payload = {
            "model": LLAMA_CPP_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 512,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        resp = requests.post(
            f"{LLAMA_CPP_HOST}/v1/chat/completions",
            json=payload, timeout=45
        )
        resp.raise_for_status()
        data = resp.json()
        summary = data["choices"][0]["message"]["content"].strip()
        summary = re.sub(r'</think>.*?</think>', '', summary, flags=re.DOTALL).strip()
        return summary if summary else None
    except Exception:
        return None


def summarize_email(body, subject):
    """Extract text from HTML email body and produce a summary. Uses BeautifulSoup if available."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(body, 'html.parser')

        # Remove script, style, nav, footer, header elements
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript']):
            tag.decompose()

        # Extract text with reasonable paragraph breaks
        text_parts = []
        for p in soup.find_all(['p', 'div', 'li', 'td', 'h1', 'h2', 'h3', 'h4']):
            t = p.get_text(' ', strip=True)
            if len(t) > 5:
                text_parts.append(t)

        # Also get alt text from images (often contains context)
        for img in soup.find_all('img'):
            alt = img.get('alt', '')
            if alt and len(alt) > 3:
                text_parts.insert(0, f"[Image: {alt}]")

    except Exception:
        # Fallback to basic HTML parser
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.in_script = False
                self.in_style = False

            def handle_starttag(self, tag, attrs):
                if tag in ('script', 'style'):
                    self.in_script = True
                elif tag == 'br':
                    self.text.append(' ')

            def handle_endtag(self, tag):
                if tag in ('script', 'style'):
                    self.in_script = True

            def handle_data(self, data):
                if not self.in_script:
                    self.text.append(data)

        extractor = TextExtractor()
        try:
            extractor.feed(body)
        except Exception:
            pass
        text_parts = [t for t in extractor.text if len(t.strip()) > 5]

    # Clean and deduplicate
    cleaned_lines = []
    seen = set()
    for line in text_parts:
        line = re.sub(r'https?://\S+', '', line)
        line = re.sub(r'\s+', ' ', line).strip()
        if line and len(line) > 10 and line not in seen:
            seen.add(line)
            cleaned_lines.append(line)

    # Score lines by length and position (longer, earlier = more important)
    scored = []
    for i, line in enumerate(cleaned_lines):
        score = len(line) * (1.0 - i / max(len(cleaned_lines), 1))
        scored.append((score, line))

    scored.sort(reverse=True)

    # Pick top 3-5 unique, meaningful lines
    summary_lines = []
    for score, line in scored:
        if len(summary_lines) >= 4:
            break
        # Allow [Image: ...] alt text, but skip other bracketed noise and URLs
        if line.startswith('[Image:') or (not line.startswith('[') and not line.startswith('http') and len(line) > 20):
            summary_lines.append(line)

    if summary_lines:
        return "\n".join(f"• {line}" for line in summary_lines[:4])
    else:
        snippet = cleaned_lines[0][:200] if cleaned_lines else "No extractable content."
        return f"{snippet}..."


def extract_unsubscribe(msg_id):
    """Extract List-Unsubscribe header or body link from an email."""
    service = get_service()
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full",
        metadataHeaders=["From", "To", "Subject", "Date"],
    ).execute()

    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == "list-unsubscribe":
            val = h.get("value", "")
            match = re.search(r'<(https?://[^>]+)>', val)
            if match:
                return match.group(1)
            match = re.search(r'https?://\S+', val)
            if match:
                return match.group(0)

    body = fetch_full_body(msg_id) or ""
    if body:
        m = re.search(r'(?:unsubscribe|opt[-_.]?out)[^<]*?href\s*=\s*[\'"]([^\'">]+)', body, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).rstrip(')')
        m = re.search(r'href=[\'"](https?://[^\'"]*(?:unsubscribe|opt[-_]?out|remove|cancel)[^\'"]*)[\'"]', body, re.IGNORECASE)
        if m:
            return m.group(1).rstrip(')')
    return None


# ── Deferred Label ─────────────────────────────────────────────

def find_deferred_label():
    global DEFERRED_LABEL_ID
    service = get_service()
    try:
        labels = service.users().labels().list(userId="me").execute()
        for l in labels.get("labels", []):
            if "Deferred" in l.get("name", ""):
                DEFERRED_LABEL_ID = l["id"]
                return
    except Exception as e:
        print(f"Warning: could not find deferred label: {e}", file=sys.stderr)

    # Try to create it
    try:
        service.users().labels().create(
            userId="me",
            body={"name": "Deferred", "type": "user"}
        ).execute()
        labels = service.users().labels().list(userId="me").execute()
        for l in labels.get("labels", []):
            if "Deferred" in l.get("name", ""):
                DEFERRED_LABEL_ID = l["id"]
                return
    except Exception:
        pass

    DEFERRED_LABEL_ID = "Label_Deferred"


# ── Enrichment ─────────────────────────────────────────────────

def quick_enrich(raw_emails):
    """Quick enrichment: add tier/priority without LLM summaries."""
    vip_map = load_vip_contacts()
    enriched = []
    for e in raw_emails:
        tier_name, tier_order, vip_info = get_priority(e, vip_map)
        enriched.append({
            **e,
            'tier': tier_name,
            'tier_order': tier_order,
            'vip_info': vip_info,
            'summary': None,
            'is_newsletter': is_newsletter_email(e),
        })
    enriched.sort(key=lambda x: x['tier_order'])
    return enriched


def full_enrich(raw_emails):
    """Full enrichment — no LLM (use snippets instead)."""
    vip_map = load_vip_contacts()
    enriched = []
    for e in raw_emails:
        tier_name, tier_order, vip_info = get_priority(e, vip_map)
        # Use snippet as summary (no LLM call)
        summary = e.get('summary') or e.get('snippet', '')
        enriched.append({
            **e,
            'tier': tier_name,
            'tier_order': tier_order,
            'vip_info': vip_info,
            'summary': summary,
            'is_newsletter': is_newsletter_email(e),
        })

    enriched.sort(key=lambda x: x['tier_order'])
    return enriched


def _do_full_enrich():
    """Full enrichment with snippets (no LLM, no body fetches)."""
    global EMAILS
    try:
        raw = fetch_emails()
        EMAILS = full_enrich(raw)
        print(f"\n  ✨ Fully enriched {len(EMAILS)} emails", flush=True)
    except Exception as e:
        print(f"\n  ⚠️  Enrichment error: {e}", file=sys.stderr, flush=True)


# ── HTTP Handler ───────────────────────────────────────────────

class DashboardHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self):
        html_path = SCRIPT_DIR / "index.html"
        try:
            with open(html_path, "r") as f:
                html = f.read()
        except FileNotFoundError:
            html = '<html><body><h1>Inbox</h1></body></html>'

        unread_count = len(EMAILS)
        html = html.replace("__COUNT__", str(unread_count))
        html = html.replace("__EMAILS_JSON__", json.dumps(EMAILS))
        body = html.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_error(self, e):
        msg = f"ERROR: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        print(msg, file=sys.stderr, flush=True)

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == "/api/reload":
                global EMAILS
                raw = fetch_emails()
                EMAILS = full_enrich(raw)
                # Re-queue any emails without summaries
                for email in EMAILS:
                    if not email.get("summary") or email["summary"] == email.get("snippet", ""):
                        priority = email.get("tier_order", 2)
                        SUMMARY_QUEUE.add(email["id"], email, priority=priority)
                self.send_json({"success": True, "count": len(EMAILS)})
                return

            if parsed.path.startswith("/api/summary_status/"):
                msg_id = parsed.path.split("/")[-1]
                status = SUMMARY_QUEUE.get_status(msg_id)
                # Also check if email already has summary from disk
                for e in EMAILS:
                    if e["id"] == msg_id and e.get("summary") and status["state"] != "ready":
                        status = {"state": "ready", "summary": e["summary"]}
                        break
                self.send_json(status)
                return

            if parsed.path == "/api/labels":
                labels = get_service().users().labels().list(userId="me").execute()
                self.send_json({"labels": labels.get("labels", [])})
                return

            if parsed.path == "/api/stats":
                vip_count = sum(1 for e in EMAILS if e.get('tier') in ('VIP_HIGH', 'HIGH'))
                with_summaries = sum(1 for e in EMAILS if e.get('summary'))
                with_unsub = sum(1 for e in EMAILS if e.get('unsubscribe_url'))
                tier_counts = {}
                for e in EMAILS:
                    t = e.get('tier', 'UNKNOWN')
                    tier_counts[t] = tier_counts.get(t, 0) + 1
                self.send_json({
                    "total_emails": len(EMAILS),
                    "unread_count": len(EMAILS),
                    "vip_high_count": vip_count,
                    "with_summaries": with_summaries,
                    "with_unsubscribe": with_unsub,
                    "tier_counts": tier_counts,
                    "emails": EMAILS,
                })
                return

            self.send_html()
        except Exception as e:
            self._handle_error(e)
            try:
                self.send_json({"error": str(e)}, 500)
            except Exception:
                pass

    def do_POST(self):
        global EMAILS
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")

        if len(parts) >= 3 and parts[0] == "api":
            action = parts[1]
            msg_id = "/".join(parts[2:])

            if action == "summary":
                body = fetch_full_body(msg_id)
                if body is None:
                    self.send_json({"error": "Failed to fetch email"}, 500)
                    return

                email_data = None
                for e in EMAILS:
                    if e["id"] == msg_id:
                        email_data = e
                        break

                if not email_data:
                    self.send_json({"error": "Email not found"}, 404)
                    return

                email_dict = {
                    'sender': email_data['from'],
                    'subject': email_data['subject'],
                    'date': email_data['date'],
                    'body': body,
                }
                summary = summarize_with_llm(email_dict)
                if not summary:
                    summary = summarize_email(body, email_data["subject"])

                unsubscribe_url = extract_unsubscribe(msg_id)

                self.send_json({
                    "success": True,
                    "summary": summary,
                    "is_school": is_school_email(email_data),
                    "is_newsletter": is_newsletter_email(email_data),
                    "gmail_link": f"https://mail.google.com/mail/mu/mp/330/#cv/Inbox/{email_data['threadId']}" if email_data.get("threadId") else "",
                    "unsubscribe_url": unsubscribe_url,
                    "from": email_data["from"],
                    "subject": email_data["subject"],
                    "date": email_data["date"]
                })
                return

            if action == "trigger_summary":
                # Queue this email for background summarization
                email_data = None
                for e in EMAILS:
                    if e["id"] == msg_id:
                        email_data = e
                        break
                
                if not email_data:
                    self.send_json({"error": "Email not found"}, 404)
                    return
                
                priority = email_data.get("tier_order", 2)
                SUMMARY_QUEUE.add(msg_id, email_data, priority=priority)
                
                status = SUMMARY_QUEUE.get_status(msg_id)
                self.send_json({
                    "success": True,
                    "status": status
                })
                return

            try:
                stdout, stderr = do_action(action, msg_id)
                
                # Only update the modified email, not all 500
                updated_email = None
                for e in EMAILS:
                    if e["id"] == msg_id:
                        updated_email = e
                        break
                
                if action == "read":
                    if updated_email:
                        updated_email["labels"] = [l for l in updated_email.get("labels", []) if l != "UNREAD"]
                        # Mark as processed so it won't be re-summarized
                        pipeline_dir = Path.home() / ".hermes" / "emails"
                        processed_file = pipeline_dir / ".processed_ids.json"
                        if processed_file.exists():
                            try:
                                with open(processed_file, "r") as f:
                                    data = json.load(f)
                                email_ids = set(data.get("email_ids", []))
                                email_ids.add(msg_id)
                                data["email_ids"] = list(email_ids)
                                data["last_updated"] = datetime.now(timezone.utc).isoformat()
                                with open(processed_file, "w") as f:
                                    json.dump(data, f, indent=2)
                            except Exception:
                                pass
                elif action == "delete":
                    # Remove from EMAILS list entirely
                    if updated_email:
                        EMAILS.remove(updated_email)
                
                self.send_json({
                    "success": True,
                    "unread_count": len(EMAILS),
                    "message": f"Email {action}d successfully"
                })
            except Exception as e:
                self._handle_error(e)
                self.send_json({"error": str(e)}, 500)
            return

        self.send_json({"error": "Not found"}, 404)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ── Main ───────────────────────────────────────────────────────

def main():
    global EMAILS

    print("📧 Email Dashboard starting...", flush=True)

    # Check LLM availability
    llm_available = False
    try:
        import requests
        resp = requests.get(f"{LLAMA_CPP_HOST}/v1/models", timeout=5)
        if resp.status_code == 200:
            llm_available = True
            print("  ✨ LLM summarizer available (Qwen via llama.cpp)", flush=True)
        else:
            print("  ⚠️  LLM summarizer unavailable — will use text extraction fallback", flush=True)
    except Exception:
        print("  ⚠️  LLM summarizer unavailable — will use text extraction fallback", flush=True)

    find_deferred_label()
    print(f"  Deferred label: {DEFERRED_LABEL_ID}", flush=True)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "localhost"
    finally:
        try:
            s.close()
        except Exception:
            pass

    # Start server FIRST so it's listening immediately
    server = ThreadedHTTPServer(("0.0.0.0", PORT), DashboardHandler)

    # Fetch and enrich emails in background — server is already up
    def start_enrichment():
        global EMAILS
        raw = fetch_emails()
        EMAILS = full_enrich(raw)
        print(f"\n  📥 Loaded {len(EMAILS)} emails (summaries from disk/snippets)", flush=True)
        
        # Re-queue emails without summaries for background processing
        for email in EMAILS:
            if not email.get("summary") or email["summary"] == email.get("snippet", ""):
                priority = email.get("tier_order", 2)
                SUMMARY_QUEUE.add(email["id"], email, priority=priority)
        
        # Start the summary worker if there are items to process
        if SUMMARY_QUEUE._queue:
            SUMMARY_QUEUE.start_worker(summarize_with_llm)
            print(f"  🚀 Summary worker started ({len(SUMMARY_QUEUE._queue)} emails queued)", flush=True)

    enrich_thread = threading.Thread(target=start_enrichment, daemon=True)
    enrich_thread.start()

    print(f"\n{'='*50}")
    print(f"  📧 Email Dashboard")
    print(f"  {'='*50}")
    print(f"  Local:   http://localhost:{PORT}")
    if local_ip != "localhost":
        print(f"  Network: http://{local_ip}:{PORT}")
    print(f"  {'='*50}\n")
    print("Press Ctrl+C to stop\n", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()
