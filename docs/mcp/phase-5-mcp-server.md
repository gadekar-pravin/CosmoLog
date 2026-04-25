# Phase 5: MCP Server Integration

## Goal

Wire everything together into the FastMCP server with 3 registered tools. This is the final integration phase that makes CosmoLog a complete, runnable MCP application.

## What This Phase Delivers

- `mcp_server.py` -- FastMCP entrypoint with 3 tool registrations and `main()` entrypoint
- `tests/test_mcp_server.py` -- 3 integration tests verifying tool registration and CRUD cycle

## Prerequisites

- Phase 1 complete (`models.py`)
- Phase 2 complete (`journal.py`)
- Phase 3 complete (`nasa_client.py`)
- Phase 4 complete (`dashboard.py`)

## Acceptance Criteria

- [ ] MCP server has exactly 3 tools registered: `fetch_space_data`, `manage_space_journal`, `show_space_dashboard`
- [ ] `fetch_space_data` calls `NASAClient.fetch_all()` and returns `SpaceData` as a dict
- [ ] `manage_space_journal` dispatches to journal CRUD functions via `match` statement
- [ ] `show_space_dashboard` is marked `app=True` and returns a `PrefabApp`
- [ ] `_nasa_client` is module-level so cache persists across invocations
- [ ] `uv run pytest -v` shows all tests passing (~44 total)
- [ ] `uv run python mcp_server.py` starts the server without errors
- [ ] Satisfies functional spec sections 13.1, 13.2, 13.3, and 13.4

---

## Step 1: Create `mcp_server.py`

**Reference:** Technical Specification section 6.

### Server Setup

```python
import os

from dotenv import load_dotenv
from fastmcp import FastMCP

from nasa_client import NASAClient

load_dotenv()

mcp = FastMCP("CosmoLog")

API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")
_nasa_client = NASAClient(api_key=API_KEY)
```

**Key design:** `_nasa_client` is module-level so the in-memory cache persists across tool invocations within a session. This is critical for the `DEMO_KEY` rate limit (30 req/hr).

### Tool 1: `fetch_space_data`

```python
@mcp.tool()
def fetch_space_data(
    date: str | None = None,
    rover: str = "curiosity",
    sol: int | None = None,
    photo_count: int = 3,
    neo_days: int = 7,
) -> dict:
    """Fetch live NASA space data: APOD, Mars rover photos, and near-Earth objects.

    Args:
        date: Date for APOD lookup (YYYY-MM-DD). Defaults to today.
        rover: Mars rover name. Defaults to 'curiosity'.
        sol: Martian sol for rover photos. Defaults to latest available.
        photo_count: Number of rover photos to return. Defaults to 3.
        neo_days: Number of days ahead to check for NEOs. Defaults to 7.
    """
    result = _nasa_client.fetch_all(
        apod_date=date,
        rover=rover,
        sol=sol,
        photo_count=photo_count,
        neo_days=neo_days,
    )
    return result.model_dump()
```

**Returns:** A dict matching the `SpaceData` model shape. The agent receives structured data it can inspect and selectively save to the journal.

### Tool 2: `manage_space_journal`

```python
@mcp.tool()
def manage_space_journal(
    operation: str,
    entry_id: str | None = None,
    payload: dict | None = None,
    tag_filter: str | None = None,
) -> dict:
    """Manage the local space journal (CRUD operations).

    Args:
        operation: One of 'create', 'read', 'update', or 'delete'.
        entry_id: Required for 'update' and 'delete' operations.
        payload: Required for 'create' and 'update'. Entry data dict.
        tag_filter: Optional tag to filter entries during 'read'.
    """
    from journal import create_entry, read_entries, update_entry, delete_entry

    match operation:
        case "create":
            return create_entry(payload or {})
        case "read":
            return read_entries(tag_filter=tag_filter)
        case "update":
            if not entry_id:
                return {"status": "error", "message": "entry_id is required for update"}
            return update_entry(entry_id, payload or {})
        case "delete":
            if not entry_id:
                return {"status": "error", "message": "entry_id is required for delete"}
            return delete_entry(entry_id)
        case _:
            return {"status": "error", "message": f"Unknown operation: '{operation}'"}
```

**Notes:**
- `match operation:` uses Python 3.10+ structural pattern matching
- `entry_id` validation is done here (not in journal.py) for `update` and `delete`
- `payload or {}` ensures a dict is always passed to journal functions
- Lazy imports (`from journal import ...`) keep the import clean

### Tool 3: `show_space_dashboard`

```python
@mcp.tool(app=True)
def show_space_dashboard(
    space_data: dict | None = None,
    journal_entries: list[dict] | None = None,
    tag_filter: str | None = None,
) -> "PrefabApp":
    """Display the CosmoLog dashboard with NASA data and journal entries.

    Args:
        space_data: Data returned from fetch_space_data.
        journal_entries: Entries returned from manage_space_journal read operation.
        tag_filter: Active tag filter for journal entries.
    """
    from dashboard import build_dashboard

    return build_dashboard(
        space_data=space_data,
        journal_entries=journal_entries,
        tag_filter=tag_filter,
    )
```

**Key detail:** The `app=True` parameter marks this as a UI tool that returns a `PrefabApp` object. This is the Prefab convention for tools that render UI.

### Entrypoint

```python
def main():
    mcp.run(transport="http")

if __name__ == "__main__":
    main()
```

**Running:** `cd CosmoLog && uv sync && uv run python mcp_server.py`

---

## Step 2: Create `tests/test_mcp_server.py`

**Reference:** Technical Specification section 11.8.

