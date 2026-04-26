from __future__ import annotations

import logging
from typing import Any

from prefab_ui.actions import CallHandler, Fetch, ShowToast
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    H2,
    H3,
    Accordion,
    AccordionItem,
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
    Carousel,
    Column,
    Dot,
    Embed,
    Grid,
    Icon,
    Image,
    Link,
    Markdown,
    Metric,
    Muted,
    Progress,
    Row,
    Separator,
    Small,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
    Text,
    Tooltip,
)
from prefab_ui.rx import ERROR

logger = logging.getLogger(__name__)

_ENTRY_TYPE_MAP: dict[str, tuple[str, str]] = {
    "observation": ("telescope", "info"),
    "apod": ("sun", "warning"),
    "rover_photo": ("camera", "success"),
}
_FALLBACK_VISUALS = ("notebook-pen", "muted")


def _entry_visuals(entry_type: str) -> tuple[str, str]:
    """Return (icon_name, dot_variant) for a journal entry type."""
    return _ENTRY_TYPE_MAP.get(entry_type, _FALLBACK_VISUALS)


def build_dashboard(
    space_data: dict[str, Any] | None = None,
    journal_entries: list[dict[str, Any]] | None = None,
    tag_filter: str | None = None,
) -> PrefabApp:
    """Build the CosmoLog Prefab dashboard from prepared data."""
    image_count = len(space_data.get("nasa_images", [])) if space_data else 0
    neo_count = len(space_data.get("near_earth_objects", [])) if space_data else 0
    entry_count = len(journal_entries) if journal_entries else 0
    logger.info(
        "build_dashboard apod=%s image_count=%d neo_count=%d entry_count=%d tag_filter=%s",
        bool(space_data and space_data.get("apod")),
        image_count,
        neo_count,
        entry_count,
        tag_filter,
    )
    apod = space_data.get("apod") if space_data else None
    nasa_images = space_data.get("nasa_images", []) if space_data else []
    neos = space_data.get("near_earth_objects", []) if space_data else []
    entries = journal_entries or []

    hazardous_count = sum(1 for neo in neos if neo.get("is_potentially_hazardous"))
    closest_neo_date = "N/A"
    if neos:
        closest = min(neos, key=lambda neo: neo.get("miss_distance_km", float("inf")))
        closest_neo_date = closest.get("close_approach_date", "N/A")

    with Column(gap=6, css_class="p-6") as view:
        _build_header(tag_filter)
        _build_stat_tiles(entries, nasa_images, neos, hazardous_count, closest_neo_date)

        with Grid(columns=[2, 1], gap=6):
            with Column(gap=6):
                _build_apod_section(apod)
                _build_images_section(nasa_images)

            _build_journal_section(entries)

        _build_neo_section(neos)
        _build_refresh_section()

        # Generation metadata footer — count before adding footer components
        total, type_counts = _count_components(view)
        _build_footer_section(total, type_counts)

        # Move footer (Separator + Column) to the very top of the dashboard
        footer_col = view.children.pop()
        footer_sep = view.children.pop()
        view.children.insert(0, footer_sep)
        view.children.insert(1, footer_col)

    logger.debug("build_dashboard_done")
    return PrefabApp(
        title="CosmoLog",
        view=view,
        state={"tag_filter": tag_filter or ""},
        js_actions={
            "sendToChat": """(ctx) => {
                window.parent.postMessage(
                    { type: "cosmolog:sendMessage", text: ctx.arguments.text },
                    "*"
                );
            }""",
        },
    )


def _build_header(tag_filter: str | None) -> None:
    with Row(gap=3, align="center"):
        H2("CosmoLog")
        Badge("Live", variant="success", css_class="animate-pulse")
        if tag_filter:
            Badge(f"Filter: {tag_filter}", variant="secondary")


