"""Tests for utility functions."""

import uuid

import pytest


class TestCorrelationId:
    """Test correlation ID generation."""

    def test_returns_string(self):
        from servicenow_mcp.utils import generate_correlation_id

        cid = generate_correlation_id()
        assert isinstance(cid, str)

    def test_valid_uuid_format(self):
        from servicenow_mcp.utils import generate_correlation_id

        cid = generate_correlation_id()
        # Should not raise
        uuid.UUID(cid)

    def test_unique_ids(self):
        from servicenow_mcp.utils import generate_correlation_id

        ids = {generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100


class TestFormatResponse:
    """Test response formatting."""

    def test_success_envelope(self):
        from servicenow_mcp.utils import format_response

        resp = format_response(data={"key": "value"}, correlation_id="test-123")

        assert resp["status"] == "success"
        assert resp["correlation_id"] == "test-123"
        assert resp["data"] == {"key": "value"}

    def test_error_envelope(self):
        from servicenow_mcp.utils import format_response

        resp = format_response(
            data=None,
            correlation_id="test-456",
            status="error",
            error="Something went wrong",
        )

        assert resp["status"] == "error"
        assert resp["error"] == "Something went wrong"

    def test_pagination_included(self):
        from servicenow_mcp.utils import format_response

        resp = format_response(
            data=[],
            correlation_id="test-789",
            pagination={"offset": 0, "limit": 100, "total": 250},
        )

        assert resp["pagination"]["total"] == 250

    def test_warnings_included(self):
        from servicenow_mcp.utils import format_response

        resp = format_response(
            data={},
            correlation_id="test-999",
            warnings=["Limit capped at 100"],
        )

        assert "Limit capped at 100" in resp["warnings"]


class TestBuildEncodedQuery:
    """Test encoded query builder."""

    def test_single_condition(self):
        from servicenow_mcp.utils import build_encoded_query

        query = build_encoded_query({"active": "true"})
        assert query == "active=true"

    def test_multiple_conditions(self):
        from servicenow_mcp.utils import build_encoded_query

        query = build_encoded_query({"active": "true", "priority": "1"})
        assert "active=true" in query
        assert "priority=1" in query
        assert "^" in query

    def test_empty_dict(self):
        from servicenow_mcp.utils import build_encoded_query

        query = build_encoded_query({})
        assert query == ""

    def test_passthrough_string(self):
        """If given a string, return it unchanged."""
        from servicenow_mcp.utils import build_encoded_query

        query = build_encoded_query("active=true^priority=1")
        assert query == "active=true^priority=1"
