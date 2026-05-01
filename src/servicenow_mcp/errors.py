"""Custom exceptions for the ServiceNow MCP server."""

from typing import Any


class ServiceNowMCPError(Exception):
    """Base exception for all ServiceNow MCP errors."""

    status_code: int | None

    def __init__(self, message: str, status_code: int | None = None, *, response_body: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class AuthError(ServiceNowMCPError):
    """Authentication failure (HTTP 401)."""

    def __init__(self, message: str = "Authentication failed", *, response_body: Any | None = None) -> None:
        super().__init__(message, status_code=401, response_body=response_body)


class ForbiddenError(ServiceNowMCPError):
    """Authorization failure (HTTP 403)."""

    def __init__(self, message: str = "Access forbidden", *, response_body: Any | None = None) -> None:
        super().__init__(message, status_code=403, response_body=response_body)


class ACLError(ForbiddenError):
    """ServiceNow ACL denial (HTTP 403)."""

    def __init__(self, message: str = "Access denied by ServiceNow ACL", *, response_body: Any | None = None) -> None:
        super().__init__(message, response_body=response_body)


class NotFoundError(ServiceNowMCPError):
    """Resource not found (HTTP 404)."""

    def __init__(self, message: str = "Resource not found", *, response_body: Any | None = None) -> None:
        super().__init__(message, status_code=404, response_body=response_body)


class ServerError(ServiceNowMCPError):
    """ServiceNow server error (HTTP 5xx)."""

    def __init__(
        self,
        message: str = "Internal server error",
        status_code: int = 500,
        *,
        response_body: Any | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_body=response_body)


class PolicyError(ServiceNowMCPError):
    """Access denied by policy (deny list, masking, etc.)."""

    def __init__(
        self,
        message: str = "Policy violation",
        status_code: int = 403,
        *,
        response_body: Any | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_body=response_body)


class QuerySafetyError(PolicyError):
    """Query violates safety policies."""

    def __init__(self, message: str = "Query safety violation", *, response_body: Any | None = None) -> None:
        super().__init__(message, status_code=403, response_body=response_body)
