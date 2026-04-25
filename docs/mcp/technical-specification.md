# Technical Specification: CosmoLog

## 1. Document Overview

### 1.1 Project Name

**CosmoLog** -- NASA Space Mission Journal Dashboard

### 1.2 Purpose

CosmoLog is an MCP application that fetches live NASA space data, stores selected results in a local journal file, and displays the saved and fetched data in an interactive dashboard UI built with the Prefab framework.

This document is the implementation-ready technical specification. It defines every module, data model, API integration detail, component tree, and test case needed to build CosmoLog. An engineer should be able to code directly from this document without consulting external references.

### 1.3 Functional Specification Reference

All requirements originate from `functional-specification.md` in this repository.

### 1.4 Technology Stack

| Package | Version Constraint | Purpose |
|---|---|---|
| Python | `>=3.12` | Runtime |
| `fastmcp` | `>=3.0.0` | MCP server framework |
| `prefab-ui` | latest | Dashboard UI components |
| `httpx` | latest | Async-capable HTTP client for NASA APIs |
| `python-dotenv` | latest | Loads `.env` file into `os.environ` |
| `pydantic` | (transitive via fastmcp/prefab-ui) | Data validation and models |

Dev dependencies: `pytest`, `pytest-asyncio`, `respx`

### 1.5 Key Conventions

These conventions are verified against the Prefab source code and must be followed exactly:

1. **Action callbacks use `on_success=SetState("key", RESULT)`** -- there is no `result_key` parameter on `CallTool`. `RESULT` is `Rx("$result")` from `prefab_ui.rx`.
2. **Template expressions use `{{ }}`** syntax for reactive state interpolation.
3. **State is a plain `dict`** passed to `PrefabApp(state={...})`.
4. **`CallTool` accepts `on_success` and `on_error`** as keyword arguments, not positional. They accept a single action or a list of actions.
5. **`ShowToast` takes `message` as its first positional argument**, with optional `variant` (`"default"`, `"success"`, `"error"`, `"warning"`, `"info"`) and `description`.

---

## 2. Project Structure

```
CosmoLog/
  pyproject.toml          # uv-managed dependencies
  .env                    # NASA_API_KEY (gitignored)
  mcp_server.py           # FastMCP entrypoint + 3 tool registrations
  models.py               # Pydantic data models
  nasa_client.py          # httpx-based NASA API client + caching
  journal.py              # CRUD operations on space_journal.json
  dashboard.py            # Prefab UI builder function
  space_journal.json      # Created at runtime (gitignored)
  tests/
    conftest.py
    test_models.py
    test_nasa_client.py
    test_journal.py
    test_dashboard.py
    test_mcp_server.py
```

This flat layout follows the pattern established by the `hitchhikers-guide` Prefab example.

### 2.1 `pyproject.toml`

```toml
[project]
name = "cosmolog"
version = "0.1.0"
description = "NASA Space Mission Journal Dashboard -- MCP + Prefab"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=3.0.0",
    "prefab-ui",
    "httpx",
    "python-dotenv",
]

[dependency-groups]
dev = [
    "pytest",
    "pytest-asyncio",
    "respx",
]

[project.scripts]
cosmolog = "mcp_server:main"
```

### 2.2 `.env`

```
NASA_API_KEY=DEMO_KEY
```

---

## 3. Data Models (`models.py`)

All models use Pydantic v2 (`BaseModel`). Field types are chosen to match NASA API response shapes after normalization.

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class APODData(BaseModel):
    """Astronomy Picture of the Day."""
    title: str
    date: str
    explanation: str
    media_type: Literal["image", "video"]
    url: str
    thumbnail_url: str | None = None
    copyright: str | None = None


class RoverPhoto(BaseModel):
    """A single Mars rover photo."""
    id: str
    rover: str
    camera: str
    earth_date: str
    sol: int
    img_src: str


class NearEarthObject(BaseModel):
    """A near-Earth asteroid or comet."""
    id: str
    name: str
    close_approach_date: str
    miss_distance_km: float
    relative_velocity_kph: float
    estimated_diameter_meters_min: float
    estimated_diameter_meters_max: float
    is_potentially_hazardous: bool


class SpaceData(BaseModel):
    """Composite result from all NASA APIs."""
    apod: APODData | None = None
    rover_photos: list[RoverPhoto] = Field(default_factory=list)
    near_earth_objects: list[NearEarthObject] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class JournalEntry(BaseModel):
    """A single journal entry."""
    id: str
    type: Literal["apod", "rover_photo"]
    title: str
    date: str
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    source_url: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class JournalFile(BaseModel):
    """Top-level wrapper for space_journal.json."""
    entries: list[JournalEntry] = Field(default_factory=list)
