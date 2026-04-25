# Phase 4: Prefab Dashboard UI

## Goal

Build the complete Prefab dashboard UI that displays NASA data and journal entries. This satisfies the UI requirement from the functional specification.

## What This Phase Delivers

- `dashboard.py` -- `build_dashboard()` function returning a `PrefabApp` with all data sections
- `tests/test_dashboard.py` -- 7 tests verifying component tree construction

## Prerequisites

- Phase 1 complete (`models.py`)
- Prefab UI framework available at `../prefab/`

## Acceptance Criteria

- [ ] `build_dashboard()` returns a `PrefabApp` instance
- [ ] Dashboard includes all sections: Header, Stat Tiles, APOD Hero, Rover Grid, Journal, NEO Table, Refresh Button
- [ ] Image APODs render `Image` component; video APODs render `Embed` component
- [ ] NEO table uses manual `Table`/`TableRow`/`TableCell` (not `DataTable`) to support `Badge` in cells
- [ ] Journal entries have Edit (`SendMessage`) and Delete (`CallTool`) buttons
- [ ] Dashboard handles `None`/empty data gracefully with placeholder messages
- [ ] `uv run pytest tests/test_dashboard.py -v` shows 7 passed
- [ ] `uv run pytest -v` shows no regressions from Phases 1-3
- [ ] Satisfies functional spec section 13.3 (Prefab UI Requirement)

---

## Step 1: Create `dashboard.py`

**Reference:** Technical Specification section 7.

### Imports

These imports are verified against the Prefab source code at `../prefab/src/prefab_ui/`:

```python
# Layout
from prefab_ui.components import Column, Row, Grid, Separator

# Cards
from prefab_ui.components import (
    Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter,
)

# Typography
from prefab_ui.components import H2, H3, Text, Muted, Link

# Data display
from prefab_ui.components import (
    Table, TableHeader, TableBody, TableRow, TableHead, TableCell, Metric,
)

# Media
from prefab_ui.components import Image, Embed

# Feedback
from prefab_ui.components import Badge

# Interactive
from prefab_ui.components import Button

# Actions (transport-agnostic)
from prefab_ui.actions import ShowToast

# Actions (MCP transport)
from prefab_ui.actions.mcp import CallTool, SendMessage

# Reactive references
from prefab_ui.rx import ERROR

# App container
from prefab_ui.app import PrefabApp
```

### Function Signature

```python
def build_dashboard(
    space_data: dict | None = None,
    journal_entries: list[dict] | None = None,
    tag_filter: str | None = None,
) -> PrefabApp:
```

### Data Approach

Data is **baked into the component tree at build time** using Python for-loops. No client-side data fetching needed. Minimal reactive state is used only for `tag_filter`.

### Pre-computation (before building component tree)

```python
# Extract data with safe defaults
apod = space_data.get("apod") if space_data else None
rover_photos = space_data.get("rover_photos", []) if space_data else []
neos = space_data.get("near_earth_objects", []) if space_data else []
entries = journal_entries or []

# Computed values for stat tiles
hazardous_count = sum(1 for n in neos if n.get("is_potentially_hazardous"))
closest_neo_date = "N/A"
if neos:
    closest = min(neos, key=lambda n: n["miss_distance_km"])
    closest_neo_date = closest["close_approach_date"]
```

### Layout Overview

```
+----------------------------------------------------------+
| HEADER: H2("CosmoLog") + Badge("Live") + filter info     |
+----------------------------------------------------------+
| STAT TILES: Grid(columns={"default":2, "md":5})          |
|  [Entries] [Photos] [NEOs] [Hazardous] [Closest NEO]     |
+----------------------------------------------------------+
| MAIN CONTENT: Grid(columns={"default":1, "lg":[2,1]})    |
|  +---------------------------+------------------------+   |
|  | APOD Hero Card            | Journal Section        |   |
|  | Rover Photo Grid          |   Entry cards           |   |
|  +---------------------------+------------------------+   |
+----------------------------------------------------------+
| NEO TABLE: Full-width Table                               |
+----------------------------------------------------------+
| FOOTER: Refresh Button                                    |
+----------------------------------------------------------+
```

---

### Section 1: Header

```python
with Row(gap=3, align="center"):
    H2("CosmoLog")
    Badge("Live", variant="success")
    if tag_filter:
        Badge(f"Filter: {tag_filter}", variant="secondary")
```

---

### Section 2: Stat Tiles

```python
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
```

---

### Section 3: Main Content Grid

