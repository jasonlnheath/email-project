"""Gmail email fetcher — pulls emails from Gmail API for the compression pipeline.

Uses raw HTTP calls to Gmail REST API (bypasses googleapiclient discovery limitations).
Returns structured email dicts matching the expected schema for the compression pipeline.

Dependencies: google-auth (for token refresh), requests or urllib.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

try:
    from google.oauth2.credentials import Credentials
except ImportError as exc:  # pragma: no cover
    print(
        f"ERROR: Required dependency not found — {exc.name}. "
        f"Install with: pip install google-auth",
        file=sys.stderr,
    )
    sys.exit(1)


# Gmail API base URL
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# Default token path used by the Hermes Google Workspace integration
DEFAULT_TOKEN_PATH = os.path.expanduser("~/.hermes/google_token.json")

# Gmail API maximum per-page results
GMAIL_API_MAX_RESULTS = 500


class GmailFetcher:
    """Fetch and parse emails from Gmail using raw HTTP REST API.

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
        self.max_results = min(max_results, 500)
        self.token_path = token_path or DEFAULT_TOKEN_PATH
        self._credentials = None
        self._token = None
        self._expiry = None

    # ── Authentication ───────────────────────────────────────────────────

    def _refresh_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        if not os.path.isfile(self.token_path):
            raise FileNotFoundError(
                f"OAuth token not found at {self.token_path}. "
                f"Run the Google Workspace setup to generate a token."
            )

        with open(self.token_path, "r", encoding="utf-8") as fh:
            token_data = json.load(fh)

        access_token = token_data.get("access_token") or token_data.get("token", "")
        refresh_token = token_data.get("refresh_token")

        if access_token:
            return access_token

        if refresh_token:
            return self._do_refresh(refresh_token, token_data)

        raise FileNotFoundError(
            f"No valid token in {self.token_path}. "
            f"File has neither 'access_token' nor 'refresh_token'."
        )

    def _do_refresh(self, refresh_token: str, token_data: dict) -> str:
        """Perform an OAuth2 refresh grant to get a new access token."""
        client_id = token_data.get("client_id", "")
        client_secret = token_data.get("client_secret", "")

        if not client_id or not client_secret:
            raise FileNotFoundError(
                f"Token file missing client_id/client_secret for refresh. "
                f"Re-run Google Workspace setup."
            )

        url = "https://oauth2.googleapis.com/token"
        data = (
            f"grant_type=refresh_token&refresh_token={refresh_token}"
            f"&client_id={client_id}&client_secret={client_secret}"
        ).encode("utf-8")

        req = Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                new_token = result.get("access_token")
                if not new_token:
                    raise FileNotFoundError(
                        f"Token refresh returned no access_token: {result}"
                    )
                return new_token
        except URLError as exc:
            raise FileNotFoundError(
                f"Token refresh failed: {exc}. "
                f"Re-run Google Workspace setup."
            ) from exc

    def _get_credentials(self):
        """Load google-auth Credentials object, refreshing if needed."""
        if self._credentials is None or self._credentials.expired:
            if not os.path.isfile(self.token_path):
                raise FileNotFoundError(
                    f"OAuth token not found at {self.token_path}. "
                    f"Run the Google Workspace setup to generate a token."
                )
            with open(self.token_path, "r", encoding="utf-8") as fh:
                token_data = json.load(fh)

            access_token = token_data.get("access_token") or token_data.get("token", "")
            refresh_token = token_data.get("refresh_token")
            client_id = token_data.get("client_id", "")
            client_secret = token_data.get("client_secret", "")
            token_uri = token_data.get("token_uri", "https://oauth2.googleapis.com/token")
            scopes = token_data.get("scopes", [])

            self._credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri=token_uri,
                client_id=client_id,
                client_secret=client_secret,
                scopes=scopes,
            )
            # Force a refresh to get a valid token
            if self._credentials.expired or not self._credentials.valid:
                try:
                    from google.auth.transport.requests import Request as AuthRequest
                    self._credentials.refresh(AuthRequest())
                except Exception:
                    pass  # Token might still be usable
        return self._credentials

    # ── API Calls ────────────────────────────────────────────────────────

    def _api_get(self, path: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to the Gmail API using google-auth transport."""
        from google.auth.transport.requests import Request as AuthRequest

        creds = self._get_credentials()

        # Build URL with query params
        url = f"{GMAIL_API_BASE}/{path}"
        if params:
            url += "?" + urlencode(params)

        # Use AuthorizedSession for proper auth handling
        try:
            from google.auth.transport.requests import AuthorizedSession
            auth_session = AuthorizedSession(creds)
            resp = auth_session.get(url, timeout=30)
        except ImportError:
            # Fallback: manually add token to headers
            if creds.token is None or creds.expired:
                creds.refresh(AuthRequest())
            req = Request(url)
            req.add_header("Authorization", f"Bearer {creds.token}")
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())

        if resp.status_code != 200:
            raise RuntimeError(
                f"Gmail API error: HTTP {resp.status_code}: {resp.text[:200]}"
            )

        return json.loads(resp.text)

    def fetch(
        self,
        query: str = "",
        after: Optional[str] = None,
        before: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[dict]:
        """Fetch emails from Gmail.

        Parameters
        ----------
        query : str
            Gmail search query string (e.g., 'is:unread').
        after : str, optional
            Only include messages dated after this date (YYYY-MM-DD).
        before : str, optional
            Only include messages dated before this date (YYYY-MM-DD).
        max_results : int, optional
            Override the instance's max_results for this call.

        Returns
        -------
        list[dict]
            List of parsed email dicts.
        """
        effective_max = max_results if max_results is not None else self.max_results
        # Build Gmail search query with date filters
        gmail_query = query.strip()
        if after:
            # Gmail uses 'after:YYYY/MM/DD' format
            gmail_after = after.replace("-", "/")
            gmail_query += f" after:{gmail_after}" if gmail_query else f"after:{gmail_after}"
        if before:
            gmail_before = before.replace("-", "/")
            gmail_query += f" before:{gmail_before}" if gmail_query else f"before:{gmail_before}"

         # Fetch message IDs via the messages/list endpoint
        params = {
            "maxResults": effective_max,
        }
        if gmail_query:
            params["q"] = gmail_query

        data = self._api_get("messages", params)
        message_ids = [m["id"] for m in data.get("messages", [])]

        if not message_ids:
            return []

        # Fetch full messages
        all_emails = []
        for msg_id in message_ids:
            try:
                msg_data = self._api_get(f"messages/{msg_id}", {"format": "full"})
                parsed = self.parse_email(msg_data)
                all_emails.append(parsed)
            except Exception:
                # Skip messages that fail to parse
                continue

        return all_emails

    # ── Parsing ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """Parse a date string in various formats.

        Supports RFC 2822, ISO 8601, and date-only formats.
        Returns naive datetime (no timezone info) for consistent comparison.
        Returns None if parsing fails.
        """
        if not date_str or not isinstance(date_str, str):
            return None

        date_str = date_str.strip()

        # Try RFC 2822 format: "Mon, 12 May 2026 10:30:00 +0000"
        try:
            dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
            return dt.replace(tzinfo=None)  # Return naive for consistent comparison
        except ValueError:
            pass

        # Try ISO 8601 with timezone: "2026-05-12T10:30:00Z" or "+00:00"
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.replace(tzinfo=None)  # Return naive for consistent comparison
        except ValueError:
            pass

        # Try date-only: "2026-05-12"
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt  # Already naive
        except ValueError:
            pass

        return None

    @staticmethod
    def _extract_text_from_payload(payload: dict) -> str:
        """Extract text content from a Gmail API payload.

        Handles plain text, multipart/alternative (prefers text/plain),
        and HTML (strips tags).
        """
        mime_type = payload.get("mimeType", "")

        # Direct body
        if "body" in payload and "data" in payload["body"]:
            raw_data = payload["body"]["data"]
            if raw_data:
                try:
                    decoded = base64.urlsafe_b64decode(raw_data).decode("utf-8")
                    if mime_type == "text/html":
                        return re.sub(r"<[^>]+>", "", decoded)
                    return decoded
                except Exception:
                    return ""

        # Multipart — look for text/plain part first, then text/html
        parts = payload.get("parts", [])
        if not parts:
            return ""

        # Prefer text/plain
        for part in parts:
            if part.get("mimeType") == "text/plain":
                body = part.get("body", {})
                raw_data = body.get("data", "")
                if raw_data:
                    try:
                        return base64.urlsafe_b64decode(raw_data).decode("utf-8")
                    except Exception:
                        continue

        # Fall back to text/html
        for part in parts:
            if part.get("mimeType") == "text/html":
                body = part.get("body", {})
                raw_data = body.get("data", "")
                if raw_data:
                    try:
                        html = base64.urlsafe_b64decode(raw_data).decode("utf-8")
                        return re.sub(r"<[^>]+>", "", html)
                    except Exception:
                        continue

        return ""

    @staticmethod
    def _get_header(headers: list, name: str) -> Optional[str]:
        """Get a header value by name (case-insensitive)."""
        for h in headers:
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return None

    @classmethod
    def parse_email(cls, raw_message: dict) -> dict:
        """Parse a raw Gmail API message into a structured email dict.

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

        # Extract standard fields
        subject = cls._get_header(headers, "Subject") or "(no subject)"
        sender = cls._get_header(headers, "From") or "(unknown sender)"
        date_str = cls._get_header(headers, "Date") or ""
        snippet = raw_message.get("snippet", "")

        # Parse date (store original string for display)
        parsed_date = cls._parse_date(date_str) if date_str else None
        date = date_str if date_str else ""

        # Extract body text
        body = cls._extract_text_from_payload(payload)

        # Extract attachments
        attachments = []
        parts = payload.get("parts", [])
        for part in parts:
            mime_type = part.get("mimeType", "")
            if mime_type and not mime_type.startswith("text/"):
                body_info = part.get("body", {})
                filename = part.get("filename", "")
                size = body_info.get("size", 0)
                attachments.append({
                    "filename": filename,
                    "type": mime_type,
                    "size_bytes": size,
                })

        # Extract RFC822 Message-ID for direct Gmail links (from headers)
        rfc822_message_id = cls._get_header(headers, "Message-ID") or ""

        return {
            "id": raw_message.get("id", ""),
            "threadId": raw_message.get("threadId", ""),
            "rfc822MessageId": rfc822_message_id,
            "subject": subject,
            "sender": sender,
            "date": date,
            "body": body,
            "snippet": snippet,
            "attachments": attachments,
        }

    @classmethod
    def _parse_messages(cls, messages: list) -> List[dict]:
        """Parse a list of raw message dicts into structured email dicts."""
        results = []
        for msg in messages:
            try:
                parsed = cls.parse_email(msg)
                results.append(parsed)
            except Exception:
                continue
        return results

    # ── Filtering ────────────────────────────────────────────────────────

    def filter_by_date(
        self,
        messages: List[dict],
        after: Optional[str] = None,
        before: Optional[str] = None,
    ) -> List[dict]:
        """Filter messages by date range.

        Parameters
        ----------
        messages : list[dict]
            List of email dicts with 'date' field.
        after : str, optional
            Only include messages dated after this date (YYYY-MM-DD).
        before : str, optional
            Only include messages dated before this date (YYYY-MM-DD).

        Returns
        -------
        list[dict]
            Filtered list of email dicts.
        """
        after_dt = self._parse_date(after) if after else None
        before_dt = self._parse_date(before) if before else None

        filtered = []
        for msg in messages:
            msg_date = self._parse_date(msg.get("date", ""))
            if msg_date is None:
                continue

            if after_dt and msg_date < after_dt:
                continue
            if before_dt and msg_date >= before_dt:
                continue

            filtered.append(msg)

        return filtered
