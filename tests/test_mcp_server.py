from __future__ import annotations

import pytest

from mcp_server import manage_space_journal, mcp


@pytest.mark.asyncio
async def test_tools_registered():
    """Verify MCP server has exactly 3 tools registered."""
    tools = await mcp.list_tools()

    assert len(tools) == 3


@pytest.mark.asyncio
async def test_tool_names():
    """Verify tool names match spec."""
    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}

    assert tool_names == {
        "fetch_space_data",
        "manage_space_journal",
        "show_space_dashboard",
    }


def test_journal_crud_cycle(tmp_path, monkeypatch):
    """End-to-end: create -> read -> update -> delete via manage_space_journal."""
    import journal

    monkeypatch.setattr(journal, "JOURNAL_PATH", tmp_path / "space_journal.json")

    result = manage_space_journal(
        operation="create",
        payload={
            "type": "apod",
            "title": "Test",
            "date": "2026-04-25",
            "tags": ["test"],
            "notes": "Test note",
        },
    )
    assert result["status"] == "success"
    entry_id = result["entry"]["id"]

    result = manage_space_journal(operation="read")
    assert len(result["entries"]) == 1

    result = manage_space_journal(
        operation="update",
        entry_id=entry_id,
        payload={"notes": "Updated note"},
    )
    assert result["status"] == "success"
    assert result["entry"]["notes"] == "Updated note"

    result = manage_space_journal(operation="delete", entry_id=entry_id)
    assert result["status"] == "success"
