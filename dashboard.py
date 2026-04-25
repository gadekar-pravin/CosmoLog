from __future__ import annotations

import logging
from typing import Any

from prefab_ui.actions import ShowToast
from prefab_ui.actions.mcp import CallTool, SendMessage
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    H2,
    H3,
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
    Column,
    Embed,
    Grid,
    Image,
    Link,
    Metric,
    Muted,
    Row,
    Separator,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
    Text,
)
from prefab_ui.rx import ERROR

logger = logging.getLogger(__name__)


def build_dashboard(
    space_data: dict[str, Any] | None = None,
    journal_entries: list[dict[str, Any]] | None = None,
    tag_filter: str | None = None,
) -> PrefabApp:
    """Build the CosmoLog Prefab dashboard from prepared data."""
    rover_count = len(space_data.get("rover_photos", [])) if space_data else 0
    neo_count = len(space_data.get("near_earth_objects", [])) if space_data else 0
    entry_count = len(journal_entries) if journal_entries else 0
    logger.info(
        "build_dashboard apod=%s rover_count=%d neo_count=%d entry_count=%d tag_filter=%s",
        bool(space_data and space_data.get("apod")),
        rover_count,
        neo_count,
        entry_count,
        tag_filter,
    )
    apod = space_data.get("apod") if space_data else None
    rover_photos = space_data.get("rover_photos", []) if space_data else []
    neos = space_data.get("near_earth_objects", []) if space_data else []
    entries = journal_entries or []

    hazardous_count = sum(1 for neo in neos if neo.get("is_potentially_hazardous"))
    closest_neo_date = "N/A"
    if neos:
        closest = min(neos, key=lambda neo: neo.get("miss_distance_km", float("inf")))
        closest_neo_date = closest.get("close_approach_date", "N/A")

    with Column(gap=6, css_class="p-6") as view:
        _build_header(tag_filter)
        _build_stat_tiles(entries, rover_photos, neos, hazardous_count, closest_neo_date)

        with Grid(columns=[2, 1], gap=6):
            with Column(gap=6):
                _build_apod_section(apod)
                _build_rover_section(rover_photos)

            _build_journal_section(entries)

        _build_neo_section(neos)
        _build_refresh_section()

    logger.debug("build_dashboard_done")
    return PrefabApp(
        title="CosmoLog",
        view=view,
        state={"tag_filter": tag_filter or ""},
    )


def _build_header(tag_filter: str | None) -> None:
    with Row(gap=3, align="center"):
        H2("CosmoLog")
        Badge("Live", variant="success")
        if tag_filter:
            Badge(f"Filter: {tag_filter}", variant="secondary")


def _build_stat_tiles(
    entries: list[dict[str, Any]],
    rover_photos: list[dict[str, Any]],
    neos: list[dict[str, Any]],
    hazardous_count: int,
    closest_neo_date: str,
) -> None:
    with Grid(columns={"default": 2, "md": 5}, gap=4):
        with Card():
            Metric(label="Journal Entries", value=len(entries))
        with Card():
            Metric(label="Rover Photos", value=len(rover_photos))
        with Card():
            Metric(label="Near-Earth Objects", value=len(neos))
        with Card():
            Metric(
                label="Hazardous",
                value=hazardous_count,
                trend="up" if hazardous_count > 0 else "neutral",
                trend_sentiment="negative" if hazardous_count > 0 else "neutral",
            )
        with Card():
            Metric(label="Closest NEO", value=closest_neo_date)


def _build_apod_section(apod: dict[str, Any] | None) -> None:
    if not apod:
        with Card():
            with CardContent():
                Muted("No APOD data available. Fetch data to see today's astronomy picture.")
        return

    title = apod.get("title", "Untitled APOD")
    url = apod.get("url", "")

    with Card():
        with CardHeader():
            CardTitle(title)
            CardDescription(f"APOD -- {apod.get('date', 'N/A')}")
        with CardContent():
            if apod.get("media_type") == "video":
                Embed(
                    url=url,
                    width="100%",
                    height="400px",
                    allow="fullscreen; autoplay",
                )
            else:
                Image(
                    src=url,
                    alt=title,
                    width="100%",
                )
            Text(apod.get("explanation", ""), css_class="mt-4 text-sm")
        with CardFooter():
            if apod.get("copyright"):
                Muted(f"Copyright: {apod['copyright']}")
            if url:
                Link("View on NASA", href=url, css_class="text-sm")


