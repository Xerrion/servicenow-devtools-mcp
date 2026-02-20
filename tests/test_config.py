"""Tests for configuration module."""

import pytest
from unittest.mock import patch


class TestSettings:
    """Test ServiceNow MCP settings loading and validation."""

    def _make_env(self, **overrides):
        """Create a minimal valid environment dict."""
        base = {
            "SERVICENOW_INSTANCE_URL": "https://test.service-now.com",
            "SERVICENOW_USERNAME": "admin",
            "SERVICENOW_PASSWORD": "password123",
        }
        base.update(overrides)
        return base

    def test_load_valid_config(self):
        """Settings loads correctly from valid environment variables."""
        from servicenow_mcp.config import Settings

        env = self._make_env()
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.servicenow_instance_url == "https://test.service-now.com"
        assert settings.servicenow_username == "admin"
        assert settings.servicenow_password == "password123"

    def test_missing_instance_url_raises(self):
        """Missing SERVICENOW_INSTANCE_URL raises validation error."""
        from servicenow_mcp.config import Settings

        env = self._make_env()
        del env["SERVICENOW_INSTANCE_URL"]
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(Exception):
                Settings(_env_file=None)

    def test_missing_username_raises(self):
        """Missing SERVICENOW_USERNAME raises validation error."""
        from servicenow_mcp.config import Settings

        env = self._make_env()
        del env["SERVICENOW_USERNAME"]
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(Exception):
                Settings(_env_file=None)

    def test_missing_password_raises(self):
        """Missing SERVICENOW_PASSWORD raises validation error."""
        from servicenow_mcp.config import Settings

        env = self._make_env()
        del env["SERVICENOW_PASSWORD"]
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(Exception):
                Settings(_env_file=None)

    def test_default_mcp_tool_package(self):
        """MCP_TOOL_PACKAGE defaults to 'dev_debug'."""
        from servicenow_mcp.config import Settings

        env = self._make_env()
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.mcp_tool_package == "dev_debug"

    def test_custom_mcp_tool_package(self):
        """MCP_TOOL_PACKAGE can be overridden."""
        from servicenow_mcp.config import Settings

        env = self._make_env(MCP_TOOL_PACKAGE="full")
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.mcp_tool_package == "full"

    def test_default_env(self):
        """SERVICENOW_ENV defaults to 'dev'."""
        from servicenow_mcp.config import Settings

        env = self._make_env()
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.servicenow_env == "dev"

    def test_default_max_row_limit(self):
        """MAX_ROW_LIMIT defaults to 100."""
        from servicenow_mcp.config import Settings

        env = self._make_env()
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.max_row_limit == 100

    def test_custom_max_row_limit(self):
        """MAX_ROW_LIMIT can be overridden."""
        from servicenow_mcp.config import Settings

        env = self._make_env(MAX_ROW_LIMIT="50")
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.max_row_limit == 50

    def test_large_table_names_default(self):
        """LARGE_TABLE_NAMES_CSV has sensible defaults."""
        from servicenow_mcp.config import Settings

        env = self._make_env()
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert "syslog" in settings.large_table_names
        assert "sys_audit" in settings.large_table_names

    def test_large_table_names_from_csv(self):
        """LARGE_TABLE_NAMES_CSV parses comma-separated string."""
        from servicenow_mcp.config import Settings

        env = self._make_env(LARGE_TABLE_NAMES_CSV="table_a,table_b,table_c")
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.large_table_names == ["table_a", "table_b", "table_c"]

    def test_instance_url_trailing_slash_stripped(self):
        """Trailing slash is stripped from instance URL."""
        from servicenow_mcp.config import Settings

        env = self._make_env(SERVICENOW_INSTANCE_URL="https://test.service-now.com/")
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.servicenow_instance_url == "https://test.service-now.com"

    def test_is_production_true(self):
        """is_production returns True when env is 'prod'."""
        from servicenow_mcp.config import Settings

        env = self._make_env(SERVICENOW_ENV="prod")
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.is_production is True

    def test_is_production_false(self):
        """is_production returns False when env is not 'prod'."""
        from servicenow_mcp.config import Settings

        env = self._make_env(SERVICENOW_ENV="dev")
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.is_production is False

    def test_allow_writes_in_prod_default_false(self):
        """ALLOW_WRITES_IN_PROD defaults to False."""
        from servicenow_mcp.config import Settings

        env = self._make_env()
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.allow_writes_in_prod is False

    def test_allow_writes_in_prod_can_be_enabled(self):
        """ALLOW_WRITES_IN_PROD can be set to True via environment variable."""
        from servicenow_mcp.config import Settings

        env = self._make_env(ALLOW_WRITES_IN_PROD="true")
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)

        assert settings.allow_writes_in_prod is True
