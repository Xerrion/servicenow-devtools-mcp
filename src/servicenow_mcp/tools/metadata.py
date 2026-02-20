"""Metadata tools for listing, inspecting, and searching ServiceNow platform artifacts."""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from servicenow_mcp.auth import BasicAuthProvider
from servicenow_mcp.client import ServiceNowClient
from servicenow_mcp.config import Settings
from servicenow_mcp.policy import enforce_query_safety
from servicenow_mcp.utils import format_response, generate_correlation_id

# Mapping from human-friendly artifact type names to ServiceNow tables
ARTIFACT_TABLES: dict[str, str] = {
    "business_rule": "sys_script",
    "script_include": "sys_script_include",
    "ui_policy": "sys_ui_policy",
    "ui_action": "sys_ui_action",
    "client_script": "sys_script_client",
    "scheduled_job": "sysauto_script",
    "fix_script": "sys_script_fix",
}

# Tables that contain script bodies (used for cross-table reference search)
SCRIPT_TABLES: list[str] = [
    "sys_script",
    "sys_script_include",
    "sys_script_client",
    "sys_ui_action",
    "sysauto_script",
    "sys_script_fix",
]


def register_tools(
    mcp: FastMCP, settings: Settings, auth_provider: BasicAuthProvider
) -> None:
    """Register metadata tools on the MCP server."""

    @mcp.tool()
    async def meta_list_artifacts(
        artifact_type: str,
        query: str = "",
        limit: int = 100,
    ) -> str:
        """List platform artifacts (business rules, script includes, etc.) filtered by type and optional query.

        Args:
            artifact_type: The type of artifact to list (business_rule, script_include, ui_policy, ui_action, client_script, scheduled_job, fix_script).
            query: Optional ServiceNow encoded query string to further filter results.
            limit: Maximum number of artifacts to return.
        """
        correlation_id = generate_correlation_id()
        warnings: list[str] = []
        try:
            table = ARTIFACT_TABLES.get(artifact_type)
            if table is None:
                valid_types = ", ".join(sorted(ARTIFACT_TABLES.keys()))
                raise ValueError(
                    f"Unknown artifact type '{artifact_type}'. "
                    f"Valid types: {valid_types}"
                )

            encoded_query = query if query else ""
            safety = enforce_query_safety(table, encoded_query, limit, settings)
            effective_limit = safety["limit"]
            if effective_limit < limit:
                warnings.append(f"Limit capped at {effective_limit}")

            async with ServiceNowClient(settings, auth_provider) as client:
                result = await client.query_records(
                    table,
                    encoded_query,
                    limit=effective_limit,
                )

            return json.dumps(
                format_response(
                    data={
                        "artifact_type": artifact_type,
                        "table": table,
                        "artifacts": result["records"],
                        "total": result["count"],
                    },
                    correlation_id=correlation_id,
                    warnings=warnings if warnings else None,
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
    async def meta_get_artifact(
        artifact_type: str,
        sys_id: str,
    ) -> str:
        """Get full details of a platform artifact including its script body.

        Args:
            artifact_type: The type of artifact (business_rule, script_include, etc.).
            sys_id: The sys_id of the artifact to retrieve.
        """
        correlation_id = generate_correlation_id()
        try:
            table = ARTIFACT_TABLES.get(artifact_type)
            if table is None:
                valid_types = ", ".join(sorted(ARTIFACT_TABLES.keys()))
                raise ValueError(
                    f"Unknown artifact type '{artifact_type}'. "
                    f"Valid types: {valid_types}"
                )

            async with ServiceNowClient(settings, auth_provider) as client:
                record = await client.get_record(table, sys_id)

            return json.dumps(
                format_response(data=record, correlation_id=correlation_id),
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
    async def meta_find_references(
        target: str,
        limit: int = 20,
    ) -> str:
        """Search across all script tables for artifacts that reference a target string (API name, table name, function, etc.).

        Uses the Code Search API when available (single indexed call), with automatic
        fallback to per-table scriptCONTAINS queries if Code Search is not installed.

        Args:
            target: The string to search for in script bodies (e.g., 'GlideRecord', 'incident', a function name).
            limit: Maximum number of matches to return per table.
        """
        correlation_id = generate_correlation_id()
        warnings: list[str] = []
        try:
            effective_limit = min(limit, settings.max_row_limit)
            if effective_limit < limit:
                warnings.append(f"Limit capped at {effective_limit}")
            matches: list[dict[str, Any]] = []
            search_method = "code_search_api"

            async with ServiceNowClient(settings, auth_provider) as client:
                # Try Code Search API first (indexed, single call)
                try:
                    cs_result = await client.code_search(
                        term=target, limit=effective_limit * len(SCRIPT_TABLES)
                    )
                    search_results = cs_result.get("search_results", [])
                    for sr in search_results:
                        matches.append(
                            {
                                "table": sr.get("className", ""),
                                "sys_id": sr.get("sys_id", ""),
                                "name": sr.get("name", ""),
                                "sys_class_name": sr.get("className", ""),
                            }
                        )
                except Exception:
                    # Fallback to per-table scriptCONTAINS search
                    search_method = "table_scan_fallback"
                    for table in SCRIPT_TABLES:
                        query = f"scriptCONTAINS{target}"
                        try:
                            result = await client.query_records(
                                table,
                                query,
                                fields=["sys_id", "name", "sys_class_name"],
                                limit=effective_limit,
                            )
                            for record in result["records"]:
                                matches.append(
                                    {
                                        "table": table,
                                        "sys_id": record.get("sys_id", ""),
                                        "name": record.get("name", ""),
                                        "sys_class_name": record.get(
                                            "sys_class_name", table
                                        ),
                                    }
                                )
                        except Exception:
                            # Skip tables that fail (e.g., access issues)
                            continue

            return json.dumps(
                format_response(
                    data={
                        "target": target,
                        "matches": matches,
                        "total_matches": len(matches),
                        "search_method": search_method,
                    },
                    correlation_id=correlation_id,
                    warnings=warnings if warnings else None,
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
    async def meta_what_writes(
        table: str,
        field: str = "",
    ) -> str:
        """Find business rules and other mechanisms that write to a specific table (and optionally a specific field).

        Args:
            table: The ServiceNow table to investigate (e.g., 'incident').
            field: Optional field name to narrow results. When provided, only returns writers whose script references this field.
        """
        correlation_id = generate_correlation_id()
        try:
            writers: list[dict[str, Any]] = []

            async with ServiceNowClient(settings, auth_provider) as client:
                # Query business rules for the target table
                result = await client.query_records(
                    "sys_script",
                    f"collection={table}",
                    limit=200,
                )

                for record in result["records"]:
                    script = record.get("script", "")
                    # If a field is specified, only include BRs that reference it
                    if field and field not in script:
                        continue
                    writers.append(record)

            return json.dumps(
                format_response(
                    data={
                        "table": table,
                        "field": field if field else None,
                        "writers": writers,
                        "total": len(writers),
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