```

### 3.1 Design Notes

- `SpaceData.errors` collects per-API error messages so partial results are still usable (e.g., APOD succeeds but NeoWs fails).
- `RoverPhoto.id` is `str` because NASA returns integer IDs but we convert to string for uniform handling.
- `JournalEntry.metadata` is a free-form dict for storing extra context (e.g., APOD explanation, camera name) without bloating the top-level schema.
- `NearEarthObject` includes `estimated_diameter_meters_min` and `estimated_diameter_meters_max` per the functional spec's normalized NEO shape (section 11.3).

---

## 4. NASA API Client (`nasa_client.py`)

### 4.1 Endpoint Specifications

#### 4.1.1 APOD (Astronomy Picture of the Day)

| Detail | Value |
|---|---|
| URL | `https://api.nasa.gov/planetary/apod` |
| Method | `GET` |
| Auth | `api_key` query parameter |
| Key params | `date` (YYYY-MM-DD, default: today), `thumbs` (boolean, default: true) |

**Response fields used:**

| NASA field | Model field | Notes |
|---|---|---|
| `title` | `title` | |
| `date` | `date` | |
| `explanation` | `explanation` | |
| `media_type` | `media_type` | `"image"` or `"video"` |
| `url` | `url` | For images: full-res image. For videos: embed URL (typically YouTube) |
| `thumbnail_url` | `thumbnail_url` | Only present when `media_type == "video"` and `thumbs=true` |
| `copyright` | `copyright` | Optional, absent for public domain images |

**Video handling:** When `media_type` is `"video"`, the `url` field contains a video embed URL (typically YouTube, e.g., `https://www.youtube.com/embed/...`). The dashboard must use the `Embed` component for videos, not `Image`.

#### 4.1.2 Mars Rover Photos

| Detail | Value |
|---|---|
| URL (by sol) | `https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/photos` |
| URL (latest) | `https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/latest_photos` |
| Method | `GET` |
| Auth | `api_key` query parameter |
| Key params | `sol` (int), `page` (int, default: 1) |

**Response fields used (from each photo object in `photos` or `latest_photos` array):**

| NASA field | Model field | Notes |
|---|---|---|
| `id` | `id` | Cast to `str` |
| `rover.name` | `rover` | Nested object |
| `camera.full_name` | `camera` | Nested object |
| `earth_date` | `earth_date` | |
| `sol` | `sol` | |
| `img_src` | `img_src` | Full image URL |

**Fallback strategy:** If a specific `sol` returns zero photos, retry using the `/latest_photos` endpoint which always returns the most recent available photos.

#### 4.1.3 NeoWs (Near Earth Object Web Service)

| Detail | Value |
|---|---|
| URL | `https://api.nasa.gov/neo/rest/v1/feed` |
| Method | `GET` |
| Auth | `api_key` query parameter |
| Key params | `start_date` (YYYY-MM-DD), `end_date` (YYYY-MM-DD) |

**Response structure:** The response has a `near_earth_objects` dict keyed by date string. Each date maps to a list of NEO objects.

**Response fields used (from each NEO object, after flattening the date-keyed dict):**

| NASA field path | Model field | Notes |
|---|---|---|
| `id` | `id` | |
| `name` | `name` | |
| `close_approach_data[0].close_approach_date` | `close_approach_date` | First entry in array |
| `close_approach_data[0].miss_distance.kilometers` | `miss_distance_km` | Cast to `float` |
| `close_approach_data[0].relative_velocity.kilometers_per_hour` | `relative_velocity_kph` | Cast to `float` |
| `estimated_diameter.meters.estimated_diameter_min` | `estimated_diameter_meters_min` | |
| `estimated_diameter.meters.estimated_diameter_max` | `estimated_diameter_meters_max` | |
| `is_potentially_hazardous_asteroid` | `is_potentially_hazardous` | |

**Flattening:** Iterate over all date keys in `near_earth_objects`, collect all NEO objects into a single flat list.

### 4.2 Client Implementation

