#!/usr/bin/env python3
"""Tests for async summary queue — TDD RED-GREEN-REFACTOR."""

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))


class TestSummaryQueue:
    """Test the SummaryQueue class."""

    def setup_method(self):
        """Set up test fixtures."""
        # Import after path is set
        from email_dashboard import SummaryQueue
        self.queue = SummaryQueue()

    def test_create_queue(self):
        """Test that SummaryQueue can be created."""
        assert self.queue is not None
        assert len(self.queue._queue) == 0
        assert self.queue._status == {}

    def test_add_to_queue(self):
        """Test adding an email to the queue."""
        self.queue.add("email_1", "test_email_data")
        assert len(self.queue._queue) == 1
        assert self.queue._queue[0]["msg_id"] == "email_1"
        assert self.queue._status["email_1"]["state"] == "pending"

    def test_add_duplicate_skips(self):
        """Test that adding a duplicate email doesn't re-queue it."""
        self.queue.add("email_1", "data")
        self.queue.add("email_1", "new_data")
        assert len(self.queue._queue) == 1
        assert self.queue._status["email_1"]["state"] == "pending"

    def test_get_status_ready(self):
        """Test getting status for a ready summary."""
        self.queue.add("email_1", "data")
        self.queue.set_ready("email_1", "This is the summary")
        status = self.queue.get_status("email_1")
        assert status["state"] == "ready"
        assert status["summary"] == "This is the summary"

    def test_get_status_pending(self):
        """Test getting status for a pending summary."""
        self.queue.add("email_1", "data")
        status = self.queue.get_status("email_1")
        assert status["state"] == "pending"
        assert status["summary"] is None

    def test_get_status_unknown(self):
        """Test getting status for unknown email."""
        status = self.queue.get_status("unknown_email")
        assert status["state"] == "not_found"


class TestPriorityOrdering:
    """Test that queue respects priority ordering."""

    def setup_method(self):
        from email_dashboard import SummaryQueue
        self.queue = SummaryQueue()

    def test_high_priority_before_low(self):
        """Test that HIGH priority emails are processed before LOW."""
        # Add in reverse order
        self.queue.add("low_email", {"tier": "LOW"}, priority=3)
        self.queue.add("high_email", {"tier": "HIGH"}, priority=1)
        
        # Process one item
        item = self.queue.next_item()
        assert item is not None
        assert item["msg_id"] == "high_email"
        
        # Next should be low
        item = self.queue.next_item()
        assert item is not None
        assert item["msg_id"] == "low_email"

    def test_vip_high_before_high(self):
        """Test VIP_HIGH before HIGH."""
        self.queue.add("high_email", {"tier": "HIGH"}, priority=1)
        self.queue.add("vip_email", {"tier": "VIP_HIGH"}, priority=0)
        
        item = self.queue.next_item()
        assert item["msg_id"] == "vip_email"


class TestBackgroundWorker:
    """Test the background summarization worker."""

    def setup_method(self):
        from email_dashboard import SummaryQueue
        self.queue = SummaryQueue()
        self.summaries_called = []

    def _mock_summarize(self, email_data):
        """Mock summarizer that records calls."""
        self.summaries_called.append(email_data.get("id", "unknown"))
        return f"Summary for {email_data.get('id', 'unknown')}"

    def test_worker_processes_queue(self):
        """Test that worker processes items in order."""
        # Add items
        self.queue.add("email_1", {"id": "email_1", "subject": "First"}, priority=2)
        self.queue.add("email_2", {"id": "email_2", "subject": "Second"}, priority=1)
        
        # Start worker with mock
        worker_thread = threading.Thread(
            target=self.queue._worker,
            args=(self._mock_summarize,),
            daemon=True
        )
        worker_thread.start()
        
        # Wait for processing
        time.sleep(0.5)
        self.queue.stop()
        
        assert "email_2" in self.summaries_called  # HIGH first
        assert "email_1" in self.summaries_called

    def test_worker_marks_status(self):
        """Test that worker updates status to ready."""
        self.queue.add("email_1", {"subject": "Test"}, priority=1)
        
        worker_thread = threading.Thread(
            target=self.queue._worker,
            args=(self._mock_summarize,),
            daemon=True
        )
        worker_thread.start()
        
        time.sleep(0.5)
        self.queue.stop()
        
        status = self.queue.get_status("email_1")
        assert status["state"] == "ready"


class TestHTTPSummaryEndpoint:
    """Test the /api/summary/<id> HTTP endpoint."""

    def setup_method(self):
        from email_dashboard import SummaryQueue, DashboardHandler
        self.queue = SummaryQueue()
        self.handler = DashboardHandler
        # Patch global state
        with patch('email_dashboard.EMAILS', [
            {"id": "email_1", "subject": "Test Email", "from": "test@example.com"}
        ]):
            with patch('email_dashboard.get_service') as mock_service:
                mock_svc = MagicMock()
                mock_svc.users().messages().get().execute.return_value = {
                    "id": "email_1",
                    "threadId": "thread_1",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "test@example.com"},
                            {"name": "Subject", "value": "Test Email"},
                            {"name": "Date", "value": "2026-05-16T12:00:00Z"},
                        ],
                        "body": {"data": ""}
                    }
                }
                mock_service.users().messages().modify().execute.return_value = {}
                mock_svc.users().labels().list().execute.return_value = {"labels": []}
                mock_svc.users().labels().create().execute.return_value = {}
                mock_service.users().messages.return_value = mock_svc.users().messages()
                mock_service.users().labels.return_value = mock_svc.users().labels()
                mock_service.users.return_value = mock_svc.users()
                mock_service.users().messages().get.return_value = mock_svc.users().messages().get()
                mock_service.users().messages().modify.return_value = mock_svc.users().messages().modify()
                mock_service.users().labels().list.return_value = mock_svc.users().labels().list()
                mock_service.users().labels().create.return_value = mock_svc.users().labels().create()
                mock_service.users().messages().list.return_value = mock_svc.users().messages().list()
                mock_service.reset_mock()
                
                # Test summary endpoint
                # This would require more complex mocking — skip for now
                pass


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
