"""Gmail email fetcher — pulls emails from Gmail API for the compression pipeline.

Uses google-api-python-client with OAuth2 authentication via ~/.hermes/google_token.json.
Returns structured email dicts matching the expected schema for the compression pipeline.

Dependencies: google-api-python-client, google-auth (both already installed).
"""

from __future__ import annotations

import base64
import email as email_module
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError as exc:  # pragma: no cover
    print(
        f"ERROR: Required dependency not found — {exc.name}. "
        f"Install with: pip install google-api-python-client google-auth google-auth-oauthlib",
        file=sys.stderr,
    )
    sys.exit(1)


# Gmail API scope — read-only access to user's email
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Default token path used by the Hermes Google Workspace integration
DEFAULT_TOKEN_PATH = os.path.expanduser("~/.hermes/google_token.json")

# Gmail API maximum per-page results
GMAIL_API_MAX_RESULTS = 500


class GmailFetcher:
    """Fetch and parse emails from Gmail using the Gmail API.

    Parameters
    ----------
    max_results : int
        Maximum number of emails to fetch (capped at 500 by Gmail API).
    token_path : str
        Path to the OAuth2 credentials JSON file. Defaults to ~/.hermes/google_token.json.
    """

    def __init__(
        self,
        max_results: int = 50,
        token_path: Optional[str] = None,
    ):
        self.max_results = min(max_results, GMAIL_API_MAX_RESULTS)
        self.token_path = token_path or DEFAULT_TOKEN_PATH
        self._service = None

    # ── Authentication ───────────────────────────────────────────────────

    def _get_credentials(self) -> Credentials:
        """Load OAuth2 credentials from the token file."""
        if not os.path.isfile(self.token_path):
            raise FileNotFoundError(
                f"OAuth token not found at {self.token_path}. "
                f"Run the Google Workspace setup to generate a token."
            )

        with open(self.token_path, "r", encoding="utf-8") as fh:
            token_data = json.load(fh)

        # Support both 'access_token' (googleapiclient format) and 'token' (google-auth format)
        access_token = token_data.get("access_token") or token_data.get("token", "")
        return Credentials(
            token=access_token,
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=[SCOPES[0]],
        )

    def _build_service(self):
        """Build the Gmail API service object."""
        if self._service is None:
            creds = self._get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    # ── Email fetching ───────────────────────────────────────────────────

    def fetch(
        self,
        query: Optional[str] = None,
        max_results: Optional[int] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
    ) -> List[Dict]:
        """Fetch emails from Gmail with optional filters.

        Parameters
        ----------
        query : str or None
            Gmail search query (e.g., 'from:boss', 'has:attachment').
        max_results : int or None
            Override the default max_results.
        after : str or None
            Only return emails after this date (YYYY-MM-DD format).
        before : str or None
            Only return emails before this date (YYYY-MM-DD format).

        Returns
        -------
        list of dict — parsed email records.
        """
        service = self._build_service()
        limit = min(max_results or self.max_results, GMAIL_API_MAX_RESULTS)

        # Build Gmail search query
        gmail_query_parts = []
        if query:
            gmail_query_parts.append(query)
        if after:
            gmail_query_parts.append(f"after:{after}")
        if before:
            gmail_query_parts.append(f"before:{before}")
        gmail_query = " ".join(gmail_query_parts) if gmail_query_parts else "in:anywhere"

        # Fetch messages
        results = service.users().messages().list(
            userId="me",
            q=gmail_query,
            maxResults=limit,
        ).execute()

        messages = results.get("messages", [])

        if not messages:
            return []

        # Fetch full message details (batched)
        parsed_emails = []
        for msg in messages:
            try:
                raw = service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="full",
                ).execute()
                parsed = self.parse_email(raw)
                parsed_emails.append(parsed)
            except Exception as exc:  # pragma: no cover — API errors on individual msgs
                print(f"[gmail_fetcher] Warning: failed to fetch message {msg.get('id')}: {exc}", file=sys.stderr)
                continue

        return parsed_emails

    def _parse_messages(self, messages: List[Dict]) -> List[Dict]:
        """Parse a list of raw Gmail message dicts into structured email records.

        This is a convenience method for testing without hitting the API.
        """
        if not messages:
            return []

        results = []
        for msg in messages:
            try:
                parsed = self.parse_email(msg)
                results.append(parsed)
            except Exception as exc:  # pragma: no cover
                print(f"[gmail_fetcher] Warning: parse error: {exc}", file=sys.stderr)
                continue
        return results

     # ── Email parsing ────────────────────────────────────────────────────

    @staticmethod
    def parse_email(raw_message: Dict) -> Dict:
        """Parse a raw Gmail API message dict into a structured email record.

        Parameters
        ----------
        raw_message : dict
            Raw message from Gmail API (format='full').

        Returns
        -------
        dict with keys: id, subject, sender, date, body, snippet, attachments
        """
        payload = raw_message.get("payload", {})
        headers = payload.get("headers", [])

        # Extract headers
        def _get_header(name: str) -> str:
            for h in headers:
                if h["name"].lower() == name.lower():
                    return h.get("value", "")
            return ""

        msg_id = raw_message.get("id", "unknown")
        subject = _get_header("Subject") or "(no subject)"
        sender = _get_header("From") or "(unknown sender)"
        date_str = _get_header("Date") or ""

        # Extract body text from MIME parts
        body = GmailFetcher._extract_body(payload)

        # Parse attachments info
        attachments = GmailFetcher._extract_attachments(payload)

        # Construct Gmail web URL for this message
        gmail_url = f"https://mail.google.com/mail/u/0/#inbox/{msg_id}"

        return {
            "id": msg_id,
            "subject": subject,
            "sender": sender,
            "date": date_str,
            "body": body,
            "snippet": raw_message.get("snippet", ""),
            "attachments": attachments,
            "gmail_url": gmail_url,
        }

    @staticmethod
    def _extract_body(payload: Dict) -> str:
        """Extract plain text body from a MIME payload."""
        parts = payload.get("parts", [])
        if not parts:
            # Try top-level body directly
            body_data = payload.get("body", {})
            if body_data and body_data.get("data"):
                raw = GmailFetcher._decode_mime_body(body_data["data"])
                # Strip HTML tags if content looks like HTML
                if "<" in raw and ">" in raw:
                    import re as _re
                    return _re.sub(r"<[^>]+>", "", raw)
                return raw
            return ""

        # First pass: prefer text/plain
        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                body_data = part.get("body", {})
                if body_data and body_data.get("data"):
                    return GmailFetcher._decode_mime_body(body_data["data"])

        # Second pass: fall back to text/html (stripped)
        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/html":
                body_data = part.get("body", {})
                if body_data and body_data.get("data"):
                    html = GmailFetcher._decode_mime_body(body_data["data"])
                    import re as _re
                    return _re.sub(r"<[^>]+>", "", html)

        # No text parts found — try multipart/alternative (nested)
        for part in parts:
            inner_parts = part.get("parts", [])
            for inner in inner_parts:
                if inner.get("mimeType") == "text/plain":
                    body_data = inner.get("body", {})
                    if body_data and body_data.get("data"):
                        return GmailFetcher._decode_mime_body(body_data["data"])

        return ""

    @staticmethod
    def _decode_mime_body(data: str) -> str:
        """Decode a base64url-encoded MIME body string."""
        if not data:
            return ""
        padded = data + "=" * (-len(data) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded)
            return decoded.decode("utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _extract_attachments(payload: Dict) -> List[Dict]:
        """Extract attachment metadata from payload parts."""
        attachments = []
        for part in payload.get("parts", []):
            if part.get("filename") and not part.get("mimeType", "").startswith("text/"):
                body = part.get("body", {})
                size = int(body.get("size", 0)) if body else 0
                attachments.append({
                    "filename": part["filename"],
                    "type": part.get("mimeType", "unknown"),
                    "size_bytes": size,
                })
        return attachments

    # ── Date filtering ───────────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """Parse a date string into a datetime object (always returns naive UTC)."""
        if not date_str:
            return None
        # Try common formats
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822
            "%a, %d %b %Y %H:%M:%S %Z",  # with timezone name
            "%Y-%m-%dT%H:%M:%SZ",         # ISO 8601 UTC
            "%Y-%m-%dT%H:%M:%S%z",        # ISO 8601 with offset
            "%Y-%m-%d",                    # Date only
        ):
            try:
                dt = datetime.strptime(date_str, fmt)
                # Normalize to naive UTC for consistent comparison
                if dt.tzinfo is not None:
                    from datetime import timezone
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except (ValueError, TypeError):
                continue
        return None

    def filter_by_date(
        self,
        messages: List[Dict],
        after: Optional[str] = None,
        before: Optional[str] = None,
    ) -> List[Dict]:
        """Filter parsed email records by date range.

        Parameters
        ----------
        messages : list of dict
            Parsed email records (must have 'date' field).
        after : str or None
            Only include emails after this date (YYYY-MM-DD).
        before : str or None
            Only include emails before this date (YYYY-MM-DD).

        Returns
        -------
        list of dict — filtered email records.
        """
        if not messages:
            return []

        after_dt = datetime.strptime(after, "%Y-%m-%d") if after else None
        before_dt = datetime.strptime(before, "%Y-%m-%d") if before else None

        results = []
        for msg in messages:
            msg_date = self._parse_date(msg.get("date", ""))
            if msg_date is None:
                continue

            # Normalize to date-only for comparison
            msg_date_only = msg_date.replace(hour=0, minute=0, second=0, microsecond=0)

            if after_dt and msg_date_only < after_dt:
                continue
            if before_dt and msg_date_only >= before_dt:
                continue

            results.append(msg)

        return results