```python
import time
from datetime import date, timedelta

import httpx

from models import APODData, NearEarthObject, RoverPhoto, SpaceData

CACHE_TTL_SECONDS = 300  # 5 minutes


class NASAClient:
    """httpx-based NASA API client with in-memory caching."""

    def __init__(self, api_key: str = "DEMO_KEY") -> None:
        self.api_key = api_key
        self.client = httpx.Client(timeout=30.0)
        self._cache: dict[str, tuple[float, object]] = {}

    def _get_cached(self, key: str) -> object | None:
        if key in self._cache:
            ts, value = self._cache[key]
            if time.time() - ts < CACHE_TTL_SECONDS:
                return value
            del self._cache[key]
        return None

    def _set_cached(self, key: str, value: object) -> None:
        self._cache[key] = (time.time(), value)

    # ... individual fetch methods below ...

    def fetch_all(
        self,
        apod_date: str | None = None,
        rover: str = "curiosity",
        sol: int | None = None,
        photo_count: int = 3,
        neo_days: int = 7,
    ) -> SpaceData:
        """Fetch all NASA data, collecting partial results and errors."""
        # Implementation calls each fetch method in try/except,
        # appending to errors list on failure.
```

### 4.3 Response Normalization Logic

#### APOD Normalization

```python
def _normalize_apod(self, data: dict) -> APODData:
    return APODData(
        title=data["title"],
        date=data["date"],
        explanation=data["explanation"],
        media_type=data["media_type"],
        url=data["url"],
        thumbnail_url=data.get("thumbnail_url"),
        copyright=data.get("copyright"),
    )
```

#### Rover Photo Normalization

```python
def _normalize_rover_photo(self, photo: dict) -> RoverPhoto:
    return RoverPhoto(
        id=str(photo["id"]),
        rover=photo["rover"]["name"],
        camera=photo["camera"]["full_name"],
        earth_date=photo["earth_date"],
        sol=photo["sol"],
        img_src=photo["img_src"],
    )
```

#### NEO Normalization

```python
def _normalize_neo(self, neo: dict) -> NearEarthObject:
    approach = neo["close_approach_data"][0]
    return NearEarthObject(
        id=neo["id"],
        name=neo["name"],
        close_approach_date=approach["close_approach_date"],
        miss_distance_km=float(approach["miss_distance"]["kilometers"]),
        relative_velocity_kph=float(
            approach["relative_velocity"]["kilometers_per_hour"]
        ),
        estimated_diameter_meters_min=neo["estimated_diameter"]["meters"][
            "estimated_diameter_min"
        ],
        estimated_diameter_meters_max=neo["estimated_diameter"]["meters"][
            "estimated_diameter_max"
        ],
        is_potentially_hazardous=neo["is_potentially_hazardous_asteroid"],
    )
```

### 4.4 Error Handling

Each individual API call is wrapped in try/except. Errors are collected into `SpaceData.errors` so partial results are still returned.

| Error Type | Source | Handling |
|---|---|---|
| `httpx.HTTPStatusError` (429) | Rate limit exceeded | Append `"APOD rate limited (429). Try again later."` to errors |
| `httpx.HTTPStatusError` (403) | Invalid API key | Append `"Invalid NASA API key (403)."` to errors |
| `httpx.HTTPStatusError` (other) | Server errors | Append `"{api_name} returned HTTP {status}"` to errors |
| `httpx.RequestError` | Network failure | Append `"{api_name} network error: {message}"` to errors |
| `KeyError` / `IndexError` | Unexpected response shape | Append `"{api_name} returned unexpected data format"` to errors |

### 4.5 Caching Strategy

- **Key format:** `"{api_name}:{param_hash}"` -- e.g., `"apod:2026-04-25"`, `"rover:curiosity:latest"`, `"neo:2026-04-25:7"`
- **TTL:** 5 minutes (300 seconds)
- **Storage:** In-memory dict `{key: (timestamp, value)}`
- **Purpose:** Avoid redundant API calls during demo when the agent re-invokes tools. Critical for `DEMO_KEY` which has a 30 req/hr limit.

---

## 5. Journal CRUD (`journal.py`)

### 5.1 Functions

```python
from pathlib import Path

JOURNAL_PATH = Path(__file__).parent / "space_journal.json"


def create_entry(payload: dict) -> dict:
    """Create a new journal entry. Returns {"status": "success", "entry": {...}}."""

def read_entries(tag_filter: str | None = None) -> dict:
    """Read entries, optionally filtered by tag. Returns {"status": "success", "entries": [...]}."""

def update_entry(entry_id: str, payload: dict) -> dict:
    """Update an existing entry. Returns {"status": "success", "entry": {...}}."""

def delete_entry(entry_id: str) -> dict:
    """Delete an entry by ID. Returns {"status": "success", "deleted_id": "..."}."""
```

### 5.2 ID Generation

Format: `"{type}-{date}-{uuid6chars}"`

Example: `"apod-2026-04-25-a1b2c3"`, `"rover_photo-2026-04-25-d4e5f6"`

