"""Investigation: comprehensive health report for a single table."""

from typing import Any

from servicenow_mcp.client import ServiceNowClient


async def run(client: ServiceNowClient, params: dict[str, Any]) -> dict[str, Any]:
    """Generate a health report for a specific table.

    Queries record count, automation density (BRs, client scripts, ACLs, UI policies),
    and recent errors from syslog.

    Params:
        table: The table name to analyze (required).
    """
    table = params.get("table")
    if not table:
        return {
            "investigation": "table_health",
            "error": "Missing required parameter: table",
            "finding_count": 0,
            "findings": [],
        }

    # 1. Record count via aggregate
    stats_result = await client.aggregate(table, query="")
    record_count = int(stats_result.get("stats", {}).get("count", 0))

    # 2. Business rules on this table
    br_result = await client.query_records(
        "sys_script",
        f"collection={table}^active=true",
        fields=["sys_id", "name", "when"],
        limit=200,
    )
    br_records = br_result["records"]

    # 3. Client scripts on this table
    cs_result = await client.query_records(
        "sys_script_client",
        f"table={table}^active=true",
        fields=["sys_id", "name", "type"],
        limit=200,
    )
    cs_records = cs_result["records"]

    # 4. ACLs for this table
    acl_result = await client.query_records(
        "sys_security_acl",
        f"nameSTARTSWITH{table}",
        fields=["sys_id", "name", "operation"],
        limit=200,
    )
    acl_records = acl_result["records"]

    # 5. UI policies on this table
    uip_result = await client.query_records(
        "sys_ui_policy",
        f"table={table}^active=true",
        fields=["sys_id", "short_description"],
        limit=200,
    )
    uip_records = uip_result["records"]

    # 6. Recent syslog errors mentioning this table
    syslog_result = await client.query_records(
        "syslog",
        f"level=0^sourceLIKE{table}",
        fields=["sys_id", "message", "source", "sys_created_on"],
        limit=20,
        order_by="sys_created_on",
    )
    recent_errors = syslog_result["records"]

    # Build health indicators
    health_indicators: list[str] = []
    if len(br_records) > 10:
        health_indicators.append(f"High business rule count ({len(br_records)})")
    if len(acl_records) > 20:
        health_indicators.append(f"High ACL count ({len(acl_records)})")
    if len(recent_errors) > 0:
        health_indicators.append(f"{len(recent_errors)} recent errors in syslog")

    return {
        "investigation": "table_health",
        "table": table,
        "record_count": record_count,
        "automation": {
            "business_rules": {
                "count": len(br_records),
                "records": br_records,
            },
            "client_scripts": {
                "count": len(cs_records),
                "records": cs_records,
            },
            "acl_count": len(acl_records),
            "ui_policies": {
                "count": len(uip_records),
                "records": uip_records,
            },
        },
        "recent_errors": recent_errors,
        "health_indicators": health_indicators,
        "finding_count": len(health_indicators),
        "findings": [
            {"category": "health_indicator", "detail": ind} for ind in health_indicators
        ],
    }


async def explain(client: ServiceNowClient, element_id: str) -> dict[str, Any]:
    """Provide rich context for a table health finding.

    element_id is the table name itself.
    """
    # Re-run a lighter query to get basic table info
    stats_result = await client.aggregate(element_id, query="")
    record_count = int(stats_result.get("stats", {}).get("count", 0))

    explanation_parts = [
        f"Table '{element_id}' contains {record_count} records.",
        "Run a full table_health investigation for detailed automation and error analysis.",
    ]

    return {
        "element": element_id,
        "explanation": " ".join(explanation_parts),
        "record_count": record_count,
    }
