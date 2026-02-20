# GitHub Copilot Custom Instructions for ServiceNow MCP

This repository contains a Python 3.12+ async MCP server for ServiceNow. Please strictly adhere to the following project standards when providing code suggestions, refactoring, or writing tests.

## 1. Core Architecture & Tooling
- **Package Manager:** Use `uv` (never use `pip` or `poetry`).
- **Frameworks:** `mcp`, `httpx`, `pydantic`, `pydantic-settings`, `uvicorn`, `starlette`.
- **Async:** All ServiceNow API calls must be `async`.

## 2. Code Style & Formatting
- **Formatter:** Code is formatted with `ruff`. Target Python 3.12.
- **Line Length:** 120 characters maximum.
- **Quotes:** Double quotes everywhere.
- **Imports:** Use absolute imports only (e.g., `from servicenow_mcp.client import ServiceNowClient`). Group specific imports, and NEVER use wildcard imports.
- **Naming:**
  - Functions/Variables: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`

## 3. Typing Rules (Strict Mypy)
- **Functions:** ALL function signatures MUST have full type hints.
- **Return Types:** Always explicit, including `-> None` for void functions.
- **Union Syntax:** Use modern unions like `str | None` instead of `Optional[str]`.
- **Generics:** Use lowercase types like `dict[str, Any]` and `list[str]`.

## 4. Error Handling & Tool Responses
- **Exception Hierarchy:** Use custom exceptions from `errors.py` (e.g., `ServiceNowMCPError`, `AuthError`, `NotFoundError`).
- **Tool Functions (`@mcp.tool()`):** MUST NEVER raise exceptions to MCP.
- **JSON Envelopes:** Tool functions must catch all exceptions and return a JSON error envelope:
  ```python
  except Exception as e:
      return json.dumps(format_response(data=None, correlation_id=correlation_id, status="error", error=str(e)))
  ```

## 5. Testing Patterns (Pytest)
- **Framework:** `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"`).
- **HTTP Mocking:** Use **respx** (`@respx.mock` decorator).
- **Settings:** ALWAYS construct `Settings(_env_file=None)` in tests to avoid loading real env files.
- **Assertions:** When testing tool JSON output, use `json.loads()` and assert on response envelope fields (`status`, `data`, `error`).
- **Integration Tests:** Marked with `@pytest.mark.integration`.