```python
import uuid

def _generate_id(entry_type: str, entry_date: str) -> str:
    short_uuid = uuid.uuid4().hex[:6]
    return f"{entry_type}-{entry_date}-{short_uuid}"
```

### 5.3 Timestamps

All timestamps are UTC ISO 8601 format:

```python
from datetime import datetime, timezone

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
```

### 5.4 File I/O

```python
import json

def _read_journal() -> dict:
    """Read journal file. Returns {"entries": []} if missing or corrupted."""
    if not JOURNAL_PATH.exists():
        return {"entries": []}
    try:
        data = json.loads(JOURNAL_PATH.read_text())
        if not isinstance(data, dict) or "entries" not in data:
            return {"entries": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"entries": []}


def _write_journal(data: dict) -> None:
    """Write journal data to file."""
    JOURNAL_PATH.write_text(json.dumps(data, indent=2))
```

### 5.5 Error Handling

| Scenario | Behavior |
|---|---|
| File does not exist | `_read_journal` returns `{"entries": []}` |
| File contains invalid JSON | `_read_journal` returns `{"entries": []}` (recovers gracefully) |
| Entry not found (update/delete) | Return `{"status": "error", "message": "Entry '{entry_id}' not found"}` |
| Unknown operation (in MCP tool) | Return `{"status": "error", "message": "Unknown operation: '{op}'"}` |
| Missing `entry_id` for update/delete | Return `{"status": "error", "message": "entry_id is required for {op}"}` |

### 5.6 Return Format

All functions return a dict with this shape:

```python
# Success
{"status": "success", "entry": {...}}      # create, update
{"status": "success", "entries": [...]}    # read
{"status": "success", "deleted_id": "..."}  # delete

# Error
{"status": "error", "message": "..."}
```

---

## 6. MCP Server (`mcp_server.py`)

### 6.1 Server Setup

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

### 6.2 Tool 1: `fetch_space_data`

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

### 6.3 Tool 2: `manage_space_journal`

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

### 6.4 Tool 3: `show_space_dashboard`

```python
@mcp.tool(app=True)
def show_space_dashboard(
    space_data: dict | None = None,
    journal_entries: list[dict] | None = None,
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
```

**Key detail:** The `app=True` parameter marks this as a UI tool that returns a `PrefabApp` object. This is the Prefab convention for tools that render UI.

### 6.5 Entrypoint

```python
def main():
    mcp.run(transport="http")

if __name__ == "__main__":
    main()
```

**Running:** `cd CosmoLog && uv sync && uv run python mcp_server.py`

---

## 7. Dashboard UI (`dashboard.py`)

### 7.1 Imports

These imports are verified against `prefab_ui/components/__init__.py` and `prefab_ui/actions/`:

```python
# Layout
from prefab_ui.components import Column, Row, Grid, GridItem, Separator

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
from prefab_ui.components import Badge, Icon, Tooltip

# Interactive
from prefab_ui.components import Button, Input

# Control flow
from prefab_ui.components import If, Else

# Actions (transport-agnostic)
from prefab_ui.actions import SetState, ShowToast

# Actions (MCP transport)
from prefab_ui.actions.mcp import CallTool, SendMessage

# Reactive references
from prefab_ui.rx import RESULT, ERROR

# App container
from prefab_ui.app import PrefabApp
```

### 7.2 Function Signature

```python
def build_dashboard(
    space_data: dict | None = None,
    journal_entries: list[dict] | None = None,
    tag_filter: str | None = None,
) -> PrefabApp:
```

### 7.3 Data Approach

Since `show_space_dashboard` receives pre-fetched data as tool arguments, data is **baked into the component tree at build time** using Python for-loops. This is the correct approach because:

1. The data is already available when the function is called.
2. No client-side data fetching is needed.
3. Python for-loops generate static component trees (no `ForEach` needed for data display).

**Minimal reactive state** is used only for the `tag_filter` Input, which filters journal entries client-side.

### 7.4 Layout Specification

The dashboard is organized into these sections, top to bottom:

```
+----------------------------------------------------------+
| HEADER: H2("CosmoLog") + Badge("Live") + filter info     |
+----------------------------------------------------------+
| STAT TILES: Grid(columns={"default":2, "md":4})          |
|  [Entries] [Photos] [NEOs] [Hazardous]                   |
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

### 7.5 Section-by-Section Component Trees

#### 7.5.1 Header

```python
with Row(gap=3, align="center"):
    H2("CosmoLog")
    Badge("Live", variant="success")
    if tag_filter:
        Badge(f"Filter: {tag_filter}", variant="secondary")
