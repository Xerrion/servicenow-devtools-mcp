"""Investigation: detect conflicting or overlapping ACL rules."""

from collections import defaultdict
from typing import Any

from servicenow_mcp.client import ServiceNowClient


async def run(client: ServiceNowClient, params: dict[str, Any]) -> dict[str, Any]:
    """Find ACL conflicts for a table — multiple ACLs with the same name.

    Two or more ACLs with the same name and operation but different conditions
    can cause unpredictable access control behavior.

    Params:
        table: The table name to check (required).
    """
    table = params.get("table")
    if not table:
        return {
            "investigation": "acl_conflicts",
            "error": "Missing required parameter: table",
            "finding_count": 0,
            "findings": [],
        }

    # Query all ACLs that start with the table name
    acl_result = await client.query_records(
        "sys_security_acl",
        f"nameSTARTSWITH{table}",
        fields=["sys_id", "name", "operation", "condition", "script", "active"],
        limit=500,
    )
    acls = acl_result["records"]

    # Group by name to find duplicates
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for acl in acls:
        groups[acl.get("name", "")].append(acl)

    # Find conflicts: groups with 2+ ACLs sharing the same name
    findings: list[dict[str, Any]] = []
    for name, group in groups.items():
        if len(group) >= 2:
            findings.append(
                {
                    "category": "acl_conflict",
                    "name": name,
                    "count": len(group),
                    "acls": [
                        {
                            "sys_id": a.get("sys_id", ""),
                            "operation": a.get("operation", ""),
                            "condition": a.get("condition", ""),
                            "active": a.get("active", ""),
                        }
                        for a in group
                    ],
                    "detail": f"ACL '{name}' has {len(group)} overlapping rules with different conditions",
                }
            )

    return {
        "investigation": "acl_conflicts",
        "table": table,
        "finding_count": len(findings),
        "findings": findings,
        "total_acls_checked": len(acls),
    }


async def explain(client: ServiceNowClient, element_id: str) -> dict[str, Any]:
    """Provide rich context for an ACL conflict finding.

    element_id is an ACL sys_id.
    """
    record = await client.get_record("sys_security_acl", element_id)

    explanation_parts = [
        f"ACL '{record.get('name', '')}' controls {record.get('operation', '')} access.",
        f"Condition: '{record.get('condition', '(none)')}'.",
        "When multiple ACLs share the same name, ServiceNow evaluates all of them. "
        "Conflicting conditions can lead to unexpected access behavior.",
        "Review whether these ACLs should be consolidated.",
    ]

    return {
        "element": element_id,
        "explanation": " ".join(explanation_parts),
        "record": record,
    }