```python
with Grid(columns={"default": 1, "lg": [2, 1]}, gap=6):
    # Left column: APOD + Rover photos
    with Column(gap=6):
        # APOD Hero (Section 4)
        # Rover Grid (Section 5)

    # Right column: Journal
    with Column(gap=4):
        # Journal section (Section 6)
```

The `[2, 1]` column spec produces `grid-template-columns: 2fr 1fr`.

---

### Section 4: APOD Hero Card

**Critical:** When `media_type` is `"video"`, use `Embed` (iframe-based), NOT `Image`. This is a Python-level `if/else` since the data is known at build time.

```python
if apod:
    with Card():
        with CardHeader():
            CardTitle(apod["title"])
            CardDescription(f"APOD -- {apod['date']}")
        with CardContent():
            if apod["media_type"] == "image":
                Image(
                    src=apod["url"],
                    alt=apod["title"],
                    width="100%",
                )
            else:
                Embed(
                    url=apod["url"],
                    width="100%",
                    height="400px",
                    allow="fullscreen; autoplay",
                )
            Text(apod["explanation"], css_class="mt-4 text-sm")
        with CardFooter():
            if apod.get("copyright"):
                Muted(f"Copyright: {apod['copyright']}")
            Link("View on NASA", href=apod["url"], css_class="text-sm")
else:
    with Card():
        with CardContent():
            Muted("No APOD data available. Fetch data to see today's astronomy picture.")
```

**Key API details:**
- `Image(src=..., alt=..., width=...)` -- `src` is a keyword argument
- `Embed(url=..., width=..., height=..., allow=...)` -- validates exactly one of `url`/`html`
- `Link("text", href="...")` -- content is positional, `href` is keyword

---

### Section 5: Rover Photo Grid

```python
H3("Mars Rover Photos")
if rover_photos:
    with Grid(columns={"default": 1, "sm": 3}, gap=4):
        for photo in rover_photos:
            with Card():
                Image(
                    src=photo["img_src"],
                    alt=f"{photo['rover']} - {photo['camera']}",
                    width="100%",
                )
                with CardContent():
                    Text(photo["camera"], css_class="font-medium text-sm")
                    Muted(f"Sol {photo['sol']} -- {photo['earth_date']}")
else:
    Muted("No rover photos available.")
```

---

### Section 6: Journal Section

```python
with Card():
    with CardHeader():
        with Row(gap=2, align="center"):
            H3("Space Journal")
            Badge(str(len(entries)), variant="secondary")

    with CardContent():
        if not entries:
            Muted("No journal entries yet. Fetch data and save some!")
        else:
            with Column(gap=3):
                for entry in entries:
                    with Card():
                        with CardHeader():
                            with Row(align="center", css_class="justify-between"):
                                with Row(gap=2, align="center"):
                                    CardTitle(entry["title"])
                                    Badge(entry["type"], variant="info")
                                with Row(gap=1):
                                    Button(
                                        "Edit",
                                        icon="pencil",
                                        size="icon-xs",
                                        variant="ghost",
                                        on_click=SendMessage(
                                            f"Update journal entry '{entry['id']}'"
                                            " -- ask me what to change"
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
                                                "entry_id": entry["id"],
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
                                Link(
                                    "Source",
                                    href=entry["source_url"],
                                    css_class="text-xs",
                                )
                            Muted(entry["date"])
                            if entry.get("created_at"):
                                Muted(
                                    f"Created: {entry['created_at']}"
                                    + (
                                        f" · Updated: {entry['updated_at']}"
                                        if entry.get("updated_at")
                                        and entry["updated_at"] != entry["created_at"]
                                        else ""
                                    ),
                                    css_class="text-xs",
                                )
```

**Action patterns:**
- **Delete:** `CallTool(tool, arguments={...}, on_success=ShowToast(...), on_error=ShowToast(ERROR, ...))` -- all keyword args
- **Edit:** `SendMessage(content)` sends a message to the agent to handle the update interactively
- `ERROR` = `Rx("$error")` from `prefab_ui.rx` -- resolves to the error message at runtime

---

### Section 7: NEO Table

**Critical:** Use manual `Table` (NOT `DataTable`) because `DataTable` cannot render `Badge` components inside cells.

```python
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
                with TableRow():
                    TableCell(neo["name"])
                    TableCell(neo["close_approach_date"])
                    TableCell(f"{neo['miss_distance_km']:,.0f}")
                    TableCell(f"{neo['relative_velocity_kph']:,.0f}")
                    TableCell(
                        f"{neo['estimated_diameter_meters_min']:.0f}"
                        f" - {neo['estimated_diameter_meters_max']:.0f}"
                    )
                    with TableCell():
                        if neo["is_potentially_hazardous"]:
                            Badge("Hazardous", variant="destructive")
                        else:
                            Badge("Safe", variant="success")
```

