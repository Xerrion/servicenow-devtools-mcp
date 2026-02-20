"""Smoke test for Phase 1+2 tools against a live ServiceNow dev instance.

Usage:
    uv run python scripts/smoke_test.py

Requires .env.local with valid credentials.
"""

import asyncio
import sys
import time
from typing import Any

# Add project root to path so we can import our modules
sys.path.insert(0, "src")

from servicenow_mcp.auth import BasicAuthProvider
from servicenow_mcp.client import ServiceNowClient
from servicenow_mcp.config import Settings
from servicenow_mcp.errors import PolicyError
from servicenow_mcp.policy import check_table_access, mask_sensitive_fields


class SmokeTestRunner:
    """Runs smoke tests and tracks results."""

    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []

    def record(self, name: str, passed: bool, detail: str = "") -> None:
        status = "PASS" if passed else "FAIL"
        self.results.append({"name": name, "passed": passed, "detail": detail})
        icon = "+" if passed else "!"
        print(f"  [{icon}] {status}: {name}")
        if detail:
            print(f"         {detail}")

    def summary(self) -> bool:
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        print(f"\n{'=' * 60}")
        print(f"  SMOKE TEST SUMMARY: {passed}/{total} passed, {failed} failed")
        if failed:
            print("\n  Failed tests:")
            for r in self.results:
                if not r["passed"]:
                    print(f"    - {r['name']}: {r['detail']}")
        print(f"{'=' * 60}")
        return failed == 0


