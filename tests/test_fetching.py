#!/usr/bin/env python3
"""Tests for email fetching — Gmail link bug + unsubscribe extraction."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestFetchEmailsIntegration(unittest.TestCase):
    """Integration tests for fetch_emails with mocked Gmail API."""

    def setUp(self):
        # Create a fake home directory for testing
        self.fake_home = Path(__file__).resolve().parent / "tmp_test" / ".hermes"
        self.fake_home.mkdir(parents=True, exist_ok=True)
        
        self.user_dir = self.fake_home / "emails" / "testuser"
        self.user_dir.mkdir(parents=True, exist_ok=True)

    def _setup_cached_email(self):
        """Set up a cached/processed email with known threadId."""
        processed_data = {
            "email_ids": ["msg_001"],
            "last_updated": "2026-05-16T00:00:00Z"
        }
        (self.user_dir / ".processed_ids.json").write_text(json.dumps(processed_data))
        
        # Store summary record WITH threadId
        with open(self.user_dir / "tier2.jsonl", "w") as f:
            f.write(json.dumps({
                "email_id": "msg_001",
                "summary": "Test summary",
                "sender": "test@example.com",
                "subject": "Test Subject",
                "date": "2026-05-16",
                "threadId": "actual_thread_abc123"
            }) + "\n")

    def test_cached_email_threadid_is_actual_threadid_not_msgid(self):
        """Verify cached emails use actual threadId, not message ID.
        
        This test will FAIL before the fix and PASS after.
        """
        self._setup_cached_email()
        
        # Mock _fetch_single_email_metadata to return empty (no new emails)
        mock_fetch = MagicMock(return_value=None)

        with patch('email_dashboard.get_credentials') as mock_creds:
            mock_creds.return_value = MagicMock()
            
            with patch('googleapiclient.discovery.build') as mock_build:
                # Return a list with msg_001 (which is already processed, so won't be fetched)
                mock_service = MagicMock()
                mock_service.users().messages().list.return_value.execute.return_value = {
                    "messages": [{"id": "msg_001"}]
                }
                mock_build.return_value = mock_service
                
                # Patch Path.home() to return the parent of fake_home
                # So that when fetch_emails appends .hermes/emails/testuser,
                # it becomes tests/tmp_test/.hermes/emails/testuser
                with patch.object(Path, 'home', return_value=self.fake_home.parent):
                    with patch('email_dashboard._fetch_single_email_metadata', mock_fetch):
                        from email_dashboard import fetch_emails
                        
                        result = fetch_emails(max_results=20, username="testuser")
                        
                        # _fetch_single_email_metadata should NOT have been called
                        # since msg_001 is already processed
                        self.assertEqual(mock_fetch.call_count, 0, 
                            f"Should not fetch already-processed emails. Call count: {mock_fetch.call_count}")
                        
                        # Find the cached email in results
                        cached_email = None
                        for e in result:
                            if isinstance(e.get("id"), str) and "msg_001" in str(e.get("id", "")):
                                cached_email = e
                                break
                        
                        self.assertIsNotNone(cached_email, f"Cached email should be in results. Got: {result}")
                        
                        # THE BUG: threadId is msg_id instead of actual threadId
                        self.assertEqual(
                            cached_email.get("threadId"),
                            "actual_thread_abc123",
                            f"Cached email threadId should be actual Gmail threadId, not msg_id. Got: {cached_email.get('threadId')}"
                        )
                        
                        # gmail_link should use threadId
                        expected_link = f"https://mail.google.com/mail/mu/mp/330/#cv/Inbox/actual_thread_abc123"
                        self.assertEqual(
                            cached_email.get("gmail_link"),
                            expected_link,
                            f"Gmail link should use threadId. Got: {cached_email.get('gmail_link')}"
                        )

    def test_new_emails_extract_unsubscribe_url(self):
        """Verify new emails have unsubscribe_url extracted from headers/body.
        
        This test will FAIL before the fix and PASS after.
        """
        # No cached emails — msg_002 is new
        
        # Mock _fetch_single_email_metadata to return a known email dict
        def mock_fetch(msg_id, token_path):
            if msg_id == "msg_002":
                return {
                    "id": "msg_002",
                    "threadId": "thread_xyz789",
                    "from": "newsletter@example.com",
                    "to": "",
                    "subject": "Weekly Newsletter",
                    "date": "2026-05-16",
                    "snippet": "Test email",
                    "labels": ["UNREAD"],
                    "gmail_link": "https://mail.google.com/mail/mu/mp/330/#cv/Inbox/thread_xyz789",
                    "unsubscribe_url": "https://example.com/unsub?token=abc",
                }
            return None
        
        mock_fetch_func = MagicMock(side_effect=mock_fetch)

        with patch('email_dashboard.get_credentials') as mock_creds:
            mock_creds.return_value = MagicMock()
            
            with patch('googleapiclient.discovery.build') as mock_build:
                mock_service = MagicMock()
                mock_service.users().messages().list.return_value.execute.return_value = {
                    "messages": [{"id": "msg_002"}]
                }
                mock_build.return_value = mock_service
                
                # Patch Path.home() to return the parent of fake_home
                with patch.object(Path, 'home', return_value=self.fake_home.parent):
                    with patch('email_dashboard._fetch_single_email_metadata', mock_fetch_func):
                        from email_dashboard import fetch_emails
                        
                        result = fetch_emails(max_results=20, username="testuser")
                        
                        # _fetch_single_email_metadata should have been called once
                        self.assertEqual(mock_fetch_func.call_count, 1)
                        
                        # Find the new email in results
                        new_email = None
                        for e in result:
                            if isinstance(e.get("id"), str) and "msg_002" in str(e.get("id", "")):
                                new_email = e
                                break
                        
                        self.assertIsNotNone(new_email, f"New email should be in results. Got: {result}")
                        
                        # THE BUG: unsubscribe_url is always None (before fix)
                        self.assertIsNotNone(
                            new_email.get("unsubscribe_url"),
                            f"Unsubscribe URL should be extracted from List-Unsubscribe header. Got: {new_email.get('unsubscribe_url')}"
                        )
                        self.assertEqual(
                            new_email.get("unsubscribe_url"),
                            "https://example.com/unsub?token=abc"
                        )


if __name__ == "__main__":
    unittest.main()
