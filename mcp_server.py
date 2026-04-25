from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from prefab_ui.app import PrefabApp

from nasa_client import NASAClient

load_dotenv()

mcp = FastMCP("CosmoLog")

API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")
_nasa_client = NASAClient(api_key=API_KEY)


@mcp.tool()
def fetch_space_data(
    date: str | None = None,
    rover: str = "curiosity",
    sol: int | None = None,
    photo_count: int = 3,
    neo_days: int = 7,
) -> dict[str, Any]:
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


@mcp.tool()
def manage_space_journal(
    operation: str,
    entry_id: str | None = None,
    payload: dict[str, Any] | None = None,
    tag_filter: str | None = None,
) -> dict[str, Any]:
    """Manage the local space journal (CRUD operations).

    Args:
        operation: One of 'create', 'read', 'update', or 'delete'.
        entry_id: Required for 'update' and 'delete' operations.
        payload: Required for 'create' and 'update'. Entry data dict.
        tag_filter: Optional tag to filter entries during 'read'.
    """
    from journal import create_entry, delete_entry, read_entries, update_entry

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


@mcp.tool(app=True)
def show_space_dashboard(
    space_data: dict[str, Any] | None = None,
    journal_entries: list[dict[str, Any]] | None = None,
    tag_filter: str | None = None,
) -> PrefabApp:
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


def main() -> None:
    mcp.run(transport="http")


if __name__ == "__main__":
    main()
