"""Relationship tools for traversing ServiceNow reference fields."""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from servicenow_mcp.auth import BasicAuthProvider
from servicenow_mcp.client import ServiceNowClient
from servicenow_mcp.config import Settings
from servicenow_mcp.policy import check_table_access
from servicenow_mcp.utils import format_response, generate_correlation_id


def register_tools(
    mcp: FastMCP, settings: Settings, auth_provider: BasicAuthProvider
) -> None:
    """Register relationship tools on the MCP server."""

    @mcp.tool()
    async def rel_references_to(table: str, sys_id: str, depth: int = 1) -> str:
        """Find records in other tables that reference a given record.

        Args:
            table: The table of the target record.
            sys_id: The sys_id of the target record.
            depth: Maximum depth for recursive reference traversal (default 1).
        """
        correlation_id = generate_correlation_id()
        try:
            check_table_access(table)
            # Query sys_dictionary for reference fields pointing to this table
            async with ServiceNowClient(settings, auth_provider) as client:
                ref_fields = await client.query_records(
                    "sys_dictionary",
                    f"internal_type=reference^reference={table}",
                    fields=["name", "element", "column_label"],
                    limit=100,
                )
                references: list[dict[str, Any]] = []
                for field in ref_fields["records"]:
                    ref_table = field.get("name", "")
                    ref_field = field.get("element", "")
                    if not ref_table or not ref_field:
                        continue
                    try:
                        check_table_access(ref_table)
                        ref_records = await client.query_records(
                            ref_table,
                            f"{ref_field}={sys_id}",
                            fields=["sys_id", ref_field],
                            limit=10,
                        )
                        if ref_records["records"]:
                            references.append(
                                {
                                    "table": ref_table,
                                    "field": ref_field,
                                    "count": ref_records["count"],
                                    "sample_records": ref_records["records"][:5],
                                }
                            )
                    except Exception:
                        continue

            return json.dumps(
                format_response(
                    data={
                        "target": {"table": table, "sys_id": sys_id},
                        "incoming_references": references,
                    },
                    correlation_id=correlation_id,
                ),
                indent=2,
            )
        except Exception as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=str(e),
                ),
                indent=2,
            )

    @mcp.tool()
    async def rel_references_from(table: str, sys_id: str, depth: int = 1) -> str:
        """Find what a record references by inspecting its reference fields.

        Args:
            table: The table of the source record.
            sys_id: The sys_id of the source record.
            depth: Maximum depth for recursive reference traversal (default 1).
        """
        correlation_id = generate_correlation_id()
        try:
            check_table_access(table)
            async with ServiceNowClient(settings, auth_provider) as client:
                # Get the record
                record = await client.get_record(table, sys_id, display_values=True)

                # Get reference fields for this table
                ref_fields = await client.query_records(
                    "sys_dictionary",
                    f"name={table}^internal_type=reference",
                    fields=["element", "reference", "column_label"],
                    limit=100,
                )

                outgoing: list[dict[str, Any]] = []
                for field in ref_fields["records"]:
                    field_name = field.get("element", "")
                    ref_table = field.get("reference", "")
                    if field_name and field_name in record and record[field_name]:
                        outgoing.append(
                            {
                                "field": field_name,
                                "reference_table": ref_table,
                                "value": record[field_name],
                                "label": field.get("column_label", ""),
                            }
                        )

            return json.dumps(
                format_response(
                    data={
                        "source": {"table": table, "sys_id": sys_id},
                        "outgoing_references": outgoing,
                    },
                    correlation_id=correlation_id,
                ),
                indent=2,
            )
        except Exception as e:
            return json.dumps(
                format_response(
                    data=None,
                    correlation_id=correlation_id,
                    status="error",
                    error=str(e),
                ),
                indent=2,
            )
