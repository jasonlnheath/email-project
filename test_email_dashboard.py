#!/usr/bin/env python3
"""Tests for email_dashboard.py — TDD approach: write failing tests first, then make them pass."""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import the module under test
import email_dashboard as ed


class TestFetchEmails:
    """Test fetch_emails() function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create temp directory for test data
        self.temp_dir = tempfile.mkdtemp()
        
        # Create .hermes/emails subdirectory (matching pipeline structure)
        self.pipeline_dir = Path(self.temp_dir) / ".hermes" / "emails"
        self.pipeline_dir.mkdir(parents=True, exist_ok=True)
        
        # Create mock processed_ids.json
        self.processed_file = self.pipeline_dir / ".processed_ids.json"
        self.processed_file.write_text(json.dumps({
            "email_ids": ["processed_1", "processed_2"],
            "last_updated": "2026-05-16T12:00:00Z",
            "total_processed": 2
        }))
        
        # Create mock tier2.jsonl
        self.tier2_file = self.pipeline_dir / "tier2.jsonl"
        self.tier2_file.write_text(json.dumps({
            "email_id": "processed_1",
            "subject": "Test Email 1",
            "sender": "test@example.com",
            "summary": "This is a test summary"
        }) + "\n")
        
    def test_fetch_emails_loads_summaries_from_disk(self):
        """Test that fetch_emails() loads summaries from tier2.jsonl."""
        # This test should FAIL initially because the current implementation
        # doesn't load summaries from disk
        with patch.object(ed, 'get_service') as mock_get_service:
            # Mock the Gmail API response
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            
            # Mock list response
            mock_list_response = {
                "messages": [
                    {"id": "processed_1"},
                    {"id": "new_email"}
                ]
            }
            mock_service.users().messages().list.return_value.execute.return_value = mock_list_response
            
            # Mock get response for new email only
            mock_get_response = {
                "id": "new_email",
                "threadId": "new_email_thread",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "new@example.com"},
                        {"name": "Subject", "value": "New Email Subject"}
                    ]
                },
                "snippet": "New email snippet"
            }
            mock_service.users().messages().get.return_value.execute.return_value = mock_get_response
            
            # Patch the pipeline directory
            with patch('pathlib.Path.home') as mock_home:
                mock_home.return_value = Path(self.temp_dir)
                
                emails = ed.fetch_emails()
                
                # Should have 2 emails (1 from disk, 1 fetched)
                assert len(emails) == 2
                
                # First email should have summary from disk
                assert emails[0]["summary"] == "This is a test summary"
                assert emails[0]["subject"] == "Test Email 1"
                
                # Second email should be freshly fetched
                assert emails[1]["subject"] == "New Email Subject"
                assert emails[1]["from"] == "new@example.com"
    
    def test_fetch_emails_only_fetches_new_emails(self):
        """Test that fetch_emails() doesn't fetch already-processed emails."""
        with patch.object(ed, 'get_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            
            mock_list_response = {
                "messages": [
                    {"id": "processed_1"},  # Should NOT be fetched
                    {"id": "new_email"}     # Should be fetched
                ]
            }
            mock_service.users().messages().list.return_value.execute.return_value = mock_list_response
            
            with patch.object(Path, 'home') as mock_home:
                mock_home.return_value = Path(self.temp_dir)
                
                ed.fetch_emails()
                
                # Should only call get() for new_email, not processed_1
                calls = mock_service.users().messages().get.call_args_list
                assert len(calls) == 1  # Only one call for the new email
                assert calls[0][1]["id"] == "new_email"


class TestDoAction:
    """Test do_action() function."""
    
    def test_do_action_read(self):
        """Test that do_action('read') removes UNREAD label."""
        with patch.object(ed, 'get_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            
            result, error = ed.do_action("read", "test_email_id")
            
            # Verify the modify call was made correctly
            mock_service.users().messages().modify.assert_called_once_with(
                userId="me", id="test_email_id", body={"removeLabelIds": ["UNREAD"]}
            )
            assert "Done" in result
    
    def test_do_action_delete(self):
        """Test that do_action('delete') removes INBOX label."""
        with patch.object(ed, 'get_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            
            result, error = ed.do_action("delete", "test_email_id")
            
            # Verify the modify call was made correctly
            mock_service.users().messages().modify.assert_called_once_with(
                userId="me", id="test_email_id", body={"removeLabelIds": ["INBOX"]}
            )
            assert "Done" in result
    
    def test_do_action_defer(self):
        """Test that do_action('defer') adds DEFERRED label and removes UNREAD."""
        with patch.object(ed, 'get_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            
            # Set up deferred label ID
            ed.DEFERRED_LABEL_ID = "Label_Deferred"
            
            result, error = ed.do_action("defer", "test_email_id")
            
            # Verify the modify call was made correctly
            mock_service.users().messages().modify.assert_called_once_with(
                userId="me", id="test_email_id", body={
                    "addLabelIds": ["Label_Deferred"],
                    "removeLabelIds": ["UNREAD"]
                }
            )
            assert "Done" in result


class TestQuickEnrich:
    """Test quick_enrich() function."""
    
    def test_quick_enrich_adds_tier(self):
        """Test that quick_enrich() adds tier/priority to emails."""
        raw_emails = [
            {"id": "1", "from": "vip@example.com", "subject": "Urgent", "labels": [], "snippet": ""},
            {"id": "2", "from": "normal@example.com", "subject": "Newsletter", "labels": ["CATEGORY_PROMOTIONS"], "snippet": ""}
        ]
        
        enriched = ed.quick_enrich(raw_emails)
        
        # Should have 2 emails with tiers
        assert len(enriched) == 2
        
        # First email should be VIP_HIGH (if vip@example.com is in contacts)
        # or HIGH (due to "Urgent" keyword)
        assert enriched[0]["tier"] in ("VIP_HIGH", "HIGH")
        
        # Second email should be LOW (newsletter/promotion)
        assert enriched[1]["tier"] == "LOW"


class TestHTTPHandler:
    """Test HTTP handler functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create a simple test server
        self.server = None
        self.server_thread = None
        
    def teardown_method(self):
        """Clean up test server."""
        if self.server:
            self.server.shutdown()
            self.server_thread.join(timeout=5)
    
    def test_get_root_serves_html(self):
        """Test that GET / serves HTML with email data."""
        # Set up test emails
        ed.EMAILS = [
            {
                "id": "test_1",
                "threadId": "test_1",
                "from": "test@example.com",
                "subject": "Test Email",
                "date": "2026-05-16T12:00:00Z",
                "snippet": "Test snippet",
                "labels": ["UNREAD"],
                "gmail_link": "https://mail.google.com/mail/mu/mp/330/#cv/Inbox/test_1",
                "unsubscribe_url": None,
                "tier": "HIGH",
                "summary": "Test summary"
            }
        ]
        
        # Create a test server
        server = ed.ThreadedHTTPServer(("127.0.0.1", 0), ed.DashboardHandler)
        port = server.server_address[1]
        self.server = server
        self.server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.server_thread.start()
        
        # Make HTTP request
        import urllib.request
        response = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        html = response.read().decode("utf-8")
        
        # Verify HTML contains email data
        assert "Test Email" in html
        assert "test@example.com" in html
        assert "Test summary" in html


class TestIntegration:
    """Integration tests for the full workflow."""
    
    def test_full_workflow(self):
        """Test the complete workflow: fetch -> enrich -> action -> verify."""
        # This is a high-level integration test
        # In a real scenario, this would test the full HTTP request/response cycle
        
        # For now, just verify the core functions work together
        raw_emails = [
            {"id": "1", "from": "vip@family.com", "subject": "Urgent: Family matter", "labels": [], "snippet": ""},
            {"id": "2", "from": "newsletter@example.com", "subject": "Weekly Newsletter", "labels": ["CATEGORY_PROMOTIONS"], "snippet": ""}
        ]
        
        enriched = ed.quick_enrich(raw_emails)
        
        # Verify enrichment worked
        assert len(enriched) == 2
        assert all("tier" in e for e in enriched)
        
        # Verify sorting (VIP_HIGH first, then LOW)
        assert enriched[0]["tier_order"] < enriched[1]["tier_order"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
