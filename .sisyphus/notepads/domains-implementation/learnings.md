## Task 8: CMDB Domain Implementation

**Date:** 2026-03-03

### Implementation Summary
Successfully implemented 5 READ-ONLY CMDB domain tools in `src/servicenow_mcp/tools/domains/cmdb.py`:
- `cmdb_list`: List CIs with dynamic ci_class parameter (default "cmdb_ci")
- `cmdb_get`: Dual lookup by sys_id OR name
- `cmdb_relationships`: Query cmdb_rel_ci table with parent/child/both directions
- `cmdb_classes`: Aggregate API to list unique CI classes
- `cmdb_health`: Aggregate API to check operational status distribution

### Key Patterns
1. **Dynamic table access**: `check_table_access(ci_class)` allows user-specified table names
2. **Sys_id detection**: Use regex `r"^[a-f0-9]{32}$"` to detect 32-char hex sys_id vs. name
3. **Aggregate API**: `client.aggregate()` returns raw result list, wrap with `format_response(data=result, ...)`
4. **Relationship queries**: Build queries like `child.sys_id={sys_id}^ORparent.sys_id={sys_id}` for bidirectional
5. **Name resolution**: For relationships by name, do lookup first to get sys_id, then query cmdb_rel_ci

### Code Style
- Ternary operators preferred over if/else blocks (SIM108 rule)
- All inline comments justified (regex logic, status mapping, API structure)
- Docstrings required for MCP tool schema generation
- URL encoding in tests: `%3D` appears in request URLs

### Testing
- All 15 tests in `tests/domains/test_cmdb.py` pass
- Full suite: 585 passed (excluding knowledge/problem/request unimplemented domains)
- Ruff + mypy clean

### Evidence Files Created
- `.sisyphus/evidence/task-8-cmdb-list.txt` (3 tests)
- `.sisyphus/evidence/task-8-cmdb-relationships.txt` (3 tests)
- `.sisyphus/evidence/task-8-full-suite.txt` (585 tests)

### Technical Details
- Client method is `aggregate()`, not `aggregate_records()`
- Aggregate API returns `{"result": [...]}`, client extracts to just the list
- Status map: operational=1, non_operational=2, etc. (standard ServiceNow values)
- No write_gate calls - all tools are read-only introspection

## Task 10: Request Management Domain Implementation

**Date:** 2026-03-03

### Implementation Summary
Successfully implemented 5 Request Management domain tools in `src/servicenow_mcp/tools/domains/request.py`:
- `request_list`: List requests (sc_request table) with state/requested_for/assignment_group filters
- `request_get`: Fetch request by REQ number (with REQ prefix validation)
- `request_items`: **UNIQUE TOOL** - Fetch request items (RITMs) for a parent request using `request.number` query
- `request_item_get`: Fetch request item by RITM number (with RITM prefix validation)
- `request_item_update`: **WRITE TOOL** - Update request items (state, assignment_group, assigned_to)

### Key Patterns - 2-Table Domain
1. **Dual table access**: `sc_request` (REQ prefix) + `sc_req_item` (RITM prefix)
2. **Dual prefix validation**: Tools validate correct prefix (REQ vs RITM) based on which table they query
3. **Parent-child relationship query**: `request_items` queries `sc_req_item` with `request.number={REQ_NUMBER}` to get all items for a request
4. **Write gate on child table**: Only `request_item_update` is a write tool, uses `write_gate("sc_req_item", ...)`
5. **Empty list is valid**: `request_items` can return `[]` without error (not all requests have items)

### Test Specification Fixes
- **Test file had incorrect mock URLs**: Changed from `instance.service-now.com` to `test.service-now.com` (15 occurrences)
- **Test file used wrong HTTP verb**: Changed from `respx.put()` to `respx.patch()` for update mocks (client uses PATCH)
- Both fixes were necessary because test file didn't match project conventions used by other domains

### Code Style
- All tools follow incident.py pattern: `safe_tool_call()` + inner `_run()` async function
- Ternary operators for query building
- Docstrings required for MCP schema generation
- `mask_sensitive_fields(record)` single-arg form on all returned records

### Testing
- All 17 tests in `tests/domains/test_request.py` pass (task description said 18, actual count is 17)
- Full suite: 619 passed, 19 failed (knowledge domain unimplemented - expected)
- Ruff + mypy clean
- Total test count: 638 non-integration tests (18 integration tests excluded)

### Evidence Files
- `.sisyphus/evidence/task-10-request-items.txt` (already existed)
- `.sisyphus/evidence/task-10-full-suite.txt` (already existed)

### Technical Details
- Request domain uses 2 separate tables unlike single-table domains (incident, problem, change)
- Parent-child relationship is queried via dot-notation: `request.number=REQ0001234`
- Only child table (sc_req_item) has write operations
- Both tables use `check_table_access()` with appropriate table name before API calls
- No state mapping needed (unlike incident which maps state names to numbers) - states used as-is