def _build_rover_section(rover_photos: list[dict[str, Any]]) -> None:
    H3("Mars Rover Photos")
    if not rover_photos:
        Muted("No rover photos available.")
        return

    with Grid(columns={"default": 1, "sm": 3}, gap=4):
        for photo in rover_photos:
            with Card():
                Image(
                    src=photo.get("img_src", ""),
                    alt=f"{photo.get('rover', 'Rover')} - {photo.get('camera', 'Camera')}",
                    width="100%",
                )
                with CardContent():
                    Text(photo.get("camera", "Unknown camera"), css_class="font-medium text-sm")
                    Muted(f"Sol {photo.get('sol', 'N/A')} -- {photo.get('earth_date', 'N/A')}")


def _build_journal_section(entries: list[dict[str, Any]]) -> None:
    with Card():
        with CardHeader():
            with Row(gap=2, align="center"):
                H3("Space Journal")
                Badge(str(len(entries)), variant="secondary")

        with CardContent():
            if not entries:
                Muted("No journal entries yet. Fetch data and save some!")
                return

            with Column(gap=3):
                for entry in entries:
                    _build_journal_entry(entry)


def _build_journal_entry(entry: dict[str, Any]) -> None:
    entry_id = entry.get("id", "")

    with Card():
        with CardHeader():
            with Row(align="center", justify="between"):
                with Row(gap=2, align="center"):
                    CardTitle(entry.get("title", "Untitled entry"))
                    Badge(entry.get("type", "entry"), variant="info")
                with Row(gap=1):
                    Button(
                        "Edit",
                        icon="pencil",
                        size="icon-xs",
                        variant="ghost",
                        on_click=SendMessage(
                            f"Update journal entry '{entry_id}' -- ask me what to change"
                        ),
                    )
                    Button(
                        "Delete",
                        icon="trash-2",
                        size="icon-xs",
                        variant="ghost",
                        on_click=CallTool(
                            "manage_space_journal",
                            arguments={
                                "operation": "delete",
                                "entry_id": entry_id,
                            },
                            on_success=ShowToast(
                                "Entry deleted",
                                variant="success",
                            ),
                            on_error=ShowToast(
                                ERROR,
                                variant="error",
                            ),
                        ),
                    )
        with CardContent():
            if entry.get("notes"):
                Text(entry["notes"])
            if entry.get("tags"):
                with Row(gap=1):
                    for tag in entry["tags"]:
                        Badge(tag, variant="outline")
            if entry.get("source_url"):
                Link("Source", href=entry["source_url"], css_class="text-xs")
            Muted(entry.get("date", "N/A"))
            if entry.get("created_at"):
                timestamp = f"Created: {entry['created_at']}"
                if entry.get("updated_at") and entry["updated_at"] != entry["created_at"]:
                    timestamp += f" - Updated: {entry['updated_at']}"
                Muted(timestamp, css_class="text-xs")


def _build_neo_section(neos: list[dict[str, Any]]) -> None:
    H3("Near-Earth Objects")
    with Card():
        with Table():
            with TableHeader():
                with TableRow():
                    TableHead("Name")
                    TableHead("Approach Date")
                    TableHead("Miss Distance (km)")
                    TableHead("Velocity (km/h)")
                    TableHead("Diameter (m)")
                    TableHead("Status")
            with TableBody():
                for neo in neos:
                    _build_neo_row(neo)


def _build_neo_row(neo: dict[str, Any]) -> None:
    with TableRow():
        TableCell(neo.get("name", "Unknown object"))
        TableCell(neo.get("close_approach_date", "N/A"))
        TableCell(f"{neo.get('miss_distance_km', 0):,.0f}")
        TableCell(f"{neo.get('relative_velocity_kph', 0):,.0f}")
        TableCell(
            f"{neo.get('estimated_diameter_meters_min', 0):.0f}"
            f" - {neo.get('estimated_diameter_meters_max', 0):.0f}"
        )
        with TableCell():
            if neo.get("is_potentially_hazardous"):
                Badge("Hazardous", variant="destructive")
            else:
                Badge("Safe", variant="success")


def _build_refresh_section() -> None:
    Separator()
    with Row(justify="center"):
        Button(
            "Refresh Dashboard",
            icon="refresh-cw",
            variant="outline",
            on_click=SendMessage("Read the journal entries and refresh the space dashboard"),
        )
