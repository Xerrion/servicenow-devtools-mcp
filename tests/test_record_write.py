"""Tests for the unified ``record_write`` and ``record_apply`` tools."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from servicenow_mcp.auth import BasicAuthProvider
from servicenow_mcp.config import Settings
from servicenow_mcp.policy import DENIED_TABLES
from servicenow_mcp.tools._artifact import validate_ui_macro_xml
from servicenow_mcp.tools._dictionary import DictionaryRegistry
from servicenow_mcp.tools._payload import MAX_JSON_PAYLOAD_BYTES
from tests.helpers import decode_response, get_tool_functions


BASE_URL = "https://test.service-now.com"
METADATA_URL = f"{BASE_URL}/api/now/table/sys_dictionary"
NO_MANDATORY_RESPONSE = httpx.Response(200, json={"result": []})

SYS_ID_INC001 = "a" * 32


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_provider(settings: Settings) -> BasicAuthProvider:
    """BasicAuthProvider for the unified record_write test scope."""
    return BasicAuthProvider(settings)


def _register_and_get_tools(settings: Settings, auth_provider: BasicAuthProvider) -> dict[str, Any]:
    """Register the unified record_write tools on a fresh MCP and return callables."""
    from mcp.server import MCPServer

    from servicenow_mcp.tools.record_write import register_tools

    mcp = MCPServer("test")
    dictionary = AsyncMock(spec=DictionaryRegistry)
    dictionary.get_fields.return_value = []
    register_tools(mcp, settings, auth_provider, dictionary=dictionary)
    return get_tool_functions(mcp)


# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------


class TestActionDispatch:
    """Cross-argument validation that runs before any HTTP call."""

    @pytest.mark.asyncio()
    async def test_unknown_action_returns_error(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](action="frobnicate", table="incident")
        result = decode_response(raw)
        assert result["status"] == "error"
        assert "frobnicate" in result["error"]["message"]

    @pytest.mark.asyncio()
    async def test_create_action_requires_data(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](action="create", table="incident")
        result = decode_response(raw)
        assert result["status"] == "error"
        assert "data is required" in result["error"]["message"]

    @pytest.mark.asyncio()
    async def test_create_with_sys_id_returns_error(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](
            action="create",
            table="incident",
            sys_id=SYS_ID_INC001,
            data=json.dumps({"short_description": "x"}),
        )
        result = decode_response(raw)
        assert result["status"] == "error"
        assert "sys_id must be empty" in result["error"]["message"]

    @pytest.mark.asyncio()
    async def test_update_requires_sys_id_and_data(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        tools = _register_and_get_tools(settings, auth_provider)

        raw = await tools["record_write"](action="update", table="incident", data=json.dumps({"state": "2"}))
        assert decode_response(raw)["error"]["message"].startswith("sys_id is required")

        raw = await tools["record_write"](action="update", table="incident", sys_id=SYS_ID_INC001)
        assert decode_response(raw)["error"]["message"].startswith("data is required")

    @pytest.mark.asyncio()
    async def test_delete_with_data_returns_error(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](
            action="delete",
            table="incident",
            sys_id=SYS_ID_INC001,
            data=json.dumps({"x": 1}),
        )
        result = decode_response(raw)
        assert result["status"] == "error"
        assert "data must be empty" in result["error"]["message"]

    @pytest.mark.asyncio()
    async def test_missing_table_returns_error(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](action="create", data=json.dumps({"x": 1}))
        result = decode_response(raw)
        assert result["status"] == "error"
        assert "table is required" in result["error"]["message"]

    @pytest.mark.asyncio()
    @respx.mock
    async def test_oversized_data_payload_rejected_before_token_creation(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        """Oversized JSON returns an error without allocating a preview token."""
        from servicenow_mcp.tools import record_write as record_write_module

        # Patch PreviewTokenStore.create to detect any token-allocation attempt.
        # If the cap fires correctly, this never runs.
        created_tokens: list[Any] = []

        original_create = record_write_module.PreviewTokenStore.create

        async def _spy_create(self: Any, payload: dict[str, Any]) -> str:
            created_tokens.append(payload)
            return await original_create(self, payload)

        with patch.object(record_write_module.PreviewTokenStore, "create", _spy_create):
            tools = _register_and_get_tools(settings, auth_provider)
            oversized_value = "x" * (MAX_JSON_PAYLOAD_BYTES + 1)
            payload = json.dumps({"short_description": oversized_value})
            assert len(payload.encode("utf-8")) > MAX_JSON_PAYLOAD_BYTES
            raw = await tools["record_write"](
                action="create",
                table="incident",
                data=payload,
            )

        result = decode_response(raw)
        assert result["status"] == "error"
        assert str(MAX_JSON_PAYLOAD_BYTES) in result["error"]["message"]
        assert created_tokens == [], "no preview token should be allocated for oversized payload"


# ---------------------------------------------------------------------------
# Standard record write
# ---------------------------------------------------------------------------


class TestStandardRecordWrite:
    """Plain record writes against a non-script-bearing table."""

    @pytest.mark.asyncio()
    @respx.mock
    async def test_create_preview_returns_token(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        respx.get(METADATA_URL).mock(return_value=NO_MANDATORY_RESPONSE)
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](
            action="create",
            table="incident",
            data=json.dumps({"short_description": "Test", "state": "1"}),
        )
        result = decode_response(raw)
        assert result["status"] == "success"
        assert result["data"]["action"] == "create"
        assert result["data"]["table"] == "incident"
        assert "preview_token" in result["data"]
        assert result["data"]["preview"]["data"]["short_description"] == "Test"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_create_direct_commits_immediately(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        respx.get(METADATA_URL).mock(return_value=NO_MANDATORY_RESPONSE)
        respx.post(f"{BASE_URL}/api/now/table/incident").mock(
            return_value=httpx.Response(
                201,
                json={"result": {"sys_id": "new001", "short_description": "Test"}},
            )
        )
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](
            action="create",
            table="incident",
            data=json.dumps({"short_description": "Test"}),
            preview=False,
        )
        result = decode_response(raw)
        assert result["status"] == "success"
        assert result["data"]["sys_id"] == "new001"
        assert "preview_token" not in result["data"]

    @pytest.mark.asyncio()
    @respx.mock
    async def test_update_preview_includes_diff(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        respx.get(f"{BASE_URL}/api/now/table/incident/{SYS_ID_INC001}").mock(
            return_value=httpx.Response(200, json={"result": {"sys_id": SYS_ID_INC001, "state": "1"}}),
        )
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](
            action="update",
            table="incident",
            sys_id=SYS_ID_INC001,
            data=json.dumps({"state": "2"}),
        )
        result = decode_response(raw)
        assert result["status"] == "success"
        diff = result["data"]["preview"]["diff"]
        assert diff["state"] == {"old": "1", "new": "2"}
        assert "preview_token" in result["data"]

    @pytest.mark.asyncio()
    @respx.mock
    async def test_delete_preview_stores_snapshot(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        respx.get(f"{BASE_URL}/api/now/table/incident/{SYS_ID_INC001}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "result": {
                        "sys_id": SYS_ID_INC001,
                        "short_description": "doomed",
                        "password": "s3cret",  # NOSONAR
                    }
                },
            ),
        )
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](action="delete", table="incident", sys_id=SYS_ID_INC001)
        result = decode_response(raw)
        assert result["status"] == "success"
        snap = result["data"]["preview"]["record_snapshot"]
        assert snap["short_description"] == "doomed"
        assert snap["password"] == "***MASKED***"  # NOSONAR

    @pytest.mark.asyncio()
    @respx.mock
    async def test_record_apply_consumes_token(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        # Phase 1: preview create
        respx.get(METADATA_URL).mock(return_value=NO_MANDATORY_RESPONSE)
        tools = _register_and_get_tools(settings, auth_provider)
        preview_raw = await tools["record_write"](
            action="create",
            table="incident",
            data=json.dumps({"short_description": "Apply me"}),
        )
        token = decode_response(preview_raw)["data"]["preview_token"]

        # Phase 2: apply
        respx.post(f"{BASE_URL}/api/now/table/incident").mock(
            return_value=httpx.Response(
                201,
                json={"result": {"sys_id": "new042", "short_description": "Apply me"}},
            ),
        )
        raw = await tools["record_apply"](preview_token=token)
        result = decode_response(raw)
        assert result["status"] == "success"
        assert result["data"]["sys_id"] == "new042"

        # Token is single-use - second call must fail.
        raw2 = await tools["record_apply"](preview_token=token)
        assert decode_response(raw2)["status"] == "error"

    @pytest.mark.asyncio()
    async def test_record_apply_unknown_token_returns_error(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_apply"](preview_token="not-a-real-token")
        result = decode_response(raw)
        assert result["status"] == "error"
        assert "Invalid or expired" in result["error"]["message"]


# ---------------------------------------------------------------------------
# Policy gates
# ---------------------------------------------------------------------------


class TestPolicyGates:
    """Defense-in-depth checks: denied tables, prod env, sys_id format."""

    @pytest.mark.asyncio()
    async def test_denied_table_returns_error(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        denied = next(iter(DENIED_TABLES))
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](
            action="create",
            table=denied,
            data=json.dumps({"x": 1}),
        )
        result = decode_response(raw)
        assert result["status"] == "error"

    @pytest.mark.asyncio()
    async def test_production_blocks_writes_with_proper_settings(
        self, prod_settings: Settings, prod_auth_provider: BasicAuthProvider
    ) -> None:
        tools = _register_and_get_tools(prod_settings, prod_auth_provider)
        raw = await tools["record_write"](
            action="create",
            table="incident",
            data=json.dumps({"short_description": "x"}),
        )
        result = decode_response(raw)
        assert result["status"] == "error"
        assert "production" in result["error"]["message"].lower()

    @pytest.mark.asyncio()
    async def test_invalid_sys_id_format_returns_error(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        tools = _register_and_get_tools(settings, auth_provider)
        raw = await tools["record_write"](
            action="update",
            table="incident",
            sys_id="not-a-real-sys-id",
            data=json.dumps({"state": "2"}),
        )
        result = decode_response(raw)
        assert result["status"] == "error"
        assert "sys_id" in result["error"]["message"].lower()


# ---------------------------------------------------------------------------
# ui_macro / XML validation
# ---------------------------------------------------------------------------


class TestUIMacroXMLValidation:
    """XML validation fires when the detected field has ``internal_type == 'xml'``."""

    def test_validate_ui_macro_xml_accepts_jelly_root(self) -> None:
        jelly = '<j:jelly xmlns:j="jelly:core" xmlns:g="glide" xmlns:g2="null"><g:evaluate>1</g:evaluate></j:jelly>'
        assert validate_ui_macro_xml(jelly) is None

    def test_validate_ui_macro_xml_rejects_malformed(self) -> None:
        bad = "<unclosed>"
        error = validate_ui_macro_xml(bad)
        assert error is not None
        assert "XML content is not well-formed" in error
