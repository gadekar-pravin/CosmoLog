# Phase 1: Data Models + Project Foundation

## Goal

Establish the foundational Pydantic data models, test infrastructure, and environment configuration. This phase has zero external dependencies (no NASA API calls, no file I/O, no Prefab) and is purely about defining the data shapes that all other modules consume.

## What This Phase Delivers

- `models.py` -- all 6 Pydantic v2 models used across the application
- `.env` -- environment file for NASA API key
- `tests/__init__.py` -- empty package init
- `tests/conftest.py` -- shared pytest fixtures for all test modules
- `tests/test_models.py` -- 10 model construction and default-value tests

## Prerequisites

- Python 3.12+ installed
- `uv` installed (`pip install uv` or `brew install uv`)
- `pyproject.toml` already exists (created during project setup)

## Acceptance Criteria

- [ ] `uv sync` installs all dependencies without errors
- [ ] `.env` exists with `NASA_API_KEY=DEMO_KEY`
- [ ] `models.py` defines 6 models: `APODData`, `RoverPhoto`, `NearEarthObject`, `SpaceData`, `JournalEntry`, `JournalFile`
- [ ] `tests/conftest.py` provides 6 shared fixtures
- [ ] `tests/test_models.py` has 10 tests, all passing
- [ ] `uv run pytest tests/test_models.py -v` shows 10 passed
- [ ] `uv run ruff check models.py tests/` is clean
- [ ] `uv run ruff format --check models.py tests/` is clean

---

## Step 1: Install Dependencies

```bash
cd CosmoLog
uv sync
```

This installs all runtime and dev dependencies declared in `pyproject.toml`.

---

## Step 2: Create `.env`

```
NASA_API_KEY=DEMO_KEY
```

This file is gitignored. The `DEMO_KEY` works for testing but is rate-limited to 30 requests per hour. For the live demo, obtain a free personal key from https://api.nasa.gov.

---

## Step 3: Create `models.py`

All models use Pydantic v2 (`BaseModel`). Field types match NASA API response shapes after normalization.

**Reference:** Technical Specification section 3.

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

### Design Notes

- `SpaceData.errors` collects per-API error messages so partial results are still usable (e.g., APOD succeeds but NeoWs fails).
- `RoverPhoto.id` is `str` because NASA returns integer IDs but we convert to string for uniform handling.
- `JournalEntry.metadata` is a free-form dict for storing extra context (e.g., APOD explanation, camera name) without bloating the top-level schema.
- `NearEarthObject` includes `estimated_diameter_meters_min` and `estimated_diameter_meters_max` per the functional spec's normalized NEO shape (section 11.3).
- Use `X | Y` union syntax (Python 3.12+), not `Union[X, Y]`.
- Use `Field(default_factory=list)` for mutable defaults.

---

## Step 4: Create `tests/__init__.py`

Empty file. Required to make `tests/` a Python package.

---

## Step 5: Create `tests/conftest.py`

Shared fixtures for all test modules.

**Reference:** Technical Specification section 11.3.

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
                            "relative_velocity": {
                                "kilometers_per_hour": "45000.567"
                            },
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

### Fixture Usage Map

| Fixture | Used By | Purpose |
|---|---|---|
| `sample_apod_response` | `test_nasa_client.py`, `test_dashboard.py` | Raw APOD image response |
| `sample_apod_video_response` | `test_nasa_client.py`, `test_dashboard.py` | Raw APOD video response |
| `sample_rover_response` | `test_nasa_client.py` | Raw Mars Rover Photos response |
| `sample_neo_response` | `test_nasa_client.py` | Raw NeoWs response (date-keyed dict) |
| `tmp_journal` | `test_journal.py` | Isolated temp path for journal CRUD |
| `sample_journal_entry` | `test_journal.py` | Payload for creating journal entries |

---

## Step 6: Create `tests/test_models.py`

**Reference:** Technical Specification section 11.4.