async def run_smoke_tests() -> bool:
    """Run all Phase 1+2 smoke tests. Returns True if all passed."""
    runner = SmokeTestRunner()

    # Load config from .env.local
    try:
        settings = Settings()
        print(f"Instance: {settings.servicenow_instance_url}")
        print(f"User:     {settings.servicenow_username}")
        print(f"Env:      {settings.servicenow_env}")
        print(f"Package:  {settings.mcp_tool_package}")
        print()
    except Exception as e:
        print(f"FATAL: Failed to load config: {e}")
        return False

    auth = BasicAuthProvider(settings)

    # We'll collect data across tests
    incident_sys_id: str | None = None
    business_rule_sys_id: str | None = None

    # ── Test 1: Connectivity ──────────────────────────────────────
    print("--- Connectivity ---")
    try:
        async with ServiceNowClient(settings, auth) as client:
            metadata = await client.get_metadata("incident")
        assert len(metadata) > 0, "No metadata returned"
        runner.record(
            "Connectivity",
            True,
            f"Got {len(metadata)} dictionary entries for 'incident'",
        )
    except Exception as e:
        runner.record("Connectivity", False, str(e))
        # If connectivity fails, abort early — nothing else will work
        print("\nAborting: cannot connect to ServiceNow instance.")
        runner.summary()
        return False

    # ── Test 2: table_describe ────────────────────────────────────
    print("\n--- Introspection Tools ---")
    try:
        async with ServiceNowClient(settings, auth) as client:
            metadata = await client.get_metadata("incident")
        fields = [
            {
                "element": e.get("element", ""),
                "internal_type": e.get("internal_type", ""),
            }
            for e in metadata
        ]
        assert len(fields) > 0, "No fields returned"
        sample_names = [f["element"] for f in fields[:5]]
        runner.record(
            "table_describe", True, f"{len(fields)} fields, sample: {sample_names}"
        )
    except Exception as e:
        runner.record("table_describe", False, str(e))

    # ── Test 3: table_query ───────────────────────────────────────
    try:
        async with ServiceNowClient(settings, auth) as client:
            result = await client.query_records(
                "incident",
                "active=true",
                fields=["sys_id", "number", "short_description", "priority"],
                limit=5,
            )
        records = result["records"]
        count = result["count"]
        assert len(records) > 0, "No active incidents found"
        # Save first sys_id for later tests
        incident_sys_id = records[0].get("sys_id", "")
        numbers = [r.get("number", "?") for r in records]
        runner.record(
            "table_query", True, f"{count} total, got {len(records)} records: {numbers}"
        )
    except Exception as e:
        runner.record("table_query", False, str(e))

    # ── Test 4: table_get ─────────────────────────────────────────
    if incident_sys_id:
        try:
            async with ServiceNowClient(settings, auth) as client:
                record = await client.get_record(
                    "incident",
                    incident_sys_id,
                    fields=["sys_id", "number", "short_description", "state"],
                )
            masked = mask_sensitive_fields(record)
            assert record.get("sys_id") == incident_sys_id, "sys_id mismatch"
            runner.record(
                "table_get",
                True,
                f"Fetched {record.get('number', '?')}: {record.get('short_description', '?')[:60]}",
            )
        except Exception as e:
            runner.record("table_get", False, str(e))
    else:
        runner.record("table_get", False, "Skipped — no sys_id from table_query")

    # ── Test 5: table_aggregate ───────────────────────────────────
    try:
        async with ServiceNowClient(settings, auth) as client:
            result = await client.aggregate("incident", "")
        # The stats API returns a result — check it's a dict or list
        assert result is not None, "No aggregate result"
        runner.record("table_aggregate", True, f"Result: {str(result)[:120]}")
    except Exception as e:
        runner.record("table_aggregate", False, str(e))

    # ── Test 6: rel_references_from ───────────────────────────────
    print("\n--- Relationship Tools ---")
    if incident_sys_id:
        try:
            async with ServiceNowClient(settings, auth) as client:
                # Get the record with display values
                record = await client.get_record(
                    "incident", incident_sys_id, display_values=True
                )
                # Get reference fields for incident
                ref_fields = await client.query_records(
                    "sys_dictionary",
                    "name=incident^internal_type=reference",
                    fields=["element", "reference", "column_label"],
                    limit=100,
                )
            outgoing = []
            for field in ref_fields["records"]:
                field_name = field.get("element", "")
                ref_table = field.get("reference", "")
                if field_name and field_name in record and record[field_name]:
                    outgoing.append(f"{field_name}->{ref_table}")
            runner.record(
                "rel_references_from",
                True,
                f"{len(outgoing)} outgoing refs, sample: {outgoing[:5]}",
            )
        except Exception as e:
            runner.record("rel_references_from", False, str(e))
    else:
        runner.record("rel_references_from", False, "Skipped — no sys_id")

    # ── Test 7: rel_references_to ─────────────────────────────────
    if incident_sys_id:
        try:
            async with ServiceNowClient(settings, auth) as client:
                ref_fields = await client.query_records(
                    "sys_dictionary",
                    "internal_type=reference^reference=incident",
                    fields=["name", "element", "column_label"],
                    limit=50,
                )
            referencing_tables = list(
                {f.get("name", "") for f in ref_fields["records"] if f.get("name")}
            )
            runner.record(
                "rel_references_to",
                True,
                f"{len(referencing_tables)} tables reference incident, sample: {referencing_tables[:5]}",
            )
        except Exception as e:
            runner.record("rel_references_to", False, str(e))
    else:
        runner.record("rel_references_to", False, "Skipped — no sys_id")

    # ── Test 8: meta_list_artifacts ───────────────────────────────
    print("\n--- Metadata Tools ---")
    try:
        async with ServiceNowClient(settings, auth) as client:
            result = await client.query_records(
                "sys_script",  # business_rule table
                "",
                limit=5,
            )
        artifacts = result["records"]
        assert len(artifacts) > 0, "No business rules found"
        business_rule_sys_id = artifacts[0].get("sys_id", "")
        names = [a.get("name", "?") for a in artifacts]
        runner.record(
            "meta_list_artifacts",
            True,
            f"{result['count']} total business rules, sample: {names}",
        )
    except Exception as e:
        runner.record("meta_list_artifacts", False, str(e))

    # ── Test 9: meta_get_artifact ─────────────────────────────────
    if business_rule_sys_id:
        try:
            async with ServiceNowClient(settings, auth) as client:
                record = await client.get_record("sys_script", business_rule_sys_id)
            assert record.get("sys_id") == business_rule_sys_id, "sys_id mismatch"
            has_script = bool(record.get("script", ""))
            runner.record(
                "meta_get_artifact",
                True,
                f"Got BR '{record.get('name', '?')}', has_script={has_script}",
            )
        except Exception as e:
            runner.record("meta_get_artifact", False, str(e))
    else:
        runner.record("meta_get_artifact", False, "Skipped — no business_rule sys_id")

    # ── Test 10: meta_find_references ─────────────────────────────
    try:
        matches = []
        async with ServiceNowClient(settings, auth) as client:
            # Search just sys_script for "incident" in script body
            result = await client.query_records(
                "sys_script",
                "scriptCONTAINSincident",
                fields=["sys_id", "name", "sys_class_name"],
                limit=10,
            )
            for r in result["records"]:
                matches.append(r.get("name", "?"))
        runner.record(
            "meta_find_references",
            True,
            f"Found {len(matches)} BRs referencing 'incident': {matches[:5]}",
        )
    except Exception as e:
        runner.record("meta_find_references", False, str(e))

    # ── Test 11: meta_what_writes ─────────────────────────────────
    try:
        async with ServiceNowClient(settings, auth) as client:
            result = await client.query_records(
                "sys_script",
                "collection=incident",
                limit=50,
            )
        writers = result["records"]
        names = [w.get("name", "?") for w in writers[:5]]
        runner.record(
            "meta_what_writes",
            True,
            f"{len(writers)} BRs write to incident, sample: {names}",
        )
    except Exception as e:
        runner.record("meta_what_writes", False, str(e))

    # ── Test 12: Policy — denied table ────────────────────────────
    print("\n--- Policy Enforcement ---")
    try:
        check_table_access("sys_user_has_password")
        runner.record(
            "policy_denied_table",
            False,
            "PolicyError was NOT raised — access should be denied!",
        )
    except PolicyError:
        runner.record(
            "policy_denied_table", True, "PolicyError correctly raised for denied table"
        )
    except Exception as e:
        runner.record(
            "policy_denied_table", False, f"Wrong exception: {type(e).__name__}: {e}"
        )

    # ══════════════════════════════════════════════════════════════
    # PHASE 2 — Change Intelligence & Debug/Trace Tools
    # ══════════════════════════════════════════════════════════════

    # Discover an update set for change intelligence tests
    update_set_sys_id: str | None = None

    # ── Test 13: changes_updateset_inspect ────────────────────────
    print("\n--- Change Intelligence Tools ---")
    try:
        async with ServiceNowClient(settings, auth) as client:
            # Find any update set with members
            us_result = await client.query_records(
                "sys_update_set",
                "stateINin progress,complete",
                fields=["sys_id", "name", "state"],
                limit=5,
            )
        us_records = us_result["records"]
        assert len(us_records) > 0, "No update sets found"
        update_set_sys_id = us_records[0].get("sys_id", "")
        us_name = us_records[0].get("name", "?")

        # Now fetch its members (like the tool does)
        async with ServiceNowClient(settings, auth) as client:
            members_result = await client.query_records(
                "sys_update_xml",
                f"update_set={update_set_sys_id}",
                fields=["sys_id", "name", "type", "action", "target_name"],
                limit=50,
            )
        member_count = len(members_result["records"])
        runner.record(
            "changes_updateset_inspect",
            True,
            f"Update set '{us_name}' has {member_count} members",
        )
    except Exception as e:
        runner.record("changes_updateset_inspect", False, str(e))

    # ── Test 14: changes_last_touched ─────────────────────────────
    if incident_sys_id:
        try:
            async with ServiceNowClient(settings, auth) as client:
                audit_result = await client.query_records(
                    "sys_audit",
                    f"tablename=incident^documentkey={incident_sys_id}",
                    fields=[
                        "sys_id",
                        "user",
                        "fieldname",
                        "oldvalue",
                        "newvalue",
                        "sys_created_on",
                    ],
                    limit=10,
                    order_by="sys_created_on",
                )
            audit_count = len(audit_result["records"])
            sample_fields = [
                e.get("fieldname", "?") for e in audit_result["records"][:3]
            ]
            runner.record(
                "changes_last_touched",
                True,
                f"{audit_count} audit entries for incident, fields: {sample_fields}",
            )
        except Exception as e:
            runner.record("changes_last_touched", False, str(e))
    else:
        runner.record("changes_last_touched", False, "Skipped — no incident sys_id")

    # ── Test 15: changes_release_notes ────────────────────────────
    if update_set_sys_id:
        try:
            async with ServiceNowClient(settings, auth) as client:
                update_set = await client.get_record(
                    "sys_update_set", update_set_sys_id
                )
            us_name = update_set.get("name", "?")
            us_state = update_set.get("state", "?")
            runner.record(
                "changes_release_notes",
                True,
                f"Fetched update set '{us_name}' (state={us_state}) for release notes",
            )
        except Exception as e:
            runner.record("changes_release_notes", False, str(e))
    else:
        runner.record("changes_release_notes", False, "Skipped — no update set sys_id")

    # ── Test 16: debug_trace ──────────────────────────────────────
    print("\n--- Debug/Trace Tools ---")
    if incident_sys_id:
        try:
            timeline_count = 0
            async with ServiceNowClient(settings, auth) as client:
                # Audit entries
                audit_r = await client.query_records(
                    "sys_audit",
                    f"tablename=incident^documentkey={incident_sys_id}",
                    fields=["sys_id", "user", "fieldname", "sys_created_on"],
                    limit=20,
                )
                timeline_count += len(audit_r["records"])

                # Journal entries
                journal_r = await client.query_records(
                    "sys_journal_field",
                    f"element_id={incident_sys_id}",
                    fields=["sys_id", "element", "sys_created_on"],
                    limit=20,
                )
                timeline_count += len(journal_r["records"])

            runner.record(
                "debug_trace",
                True,
                f"Timeline: {len(audit_r['records'])} audit + {len(journal_r['records'])} journal = {timeline_count} events",
            )
        except Exception as e:
            runner.record("debug_trace", False, str(e))
    else:
        runner.record("debug_trace", False, "Skipped — no incident sys_id")

    # ── Test 17: debug_integration_health ─────────────────────────
    try:
        async with ServiceNowClient(settings, auth) as client:
            ecc_result = await client.query_records(
                "ecc_queue",
                "state=error",
                fields=["sys_id", "name", "queue", "error_string", "sys_created_on"],
                limit=20,
            )
        error_count = len(ecc_result["records"])
        runner.record(
            "debug_integration_health",
            True,
            f"ECC queue: {error_count} error entries found",
        )
    except Exception as e:
        runner.record("debug_integration_health", False, str(e))

    # ── Test 18: debug_field_mutation_story ────────────────────────
    if incident_sys_id:
        try:
            async with ServiceNowClient(settings, auth) as client:
                mutation_result = await client.query_records(
                    "sys_audit",
                    f"tablename=incident^documentkey={incident_sys_id}^fieldname=state",
                    fields=[
                        "sys_id",
                        "user",
                        "oldvalue",
                        "newvalue",
                        "sys_created_on",
                    ],
                    limit=20,
                    order_by="sys_created_on",
                )
            mutation_count = len(mutation_result["records"])
            runner.record(
                "debug_field_mutation_story",
                True,
                f"'state' field: {mutation_count} mutations found",
            )
        except Exception as e:
            runner.record("debug_field_mutation_story", False, str(e))
    else:
        runner.record(
            "debug_field_mutation_story", False, "Skipped — no incident sys_id"
        )

    # ── Summary ───────────────────────────────────────────────────
    print()
    return runner.summary()


def main() -> None:
    print("=" * 60)
    print("  ServiceNow MCP — Phase 1+2 Smoke Test")
    print("=" * 60)
    print()

    start = time.time()
    all_passed = asyncio.run(run_smoke_tests())
    elapsed = time.time() - start

    print(f"\n  Completed in {elapsed:.1f}s")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
