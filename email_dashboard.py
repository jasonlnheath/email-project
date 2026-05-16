#!/usr/bin/env python3
"""Email Action Dashboard — mobile-first, AJAX-powered, with LLM summaries & VIP priority."""

import http.server
import json
import os
import re
import socket
import socketserver
import sys
import threading
import traceback
import urllib.parse

# ── Configuration ──────────────────────────────────────────────
PORT = 9999
GAPI = os.path.expanduser("~/.hermes/skills/productivity/google-workspace/scripts/google_api.py")
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.expanduser("/home/jason/relmgr/contacts.db")
LLAMA_CPP_HOST = "http://localhost:8033"
LLAMA_CPP_MODEL = "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"

# ── Global state ───────────────────────────────────────────────
EMAILS = []
DEFERRED_LABEL_ID = None


def subprocess_run(cmd):
    """Run a subprocess and return stdout/stderr/returncode."""
    import subprocess as sp
    try:
        r = sp.run(cmd, capture_output=True, text=True, timeout=60)
        return {"stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode}
    except sp.TimeoutExpired:
        return {"stdout": "", "stderr": "timeout", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


# ── VIP / Contact Lookup ───────────────────────────────────────
def load_vip_contacts():
    """Load VIP contacts from RelMgr database. Returns dict: email -> {name, relationship_type}."""
    vip_map = {}
    if not os.path.isfile(DB_PATH):
        return vip_map
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
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
                # Also store by name for fuzzy matching
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


def get_priority(email, vip_map):
    """Determine priority tier for an email. Returns (tier_name, tier_order, vip_info)."""
    from_field = email.get('from', '')
    sender_email, display_name = extract_sender_email(from_field)

    # VIP check
    vip_info = vip_map.get(sender_email)
    if not vip_info and display_name:
        vip_info = vip_map.get(f"vip_name_{display_name.lower()}")

    if vip_info:
        return ('VIP_HIGH', 0, vip_info)

    # HIGH: school/family, financial, security
    high_keywords = ['school', 'trip', 'deadline', 'payment', 'due', 'security', 'alert',
                     'password', 'login', 'transaction', 'bank', 'financial']
    text = f"{email.get('subject','')} {email.get('snippet','')}".lower()
    labels = set(email.get('labels', []))
    if any(kw in text for kw in high_keywords):
        return ('HIGH', 1, None)

    # CATEGORY_UPDATES → MEDIUM
    if labels & {'CATEGORY_UPDATES'}:
        return ('MEDIUM', 2, None)

    # Promotions/Promotions category → LOW
    if labels & {'CATEGORY_PROMOTIONS'}:
        return ('LOW', 3, None)

    # Newsletter keywords → LOW
    newsletter_kw = ['newsletter', 'unsubscribe', 'mailing', 'campaign', 'digest', 'promo']
    if any(kw in text for kw in newsletter_kw):
        return ('LOW', 3, None)

    # Default → MEDIUM
    return ('MEDIUM', 2, None)


# ── LLM Summarizer ─────────────────────────────────────────────
def summarize_with_llm(email_dict):
    """Summarize an email using Qwen via llama.cpp. Returns summary string or None on failure."""
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
        # Strip thinking tags if present
        summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL).strip()
        return summary if summary else None
    except Exception:
        return None


def fetch_full_body(msg_id):
    """Fetch the full body of an email via GAPI."""
    result = subprocess_run([sys.executable, GAPI, "gmail", "get", msg_id])
    try:
        data = json.loads(result["stdout"])
        return data.get("body", "")
    except (json.JSONDecodeError, KeyError):
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
        if not line.startswith('[') and not line.startswith('http') and len(line) > 20:
            summary_lines.append(line)

    if summary_lines:
        return "\n".join(f"• {line}" for line in summary_lines[:4])
    else:
        snippet = cleaned_lines[0][:200] if cleaned_lines else "No extractable content."
        return f"{snippet}..."


def extract_unsubscribe(msg_id):
    """Extract List-Unsubscribe header or body link from an email. Returns URL or None."""
    result = subprocess_run([sys.executable, GAPI, "gmail", "get", msg_id])
    try:
        data = json.loads(result["stdout"])
        payload = data.get("payload", {})
        headers = payload.get("headers", [])
        for h in headers:
            if h.get("name", "").lower() == "list-unsubscribe":
                val = h.get("value", "")
                # Extract URL from header value (may contain <url> or just url)
                match = re.search(r'<(https?://[^>]+)>', val)
                if match:
                    return match.group(1)
                # Try bare URL
                match = re.search(r'https?://\S+', val)
                if match:
                    return match.group(0)
        # No header unsubscribe — try extracting from body HTML
        body = data.get("body", "") or ""
        if body:
            # Pattern 1: word like "unsubscribe" followed by href
            m = re.search(r'(?:unsubscribe|opt[-_.]?out)[^<]*?href\s*=\s*[\'"]([^\'">]+)', body, re.IGNORECASE | re.DOTALL)
            if m:
                url = m.group(1).rstrip(')')
                return url
            # Pattern 2: href contains unsubscribe keyword
            m = re.search(r'href=[\'"](https?://[^\'"]*(?:unsubscribe|opt[-_]?out|remove|cancel)[^\'"]*)[\'"]', body, re.IGNORECASE)
            if m:
                return m.group(1).rstrip(')')
            # Pattern 3: <a> tag with unsubscribe text and href
            m = re.search(r'<a[^>]*>(?:.*(?:unsubscribe|opt[-_.]?out).*)?</a>', body, re.IGNORECASE | re.DOTALL)
            if m:
                anchor = m.group(0)
                hm = re.search(r'href=[\'"](https?://[^\'">]+)', anchor)
                if hm:
                    return hm.group(1).rstrip(')')
    except Exception:
        pass
    return None


def extract_unsubscribe_header_only(msg_id):
    """Fast unsubscribe check — only header, no body parsing. Returns URL or None."""
    result = subprocess_run([sys.executable, GAPI, "gmail", "get", msg_id])
    try:
        data = json.loads(result["stdout"])
        payload = data.get("payload", {})
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
    except Exception:
        pass
    return None


# ── Helpers ────────────────────────────────────────────────────
def find_deferred_label():
    global DEFERRED_LABEL_ID
    try:
        result = subprocess_run([sys.executable, GAPI, "gmail", "labels"])
        labels = json.loads(result["stdout"])
        for l in labels:
            if "Deferred" in l.get("name", ""):
                DEFERRED_LABEL_ID = l["id"]
                return
    except Exception as e:
        print(f"Warning: could not find deferred label: {e}", file=sys.stderr)

    if EMAILS:
        subprocess_run([sys.executable, GAPI, "gmail", "modify", EMAILS[0]["id"],
                        "add-labels", "Label_Deferred"])
        try:
            result = subprocess_run([sys.executable, GAPI, "gmail", "labels"])
            labels = json.loads(result["stdout"])
            for l in labels:
                if "Deferred" in l.get("name", ""):
                    DEFERRED_LABEL_ID = l["id"]
                    return
        except Exception:
            pass

    DEFERRED_LABEL_ID = "Label_Deferred"


def fetch_emails():
    result = subprocess_run([sys.executable, GAPI, "gmail", "search", "is:unread", "--max", "50"])
    try:
        data = json.loads(result["stdout"])
    except (json.JSONDecodeError, KeyError):
        return []

    emails = []
    for e in data:
        thread_id = e.get("threadId", "")
        msg_id = e.get("id", "")
        # Skip unsubscribe check here — background enrichment handles it
        emails.append({
            "id": msg_id,
            "threadId": thread_id,
            "from": e.get("from", "Unknown"),
            "to": e.get("to", ""),
            "subject": e.get("subject", "No subject"),
            "date": e.get("date", ""),
            "snippet": e.get("snippet", ""),
            "labels": e.get("labels", []),
            "gmail_link": f"https://mail.google.com/mail/mu/mp/330/#cv/Inbox/{thread_id}" if thread_id else "",
            "unsubscribe_url": None,
        })
    return emails


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


# ── Enrich & Sort Emails ───────────────────────────────────────
def enrich_and_sort_emails(raw_emails):
    """Enrich emails with VIP/priority info, pre-compute summaries for VIP/HIGH, and sort."""
    vip_map = load_vip_contacts()

    enriched = []
    for e in raw_emails:
        tier_name, tier_order, vip_info = get_priority(e, vip_map)
        enriched.append({
            **e,
            'tier': tier_name,
            'tier_order': tier_order,
            'vip_info': vip_info,
            'summary': None,  # Will be filled below for VIP/HIGH
        })

    # Pre-compute summaries for VIP and HIGH priority emails only
    llm_available = False
    try:
        import requests
        resp = requests.get(f"{LLAMA_CPP_HOST}/v1/models", timeout=5)
        if resp.status_code == 200:
            llm_available = True
    except Exception:
        pass

    if llm_available:
        for email in enriched:
            if email['tier'] in ('VIP_HIGH', 'HIGH') and not email.get('summary'):
                body = fetch_full_body(email['id'])
                if body:
                    email_dict = {
                        'sender': email['from'],
                        'subject': email['subject'],
                        'date': email['date'],
                        'body': body,
                    }
                    summary = summarize_with_llm(email_dict)
                    if not summary:
                        summary = summarize_email(body, email['subject'])
                    email['summary'] = summary

    # Sort: VIP_HIGH first, then HIGH, MEDIUM, LOW
    enriched.sort(key=lambda x: x['tier_order'])
    return enriched


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
        html_path = os.path.join(SCRIPT_DIR, "index.html")
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
                EMAILS = quick_enrich(raw)
                # Kick off full enrichment in background for VIP/HIGH summaries
                threading.Thread(target=_do_full_enrich, daemon=True).start()
                self.send_json({"success": True, "count": len(EMAILS)})
                return

            if parsed.path == "/api/labels":
                result = subprocess_run([sys.executable, GAPI, "gmail", "labels"])
                try:
                    labels = json.loads(result["stdout"])
                    self.send_json({"labels": labels})
                except Exception:
                    self.send_json({"labels": []})
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

                # Try LLM summary first, fall back to text extraction
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

            try:
                stdout, stderr = do_action(action, msg_id)
                raw = fetch_emails()
                EMAILS = enrich_and_sort_emails(raw)

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


def do_action(action, msg_id):
    add_labels = []
    remove_labels = []

    if action == "read":
        remove_labels.append("UNREAD")
    elif action == "delete":
        remove_labels.append("INBOX")
    elif action == "defer":
        add_labels.append(DEFERRED_LABEL_ID)
        remove_labels.append("UNREAD")

    cmd = [sys.executable, GAPI, "gmail", "modify", msg_id]
    if add_labels:
        cmd.extend(["--add-labels", ",".join(add_labels)])
    if remove_labels:
        cmd.extend(["--remove-labels", ",".join(remove_labels)])

    result = subprocess_run(cmd)
    return result["stdout"].strip(), result.get("stderr", "").strip()


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ── Quick enrichment (no LLM — just tier/sort) ────────────────
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


# ── Full enrichment (with LLM summaries for VIP/HIGH) ─────────
def full_enrich(raw_emails):
    """Full enrichment with LLM summaries for VIP/HIGH emails."""
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

    llm_available = False
    try:
        import requests
        resp = requests.get(f"{LLAMA_CPP_HOST}/v1/models", timeout=5)
        if resp.status_code == 200:
            llm_available = True
    except Exception:
        pass

    if llm_available:
        for email in enriched:
            if email['tier'] in ('VIP_HIGH', 'HIGH') and not email.get('summary'):
                body = fetch_full_body(email['id'])
                if body:
                    email_dict = {
                        'sender': email['from'],
                        'subject': email['subject'],
                        'date': email['date'],
                        'body': body,
                    }
                    summary = summarize_with_llm(email_dict)
                    if not summary:
                        summary = summarize_email(body, email['subject'])
                    email['summary'] = summary

    enriched.sort(key=lambda x: x['tier_order'])
    return enriched


# ── Background enrichment ──────────────────────────────────────
def _do_full_enrich():
    """Full enrichment with LLM summaries and body-based unsubscribe for all emails."""
    global EMAILS
    try:
        raw = fetch_emails()
        EMAILS = full_enrich(raw)

        # Now do body-based unsubscribe extraction for ALL emails (not just VIP/HIGH)
        updated = False
        for email in EMAILS:
            if not email.get('unsubscribe_url'):
                unsub = extract_unsubscribe(email['id'])
                if unsub:
                    email['unsubscribe_url'] = unsub
                    updated = True

        if updated:
            print(f"  ✨ Found unsubscribe links for {sum(1 for e in EMAILS if e.get('unsubscribe_url'))} emails", flush=True)

        print(f"\n  ✨ Fully enriched {len(EMAILS)} emails", flush=True)
    except Exception as e:
        print(f"\n  ⚠️  Enrichment error: {e}", file=sys.stderr, flush=True)


def background_enrich():
    """Alias for backward compat — same as _do_full_enrich."""
    _do_full_enrich()


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
        raw = fetch_emails()
        EMAILS = quick_enrich(raw)
        print(f"\n  📥 Loaded {len(EMAILS)} emails (summaries loading...)", flush=True)
        # Full enrichment (LLM summaries + body-based unsubscribe) in another thread
        full_thread = threading.Thread(target=_do_full_enrich, daemon=True)
        full_thread.start()

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
