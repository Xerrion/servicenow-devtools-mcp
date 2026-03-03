"""Request Management domain tools."""

import json
import uuid

from mcp.server.fastmcp import FastMCP

from servicenow_mcp.auth import BasicAuthProvider
from servicenow_mcp.client import ServiceNowClient
from servicenow_mcp.config import Settings
from servicenow_mcp.policy import check_table_access, mask_sensitive_fields, write_gate
from servicenow_mcp.utils import ServiceNowQuery, format_response, safe_tool_call


def register_tools(mcp: FastMCP, settings: Settings, auth_provider: BasicAuthProvider) -> None:
    """Register Request Management tools with MCP server.

    Args:
        mcp: FastMCP instance for tool registration
        settings: Server configuration settings
        auth_provider: Authentication provider for ServiceNow API
    """

    @mcp.tool()
    async def request_list(
        state: str = "",
        requested_for: str = "",
        assignment_group: str = "",
        fields: str = "number,short_description,state,requested_for,assignment_group,sys_created_on",
        limit: int = 20,
    ) -> str:
        """List requests with optional filters.

        Args:
            state: Request state filter
            requested_for: sys_id of requested_for user
            assignment_group: sys_id or name of assignment group
            fields: Comma-separated list of fields to return (empty for all)
            limit: Maximum results to return (default 20)
        """
        correlation_id = str(uuid.uuid4())

        async def _run() -> str:
            check_table_access("sc_request")

            q = ServiceNowQuery()
            if state:
                q = q.equals("state", state)
            if requested_for:
                q = q.equals("requested_for", requested_for)
            if assignment_group:
                q = q.equals("assignment_group", assignment_group)
            query = q.build()
            field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

            async with ServiceNowClient(settings, auth_provider) as client:
                result = await client.query_records(
                    table="sc_request",
                    query=query,
                    fields=field_list,
                    display_values=True,
                    limit=limit,
                )
                masked = [mask_sensitive_fields(r) for r in result["records"]]
                return json.dumps(
                    format_response(data=masked, correlation_id=correlation_id),
                    indent=2,
                )

        return await safe_tool_call(_run, correlation_id)

    @mcp.tool()
    async def request_get(number: str) -> str:
        """Fetch request by REQ number.

        Args:
            number: Request number (must start with REQ prefix)
        """
        correlation_id = str(uuid.uuid4())

        async def _run() -> str:
            check_table_access("sc_request")

            if not number.upper().startswith("REQ"):
                return json.dumps(
                    format_response(
                        data=None,
                        correlation_id=correlation_id,
                        status="error",
                        error=f"Invalid request number: {number}. Must start with REQ prefix.",
                    ),
                    indent=2,
                )

            async with ServiceNowClient(settings, auth_provider) as client:
                result = await client.query_records(
                    table="sc_request",
                    query=ServiceNowQuery().equals("number", number.upper()).build(),
                    display_values=True,
                    limit=1,
                )
                if not result["records"]:
                    return json.dumps(
                        format_response(
                            data=None,
                            correlation_id=correlation_id,
                            status="error",
                            error=f"Request {number} not found.",
                        ),
                        indent=2,
                    )
                masked = mask_sensitive_fields(result["records"][0])
                return json.dumps(format_response(data=masked, correlation_id=correlation_id), indent=2)

        return await safe_tool_call(_run, correlation_id)

    @mcp.tool()
    async def request_items(
        number: str,
        fields: str = "number,short_description,state,assignment_group,assigned_to,sys_created_on",
        limit: int = 20,
    ) -> str:
        """Fetch request items (RITMs) for a request.

        Args:
            number: Request number (must start with REQ prefix)
            fields: Comma-separated list of fields to return (empty for all)
            limit: Maximum results to return (default 20)
        """
        correlation_id = str(uuid.uuid4())

        async def _run() -> str:
            check_table_access("sc_req_item")

            if not number.upper().startswith("REQ"):
                return json.dumps(
                    format_response(
                        data=None,
                        correlation_id=correlation_id,
                        status="error",
                        error=f"Invalid request number: {number}. Must start with REQ prefix.",
                    ),
                    indent=2,
                )

            field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

            async with ServiceNowClient(settings, auth_provider) as client:
                result = await client.query_records(
                    table="sc_req_item",
                    query=ServiceNowQuery().equals("request.number", number.upper()).build(),
                    fields=field_list,
                    display_values=True,
                    limit=limit,
                )
                masked = [mask_sensitive_fields(r) for r in result["records"]]
                return json.dumps(
                    format_response(data=masked, correlation_id=correlation_id),
                    indent=2,
                )

        return await safe_tool_call(_run, correlation_id)

    @mcp.tool()
    async def request_item_get(number: str) -> str:
        """Fetch request item by RITM number.

        Args:
            number: Request item number (must start with RITM prefix)
        """
        correlation_id = str(uuid.uuid4())

        async def _run() -> str:
            check_table_access("sc_req_item")

            if not number.upper().startswith("RITM"):
                return json.dumps(
                    format_response(
                        data=None,
                        correlation_id=correlation_id,
                        status="error",
                        error=f"Invalid request item number: {number}. Must start with RITM prefix.",
                    ),
                    indent=2,
                )

            async with ServiceNowClient(settings, auth_provider) as client:
                result = await client.query_records(
                    table="sc_req_item",
                    query=ServiceNowQuery().equals("number", number.upper()).build(),
                    display_values=True,
                    limit=1,
                )
                if not result["records"]:
                    return json.dumps(
                        format_response(
                            data=None,
                            correlation_id=correlation_id,
                            status="error",
                            error=f"Request item {number} not found.",
                        ),
                        indent=2,
                    )
                masked = mask_sensitive_fields(result["records"][0])
                return json.dumps(format_response(data=masked, correlation_id=correlation_id), indent=2)

        return await safe_tool_call(_run, correlation_id)

    @mcp.tool()
    async def request_item_update(
        number: str,
        state: str = "",
        assignment_group: str = "",
        assigned_to: str = "",
    ) -> str:
        """Update a request item by RITM number.

        Args:
            number: Request item number (must start with RITM prefix)
            state: Request item state
            assignment_group: sys_id or name of assignment group
            assigned_to: sys_id of assigned user
        """
        correlation_id = str(uuid.uuid4())

        async def _run() -> str:
            check_table_access("sc_req_item")

            blocked = write_gate("sc_req_item", settings, correlation_id)
            if blocked:
                return blocked

            if not number.upper().startswith("RITM"):
                return json.dumps(
                    format_response(
                        data=None,
                        correlation_id=correlation_id,
                        status="error",
                        error=f"Invalid request item number: {number}. Must start with RITM prefix.",
                    ),
                    indent=2,
                )

            async with ServiceNowClient(settings, auth_provider) as client:
                result = await client.query_records(
                    table="sc_req_item",
                    query=ServiceNowQuery().equals("number", number.upper()).build(),
                    limit=1,
                )
                if not result["records"]:
                    return json.dumps(
                        format_response(
                            data=None,
                            correlation_id=correlation_id,
                            status="error",
                            error=f"Request item {number} not found.",
                        ),
                        indent=2,
                    )

                sys_id = result["records"][0]["sys_id"]

                changes = {}
                if state:
                    changes["state"] = state
                if assignment_group:
                    changes["assignment_group"] = assignment_group
                if assigned_to:
                    changes["assigned_to"] = assigned_to

                if not changes:
                    return json.dumps(
                        format_response(
                            data=None,
                            correlation_id=correlation_id,
                            status="error",
                            error="No fields to update provided.",
                        ),
                        indent=2,
                    )

                updated = await client.update_record("sc_req_item", sys_id, changes)
                masked = mask_sensitive_fields(updated)
                return json.dumps(format_response(data=masked, correlation_id=correlation_id), indent=2)

        return await safe_tool_call(_run, correlation_id)
