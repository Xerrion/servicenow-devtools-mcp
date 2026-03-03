"""Tests for tool package system."""

import pytest


class TestPackageRegistry:
    """Test package registry and loading."""

    def test_registry_contains_full(self):
        """full package is defined in the registry."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert "full" in PACKAGE_REGISTRY

    def test_registry_contains_none(self):
        """'none' package is defined in the registry."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert "none" in PACKAGE_REGISTRY

    def test_registry_contains_introspection_only(self):
        """introspection_only package is defined."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert "introspection_only" in PACKAGE_REGISTRY

    def test_full_includes_introspection(self):
        """full package includes introspection tools."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert "introspection" in PACKAGE_REGISTRY["full"]

    def test_full_includes_metadata(self):
        """full package includes metadata tools."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert "metadata" in PACKAGE_REGISTRY["full"]

    def test_full_includes_relationships(self):
        """full package includes relationship tools."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert "relationships" in PACKAGE_REGISTRY["full"]

    def test_none_package_is_empty(self):
        """'none' package has no tool groups."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert PACKAGE_REGISTRY["none"] == []

    def test_get_package_valid(self):
        """get_package returns tool groups for a valid package."""
        from servicenow_mcp.packages import get_package

        groups = get_package("full")
        assert isinstance(groups, list)
        assert len(groups) > 0

    def test_get_package_invalid_raises(self):
        """get_package raises ValueError for unknown package."""
        from servicenow_mcp.packages import get_package

        with pytest.raises(ValueError, match="Unknown"):
            get_package("nonexistent_package")

    def test_full_includes_changes(self):
        """full package includes change intelligence tools."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert "changes" in PACKAGE_REGISTRY["full"]

    def test_full_includes_debug(self):
        """full package includes debug/trace tools."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert "debug" in PACKAGE_REGISTRY["full"]

    def test_list_packages_returns_all(self):
        """list_packages returns all registered packages."""
        from servicenow_mcp.packages import list_packages

        packages = list_packages()
        assert "none" in packages
        assert "full" in packages
        assert "introspection_only" in packages

    def test_dev_debug_not_in_registry(self):
        """dev_debug package has been removed from the registry."""
        from servicenow_mcp.packages import PACKAGE_REGISTRY

        assert "dev_debug" not in PACKAGE_REGISTRY

    def test_get_package_returns_copy(self):
        """get_package returns a copy — mutating it does not affect the registry."""
        from servicenow_mcp.packages import get_package

        groups = get_package("full")
        groups.append("should_not_persist")
        fresh = get_package("full")
        assert "should_not_persist" not in fresh

    def test_list_packages_returns_copies(self):
        """list_packages returns deep copies of value lists."""
        from servicenow_mcp.packages import list_packages

        packages = list_packages()
        packages["full"].append("should_not_persist")
        fresh = list_packages()
        assert "should_not_persist" not in fresh["full"]

    def test_get_package_itil(self):
        """get_package returns correct groups for itil preset."""
        from servicenow_mcp.packages import get_package

        groups = get_package("itil")
        expected = ["introspection", "relationships", "metadata", "changes", "debug", "documentation", "utility"]
        assert groups == expected
        assert len(groups) == 7

    def test_get_package_developer(self):
        """get_package returns correct groups for developer preset."""
        from servicenow_mcp.packages import get_package

        groups = get_package("developer")
        expected = [
            "introspection",
            "relationships",
            "metadata",
            "changes",
            "debug",
            "developer",
            "dev_utils",
            "investigations",
            "documentation",
            "utility",
        ]
        assert groups == expected
        assert len(groups) == 10

    def test_get_package_readonly(self):
        """get_package returns correct groups for readonly preset."""
        from servicenow_mcp.packages import get_package

        groups = get_package("readonly")
        expected = [
            "introspection",
            "relationships",
            "metadata",
            "changes",
            "debug",
            "investigations",
            "documentation",
            "utility",
        ]
        assert groups == expected
        assert len(groups) == 8

    def test_get_package_analyst(self):
        """get_package returns correct groups for analyst preset."""
        from servicenow_mcp.packages import get_package

        groups = get_package("analyst")
        expected = ["introspection", "relationships", "metadata", "investigations", "documentation", "utility"]
        assert groups == expected
        assert len(groups) == 6

    def test_list_packages_includes_itil(self):
        """list_packages includes itil preset."""
        from servicenow_mcp.packages import list_packages

        packages = list_packages()
        assert "itil" in packages

    def test_list_packages_includes_developer(self):
        """list_packages includes developer preset."""
        from servicenow_mcp.packages import list_packages

        packages = list_packages()
        assert "developer" in packages

    def test_list_packages_includes_readonly(self):
        """list_packages includes readonly preset."""
        from servicenow_mcp.packages import list_packages

        packages = list_packages()
        assert "readonly" in packages

    def test_list_packages_includes_analyst(self):
        """list_packages includes analyst preset."""
        from servicenow_mcp.packages import list_packages

        packages = list_packages()
        assert "analyst" in packages

    def test_full_package_unchanged(self):
        """full package still returns all groups unchanged."""
        from servicenow_mcp.packages import get_package

        groups = get_package("full")
        assert "introspection" in groups
        assert "relationships" in groups
        assert "metadata" in groups
        assert "changes" in groups
        assert "debug" in groups
        assert "developer" in groups
        assert "dev_utils" in groups
        assert "investigations" in groups
        assert "documentation" in groups
        assert "utility" in groups
        assert len(groups) == 11


class TestCommaSeparatedGroups:
    """Test comma-separated group syntax for custom tool packages."""

    def test_comma_separated_valid_groups(self):
        """get_package accepts comma-separated group names and returns list."""
        from servicenow_mcp.packages import get_package

        groups = get_package("introspection,debug,utility")
        assert groups == ["introspection", "debug", "utility"]

    def test_comma_separated_with_spaces(self):
        """get_package strips whitespace from comma-separated groups."""
        from servicenow_mcp.packages import get_package

        groups = get_package("introspection, debug, utility")
        assert groups == ["introspection", "debug", "utility"]

    def test_comma_separated_deduplicates(self):
        """get_package deduplicates repeated group names."""
        from servicenow_mcp.packages import get_package

        groups = get_package("debug,debug,debug")
        assert groups == ["debug"]

    def test_comma_separated_mixed_duplicates(self):
        """get_package deduplicates mixed repeated groups."""
        from servicenow_mcp.packages import get_package

        groups = get_package("introspection,debug,introspection,utility,debug")
        assert groups == ["introspection", "debug", "utility"]

    def test_comma_separated_invalid_group_raises(self):
        """get_package raises ValueError for unknown group names."""
        from servicenow_mcp.packages import get_package

        with pytest.raises(ValueError, match="Unknown group"):
            get_package("introspection,invalid_group")

    def test_comma_separated_multiple_invalid_groups_raises(self):
        """get_package mentions all invalid group names in error."""
        from servicenow_mcp.packages import get_package

        with pytest.raises(ValueError, match="invalid_group"):
            get_package("introspection,invalid_group,debug,fake_group")

    def test_comma_separated_empty_groups_raises(self):
        """get_package raises ValueError for empty group names."""
        from servicenow_mcp.packages import get_package

        with pytest.raises(ValueError, match="empty"):
            get_package(",,,")

    def test_comma_separated_trailing_comma_raises(self):
        """get_package raises ValueError for trailing commas."""
        from servicenow_mcp.packages import get_package

        with pytest.raises(ValueError, match="empty"):
            get_package("debug,introspection,")

    def test_comma_separated_leading_comma_raises(self):
        """get_package raises ValueError for leading commas."""
        from servicenow_mcp.packages import get_package

        with pytest.raises(ValueError, match="empty"):
            get_package(",debug,introspection")

    def test_preset_name_still_works(self):
        """get_package still returns preset when name is in PACKAGE_REGISTRY."""
        from servicenow_mcp.packages import get_package

        groups = get_package("itil")
        assert isinstance(groups, list)
        assert "introspection" in groups

    def test_comma_separated_cannot_use_preset_names(self):
        """get_package rejects preset names in comma syntax."""
        from servicenow_mcp.packages import get_package

        with pytest.raises(ValueError, match="Unknown group"):
            get_package("introspection,itil,debug")

    def test_comma_separated_single_group(self):
        """get_package accepts single group name."""
        from servicenow_mcp.packages import get_package

        groups = get_package("debug")
        assert groups == ["debug"]

    def test_comma_separated_preserves_order(self):
        """get_package preserves order while deduplicating."""
        from servicenow_mcp.packages import get_package

        groups = get_package("utility,debug,introspection,debug")
        assert groups == ["utility", "debug", "introspection"]