def _build_stat_tiles(
    entries: list[dict[str, Any]],
    nasa_images: list[dict[str, Any]],
    neos: list[dict[str, Any]],
    hazardous_count: int,
    closest_neo_date: str,
) -> None:
    with Grid(columns={"default": 2, "md": 5}, gap=4):
        with Card(css_class="animate-fade-in duration-500 border-l-4 border-l-blue-500"):
            Metric(label="Journal Entries", value=len(entries))
        with Card(
            css_class="animate-fade-in duration-500 delay-100 border-l-4 border-l-orange-500"
        ):
            Metric(label="NASA Images", value=len(nasa_images))
        with Card(
            css_class="animate-fade-in duration-500 delay-200 border-l-4 border-l-violet-500"
        ):
            Metric(label="Near-Earth Objects", value=len(neos))
        with Card(
            css_class="animate-fade-in duration-500 delay-300 border-l-4 border-l-red-500"
            + (" text-red-600 dark:text-red-400" if hazardous_count > 0 else ""),
        ):
            Metric(
                label="Hazardous",
                value=hazardous_count,
                trend="up" if hazardous_count > 0 else "neutral",
                trend_sentiment="negative" if hazardous_count > 0 else "neutral",
            )
        with Card(
            css_class="animate-fade-in duration-500 delay-500 border-l-4 border-l-amber-500"
        ):
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
                    css_class="animate-zoom-in-95 duration-700",
                )
            else:
                Image(
                    src=url,
                    alt=title,
                    width="100%",
                    css_class="animate-zoom-in-95 duration-700",
                )
            Text(apod.get("explanation", ""), css_class="mt-4 text-sm")
        with CardFooter():
            if apod.get("copyright"):
                Muted(f"Copyright: {apod['copyright']}")
            if url:
                Link("View on NASA", href=url, css_class="text-sm")


def _build_images_section(nasa_images: list[dict[str, Any]]) -> None:
    H3("NASA Imagery", css_class="text-orange-700 dark:text-orange-400")
    if not nasa_images:
        Muted("No NASA images available.")
        return

    with Carousel(
        auto_advance=4000,
        effect="fade",
        loop=True,
        show_dots=True,
        pause_on_hover=True,
        css_class="animate-fade-in duration-500",
    ):
        for image in nasa_images:
            with Card():
                Image(
                    src=image.get("img_src", ""),
                    alt=image.get("title", "NASA Image"),
                    width="100%",
                )
                with CardContent():
                    Text(image.get("title", "Untitled"), css_class="font-medium text-sm")
                    Muted(image.get("date_created", "N/A"))


def _build_journal_section(entries: list[dict[str, Any]]) -> None:
    with Card():
        with CardHeader():
            with Row(gap=2, align="center"):
                Icon("book-open", css_class="text-blue-600 dark:text-blue-400")
                H3("Mission Log")
                Badge(str(len(entries)), variant="secondary")

        with CardContent():
            if not entries:
                with Column(gap=2, align="center", css_class="py-4"):
                    Icon("file-question", size="lg")
                    Muted("No journal entries yet. Fetch data and save some!")
                return

            with Accordion(multiple=True, default_open_items=0):
                for entry in entries:
                    _build_journal_entry(entry)


