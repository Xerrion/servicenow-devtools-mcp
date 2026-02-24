"""Investigation: find stale automations — stuck flows, disabled scripts, stale jobs."""

from typing import Any

from servicenow_mcp.client import ServiceNowClient
from servicenow_mcp.utils import ServiceNowQuery


async def run(client: ServiceNowClient, params: dict[str, Any]) -> dict[str, Any]:
    """Find stale automations across the instance.

    Checks:
    - Flow contexts stuck in IN_PROGRESS for > stale_days
    - Disabled business rules
    - Disabled script includes
    - Stale scheduled jobs (not run in > stale_days)

    Params:
        stale_days: Number of days to consider stale (default 30).
        limit: Maximum findings per category (default 20).
    """
    stale_days = params.get("stale_days", 30)
    limit = params.get("limit", 20)

    findings: list[dict[str, Any]] = []

    # 1. Stuck flow contexts (IN_PROGRESS created before cutoff)
    flow_query = ServiceNowQuery().equals("state", "IN_PROGRESS").older_than_days("sys_created_on", stale_days).build()
    flow_result = await client.query_records(
        "flow_context",
        flow_query,
        fields=["sys_id", "name", "state", "sys_created_on"],
        limit=limit,
    )

    # 2. Disabled business rules
    br_query = ServiceNowQuery().equals("active", "false").build()
    br_result = await client.query_records(
        "sys_script",
        br_query,
        fields=["sys_id", "name", "collection", "sys_updated_on"],
        limit=limit,
    )

    # 3. Disabled script includes
    si_query = ServiceNowQuery().equals("active", "false").build()
    si_result = await client.query_records(
        "sys_script_include",
        si_query,
        fields=["sys_id", "name", "api_name", "sys_updated_on"],
        limit=limit,
    )

    # 4. Stale scheduled jobs (not updated in > stale_days)
    sj_query = ServiceNowQuery().older_than_days("sys_updated_on", stale_days).build()
    sj_result = await client.query_records(
        "sysauto_script",
        sj_query,
        fields=["sys_id", "name", "run_type", "sys_updated_on"],
        limit=limit,
    )

    for rec in flow_result["records"]:
        findings.append(
            {
                "category": "stuck_flow",
                "element_id": f"flow_context:{rec.get('sys_id', '')}",
                "name": rec.get("name", ""),
                "detail": f"Flow stuck in IN_PROGRESS since {rec.get('sys_created_on', '')}",
            }
        )

    for rec in br_result["records"]:
        findings.append(
            {
                "category": "disabled_business_rule",
                "element_id": f"sys_script:{rec.get('sys_id', '')}",
                "name": rec.get("name", ""),
                "detail": f"Disabled BR on table '{rec.get('collection', '')}'",
            }
        )

    for rec in si_result["records"]:
        findings.append(
            {
                "category": "disabled_script_include",
                "element_id": f"sys_script_include:{rec.get('sys_id', '')}",
                "name": rec.get("name", ""),
                "detail": f"Disabled script include '{rec.get('api_name', '')}'",
            }
        )

    for rec in sj_result["records"]:
        findings.append(
            {
                "category": "stale_scheduled_job",
                "element_id": f"sysauto_script:{rec.get('sys_id', '')}",
                "name": rec.get("name", ""),
                "detail": f"Scheduled job not updated since {rec.get('sys_updated_on', '')}",
            }
        )

    return {
        "investigation": "stale_automations",
        "finding_count": len(findings),
        "findings": findings,
        "params": {"stale_days": stale_days, "limit": limit},
    }


async def explain(client: ServiceNowClient, element_id: str) -> dict[str, Any]:
    """Provide rich context for a stale automation finding.

    element_id format: "table:sys_id" (e.g. "flow_context:fc001").
    """
    table, sys_id = element_id.split(":", 1)
    record = await client.get_record(table, sys_id)

    explanation_parts = [f"Record from '{table}' with sys_id '{sys_id}'."]

    if table == "flow_context":
        explanation_parts.append(
            f"Flow '{record.get('name', '')}' has been in state "
            f"'{record.get('state', '')}' since {record.get('sys_created_on', '')}."
        )
        explanation_parts.append(
            "Consider cancelling this flow if it is no longer needed, or investigate why it is stuck."
        )
    elif table == "sys_script":
        explanation_parts.append(
            f"Business rule '{record.get('name', '')}' is disabled. Review whether it should be removed or re-enabled."
        )
    elif table == "sys_script_include":
        explanation_parts.append(
            f"Script include '{record.get('name', '')}' is disabled. Check if any other scripts reference it."
        )
    elif table == "sysauto_script":
        explanation_parts.append(
            f"Scheduled job '{record.get('name', '')}' has not been updated recently. Verify it is still needed."
        )

    return {
        "element": element_id,
        "explanation": " ".join(explanation_parts),
        "record": record,
    }