```

#### 7.5.2 Stat Tiles

```python
with Grid(columns={"default": 2, "md": 5}, gap=4):
    with Card():
        Metric(
            label="Journal Entries",
            value=len(journal_entries or []),
        )
    with Card():
        Metric(
            label="Rover Photos",
            value=len(apod_data.get("rover_photos", [])) if space_data else 0,
        )
    with Card():
        Metric(
            label="Near-Earth Objects",
            value=len(neos),
        )
    with Card():
        Metric(
            label="Hazardous",
            value=hazardous_count,
            trend="up" if hazardous_count > 0 else "neutral",
            trend_sentiment="negative" if hazardous_count > 0 else "neutral",
        )
    with Card():
        Metric(
            label="Closest NEO",
            value=closest_neo_date if closest_neo_date else "N/A",
        )
```

**Closest NEO date:** Computed before the component tree by finding the NEO with the smallest `miss_distance_km`:

```python
closest_neo_date = "N/A"
if neos:
    closest = min(neos, key=lambda n: n["miss_distance_km"])
    closest_neo_date = closest["close_approach_date"]
```

**Note on Metric:** The `Metric` component accepts `label`, `value`, and optional `delta`, `trend`, `trend_sentiment`. See verified API in section 7.1.

#### 7.5.3 Main Content Grid

```python
with Grid(columns={"default": 1, "lg": [2, 1]}, gap=6):
    # Left column: APOD + Rover photos
    with Column(gap=6):
        # APOD Hero (section 7.5.4)
        # Rover Grid (section 7.5.5)

    # Right column: Journal
    with Column(gap=4):
        # Journal section (section 7.5.6)
```

The `[2, 1]` column spec produces `grid-template-columns: 2fr 1fr`, giving the left content area twice the width of the journal sidebar on large screens.

#### 7.5.4 APOD Hero Card

```python
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
            # Video APOD: embed URL (YouTube or other)
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
```

**Critical:** When `media_type` is `"video"`, the `url` is a video embed URL (typically YouTube). We use `Embed` (iframe-based), not the `Video` component (which is for direct video files). This is a Python-level `if/else` since the data is known at build time.

#### 7.5.5 Rover Photo Grid

```python
H3("Mars Rover Photos")
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
```

#### 7.5.6 Journal Section

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
                                            f"Update journal entry '{entry['id']}' — ask me what to change"
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
                                    + (f" · Updated: {entry['updated_at']}"
                                       if entry.get("updated_at") and entry["updated_at"] != entry["created_at"]
                                       else ""),
                                    css_class="text-xs",
                                )
```

**Action pattern for Delete:**
- `CallTool("manage_space_journal", arguments={...})` calls the MCP tool.
- `on_success=ShowToast(...)` shows a success toast when the entry is deleted.
- `on_error=ShowToast(ERROR, variant="error")` shows the error message (`ERROR` = `Rx("$error")`).

**Action pattern for Edit:**
- `SendMessage` sends a message to the agent, which then prompts the user for which fields to update and calls `manage_space_journal` with `operation: "update"`. This avoids complex inline form UI while still satisfying the functional spec's update requirement (section 4.4, UI Actions).

**Note:** After deletion, the dashboard is not automatically refreshed. The user (or agent) must re-invoke `show_space_dashboard`. The `SendMessage` approach (section 7.5.8) provides a refresh button for this purpose.

#### 7.5.7 NEO Table

The NEO table uses the manual `Table` component (not `DataTable`) because `DataTable` cannot render `Badge` components inside cells. Manual `Table` gives full control over cell content.

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

**Badge variants verified:** `"destructive"` (red) and `"success"` (green) are valid `BadgeVariant` literals per `badge.py`.

#### 7.5.8 Refresh Button

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

`SendMessage` sends a message to the AI chat, which triggers the agent to re-invoke the tools and regenerate the dashboard.

### 7.6 PrefabApp Assembly

```python
return PrefabApp(
    title="CosmoLog",
    view=view,
    state={
        "tag_filter": tag_filter or "",
    },
)
```

State is minimal because the dashboard data is baked into the component tree at build time. Only `tag_filter` needs to be reactive for potential client-side filtering.

---

## 8. Sequence Diagrams

### 8.1 Primary Demo Flow (Functional Spec Section 5.1)

