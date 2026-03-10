"""Tests for attachment MCP tools."""

import base64
from typing import Any

import httpx
import pytest
import respx

from servicenow_mcp.auth import BasicAuthProvider
from servicenow_mcp.config import Settings
from servicenow_mcp.policy import DENIED_TABLES
from servicenow_mcp.tools._attachment_common import MAX_ATTACHMENT_BYTES
from tests.helpers import decode_response, get_tool_functions


BASE_URL = "https://test.service-now.com"
ATTACHMENT_SYS_ID = "a" * 32
TABLE_SYS_ID = "b" * 32


@pytest.fixture()
def auth_provider(settings: Settings) -> BasicAuthProvider:
    """Create a BasicAuthProvider from test settings."""
    return BasicAuthProvider(settings)


def _register_read_tools(settings: Settings, auth_provider: BasicAuthProvider) -> dict[str, Any]:
    """Register attachment read tools on a fresh MCP server."""
    from mcp.server.fastmcp import FastMCP

    from servicenow_mcp.tools.attachment import register_tools

    mcp = FastMCP("test")
    register_tools(mcp, settings, auth_provider)
    return get_tool_functions(mcp)


def _register_write_tools(settings: Settings, auth_provider: BasicAuthProvider) -> dict[str, Any]:
    """Register attachment write tools on a fresh MCP server."""
    from mcp.server.fastmcp import FastMCP

    from servicenow_mcp.tools.attachment_write import register_tools

    mcp = FastMCP("test")
    register_tools(mcp, settings, auth_provider)
    return get_tool_functions(mcp)


def _metadata(*, table_name: str = "incident", sys_id: str = ATTACHMENT_SYS_ID) -> dict[str, str]:
    """Build a representative attachment metadata payload."""
    return {
        "sys_id": sys_id,
        "table_name": table_name,
        "table_sys_id": TABLE_SYS_ID,
        "file_name": "hello.txt",
        "content_type": "text/plain",
        "size_bytes": "5",
    }


