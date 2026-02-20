"""Tests for in-memory state management (PreviewTokenStore, SeededRecordTracker)."""

import time

from servicenow_mcp.state import PreviewTokenStore, SeededRecordTracker


class TestPreviewTokenStore:
    """Tests for PreviewTokenStore."""

    def test_create_returns_token_string(self):
        """create() returns a UUID-style string token."""
        store = PreviewTokenStore(ttl_seconds=300)
        token = store.create({"table": "incident", "sys_id": "abc", "changes": {"state": "2"}})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_get_returns_stored_payload(self):
        """get() returns the payload stored for a valid token."""
        store = PreviewTokenStore(ttl_seconds=300)
        payload = {"table": "incident", "sys_id": "abc", "changes": {"state": "2"}}
        token = store.create(payload)
        result = store.get(token)
        assert result is not None
        assert result["table"] == "incident"
        assert result["changes"] == {"state": "2"}

    def test_get_returns_none_for_unknown_token(self):
        """get() returns None for a token that was never created."""
        store = PreviewTokenStore(ttl_seconds=300)
        result = store.get("nonexistent-token")
        assert result is None

    def test_get_returns_none_for_expired_token(self):
        """get() returns None for a token that has expired."""
        store = PreviewTokenStore(ttl_seconds=0)  # Immediate expiry
        token = store.create({"table": "incident"})
        time.sleep(0.01)  # Ensure expiry
        result = store.get(token)
        assert result is None

    def test_consume_returns_payload_and_removes(self):
        """consume() returns the payload and removes the token from the store."""
        store = PreviewTokenStore(ttl_seconds=300)
        payload = {"table": "incident", "sys_id": "abc"}
        token = store.create(payload)

        result = store.consume(token)
        assert result is not None
        assert result["table"] == "incident"

        # Token should be gone now
        assert store.get(token) is None

    def test_consume_returns_none_for_expired_token(self):
        """consume() returns None for an expired token."""
        store = PreviewTokenStore(ttl_seconds=0)
        token = store.create({"table": "incident"})
        time.sleep(0.01)
        result = store.consume(token)
        assert result is None


class TestSeededRecordTracker:
    """Tests for SeededRecordTracker."""

    def test_track_and_get(self):
        """track() stores records, get() retrieves them."""
        tracker = SeededRecordTracker()
        tracker.track("tag1", "incident", ["sys1", "sys2"])
        result = tracker.get("tag1")
        assert result is not None
        assert len(result) == 1
        assert result[0]["table"] == "incident"
        assert result[0]["sys_ids"] == ["sys1", "sys2"]

    def test_track_multiple_tables(self):
        """track() accumulates records across multiple tables for the same tag."""
        tracker = SeededRecordTracker()
        tracker.track("tag1", "incident", ["sys1"])
        tracker.track("tag1", "problem", ["sys2", "sys3"])
        result = tracker.get("tag1")
        assert result is not None
        assert len(result) == 2

    def test_get_unknown_tag_returns_none(self):
        """get() returns None for a tag that was never tracked."""
        tracker = SeededRecordTracker()
        assert tracker.get("unknown") is None

    def test_remove(self):
        """remove() deletes all tracked records for a tag."""
        tracker = SeededRecordTracker()
        tracker.track("tag1", "incident", ["sys1"])
        tracker.remove("tag1")
        assert tracker.get("tag1") is None