```
User                    Agent                   MCP Server (CosmoLog)
  |                       |                           |
  |-- "Fetch today's..." ->|                           |
  |                       |                           |
  |                       |-- fetch_space_data() ----->|
  |                       |                           |-- GET /planetary/apod
  |                       |                           |-- GET /mars-photos/...
  |                       |                           |-- GET /neo/rest/v1/feed
  |                       |<---- SpaceData dict ------|
  |                       |                           |
  |                       |-- manage_space_journal --->|
  |                       |   (create APOD entry)     |-- write space_journal.json
  |                       |<---- {status: success} ---|
  |                       |                           |
  |                       |-- manage_space_journal --->|
  |                       |   (create rover entries)  |-- write space_journal.json
  |                       |<---- {status: success} ---|
  |                       |                           |
  |                       |-- manage_space_journal --->|
  |                       |   (read, tag_filter)      |-- read space_journal.json
  |                       |<---- {entries: [...]} ----|
  |                       |                           |
  |                       |-- show_space_dashboard -->|
  |                       |   (space_data, entries)   |-- build_dashboard()
  |                       |<---- PrefabApp ----------|
  |                       |                           |
  |<-- Rendered Dashboard -|                           |
```

### 8.2 CRUD Demo Flow (Functional Spec Section 6)

```
User                    Agent                   MCP Server (CosmoLog)
  |                       |                           |
  |-- "Update notes..." ->|                           |
  |                       |                           |
  |                       |-- manage_space_journal --->|
  |                       |   (update APOD entry)     |-- read/write journal
  |                       |<---- {status: success} ---|
  |                       |                           |
  |                       |-- manage_space_journal --->|
  |                       |   (delete rover entry)    |-- read/write journal
  |                       |<---- {status: success} ---|
  |                       |                           |
  |                       |-- manage_space_journal --->|
  |                       |   (read)                  |-- read journal
  |                       |<---- {entries: [...]} ----|
  |                       |                           |
  |                       |-- show_space_dashboard -->|
  |                       |   (space_data, entries)   |-- build_dashboard()
  |                       |<---- PrefabApp ----------|
  |                       |                           |
  |<-- Updated Dashboard --|                           |
```

---

## 9. Error Handling Summary

### 9.1 `fetch_space_data` Error Patterns

The tool never raises exceptions. It always returns a `SpaceData` dict with partial results and an `errors` list:

```python
# Partial success example
{
    "apod": {...},            # succeeded
    "rover_photos": [],       # failed, empty
    "near_earth_objects": [], # failed, empty
    "errors": [
        "Mars Rover Photos rate limited (429). Try again later.",
        "NeoWs network error: Connection refused"
    ]
}

# Total failure example
{
    "apod": None,
    "rover_photos": [],
    "near_earth_objects": [],
    "errors": [
        "APOD rate limited (429). Try again later.",
        "Mars Rover Photos rate limited (429). Try again later.",
        "NeoWs rate limited (429). Try again later."
    ]
}
```

### 9.2 `manage_space_journal` Error Patterns

```python
# Entry not found
{"status": "error", "message": "Entry 'apod-2026-04-25-abc123' not found"}

# Missing required field
{"status": "error", "message": "entry_id is required for delete"}

# Unknown operation
{"status": "error", "message": "Unknown operation: 'upsert'"}
```

### 9.3 `show_space_dashboard` Error Patterns

The dashboard handles `None` and empty data gracefully by showing placeholder messages. It does not raise exceptions.

### 9.4 Graceful Degradation

| Scenario | Dashboard Behavior |
|---|---|
| `space_data` is `None` | Skip APOD hero and rover grid. Show "No data fetched" placeholder |
| `rover_photos` is empty | Show "No rover photos available" in the grid area |
| `journal_entries` is empty | Show "No journal entries yet" message |
| `near_earth_objects` is empty | Show empty table with headers only |
| APOD is a video | Render `Embed` component instead of `Image` |
| API errors present | Stat tiles show 0 counts; data sections show placeholders |

---

## 10. Configuration

### 10.1 Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NASA_API_KEY` | No | `DEMO_KEY` | NASA API key for authentication |

### 10.2 `.env` File Format

```
NASA_API_KEY=your_api_key_here
```

The `DEMO_KEY` works for testing but is rate-limited to 30 requests per hour per IP. For demo stability, obtain a free personal key from https://api.nasa.gov.

### 10.3 Running the Application

```bash
cd CosmoLog
uv sync
uv run python mcp_server.py
```

The server starts on the default FastMCP HTTP transport. Connect an MCP-compatible client (e.g., Claude Desktop, Prefab host) to interact with the tools.

---

## 11. Testing Plan

### 11.1 Test Runner

```bash
uv run pytest
```

### 11.2 Mock Library

`respx` is used to mock `httpx` requests. No real NASA API calls are made in tests.

### 11.3 `conftest.py` Fixtures

