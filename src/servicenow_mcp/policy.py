"""Policy engine for query safety, deny lists, field masking and write gating."""

import logging
import re
from typing import Any

from servicenow_mcp.config import Settings
from servicenow_mcp.errors import PolicyError, QuerySafetyError

logger = logging.getLogger(__name__)

# Tables that must never be accessed via the MCP server
DENIED_TABLES: set[str] = {
    "sys_user_has_password",
    "oauth_credential",
    "oauth_entity",
    "sys_certificate",
    "sys_ssh_key",
    "sys_credentials",
    "discovery_credentials",
    "sys_user_token",
}

# Field name patterns that trigger masking
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"api_key", re.IGNORECASE),
    re.compile(r"private_key", re.IGNORECASE),
]

MASK_VALUE = "***MASKED***"

# Date field patterns used to detect date-bounded filters
_DATE_FIELD_PATTERNS = [
    "sys_created_on",
    "sys_updated_on",
    "opened_at",
    "closed_at",
    "sys_recorded_at",
]


def check_table_access(table: str) -> None:
    """Raise PolicyError if the table is on the deny list.

    Returns None if access is allowed.
    """
    if table in DENIED_TABLES:
        raise PolicyError(f"Access to table '{table}' is denied by policy")


def _is_sensitive_field(field_name: str) -> bool:
    """Check if a field name matches sensitive patterns."""
    return any(pattern.search(field_name) for pattern in _SENSITIVE_PATTERNS)


def mask_sensitive_fields(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the record with sensitive fields masked."""
    masked = dict(record)
    for key in masked:
        if _is_sensitive_field(key):
            masked[key] = MASK_VALUE
    return masked


def _has_date_filter(query: str) -> bool:
    """Check if the query contains a date-bounded filter."""
    return any(field in query for field in _DATE_FIELD_PATTERNS)


def enforce_query_safety(
    table: str,
    query: str,
    limit: int | None,
    settings: Settings,
) -> dict[str, Any]:
    """Validate and enforce query safety constraints.

    Returns a dict with the validated 'limit' value.
    Raises QuerySafetyError if constraints are violated.
    """
    check_table_access(table)

    # Cap limit at max_row_limit
    if limit is None or limit > settings.max_row_limit:
        effective_limit = settings.max_row_limit
    else:
        effective_limit = limit

    # Large tables require date-bounded filters
    if table in settings.large_table_names and not _has_date_filter(query):
        raise QuerySafetyError(
            f"Table '{table}' is large and requires a date-bounded filter "
            f"(e.g., sys_created_on>=YYYY-MM-DD). "
            f"Add a date field constraint to your query."
        )

    return {"limit": effective_limit}


def can_write(
    table: str,
    settings: Settings,
    override: bool = False,
) -> bool:
    """Check if write operations are allowed for the given table and environment."""
    # Always block writes to denied tables
    if table in DENIED_TABLES:
        return False

    # In production, require explicit override
    if settings.is_production and not override:
        return False

    return True
