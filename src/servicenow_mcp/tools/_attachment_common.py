"""Shared attachment helpers for validation, metadata parsing and size limits."""

import base64
import binascii
from typing import Any

from servicenow_mcp.utils import resolve_ref_value, validate_identifier, validate_sys_id


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def ensure_attachment_size_within_limit(content: bytes, *, operation: str) -> None:
    """Raise ValueError when attachment bytes exceed the supported MCP transfer limit."""
    size_bytes = len(content)
    if size_bytes <= MAX_ATTACHMENT_BYTES:
        return
    raise ValueError(
        f"Attachment {operation} size {size_bytes} bytes exceeds the maximum supported size of "
        f"{MAX_ATTACHMENT_BYTES} bytes"
    )


def decode_content_base64(content_base64: str) -> bytes:
    """Decode validated base64 attachment content into raw bytes."""
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 content") from exc


def encode_content_base64(content: bytes) -> str:
    """Encode attachment bytes for MCP transport."""
    return base64.b64encode(content).decode("ascii")


def get_attachment_field(metadata: dict[str, Any], field_name: str) -> str:
    """Return a required attachment metadata field as a normalized string."""
    value = resolve_ref_value(metadata.get(field_name, ""))
    if value:
        return value
    raise ValueError(f"Attachment metadata is missing required field '{field_name}'")


def get_attachment_sys_id(metadata: dict[str, Any]) -> str:
    """Return and validate the attachment sys_id from metadata."""
    sys_id = get_attachment_field(metadata, "sys_id")
    validate_sys_id(sys_id)
    return sys_id


def get_attachment_table_name(metadata: dict[str, Any]) -> str:
    """Return and validate the source table name from attachment metadata."""
    table_name = get_attachment_field(metadata, "table_name")
    validate_identifier(table_name)
    return table_name


def get_attachment_table_sys_id(metadata: dict[str, Any]) -> str:
    """Return and validate the source record sys_id from attachment metadata."""
    table_sys_id = get_attachment_field(metadata, "table_sys_id")
    validate_sys_id(table_sys_id)
    return table_sys_id


def build_attachment_download_payload(metadata: dict[str, Any], content: bytes) -> dict[str, Any]:
    """Build a stable attachment download response payload."""
    return {
        "sys_id": get_attachment_sys_id(metadata),
        "table_name": get_attachment_table_name(metadata),
        "table_sys_id": get_attachment_table_sys_id(metadata),
        "file_name": get_attachment_field(metadata, "file_name"),
        "content_type": resolve_ref_value(metadata.get("content_type", "")),
        "size_bytes": len(content),
        "content_base64": encode_content_base64(content),
    }