```python
import pytest
from pathlib import Path

@pytest.fixture
def sample_apod_response():
    """Raw NASA APOD API response (image type)."""
    return {
        "title": "Test Nebula",
        "date": "2026-04-25",
        "explanation": "A beautiful nebula...",
        "media_type": "image",
        "url": "https://apod.nasa.gov/image.jpg",
        "copyright": "Test Author",
    }

@pytest.fixture
def sample_apod_video_response():
    """Raw NASA APOD API response (video type)."""
    return {
        "title": "Test Video",
        "date": "2026-04-25",
        "explanation": "An amazing video...",
        "media_type": "video",
        "url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/0.jpg",
    }

@pytest.fixture
def sample_rover_response():
    """Raw NASA Mars Rover Photos API response."""
    return {
        "photos": [
            {
                "id": 12345,
                "rover": {"name": "Curiosity"},
                "camera": {"full_name": "Navigation Camera"},
                "earth_date": "2026-04-20",
                "sol": 4100,
                "img_src": "https://mars.nasa.gov/photo.jpg",
            }
        ]
    }

@pytest.fixture
def sample_neo_response():
    """Raw NASA NeoWs API response."""
    return {
        "near_earth_objects": {
            "2026-04-25": [
                {
                    "id": "54321",
                    "name": "2026 AB1",
                    "close_approach_data": [
                        {
                            "close_approach_date": "2026-04-25",
                            "miss_distance": {"kilometers": "7500000.123"},
                            "relative_velocity": {"kilometers_per_hour": "45000.567"},
                        }
                    ],
                    "estimated_diameter": {
                        "meters": {
                            "estimated_diameter_min": 100.0,
                            "estimated_diameter_max": 250.0,
                        }
                    },
                    "is_potentially_hazardous_asteroid": True,
                }
            ]
        }
    }

@pytest.fixture
def tmp_journal(tmp_path):
    """Provide a temporary journal path for isolated CRUD tests."""
    return tmp_path / "space_journal.json"

@pytest.fixture
def sample_journal_entry():
    """A complete journal entry dict."""
    return {
        "type": "apod",
        "title": "Test Nebula",
        "date": "2026-04-25",
        "tags": ["mars-week"],
        "notes": "Test note",
        "source_url": "https://apod.nasa.gov/image.jpg",
    }
```

### 11.4 `test_models.py`

| Test | Description |
|---|---|
| `test_apod_data_image` | Construct `APODData` with `media_type="image"`, verify fields |
| `test_apod_data_video` | Construct `APODData` with `media_type="video"` and `thumbnail_url` |
| `test_apod_data_optional_fields` | Verify `thumbnail_url` and `copyright` default to `None` |
| `test_rover_photo` | Construct `RoverPhoto`, verify `id` is string |
| `test_near_earth_object_hazardous` | Construct `NearEarthObject` with `is_potentially_hazardous=True` |
| `test_near_earth_object_safe` | Construct with `is_potentially_hazardous=False` |
| `test_space_data_partial` | Construct `SpaceData` with `apod=None` and non-empty `errors` |
| `test_journal_entry` | Construct `JournalEntry` with all fields |
| `test_journal_entry_defaults` | Verify default empty lists/strings |
| `test_journal_file_empty` | Construct `JournalFile` with no entries |

### 11.5 `test_nasa_client.py`

All tests use `@respx.mock` decorator to intercept httpx requests.

| Test | Description |
|---|---|
| `test_fetch_apod_success` | Mock APOD endpoint, verify `APODData` fields |
| `test_fetch_apod_video` | Mock APOD with `media_type="video"`, verify `thumbnail_url` |
| `test_fetch_rover_photos_success` | Mock rover endpoint, verify photo list and count limit |
| `test_fetch_rover_latest_fallback` | Mock sol endpoint returning empty, verify `/latest_photos` fallback |
| `test_fetch_neo_success` | Mock NeoWs, verify flattening of date-keyed response |
| `test_fetch_neo_hazardous_flag` | Verify `is_potentially_hazardous` mapping |
| `test_rate_limit_429` | Mock 429 response, verify error message in `SpaceData.errors` |
| `test_invalid_key_403` | Mock 403 response, verify error message |
| `test_network_error` | Mock `httpx.ConnectError`, verify graceful error collection |
| `test_empty_response` | Mock empty JSON body, verify no crash |
| `test_caching` | Call twice, verify second call uses cache (no second HTTP request) |
| `test_cache_expiry` | Advance time past TTL, verify cache miss |
| `test_partial_failure` | APOD succeeds, rover fails -- verify partial `SpaceData` |

### 11.6 `test_journal.py`

All tests use `tmp_path` fixtures for isolated file I/O.

