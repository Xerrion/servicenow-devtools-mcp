"""Shared test fixtures and helpers."""

from collections.abc import Generator
from unittest.mock import patch

import pytest

from servicenow_mcp.auth import BasicAuthProvider
from servicenow_mcp.config import Settings


@pytest.fixture(autouse=True)
def _disable_sentry_capture() -> Generator[None, None, None]:
    """Prevent Sentry from capturing exceptions during tests.

    Resets the module-level ``_initialized`` flag so that
    ``capture_exception()`` short-circuits before reaching the real SDK.
    """
    import servicenow_mcp.sentry as _sentry_mod

    _sentry_mod._initialized = False
    yield
    _sentry_mod._initialized = False


@pytest.fixture()
def settings() -> Settings:
    """Create test settings with valid defaults."""
    env = {
        "SERVICENOW_INSTANCE_URL": "https://test.service-now.com",
        "SERVICENOW_USERNAME": "admin",
        "SERVICENOW_PASSWORD": "s3cret",
        "SERVICENOW_ENV": "dev",
        "MCP_TOOL_PACKAGE": "full",
    }
    with patch.dict("os.environ", env, clear=True):
        return Settings(_env_file=None)


@pytest.fixture()
def prod_settings() -> Settings:
    """Create test settings for production environment."""
    env = {
        "SERVICENOW_INSTANCE_URL": "https://prod.service-now.com",
        "SERVICENOW_USERNAME": "admin",
        "SERVICENOW_PASSWORD": "s3cret",
        "SERVICENOW_ENV": "prod",
        "MCP_TOOL_PACKAGE": "full",
    }
    with patch.dict("os.environ", env, clear=True):
        return Settings(_env_file=None)


@pytest.fixture()
def prod_auth_provider(prod_settings: Settings) -> BasicAuthProvider:
    """Create a BasicAuthProvider from production test settings."""
    return BasicAuthProvider(prod_settings)
