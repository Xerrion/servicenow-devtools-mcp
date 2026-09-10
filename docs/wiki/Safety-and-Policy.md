# Safety and Policy

The server enforces multiple layers of safety guardrails to prevent accidental data exposure, unbounded queries, and unintended modifications. These policies are applied automatically by the platform layer.

---

## Overview

| Layer | Purpose |
| --- | --- |
| Table access control | Blocks access to security-sensitive tables (e.g., `sys_credentials`) |
| Sensitive field masking | Masks passwords, tokens, and secrets in responses |
| Query safety | Enforces row limits and date-bounded filters on large tables |
| Write gating | Blocks all mutations in production environments |
| Input validation | Validates identifiers and sys_ids to prevent injection |
| Write payload validation | Bounds inline JSON and checks dictionary-confirmed XML fields |

---

## Table Access Control

The following security-sensitive tables are permanently blocked. Any attempt to use them via `query`, `describe`, or `record_write` will raise a `PolicyError`.

- `sys_user_has_password`
- `oauth_credential`
- `oauth_entity`
- `sys_certificate`
- `sys_ssh_key`
- `sys_credentials`
- `discovery_credentials`
- `sys_user_token`

---

## Sensitive Field Masking

The `mask_record` (used by `query`) and `mask_sensitive_fields` (used by `record_write`) functions automatically replace sensitive values with `***MASKED***`.

### Masked Patterns

Any field name matching these regex patterns is masked:

- `password`, `token`, `secret`, `credential`, `api_key`, `private_key`.

---

## Query Safety

Query safety prevents performance degradation on the ServiceNow instance.

### Row Limits

- All queries are capped at `MAX_ROW_LIMIT` (default 100, max 10000).
- If no limit is provided, the default is applied automatically.

### Large Table Protection

The following tables require a date-bounded filter (e.g., `sys_created_on>=javascript:gs.daysAgo(1)`):

- `syslog`, `sys_audit`, `sys_log_transaction`, `sys_email_log`.

Failure to provide a date filter on these tables results in a `QuerySafetyError`.

---

## Write Gating

Mutations are controlled by the `write_gate` function.

### Production Blocking

All write operations are blocked when `SERVICENOW_ENV` is set to `"prod"` or `"production"`. This affects:

- `record_write` and `record_apply`
- `attachment_write` (upload and delete)
- `service_catalog` (order and cart mutations)

### Preview Pattern

The system defaults to a preview/apply flow mediated by the `PreviewTokenStore`. Call `record_write` with `preview=true` to stage the change and receive a `preview_token`. This staged change is committed when the token is passed to `record_apply`. Tokens are single-use, and apply re-checks write gates. Set `preview=false` only for an authorized immediate write.

---

## Inline Write Validation

- **Input:** `record_write.data` is a JSON string mapping field names to complete values. The server does not read local script files. Multiple script fields can be written in one payload; omitted fields stay unchanged on update.
- **Limits:** The complete UTF-8 JSON input is capped at 256 KiB (262144 bytes), including field names and escaping. Parsing and key validation run before metadata I/O.
- **XML validation:** Dictionary types are fetched only for supplied fields, with child-first inheritance. Every supplied field with `internal_type == 'xml'` must contain a string of well-formed XML. Empty, null, and malformed XML are rejected before token creation or mutation. Script syntax is not checked.
- **Metadata access:** Request errors block writes. Dictionary ACLs can hide fields, which prevents local type validation for those fields. ServiceNow remains the authority for authorization and server-side validation.

---

## Error Handling

All safety violations result in a JSON error envelope. The `@tool_handler` decorator ensures that `PolicyError`, `QuerySafetyError`, and `ForbiddenError` (ACL denials) are caught and returned gracefully with a descriptive message.

For more details on the implementation of these policies, see [[Architecture]].