def _build_journal_entry(entry: dict[str, Any]) -> None:
    entry_id = entry.get("id", "")
    entry_type = entry.get("type", "entry")
    icon_name, dot_variant = _entry_visuals(entry_type)
    content = entry.get("content") or entry.get("notes", "")

    with AccordionItem(entry.get("title", "Untitled entry"), value=entry_id or None):
        with Column(gap=3):
            with Row(align="center", justify="between"):
                with Row(gap=2, align="center"):
                    Dot(variant=dot_variant)
                    Icon(icon_name, size="sm")
                    Badge(entry_type, variant="info")
                    Small(entry.get("date", "N/A"))
                with Row(gap=1):
                    with Tooltip("Edit this entry"):
                        Button(
                            "Edit",
                            icon="pencil",
                            size="icon-xs",
                            variant="ghost",
                            on_click=CallHandler(
                                "sendToChat",
                                arguments={
                                    "text": f"Update journal entry '{entry_id}'"
                                    " -- ask me what to change"
                                },
                            ),
                        )
                    with Tooltip("Delete this entry"):
                        Button(
                            "Delete",
                            icon="trash-2",
                            size="icon-xs",
                            variant="ghost",
                            on_click=Fetch.delete(
                                f"/api/journal/{entry_id}",
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
            if content:
                Markdown(content, css_class="text-sm")
            if entry.get("tags"):
                Separator()
                with Row(gap=1, css_class="flex-wrap"):
                    for tag in entry["tags"]:
                        Badge(tag, variant="secondary")
            if entry.get("source_url"):
                Link("Source", href=entry["source_url"], css_class="text-xs")
            if entry.get("created_at"):
                timestamp = entry["created_at"][:16]
                if entry.get("updated_at") and entry["updated_at"] != entry["created_at"]:
                    timestamp += f" (edited {entry['updated_at'][:16]})"
                with Row(gap=1, align="center"):
                    Icon("clock", size="sm")
                    Small(timestamp)


def _build_neo_section(neos: list[dict[str, Any]]) -> None:
    H3("Near-Earth Objects", css_class="text-amber-700 dark:text-amber-400")
    max_dist = max((n.get("miss_distance_km", 0) for n in neos), default=1) or 1
    with Card():
        with Table():
            with TableHeader():
                with TableRow():
                    TableHead("Name")
                    TableHead("Approach Date")
                    TableHead("Miss Distance (km)")
                    TableHead("Proximity")
                    TableHead("Velocity (km/h)")
                    TableHead("Diameter (m)")
                    TableHead("Status")
            with TableBody():
                for neo in neos:
                    _build_neo_row(neo, max_dist)


def _build_neo_row(neo: dict[str, Any], max_dist: float) -> None:
    dist = neo.get("miss_distance_km", 0)
    proximity_pct = max(0, min(100, 100 * (1 - dist / max_dist)))
    is_hazardous = neo.get("is_potentially_hazardous", False)

    with TableRow():
        TableCell(neo.get("name", "Unknown object"))
        TableCell(neo.get("close_approach_date", "N/A"))
        TableCell(f"{dist:,.0f}")
        with TableCell():
            Progress(
                value=proximity_pct,
                variant="destructive" if is_hazardous else "info",
                size="sm",
                gradient=True,
            )
        TableCell(f"{neo.get('relative_velocity_kph', 0):,.0f}")
        TableCell(
            f"{neo.get('estimated_diameter_meters_min', 0):.0f}"
            f" - {neo.get('estimated_diameter_meters_max', 0):.0f}"
        )
        with TableCell():
            if is_hazardous:
                Badge("Hazardous", variant="destructive", css_class="animate-pulse")
            else:
                Badge("Safe", variant="success")


def _build_refresh_section() -> None:
    Separator()
    with Row(justify="center"):
        Button(
            "Refresh Dashboard",
            icon="refresh-cw",
            variant="outline",
            on_click=CallHandler(
                "sendToChat",
                arguments={"text": "Read the journal entries and refresh the space dashboard"},
            ),
        )


def _count_components(root: Any) -> tuple[int, dict[str, int]]:
    """Walk the in-memory Prefab component tree and return (total, {type: count})."""
    from collections import Counter

    from prefab_ui.components.base import Component, ContainerComponent

    counts: Counter[str] = Counter()

    def _walk(node: Component) -> None:
        counts[node.type] += 1
        if isinstance(node, ContainerComponent):
            for child in node.children:
                _walk(child)

    _walk(root)
    return sum(counts.values()), dict(counts)


def _build_footer_section(total_count: int, type_counts: dict[str, int]) -> None:
    """Render a generation metadata footer proving dynamic construction."""
    from datetime import UTC, datetime

    sorted_types = sorted(type_counts)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    Separator()
    with Column(gap=3, align="center", css_class="py-4 opacity-75"):
        with Row(gap=2, align="center"):
            Dot(variant="success", size="sm")
            H2("Built with Prefab UI")
        Muted(f"Generated {timestamp}")
        Muted(f"{total_count} components \u00b7 {len(sorted_types)} types")
        with Row(gap=1, css_class="flex-wrap", justify="center"):
            for type_name in sorted_types:
                Badge(type_name, variant="outline")