class TestAttachmentReadTools:
    """Tests for attachment read tools."""

    @pytest.mark.asyncio()
    @respx.mock
    async def test_attachment_list_success(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Lists attachment metadata via the attachment API."""
        route = respx.get(f"{BASE_URL}/api/now/attachment").mock(
            return_value=httpx.Response(
                200,
                json={"result": [_metadata()]},
                headers={"X-Total-Count": "1"},
            )
        )

        tools = _register_read_tools(settings, auth_provider)
        raw = await tools["attachment_list"](table_name="incident", table_sys_id=TABLE_SYS_ID, file_name="hello.txt")
        result = decode_response(raw)

        assert result["status"] == "success"
        assert result["data"][0]["sys_id"] == ATTACHMENT_SYS_ID
        assert result["pagination"]["total"] == 1
        assert route.called

    @pytest.mark.asyncio()
    @respx.mock
    async def test_attachment_get_success(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Returns attachment metadata after metadata-first policy checks."""
        respx.get(f"{BASE_URL}/api/now/attachment/{ATTACHMENT_SYS_ID}").mock(
            return_value=httpx.Response(200, json={"result": _metadata()})
        )

        tools = _register_read_tools(settings, auth_provider)
        raw = await tools["attachment_get"](sys_id=ATTACHMENT_SYS_ID)
        result = decode_response(raw)

        assert result["status"] == "success"
        assert result["data"]["table_name"] == "incident"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_attachment_download_success_with_base64(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        """Downloads binary content and returns a base64 payload."""
        respx.get(f"{BASE_URL}/api/now/attachment/{ATTACHMENT_SYS_ID}").mock(
            return_value=httpx.Response(200, json={"result": _metadata()})
        )
        respx.get(f"{BASE_URL}/api/now/attachment/{ATTACHMENT_SYS_ID}/file").mock(
            return_value=httpx.Response(200, content=b"hello")
        )

        tools = _register_read_tools(settings, auth_provider)
        raw = await tools["attachment_download"](sys_id=ATTACHMENT_SYS_ID)
        result = decode_response(raw)

        assert result["status"] == "success"
        assert result["data"]["sys_id"] == ATTACHMENT_SYS_ID
        assert result["data"]["content_base64"] == base64.b64encode(b"hello").decode("ascii")

    @pytest.mark.asyncio()
    @respx.mock
    async def test_attachment_download_by_name_success_uses_metadata_sys_id(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        """Downloads by file name through metadata resolution, not caller path trust."""
        query_route = respx.get(f"{BASE_URL}/api/now/table/sys_attachment").mock(
            return_value=httpx.Response(200, json={"result": [_metadata()]}, headers={"X-Total-Count": "1"})
        )
        download_route = respx.get(f"{BASE_URL}/api/now/attachment/{ATTACHMENT_SYS_ID}/file").mock(
            return_value=httpx.Response(200, content=b"hello")
        )
        by_name_route = respx.get(f"{BASE_URL}/api/now/attachment/{TABLE_SYS_ID}/hello.txt/file").mock(
            return_value=httpx.Response(500)
        )

        tools = _register_read_tools(settings, auth_provider)
        raw = await tools["attachment_download_by_name"](
            table_name="incident",
            table_sys_id=TABLE_SYS_ID,
            file_name="hello.txt",
        )
        result = decode_response(raw)

        assert result["status"] == "success"
        assert result["data"]["sys_id"] == ATTACHMENT_SYS_ID
        assert query_route.called
        assert download_route.called
        assert not by_name_route.called

    @pytest.mark.asyncio()
    @respx.mock
    async def test_attachment_download_by_name_blocks_denied_table_via_metadata_lookup(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        """Denied tables are blocked after metadata resolution before download occurs."""
        denied_table = next(iter(DENIED_TABLES))
        respx.get(f"{BASE_URL}/api/now/table/sys_attachment").mock(
            return_value=httpx.Response(
                200, json={"result": [_metadata(table_name=denied_table)]}, headers={"X-Total-Count": "1"}
            )
        )
        download_route = respx.get(f"{BASE_URL}/api/now/attachment/{ATTACHMENT_SYS_ID}/file").mock(
            return_value=httpx.Response(200, content=b"hello")
        )

        tools = _register_read_tools(settings, auth_provider)
        raw = await tools["attachment_download_by_name"](
            table_name="incident",
            table_sys_id=TABLE_SYS_ID,
            file_name="hello.txt",
        )
        result = decode_response(raw)

        assert result["status"] == "error"
        assert "denied" in result["error"]["message"].lower()
        assert not download_route.called

    @pytest.mark.asyncio()
    @respx.mock
    async def test_oversized_download_rejection(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Rejects downloads larger than the MCP attachment transfer limit."""
        respx.get(f"{BASE_URL}/api/now/attachment/{ATTACHMENT_SYS_ID}").mock(
            return_value=httpx.Response(200, json={"result": _metadata()})
        )
        respx.get(f"{BASE_URL}/api/now/attachment/{ATTACHMENT_SYS_ID}/file").mock(
            return_value=httpx.Response(200, content=b"x" * (MAX_ATTACHMENT_BYTES + 1))
        )

        tools = _register_read_tools(settings, auth_provider)
        raw = await tools["attachment_download"](sys_id=ATTACHMENT_SYS_ID)
        result = decode_response(raw)

        assert result["status"] == "error"
        assert "exceeds the maximum supported size" in result["error"]["message"]


class TestAttachmentWriteTools:
    """Tests for attachment write tools."""

    @pytest.mark.asyncio()
    @respx.mock
    async def test_attachment_upload_success_with_base64(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        """Uploads decoded base64 content through the attachment API."""
        route = respx.post(f"{BASE_URL}/api/now/attachment/file").mock(
            return_value=httpx.Response(201, json={"result": _metadata()})
        )

        tools = _register_write_tools(settings, auth_provider)
        raw = await tools["attachment_upload"](
            table_name="incident",
            table_sys_id=TABLE_SYS_ID,
            file_name="hello.txt",
            content_base64=base64.b64encode(b"hello").decode("ascii"),
            content_type="text/plain",
        )
        result = decode_response(raw)

        assert result["status"] == "success"
        assert result["data"]["sys_id"] == ATTACHMENT_SYS_ID
        assert route.calls.last is not None
        assert route.calls.last.request.content == b"hello"

    @pytest.mark.asyncio()
    async def test_attachment_upload_invalid_base64_error_envelope(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        """Rejects invalid base64 input before any HTTP call."""
        tools = _register_write_tools(settings, auth_provider)
        raw = await tools["attachment_upload"](
            table_name="incident",
            table_sys_id=TABLE_SYS_ID,
            file_name="hello.txt",
            content_base64="not-base64!",
        )
        result = decode_response(raw)

        assert result["status"] == "error"
        assert "invalid base64" in result["error"]["message"].lower()

    @pytest.mark.asyncio()
    async def test_oversized_upload_rejection(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Rejects uploads larger than the MCP attachment transfer limit."""
        tools = _register_write_tools(settings, auth_provider)
        oversized_content = base64.b64encode(b"x" * (MAX_ATTACHMENT_BYTES + 1)).decode("ascii")

        raw = await tools["attachment_upload"](
            table_name="incident",
            table_sys_id=TABLE_SYS_ID,
            file_name="hello.txt",
            content_base64=oversized_content,
        )
        result = decode_response(raw)

        assert result["status"] == "error"
        assert "exceeds the maximum supported size" in result["error"]["message"]

    @pytest.mark.asyncio()
    @respx.mock
    async def test_attachment_delete_success(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Deletes an attachment after metadata-first policy and write-gate checks."""
        respx.get(f"{BASE_URL}/api/now/attachment/{ATTACHMENT_SYS_ID}").mock(
            return_value=httpx.Response(200, json={"result": _metadata()})
        )
        delete_route = respx.delete(f"{BASE_URL}/api/now/attachment/{ATTACHMENT_SYS_ID}").mock(
            return_value=httpx.Response(204)
        )

        tools = _register_write_tools(settings, auth_provider)
        raw = await tools["attachment_delete"](sys_id=ATTACHMENT_SYS_ID)
        result = decode_response(raw)

        assert result["status"] == "success"
        assert result["data"]["deleted"] is True
        assert delete_route.called

    @pytest.mark.asyncio()
    async def test_upload_blocked_in_prod(self, prod_settings: Settings, prod_auth_provider: BasicAuthProvider) -> None:
        """Blocks uploads in production environments."""
        tools = _register_write_tools(prod_settings, prod_auth_provider)
        raw = await tools["attachment_upload"](
            table_name="incident",
            table_sys_id=TABLE_SYS_ID,
            file_name="hello.txt",
            content_base64=base64.b64encode(b"hello").decode("ascii"),
        )
        result = decode_response(raw)

        assert result["status"] == "error"
        assert "production" in result["error"]["message"].lower()