```python
from models import (
    APODData,
    JournalEntry,
    JournalFile,
    NearEarthObject,
    RoverPhoto,
    SpaceData,
)


def test_apod_data_image():
    """Construct APODData with media_type='image', verify all fields."""
    apod = APODData(
        title="Test Nebula",
        date="2026-04-25",
        explanation="A beautiful nebula...",
        media_type="image",
        url="https://apod.nasa.gov/image.jpg",
        copyright="Test Author",
    )
    assert apod.title == "Test Nebula"
    assert apod.media_type == "image"
    assert apod.copyright == "Test Author"


def test_apod_data_video():
    """Construct APODData with media_type='video' and thumbnail_url."""
    apod = APODData(
        title="Test Video",
        date="2026-04-25",
        explanation="An amazing video...",
        media_type="video",
        url="https://www.youtube.com/embed/dQw4w9WgXcQ",
        thumbnail_url="https://img.youtube.com/vi/dQw4w9WgXcQ/0.jpg",
    )
    assert apod.media_type == "video"
    assert apod.thumbnail_url is not None


def test_apod_data_optional_fields():
    """Verify thumbnail_url and copyright default to None."""
    apod = APODData(
        title="Test",
        date="2026-04-25",
        explanation="Test",
        media_type="image",
        url="https://example.com/img.jpg",
    )
    assert apod.thumbnail_url is None
    assert apod.copyright is None


def test_rover_photo():
    """Construct RoverPhoto, verify id is string."""
    photo = RoverPhoto(
        id="12345",
        rover="Curiosity",
        camera="Navigation Camera",
        earth_date="2026-04-20",
        sol=4100,
        img_src="https://mars.nasa.gov/photo.jpg",
    )
    assert isinstance(photo.id, str)
    assert photo.rover == "Curiosity"
    assert photo.sol == 4100


def test_near_earth_object_hazardous():
    """Construct NearEarthObject with is_potentially_hazardous=True."""
    neo = NearEarthObject(
        id="54321",
        name="2026 AB1",
        close_approach_date="2026-04-25",
        miss_distance_km=7500000.123,
        relative_velocity_kph=45000.567,
        estimated_diameter_meters_min=100.0,
        estimated_diameter_meters_max=250.0,
        is_potentially_hazardous=True,
    )
    assert neo.is_potentially_hazardous is True
    assert neo.miss_distance_km == 7500000.123


def test_near_earth_object_safe():
    """Construct NearEarthObject with is_potentially_hazardous=False."""
    neo = NearEarthObject(
        id="99999",
        name="2026 XY9",
        close_approach_date="2026-04-26",
        miss_distance_km=50000000.0,
        relative_velocity_kph=10000.0,
        estimated_diameter_meters_min=10.0,
        estimated_diameter_meters_max=20.0,
        is_potentially_hazardous=False,
    )
    assert neo.is_potentially_hazardous is False


def test_space_data_partial():
    """Construct SpaceData with apod=None and non-empty errors."""
    data = SpaceData(
        apod=None,
        errors=["APOD rate limited (429). Try again later."],
    )
    assert data.apod is None
    assert len(data.errors) == 1
    assert data.rover_photos == []
    assert data.near_earth_objects == []


def test_journal_entry():
    """Construct JournalEntry with all fields."""
    entry = JournalEntry(
        id="apod-2026-04-25-a1b2c3",
        type="apod",
        title="Test Nebula",
        date="2026-04-25",
        tags=["mars-week"],
        notes="Test note",
        source_url="https://apod.nasa.gov/image.jpg",
        metadata={"explanation": "A beautiful nebula..."},
        created_at="2026-04-25T10:30:00+00:00",
        updated_at="2026-04-25T10:30:00+00:00",
    )
    assert entry.id == "apod-2026-04-25-a1b2c3"
    assert entry.type == "apod"
    assert "mars-week" in entry.tags


def test_journal_entry_defaults():
    """Verify default empty lists/strings."""
    entry = JournalEntry(
        id="test-id",
        type="rover_photo",
        title="Test",
        date="2026-04-25",
    )
    assert entry.tags == []
    assert entry.notes == ""
    assert entry.source_url == ""
    assert entry.metadata == {}
    assert entry.created_at == ""
    assert entry.updated_at == ""


def test_journal_file_empty():
    """Construct JournalFile with no entries."""
    journal = JournalFile()
    assert journal.entries == []
```

### Test Summary

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_apod_data_image` | Image APOD construction, field access |
| 2 | `test_apod_data_video` | Video APOD with `thumbnail_url` populated |
| 3 | `test_apod_data_optional_fields` | `thumbnail_url` and `copyright` default to `None` |
| 4 | `test_rover_photo` | `id` is stored as `str`, field values correct |
| 5 | `test_near_earth_object_hazardous` | Hazardous NEO, `float` fields preserved |
| 6 | `test_near_earth_object_safe` | Safe NEO, `is_potentially_hazardous=False` |
| 7 | `test_space_data_partial` | Partial results: `apod=None` with errors list |
| 8 | `test_journal_entry` | Full entry with all fields populated |
| 9 | `test_journal_entry_defaults` | Default values for optional fields |
| 10 | `test_journal_file_empty` | Empty journal file wrapper |

---

## Verification

```bash
cd CosmoLog
uv sync
uv run pytest tests/test_models.py -v
uv run ruff check models.py tests/
uv run ruff format --check models.py tests/
```

All 10 tests should pass. Lint and format should be clean.

---

## Spec References

- Tech spec section 3: Data Models
- Tech spec section 3.1: Design Notes
- Tech spec section 11.3: conftest.py fixtures
- Tech spec section 11.4: test_models.py test table
- Functional spec section 10: Data Storage Specification
- Functional spec section 11: API Response Normalization

---

## Commit

```
feat: add Pydantic data models and test fixtures
```
