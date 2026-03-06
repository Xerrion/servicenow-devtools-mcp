"""Shared helpers for domain tool modules."""

from servicenow_mcp.choices import ChoiceRegistry
from servicenow_mcp.client import ServiceNowClient
from servicenow_mcp.policy import mask_sensitive_fields
from servicenow_mcp.utils import ServiceNowQuery, format_response


def validate_number_prefix(number: str, prefix: str, entity_label: str, correlation_id: str) -> str | None:
    """Return an error response if *number* does not start with *prefix*, else None.

    Args:
        number: The record number to validate (e.g. "INC0010001")
        prefix: Expected prefix (e.g. "INC", "PRB", "CHG", "REQ", "RITM")
        entity_label: Human-readable entity name for error messages (e.g. "incident", "problem", "change request", "request", "request item")
        correlation_id: Request correlation ID
    """
    if not number.upper().startswith(prefix):
        return format_response(
            data=None,
            correlation_id=correlation_id,
            status="error",
            error=f"Invalid {entity_label} number: {number}. Must start with {prefix} prefix.",
        )
    return None


async def lookup_record_by_number(
    client: ServiceNowClient,
    table: str,
    number: str,
    entity_label: str,
    correlation_id: str,
) -> tuple[str, str | None]:
    """Look up a record by number and return (sys_id, None) or ("", error_response).

    Args:
        client: Active ServiceNow client
        table: Table name (e.g. "incident")
        number: Record number (already validated, will be uppercased)
        entity_label: Human-readable name for error messages (e.g. "Incident", "Problem")
        correlation_id: Request correlation ID
    """
    result = await client.query_records(
        table=table,
        query=ServiceNowQuery().equals("number", number.upper()).build(),
        limit=1,
    )
    if not result["records"]:
        return "", format_response(
            data=None,
            correlation_id=correlation_id,
            status="error",
            error=f"{entity_label} {number} not found.",
        )
    return result["records"][0]["sys_id"], None


async def fetch_record_by_number(
    client: ServiceNowClient,
    table: str,
    number: str,
    entity_label: str,
    correlation_id: str,
) -> str:
    """Fetch a single record by number, returning a formatted success or error response.

    Used by _get tools that return the full record. Applies mask_sensitive_fields.

    Args:
        client: Active ServiceNow client
        table: Table name (e.g. "incident")
        number: Record number (already validated, will be uppercased)
        entity_label: Human-readable name for error messages (e.g. "Incident")
        correlation_id: Request correlation ID
    """
    result = await client.query_records(
        table=table,
        query=ServiceNowQuery().equals("number", number.upper()).build(),
        display_values=True,
        limit=1,
    )
    if not result["records"]:
        return format_response(
            data=None,
            correlation_id=correlation_id,
            status="error",
            error=f"{entity_label} {number} not found.",
        )
    masked = mask_sensitive_fields(result["records"][0])
    return format_response(data=masked, correlation_id=correlation_id)


def validate_int_range(value: int, field_name: str, min_val: int, max_val: int, correlation_id: str) -> str | None:
    """Return an error response if *value* is outside [min_val, max_val], else None.

    Args:
        value: The integer value to validate
        field_name: Field name for error message (e.g. "urgency", "impact")
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)
        correlation_id: Request correlation ID
    """
    if value < min_val or value > max_val:
        return format_response(
            data=None,
            correlation_id=correlation_id,
            status="error",
            error=f"{field_name} must be between {min_val} and {max_val}, got {value}.",
        )
    return None


def validate_required_string(value: str, field_name: str, correlation_id: str) -> str | None:
    """Return an error response if *value* is empty or whitespace, else None.

    Args:
        value: The string value to validate
        field_name: Field name for error message (e.g. "short_description", "close_code")
        correlation_id: Request correlation ID
    """
    if not value or not value.strip():
        return format_response(
            data=None,
            correlation_id=correlation_id,
            status="error",
            error=f"{field_name} is required and cannot be empty.",
        )
    return None


def validate_no_empty_changes(changes: dict[str, str], correlation_id: str) -> str | None:
    """Return an error response if *changes* dict is empty, else None.

    Args:
        changes: Dictionary of field changes
        correlation_id: Request correlation ID
    """
    if not changes:
        return format_response(
            data=None,
            correlation_id=correlation_id,
            status="error",
            error="No fields to update provided.",
        )
    return None


def parse_field_list(fields: str) -> list[str] | None:
    """Parse a comma-separated field string into a list, or None if empty.

    Args:
        fields: Comma-separated field names (may contain whitespace around commas)
    """
    return [f.strip() for f in fields.split(",") if f.strip()] if fields else None


async def resolve_state(table: str, state: str, choices: ChoiceRegistry | None) -> str:
    """Resolve a human-readable state label to its internal value.

    Args:
        table: ServiceNow table name (e.g. "incident")
        state: State label to resolve (will be lowercased)
        choices: Optional ChoiceRegistry for label-to-value mapping
    """
    if choices:
        return await choices.resolve(table, "state", state.lower())
    return state
