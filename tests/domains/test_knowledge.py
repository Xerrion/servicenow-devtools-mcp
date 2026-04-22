"""Tests for Knowledge Management domain tools."""

from typing import Any

import pytest
import respx
from httpx import Response

from servicenow_mcp.auth import BasicAuthProvider
from servicenow_mcp.config import Settings
from tests.helpers import decode_response, get_tool_functions


BASE_URL = "https://test.service-now.com"


def _register_and_get_tools(settings: Settings, auth_provider: BasicAuthProvider) -> dict[str, Any]:
    """Helper to register knowledge tools and extract callables."""
    from mcp.server.fastmcp import FastMCP

    from servicenow_mcp.choices import ChoiceRegistry
    from servicenow_mcp.tools.domains.knowledge import register_tools

    mcp = FastMCP("test")
    choices = ChoiceRegistry(settings, auth_provider)
    choices._fetched = True
    choices._cache = {k: dict(v) for k, v in ChoiceRegistry._DEFAULTS.items()}
    register_tools(mcp, settings, auth_provider, choices=choices)
    return get_tool_functions(mcp)


class TestKnowledgeSearch:
    """Tests for knowledge_search tool."""

    @pytest.mark.asyncio()
    @respx.mock
    async def test_search_default_published(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should search published articles by default."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                200,
                json={
                    "result": [
                        {
                            "sys_id": "7c619f62967fb08716b0990029693c5f",
                            "number": "KB0010001",
                            "short_description": "How to reset password",
                        },
                        {
                            "sys_id": "b558b88d797966be4a15e865ac316489",
                            "number": "KB0010002",
                            "short_description": "Password policy guide",
                        },
                    ]
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_search"](query="password")
        data = decode_response(result)

        assert data["status"] == "success"
        assert len(data["data"]) == 2
        request = respx.calls.last.request
        assert "short_descriptionLIKEpassword" in str(request.url)
        assert "textLIKEpassword" in str(request.url)
        assert "workflow_state%3Dpublished" in str(request.url)

    @pytest.mark.asyncio()
    @respx.mock
    async def test_search_custom_workflow_state(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should filter by custom workflow_state."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(return_value=Response(200, json={"result": []}))

        tools = _register_and_get_tools(settings, auth_provider)
        await tools["knowledge_search"](query="test", workflow_state="draft")

        request = respx.calls.last.request
        assert "workflow_state%3Ddraft" in str(request.url)

    @pytest.mark.asyncio()
    @respx.mock
    async def test_search_custom_limit(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should respect custom limit parameter."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(return_value=Response(200, json={"result": []}))

        tools = _register_and_get_tools(settings, auth_provider)
        await tools["knowledge_search"](query="test", limit=50)

        request = respx.calls.last.request
        assert "sysparm_limit=50" in str(request.url)


class TestKnowledgeGet:
    """Tests for knowledge_get tool."""

    @pytest.mark.asyncio()
    @respx.mock
    async def test_get_by_kb_number(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should fetch knowledge article by KB number."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                200,
                json={
                    "result": [
                        {
                            "sys_id": "6130004ffc6243feb8a9d8cec33c263b",
                            "number": "KB0010001",
                            "short_description": "Test article",
                        }
                    ]
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_get"](number_or_sys_id="KB0010001")
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["number"] == "KB0010001"
        request = respx.calls.last.request
        assert "number%3DKB0010001" in str(request.url)

    @pytest.mark.asyncio()
    @respx.mock
    async def test_get_by_sys_id(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should fetch knowledge article by sys_id if 32-char hex."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            side_effect=[
                Response(200, json={"result": []}),  # First query by number fails
                Response(
                    200,
                    json={
                        "result": [
                            {
                                "sys_id": "abc123def456abc123def456abc12345",
                                "number": "KB0010001",
                            }
                        ]
                    },
                ),  # Second query by sys_id succeeds
            ]
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_get"](number_or_sys_id="abc123def456abc123def456abc12345")
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["number"] == "KB0010001"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_get_not_found(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should return error when knowledge article not found."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            side_effect=[
                Response(200, json={"result": []}),  # Query by number
                Response(200, json={"result": []}),  # Query by sys_id
            ]
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_get"](number_or_sys_id="abc123def456abc123def456abc12345")
        data = decode_response(result)

        assert data["status"] == "error"
        assert "not found" in data["error"]["message"].lower()


class TestKnowledgeCreate:
    """Tests for knowledge_create tool."""

    @pytest.mark.asyncio()
    @respx.mock
    async def test_create_minimal(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should create knowledge article with minimal required fields."""
        respx.post(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                201,
                json={
                    "result": {
                        "sys_id": "kb_new",
                        "number": "KB0010003",
                        "short_description": "New article",
                        "text": "Article content",
                        "workflow_state": "draft",
                    }
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_create"](short_description="New article", text="Article content")
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["number"] == "KB0010003"
        assert data["data"]["workflow_state"] == "draft"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_create_missing_short_description(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should return error if short_description is empty."""
        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_create"](short_description="", text="Article content")
        data = decode_response(result)

        assert data["status"] == "error"
        assert "short_description" in data["error"]["message"].lower()

    @pytest.mark.asyncio()
    @respx.mock
    async def test_create_missing_text(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should return error if text is empty."""
        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_create"](short_description="New article", text="")
        data = decode_response(result)

        assert data["status"] == "error"
        assert "text" in data["error"]["message"].lower()

    @pytest.mark.asyncio()
    @respx.mock
    async def test_create_with_kb_knowledge_base_and_category(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        """Should include kb_knowledge_base and kb_category in create data when provided."""
        respx.post(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                201,
                json={
                    "result": {
                        "sys_id": "kb_new",
                        "number": "KB0010004",
                        "short_description": "New article",
                        "text": "Content",
                        "workflow_state": "draft",
                        "kb_knowledge_base": "84e801a553d572fa894b3d74e1a0f240",
                        "kb_category": "9ac848b24a0fbf6b8156d31c0431deea",
                    }
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_create"](
            short_description="New article",
            text="Content",
            kb_knowledge_base="84e801a553d572fa894b3d74e1a0f240",
            kb_category="9ac848b24a0fbf6b8156d31c0431deea",
        )
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["kb_knowledge_base"] == "84e801a553d572fa894b3d74e1a0f240"
        assert data["data"]["kb_category"] == "9ac848b24a0fbf6b8156d31c0431deea"

        # Verify the POST body included both optional fields
        import json

        request_body = json.loads(respx.calls.last.request.content)
        assert request_body["kb_knowledge_base"] == "84e801a553d572fa894b3d74e1a0f240"
        assert request_body["kb_category"] == "9ac848b24a0fbf6b8156d31c0431deea"

    @pytest.mark.asyncio()
    async def test_create_production_blocked(
        self, prod_settings: Settings, prod_auth_provider: BasicAuthProvider
    ) -> None:
        """Should block write in production environment."""
        tools = _register_and_get_tools(prod_settings, prod_auth_provider)
        result = await tools["knowledge_create"](short_description="Test", text="Content")
        data = decode_response(result)

        assert data["status"] == "error"
        assert "production" in data["error"]["message"].lower()


class TestKnowledgeUpdate:
    """Tests for knowledge_update tool."""

    @pytest.mark.asyncio()
    @respx.mock
    async def test_update_by_number(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should update knowledge article by KB number."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                200,
                json={"result": [{"sys_id": "6130004ffc6243feb8a9d8cec33c263b", "number": "KB0010001"}]},
            )
        )
        respx.patch(f"{BASE_URL}/api/now/table/kb_knowledge/6130004ffc6243feb8a9d8cec33c263b").mock(
            return_value=Response(
                200,
                json={
                    "result": {
                        "sys_id": "6130004ffc6243feb8a9d8cec33c263b",
                        "number": "KB0010001",
                        "short_description": "Updated title",
                    }
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_update"](number_or_sys_id="KB0010001", short_description="Updated title")
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["short_description"] == "Updated title"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_update_by_sys_id(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should update knowledge article by sys_id."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            side_effect=[
                Response(200, json={"result": []}),  # Query by number fails
                Response(
                    200,
                    json={
                        "result": [
                            {
                                "sys_id": "abc123def456abc123def456abc12345",
                                "number": "KB0010001",
                            }
                        ]
                    },
                ),
            ]
        )
        respx.patch(f"{BASE_URL}/api/now/table/kb_knowledge/abc123def456abc123def456abc12345").mock(
            return_value=Response(
                200,
                json={
                    "result": {
                        "sys_id": "abc123def456abc123def456abc12345",
                        "number": "KB0010001",
                        "text": "Updated content",
                    }
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_update"](
            number_or_sys_id="abc123def456abc123def456abc12345",
            text="Updated content",
        )
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["text"] == "Updated content"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_update_not_found(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should return error if article not found."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            side_effect=[
                Response(200, json={"result": []}),
                Response(200, json={"result": []}),
            ]
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_update"](number_or_sys_id="KB9999999", short_description="Test")
        data = decode_response(result)

        assert data["status"] == "error"
        assert "not found" in data["error"]["message"].lower()

    @pytest.mark.asyncio()
    @respx.mock
    async def test_update_no_changes_provided(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should return error when no update fields are provided."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                200,
                json={"result": [{"sys_id": "6130004ffc6243feb8a9d8cec33c263b", "number": "KB0010001"}]},
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_update"](number_or_sys_id="KB0010001")
        data = decode_response(result)

        assert data["status"] == "error"
        assert "no fields" in data["error"]["message"].lower()

    @pytest.mark.asyncio()
    async def test_update_production_blocked(
        self, prod_settings: Settings, prod_auth_provider: BasicAuthProvider
    ) -> None:
        """Should block write in production environment."""
        tools = _register_and_get_tools(prod_settings, prod_auth_provider)
        result = await tools["knowledge_update"](number_or_sys_id="KB0010001", short_description="Updated")
        data = decode_response(result)

        assert data["status"] == "error"
        assert "production" in data["error"]["message"].lower()

    @pytest.mark.asyncio()
    @respx.mock
    async def test_update_with_workflow_state_kb_base_and_category(
        self, settings: Settings, auth_provider: BasicAuthProvider
    ) -> None:
        """Should include workflow_state, kb_knowledge_base, and kb_category in update."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                200,
                json={"result": [{"sys_id": "6130004ffc6243feb8a9d8cec33c263b", "number": "KB0010001"}]},
            )
        )
        respx.patch(f"{BASE_URL}/api/now/table/kb_knowledge/6130004ffc6243feb8a9d8cec33c263b").mock(
            return_value=Response(
                200,
                json={
                    "result": {
                        "sys_id": "6130004ffc6243feb8a9d8cec33c263b",
                        "number": "KB0010001",
                        "workflow_state": "published",
                        "kb_knowledge_base": "587292a058efc3bab6512dd94cecb291",
                        "kb_category": "f424021bde94bfa660418bee7c99fdeb",
                    }
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_update"](
            number_or_sys_id="KB0010001",
            workflow_state="published",
            kb_knowledge_base="587292a058efc3bab6512dd94cecb291",
            kb_category="f424021bde94bfa660418bee7c99fdeb",
        )
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["workflow_state"] == "published"
        assert data["data"]["kb_knowledge_base"] == "587292a058efc3bab6512dd94cecb291"
        assert data["data"]["kb_category"] == "f424021bde94bfa660418bee7c99fdeb"

        # Verify the PATCH body included all three optional fields
        import json

        request_body = json.loads(respx.calls.last.request.content)
        assert request_body["workflow_state"] == "published"
        assert request_body["kb_knowledge_base"] == "587292a058efc3bab6512dd94cecb291"
        assert request_body["kb_category"] == "f424021bde94bfa660418bee7c99fdeb"


class TestKnowledgeFeedback:
    """Tests for knowledge_feedback tool."""

    @pytest.mark.asyncio()
    @respx.mock
    async def test_feedback_with_rating(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should submit rating feedback to kb_feedback table."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                200,
                json={"result": [{"sys_id": "6130004ffc6243feb8a9d8cec33c263b", "number": "KB0010001"}]},
            )
        )
        respx.post(f"{BASE_URL}/api/now/table/kb_feedback").mock(
            return_value=Response(
                201,
                json={
                    "result": {
                        "sys_id": "1fc91770103833a7b6221b1a79c3e4c9",
                        "article": "6130004ffc6243feb8a9d8cec33c263b",
                        "rating": "5",
                    }
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_feedback"](number_or_sys_id="KB0010001", rating=5)
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["article"] == "6130004ffc6243feb8a9d8cec33c263b"
        assert data["data"]["rating"] == "5"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_feedback_with_comment(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should submit comment feedback to kb_feedback table."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                200,
                json={"result": [{"sys_id": "6130004ffc6243feb8a9d8cec33c263b", "number": "KB0010001"}]},
            )
        )
        respx.post(f"{BASE_URL}/api/now/table/kb_feedback").mock(
            return_value=Response(
                201,
                json={
                    "result": {
                        "sys_id": "a7a140263c8ad16a53bb98c1359610a1",
                        "article": "6130004ffc6243feb8a9d8cec33c263b",
                        "comments": "Very helpful",
                    }
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_feedback"](number_or_sys_id="KB0010001", comment="Very helpful")
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["article"] == "6130004ffc6243feb8a9d8cec33c263b"
        assert data["data"]["comments"] == "Very helpful"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_feedback_both_rating_and_comment(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should submit both rating and comment to kb_feedback."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            return_value=Response(
                200,
                json={"result": [{"sys_id": "6130004ffc6243feb8a9d8cec33c263b", "number": "KB0010001"}]},
            )
        )
        respx.post(f"{BASE_URL}/api/now/table/kb_feedback").mock(
            return_value=Response(
                201,
                json={
                    "result": {
                        "sys_id": "1c19684601aea2164d28b87d816c0144",
                        "article": "6130004ffc6243feb8a9d8cec33c263b",
                        "rating": "4",
                        "comments": "Good article",
                    }
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_feedback"](number_or_sys_id="KB0010001", rating=4, comment="Good article")
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["rating"] == "4"
        assert data["data"]["comments"] == "Good article"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_feedback_missing_both(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should return error if neither rating nor comment provided."""
        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_feedback"](number_or_sys_id="KB0010001")
        data = decode_response(result)

        assert data["status"] == "error"
        assert "rating or comment" in data["error"]["message"].lower()

    @pytest.mark.asyncio()
    @respx.mock
    async def test_feedback_invalid_rating_low(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should return error if rating below 1."""
        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_feedback"](number_or_sys_id="KB0010001", rating=0)
        data = decode_response(result)

        assert data["status"] == "error"
        assert "between 1 and 5" in data["error"]["message"].lower()

    @pytest.mark.asyncio()
    @respx.mock
    async def test_feedback_invalid_rating_high(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should return error if rating above 5."""
        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_feedback"](number_or_sys_id="KB0010001", rating=6)
        data = decode_response(result)

        assert data["status"] == "error"
        assert "between 1 and 5" in data["error"]["message"].lower()

    @pytest.mark.asyncio()
    async def test_feedback_production_blocked(
        self, prod_settings: Settings, prod_auth_provider: BasicAuthProvider
    ) -> None:
        """Should block write in production environment."""
        tools = _register_and_get_tools(prod_settings, prod_auth_provider)
        result = await tools["knowledge_feedback"](number_or_sys_id="KB0010001", rating=5)
        data = decode_response(result)

        assert data["status"] == "error"
        assert "production" in data["error"]["message"].lower()

    @pytest.mark.asyncio()
    @respx.mock
    async def test_feedback_lookup_by_sys_id(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should fall back to sys_id lookup when number lookup returns nothing."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            side_effect=[
                Response(200, json={"result": []}),  # Query by number fails
                Response(
                    200,
                    json={
                        "result": [
                            {
                                "sys_id": "abc123def456abc123def456abc12345",
                                "number": "KB0010001",
                            }
                        ]
                    },
                ),  # Query by sys_id succeeds
            ]
        )
        respx.post(f"{BASE_URL}/api/now/table/kb_feedback").mock(
            return_value=Response(
                201,
                json={
                    "result": {
                        "sys_id": "1554b2d3b27083dd0079295310f73361",
                        "article": "abc123def456abc123def456abc12345",
                        "rating": "3",
                    }
                },
            )
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_feedback"](number_or_sys_id="abc123def456abc123def456abc12345", rating=3)
        data = decode_response(result)

        assert data["status"] == "success"
        assert data["data"]["article"] == "abc123def456abc123def456abc12345"

    @pytest.mark.asyncio()
    @respx.mock
    async def test_feedback_article_not_found(self, settings: Settings, auth_provider: BasicAuthProvider) -> None:
        """Should return error when article not found for feedback."""
        respx.get(f"{BASE_URL}/api/now/table/kb_knowledge").mock(
            side_effect=[
                Response(200, json={"result": []}),  # Query by number fails
                Response(200, json={"result": []}),  # Query by sys_id also fails
            ]
        )

        tools = _register_and_get_tools(settings, auth_provider)
        result = await tools["knowledge_feedback"](number_or_sys_id="abc123def456abc123def456abc12345", rating=4)
        data = decode_response(result)

        assert data["status"] == "error"
        assert "not found" in data["error"]["message"].lower()
