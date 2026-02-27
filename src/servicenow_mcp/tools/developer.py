"""Record CRUD tools for creating, reading, updating, and deleting ServiceNow records."""

import json

from mcp.server.fastmcp import FastMCP

from servicenow_mcp.auth import BasicAuthProvider
from servicenow_mcp.client import ServiceNowClient
from servicenow_mcp.config import Settings
from servicenow_mcp.errors import ForbiddenError
from servicenow_mcp.policy import (
    MASK_VALUE,
    _is_sensitive_field,
    check_table_access,
    mask_sensitive_fields,
    write_blocked_reason,
)
from servicenow_mcp.state import PreviewTokenStore
from servicenow_mcp.utils import format_response, generate_correlation_id, validate_identifier


def _write_gate(table: str, settings: Settings, correlation_id: str) -> str | None:
    """Check write access and return a JSON error envelope if blocked, or None if allowed."""
    reason = write_blocked_reason(table, settings)
    if reason:
        return json.dumps(
            format_response(
                data=None,
                correlation_id=correlation_id,
                status="error",
                error=reason,
            )
        )
    return None


def register_tools(mcp: FastMCP, settings: Settings, auth_provider: BasicAuthProvider) -> None:
    """Register record CRUD tools on the MCP server."""

    # In-memory preview token store, shared across preview/apply tools via closure
    preview_store = PreviewTokenStore()

    @mcp.tool()
    async def record_create(table: str, data: str) -> str:
        """Create a new record in a ServiceNow table.

        Args:
            table: The table to create the record in (e.g. 'incident').
            data: A JSON string of field-value pairs for the new record.
        """
        correlation_id = generate_correlation_id()
        try:
            validate_identifier(table)
            check_table_access(table)

            blocked = _write_gate(table, settings, correlation_id)
            if blocked:
                return blocked

            record_data = json.loads(data)

            async with ServiceNowClient(settings, auth_provider) as client:
                created = await client.create_record(table, record_data)

            return json.dumps(
                format_response(
                    data={
                        "table": table,
                        "sys_id": created["sys_id"],
                        "record": mask_sensitive_fields(created),
                    },
                    correlation_id=correlation_id,
                )
            )
        except ForbiddenError as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=f"Access denied by ServiceNow ACL: {e}",
                )
            )
        except Exception as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=str(e),
                )
            )

    @mcp.tool()
    async def record_preview_create(table: str, data: str) -> str:
        """Preview a record creation without executing it. Returns a token to apply later.

        Args:
            table: The table to create the record in (e.g. 'incident').
            data: A JSON string of field-value pairs for the new record.
        """
        correlation_id = generate_correlation_id()
        try:
            validate_identifier(table)
            check_table_access(table)

            blocked = _write_gate(table, settings, correlation_id)
            if blocked:
                return blocked

            record_data = json.loads(data)

            # Store for later apply - no HTTP call needed for create preview
            token = preview_store.create(
                {
                    "action": "create",
                    "table": table,
                    "data": record_data,
                }
            )

            return json.dumps(
                format_response(
                    data={
                        "token": token,
                        "table": table,
                        "action": "create",
                        "data": mask_sensitive_fields(record_data),
                    },
                    correlation_id=correlation_id,
                )
            )
        except ForbiddenError as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=f"Access denied by ServiceNow ACL: {e}",
                )
            )
        except Exception as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=str(e),
                )
            )

    @mcp.tool()
    async def record_update(table: str, sys_id: str, changes: str) -> str:
        """Update an existing record in a ServiceNow table.

        Args:
            table: The table containing the record (e.g. 'incident').
            sys_id: The sys_id of the record to update.
            changes: A JSON string of field-value pairs to update.
        """
        correlation_id = generate_correlation_id()
        try:
            validate_identifier(table)
            validate_identifier(sys_id)
            check_table_access(table)

            blocked = _write_gate(table, settings, correlation_id)
            if blocked:
                return blocked

            changes_dict = json.loads(changes)

            async with ServiceNowClient(settings, auth_provider) as client:
                updated = await client.update_record(table, sys_id, changes_dict)

            return json.dumps(
                format_response(
                    data={
                        "table": table,
                        "sys_id": sys_id,
                        "record": mask_sensitive_fields(updated),
                    },
                    correlation_id=correlation_id,
                )
            )
        except ForbiddenError as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=f"Access denied by ServiceNow ACL: {e}",
                )
            )
        except Exception as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=str(e),
                )
            )

    @mcp.tool()
    async def record_preview_update(table: str, sys_id: str, changes: str) -> str:
        """Preview an update to a record: shows field-level diff and returns a token to apply.

        Args:
            table: The table containing the record.
            sys_id: The sys_id of the record to update.
            changes: A JSON string of field-value pairs to change.
        """
        correlation_id = generate_correlation_id()
        try:
            validate_identifier(table)
            validate_identifier(sys_id)
            check_table_access(table)

            blocked = _write_gate(table, settings, correlation_id)
            if blocked:
                return blocked

            changes_dict = json.loads(changes)

            async with ServiceNowClient(settings, auth_provider) as client:
                current = await client.get_record(table, sys_id)

            # Build field-level diff (only for fields being changed)
            diff: dict[str, dict[str, str]] = {}
            for field, new_value in changes_dict.items():
                old_value = current.get(field, "")
                if _is_sensitive_field(field):
                    diff[field] = {"old": MASK_VALUE, "new": MASK_VALUE}
                else:
                    diff[field] = {"old": old_value, "new": new_value}

            # Store preview for later apply
            token = preview_store.create(
                {
                    "action": "update",
                    "table": table,
                    "sys_id": sys_id,
                    "changes": changes_dict,
                }
            )

            return json.dumps(
                format_response(
                    data={
                        "token": token,
                        "table": table,
                        "sys_id": sys_id,
                        "diff": diff,
                    },
                    correlation_id=correlation_id,
                )
            )
        except ForbiddenError as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=f"Access denied by ServiceNow ACL: {e}",
                )
            )
        except Exception as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=str(e),
                )
            )

    @mcp.tool()
    async def record_delete(table: str, sys_id: str) -> str:
        """Delete a record from a ServiceNow table.

        Args:
            table: The table containing the record (e.g. 'incident').
            sys_id: The sys_id of the record to delete.
        """
        correlation_id = generate_correlation_id()
        try:
            validate_identifier(table)
            validate_identifier(sys_id)
            check_table_access(table)

            blocked = _write_gate(table, settings, correlation_id)
            if blocked:
                return blocked

            async with ServiceNowClient(settings, auth_provider) as client:
                await client.delete_record(table, sys_id)

            return json.dumps(
                format_response(
                    data={
                        "table": table,
                        "sys_id": sys_id,
                        "deleted": True,
                    },
                    correlation_id=correlation_id,
                )
            )
        except ForbiddenError as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=f"Access denied by ServiceNow ACL: {e}",
                )
            )
        except Exception as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=str(e),
                )
            )

    @mcp.tool()
    async def record_preview_delete(table: str, sys_id: str) -> str:
        """Preview a record deletion: shows the record that will be deleted and returns a token to confirm.

        Args:
            table: The table containing the record (e.g. 'incident').
            sys_id: The sys_id of the record to delete.
        """
        correlation_id = generate_correlation_id()
        try:
            validate_identifier(table)
            validate_identifier(sys_id)
            check_table_access(table)

            blocked = _write_gate(table, settings, correlation_id)
            if blocked:
                return blocked

            async with ServiceNowClient(settings, auth_provider) as client:
                record = await client.get_record(table, sys_id)

            # Store preview for later apply
            token = preview_store.create(
                {
                    "action": "delete",
                    "table": table,
                    "sys_id": sys_id,
                    "record_snapshot": record,
                }
            )

            return json.dumps(
                format_response(
                    data={
                        "token": token,
                        "table": table,
                        "sys_id": sys_id,
                        "record_snapshot": mask_sensitive_fields(record),
                    },
                    correlation_id=correlation_id,
                )
            )
        except ForbiddenError as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=f"Access denied by ServiceNow ACL: {e}",
                )
            )
        except Exception as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=str(e),
                )
            )

    @mcp.tool()
    async def record_apply(preview_token: str) -> str:
        """Apply a previously previewed action (create, update, or delete) using the preview token.

        Args:
            preview_token: The single-use token returned by record_preview_create, record_preview_update, or record_preview_delete.
        """
        correlation_id = generate_correlation_id()
        try:
            # Consume the token (single-use)
            payload = preview_store.consume(preview_token)
            if payload is None:
                return json.dumps(
                    format_response(
                        data=None,
                        correlation_id=correlation_id,
                        status="error",
                        error="Invalid or expired preview token",
                    )
                )

            action = payload["action"]
            table = payload["table"]

            # Defense in depth - re-check access and write gate
            check_table_access(table)
            blocked = _write_gate(table, settings, correlation_id)
            if blocked:
                return blocked

            async with ServiceNowClient(settings, auth_provider) as client:
                if action == "create":
                    result = await client.create_record(table, payload["data"])
                    return json.dumps(
                        format_response(
                            data={
                                "action": "create",
                                "table": table,
                                "sys_id": result["sys_id"],
                                "record": mask_sensitive_fields(result),
                            },
                            correlation_id=correlation_id,
                        )
                    )

                elif action == "update":
                    sys_id = payload["sys_id"]
                    result = await client.update_record(table, sys_id, payload["changes"])
                    return json.dumps(
                        format_response(
                            data={
                                "action": "update",
                                "table": table,
                                "sys_id": sys_id,
                                "record": mask_sensitive_fields(result),
                            },
                            correlation_id=correlation_id,
                        )
                    )

                elif action == "delete":
                    sys_id = payload["sys_id"]
                    await client.delete_record(table, sys_id)
                    return json.dumps(
                        format_response(
                            data={
                                "action": "delete",
                                "table": table,
                                "sys_id": sys_id,
                                "deleted": True,
                            },
                            correlation_id=correlation_id,
                        )
                    )

                else:
                    return json.dumps(
                        format_response(
                            data=None,
                            correlation_id=correlation_id,
                            status="error",
                            error=f"Unknown preview action: '{action}'",
                        )
                    )

        except ForbiddenError as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=f"Access denied by ServiceNow ACL: {e}",
                )
            )
        except Exception as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=str(e),
                )
            )