| Test | Description |
|---|---|
| `test_create_entry` | Create entry, verify returned entry has `id`, `created_at`, `updated_at` |
| `test_create_generates_id` | Verify ID format: `"{type}-{date}-{6chars}"` |
| `test_read_empty` | Read from non-existent file, verify empty entries list |
| `test_read_all_entries` | Create 3 entries, read all, verify count |
| `test_read_with_tag_filter` | Create entries with different tags, filter, verify results |
| `test_update_entry` | Create then update, verify changed fields and `updated_at` refreshed |
| `test_update_not_found` | Update non-existent ID, verify error response |
| `test_delete_entry` | Create then delete, verify entry removed |
| `test_delete_not_found` | Delete non-existent ID, verify error response |
| `test_corrupted_json_recovery` | Write invalid JSON to file, verify read returns empty journal |
| `test_full_crud_cycle` | Create -> Read -> Update -> Read -> Delete -> Read |

### 11.7 `test_dashboard.py`

| Test | Description |
|---|---|
| `test_build_dashboard_returns_prefab_app` | Verify return type is `PrefabApp` |
| `test_build_dashboard_with_image_apod` | Verify `Image` component in tree for image APOD |
| `test_build_dashboard_with_video_apod` | Verify `Embed` component in tree for video APOD |
| `test_build_dashboard_empty_data` | Verify no crash with `None`/empty data |
| `test_build_dashboard_with_journal_entries` | Verify journal cards appear in tree |
| `test_build_dashboard_with_neo_data` | Verify table rows match NEO count |
| `test_build_dashboard_hazardous_badges` | Verify "Hazardous"/"Safe" badges in NEO table |

### 11.8 `test_mcp_server.py`

| Test | Description |
|---|---|
| `test_tools_registered` | Verify MCP server has exactly 3 tools registered |
| `test_tool_names` | Verify tool names match spec: `fetch_space_data`, `manage_space_journal`, `show_space_dashboard` |
| `test_journal_crud_cycle` | End-to-end: create -> read -> update -> delete via `manage_space_journal` |

---

## 12. Technical Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| APOD video = YouTube embed URL | `Image` component would fail silently | Use `Embed` component for videos; Python `if` on `media_type` at build time |
| `DataTable` cannot render `Badge` in cells | NEO hazard status would display as plain text | Use manual `Table` with `TableRow`/`TableCell` for NEO table |
| NASA `DEMO_KEY` rate limit (30 req/hr) | Demo may fail mid-presentation | In-memory 5-minute cache; recommend personal API key |
| Rover photos empty for arbitrary sol | Empty photo grid | Fallback to `/latest_photos` endpoint when sol-specific request returns empty |
| NeoWs response is date-keyed dict | Code must flatten before display | Iterate all date keys, collect NEOs into flat list |
| `close_approach_data` can be empty array | `IndexError` on `[0]` access | Wrap in try/except, skip NEOs without approach data |
| NASA API returns string numbers | Type mismatch in Pydantic models | Explicit `float()` cast in normalization for `miss_distance_km` and `relative_velocity_kph` |
| Journal file deleted externally | CRUD operations fail | `_read_journal` returns empty journal on missing file |
| Journal file corrupted | `json.loads` raises | `_read_journal` catches `JSONDecodeError` and returns empty journal |

---

## 13. Acceptance Criteria Cross-Reference

This section maps the functional specification's acceptance criteria (section 13) to the technical implementation:

| Criterion | Spec Section | Implementation |
|---|---|---|
| Agent calls `fetch_space_data` | 13.1 | `mcp_server.py` Tool 1 (section 6.2) |
| Tool retrieves live or cached NASA data | 13.1 | `nasa_client.py` with caching (section 4) |
| Returned data includes APOD, rover, NEO | 13.1 | `SpaceData` model (section 3) |
| Agent creates entries in journal | 13.2 | `journal.py` `create_entry` (section 5) |
| Agent reads entries from journal | 13.2 | `journal.py` `read_entries` (section 5) |
| Agent updates at least one entry | 13.2 | `journal.py` `update_entry` (section 5) |
| Agent deletes at least one entry | 13.2 | `journal.py` `delete_entry` (section 5) |
| Agent calls `show_space_dashboard` | 13.3 | `mcp_server.py` Tool 3 with `app=True` (section 6.4) |
| Tool returns a Prefab dashboard UI | 13.3 | `dashboard.py` returns `PrefabApp` (section 7) |
| Dashboard displays NASA + journal data | 13.3 | All dashboard sections (section 7.5) |
| Prompt triggers all three tools | 13.4 | Demo prompt in functional spec section 5.1 |