```python
from mcp_server import mcp, manage_space_journal


def test_tools_registered():
    """Verify MCP server has exactly 3 tools registered."""
    # FastMCP stores tools internally -- check the tool manager
    # The exact API depends on the FastMCP version.
    # Common patterns:
    #   tools = mcp._tool_manager._tools  (dict)
    #   tools = await mcp.list_tools()     (async)
    #
    # Try the synchronous attribute first. If FastMCP's internal API
    # differs, adjust to match what's available.
    tools = mcp._tool_manager._tools
    assert len(tools) == 3


def test_tool_names():
    """Verify tool names match spec."""
    tools = mcp._tool_manager._tools
    tool_names = set(tools.keys())
    assert tool_names == {
        "fetch_space_data",
        "manage_space_journal",
        "show_space_dashboard",
    }


def test_journal_crud_cycle(tmp_path, monkeypatch):
    """End-to-end: create -> read -> update -> delete via manage_space_journal."""
    import journal

    monkeypatch.setattr(journal, "JOURNAL_PATH", tmp_path / "space_journal.json")

    # Create
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

    # Read
    result = manage_space_journal(operation="read")
    assert len(result["entries"]) == 1

    # Update
    result = manage_space_journal(
        operation="update",
        entry_id=entry_id,
        payload={"notes": "Updated note"},
    )
    assert result["status"] == "success"
    assert result["entry"]["notes"] == "Updated note"

    # Delete
    result = manage_space_journal(operation="delete", entry_id=entry_id)
    assert result["status"] == "success"
    assert result["deleted_id"] == entry_id

    # Verify empty
    result = manage_space_journal(operation="read")
    assert len(result["entries"]) == 0
```

### Test Summary

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_tools_registered` | Exactly 3 tools registered on the MCP server |
| 2 | `test_tool_names` | Tool names are `fetch_space_data`, `manage_space_journal`, `show_space_dashboard` |
| 3 | `test_journal_crud_cycle` | Full CRUD lifecycle through the MCP tool function |

### Implementation Note: Accessing Registered Tools

The `test_tools_registered` and `test_tool_names` tests need to inspect FastMCP's internal tool registry. The exact API depends on the installed FastMCP version. Common approaches:

```python
# Approach 1: Internal attribute (most common)
tools = mcp._tool_manager._tools

# Approach 2: If FastMCP exposes a public method
import asyncio
tools = asyncio.run(mcp.list_tools())

# Approach 3: Check if tools dict is directly accessible
tools = mcp.tools
```

Check the FastMCP source at implementation time and use whichever accessor works. The test assertions remain the same regardless of access pattern.

### Test Isolation Note

The `test_journal_crud_cycle` test uses `monkeypatch` to redirect `journal.JOURNAL_PATH` to a temp directory. This avoids writing to the real `space_journal.json` during tests. Note that `manage_space_journal` calls journal functions without `journal_path=` (it uses the default `JOURNAL_PATH`), so monkeypatching the module-level constant is the correct isolation approach for integration tests.

---

## Verification

### Automated Tests

```bash
cd CosmoLog
uv run pytest -v                    # all tests pass (~44 total)
uv run ruff check .                 # lint clean
uv run ruff format --check .        # format clean
```

Expected test count breakdown:
- `test_models.py`: 10 tests
- `test_journal.py`: 11 tests
- `test_nasa_client.py`: 13 tests
- `test_dashboard.py`: 7 tests
- `test_mcp_server.py`: 3 tests
- **Total: ~44 tests**

### Manual Server Test

```bash
uv run python mcp_server.py
# Server should start on default FastMCP HTTP transport
# Ctrl+C to stop
```

### End-to-End Demo

Connect an MCP-compatible client and run the demo prompt from functional specification section 5.1:

```
Fetch today's NASA APOD, 3 recent Curiosity rover photos, and upcoming near-Earth objects.
Save the APOD and rover photos into space_journal.json with the tag mars-week.
Then read the saved journal entries and display them in a Prefab dashboard with the APOD
hero image, rover photo grid, and a near-Earth asteroid table.
```

Expected agent behavior:
1. Calls `fetch_space_data` -> receives NASA data
2. Calls `manage_space_journal` (create APOD entry)
3. Calls `manage_space_journal` (create rover photo entries)
4. Calls `manage_space_journal` (read with tag_filter)
5. Calls `show_space_dashboard` -> renders dashboard

---

## Spec References

- Tech spec section 6: MCP Server
- Tech spec section 6.1: Server Setup
- Tech spec section 6.2: Tool 1 (fetch_space_data)
- Tech spec section 6.3: Tool 2 (manage_space_journal)
- Tech spec section 6.4: Tool 3 (show_space_dashboard)
- Tech spec section 6.5: Entrypoint
- Tech spec section 8: Sequence Diagrams
- Tech spec section 11.8: test_mcp_server.py test table
- Functional spec section 4.1: MCP Server Requirements
- Functional spec section 5.1: Primary Demo Flow
- Functional spec section 13: Acceptance Criteria (all sections)

---

## Commit

```
feat: wire MCP server with all three tools
```

---

## Final Project Structure

After all 5 phases, the project should have:

```
CosmoLog/
  pyproject.toml          # existed
  .env                    # Phase 1
  CLAUDE.md               # existed
  models.py               # Phase 1
  journal.py              # Phase 2
  nasa_client.py          # Phase 3
  dashboard.py            # Phase 4
  mcp_server.py           # Phase 5
  space_journal.json      # Created at runtime (gitignored)
  tests/
    __init__.py           # Phase 1
    conftest.py           # Phase 1
    test_models.py        # Phase 1
    test_journal.py       # Phase 2
    test_nasa_client.py   # Phase 3
    test_dashboard.py     # Phase 4
    test_mcp_server.py    # Phase 5
  docs/
    phase-1-models.md
    phase-2-journal.md
    phase-3-nasa-client.md
    phase-4-dashboard.md
    phase-5-mcp-server.md
```