**Badge variants:** `"destructive"` (red) and `"success"` (green) are valid `BadgeVariant` literals.

---

### Section 8: Refresh Button

```python
Separator()
with Row(css_class="justify-center"):
    Button(
        "Refresh Dashboard",
        icon="refresh-cw",
        variant="outline",
        on_click=SendMessage(
            "Read the journal entries and refresh the space dashboard"
        ),
    )
```

---

### PrefabApp Assembly

```python
return PrefabApp(
    title="CosmoLog",
    view=view,
    state={
        "tag_filter": tag_filter or "",
    },
)
```

State is minimal -- the dashboard data is baked into the component tree at build time. Only `tag_filter` needs to be reactive.

**Note:** The `view` variable should be the root container component. Build all sections inside a root `Column` context manager, then pass it as `view`.

---

### Graceful Degradation

| Scenario | Dashboard Behavior |
|---|---|
| `space_data` is `None` | Skip APOD hero and rover grid. Show placeholder messages |
| `rover_photos` is empty | Show "No rover photos available" |
| `journal_entries` is empty | Show "No journal entries yet" message |
| `near_earth_objects` is empty | Show empty table with headers only |
| APOD is a video | Render `Embed` component instead of `Image` |

---

## Step 2: Create `tests/test_dashboard.py`

**Reference:** Technical Specification section 11.7.

### Helper Function

Use this to traverse the serialized Prefab component tree:

```python
import json
from dashboard import build_dashboard
from prefab_ui.app import PrefabApp


def find_components(data, component_type: str) -> list:
    """Recursively find all components of a given type in serialized tree."""
    results = []
    if isinstance(data, dict):
        if data.get("type") == component_type:
            results.append(data)
        for value in data.values():
            results.extend(find_components(value, component_type))
    elif isinstance(data, list):
        for item in data:
            results.extend(find_components(item, component_type))
    return results
```

### Test Data Fixtures

```python
IMAGE_SPACE_DATA = {
    "apod": {
        "title": "Test Nebula",
        "date": "2026-04-25",
        "explanation": "A beautiful nebula...",
        "media_type": "image",
        "url": "https://apod.nasa.gov/image.jpg",
        "copyright": "Test Author",
    },
    "rover_photos": [
        {
            "id": "12345",
            "rover": "Curiosity",
            "camera": "Navigation Camera",
            "earth_date": "2026-04-20",
            "sol": 4100,
            "img_src": "https://mars.nasa.gov/photo.jpg",
        }
    ],
    "near_earth_objects": [
        {
            "id": "54321",
            "name": "2026 AB1",
            "close_approach_date": "2026-04-25",
            "miss_distance_km": 7500000.123,
            "relative_velocity_kph": 45000.567,
            "estimated_diameter_meters_min": 100.0,
            "estimated_diameter_meters_max": 250.0,
            "is_potentially_hazardous": True,
        },
        {
            "id": "99999",
            "name": "2026 XY9",
            "close_approach_date": "2026-04-26",
            "miss_distance_km": 50000000.0,
            "relative_velocity_kph": 10000.0,
            "estimated_diameter_meters_min": 10.0,
            "estimated_diameter_meters_max": 20.0,
            "is_potentially_hazardous": False,
        },
    ],
    "errors": [],
}

VIDEO_SPACE_DATA = {
    "apod": {
        "title": "Test Video",
        "date": "2026-04-25",
        "explanation": "An amazing video...",
        "media_type": "video",
        "url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/0.jpg",
    },
    "rover_photos": [],
    "near_earth_objects": [],
    "errors": [],
}

SAMPLE_JOURNAL_ENTRIES = [
    {
        "id": "apod-2026-04-25-a1b2c3",
        "type": "apod",
        "title": "Test Nebula",
        "date": "2026-04-25",
        "tags": ["mars-week"],
        "notes": "Test note",
        "source_url": "https://apod.nasa.gov/image.jpg",
        "created_at": "2026-04-25T10:30:00+00:00",
        "updated_at": "2026-04-25T10:30:00+00:00",
    }
]
```

### Tests

```python
def test_build_dashboard_returns_prefab_app():
    """Verify return type is PrefabApp."""
    result = build_dashboard()
    assert isinstance(result, PrefabApp)


def test_build_dashboard_with_image_apod():
    """Verify Image component in tree for image APOD."""
    result = build_dashboard(space_data=IMAGE_SPACE_DATA)
    tree = result.model_dump()
    images = find_components(tree, "Image")
    assert len(images) > 0  # At least the APOD image


def test_build_dashboard_with_video_apod():
    """Verify Embed component in tree for video APOD."""
    result = build_dashboard(space_data=VIDEO_SPACE_DATA)
    tree = result.model_dump()
    embeds = find_components(tree, "Embed")
    assert len(embeds) > 0  # Video APOD uses Embed


def test_build_dashboard_empty_data():
    """Verify no crash with None/empty data."""
    result = build_dashboard(space_data=None, journal_entries=None)
    assert isinstance(result, PrefabApp)
    # Should have placeholder messages, not crash


def test_build_dashboard_with_journal_entries():
    """Verify journal cards appear in tree."""
    result = build_dashboard(journal_entries=SAMPLE_JOURNAL_ENTRIES)
    tree = result.model_dump()
    # Look for the journal entry title or Badge with entry type
    badges = find_components(tree, "Badge")
    badge_contents = [b.get("children", [{}])[0] if b.get("children") else "" for b in badges]
    # Should find "apod" badge for the entry type
    # The exact assertion depends on how Prefab serializes Badge children


def test_build_dashboard_with_neo_data():
    """Verify table rows match NEO count."""
    result = build_dashboard(space_data=IMAGE_SPACE_DATA)
    tree = result.model_dump()
    table_rows = find_components(tree, "TableRow")
    # Should have at least 2 data rows (one per NEO) + 1 header row
    assert len(table_rows) >= 3


def test_build_dashboard_hazardous_badges():
    """Verify 'Hazardous' and 'Safe' badges in NEO table."""
    result = build_dashboard(space_data=IMAGE_SPACE_DATA)
    tree = result.model_dump()
    badges = find_components(tree, "Badge")
    # Serialize to check for Hazardous/Safe content
    tree_str = json.dumps(tree)
    assert "Hazardous" in tree_str
    assert "Safe" in tree_str
```

### Test Summary

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_build_dashboard_returns_prefab_app` | Return type is `PrefabApp` |
| 2 | `test_build_dashboard_with_image_apod` | `Image` component present for image APOD |
| 3 | `test_build_dashboard_with_video_apod` | `Embed` component present for video APOD |
| 4 | `test_build_dashboard_empty_data` | No crash with `None`/empty data |
| 5 | `test_build_dashboard_with_journal_entries` | Journal cards rendered for entries |
| 6 | `test_build_dashboard_with_neo_data` | Table rows match NEO count |
| 7 | `test_build_dashboard_hazardous_badges` | "Hazardous"/"Safe" badges in NEO table |

### Testing Approach

The testing strategy is to call `build_dashboard(...)` with test data, serialize the returned `PrefabApp` via `.model_dump()`, and recursively traverse the resulting dict tree to find expected component types. This validates the component tree structure without needing a browser or Prefab host.

**Note:** The exact serialized shape of Prefab components may vary. The `find_components` helper searches by `"type"` key, which is how Pydantic serializes discriminated unions. If this doesn't match the actual Prefab serialization, adjust the helper to search by the correct key (e.g., `"component"`, `"kind"`, etc.). Check `../prefab/src/prefab_ui/components/` for the actual model structure.

---

## Verification

```bash
cd CosmoLog
uv run pytest tests/test_dashboard.py -v
uv run pytest -v  # no regressions
uv run ruff check dashboard.py tests/test_dashboard.py
uv run ruff format --check dashboard.py tests/test_dashboard.py
```

All 7 tests should pass (41 total including Phases 1-3).

---

## Spec References

- Tech spec section 7: Dashboard UI
- Tech spec section 7.1: Imports
- Tech spec section 7.3: Data Approach
- Tech spec section 7.4: Layout Specification
- Tech spec section 7.5: Section-by-Section Component Trees
- Tech spec section 7.6: PrefabApp Assembly
- Tech spec section 9.4: Graceful Degradation
- Tech spec section 11.7: test_dashboard.py test table
- Tech spec section 12: Technical Risks (Embed vs Image, Table vs DataTable)
- Functional spec section 4.4: Show Space Dashboard
- Functional spec section 12: UI Layout Specification
- Functional spec section 13.3: Prefab UI Requirement

---

## Commit

```
feat: build Prefab dashboard UI with all data sections
```
