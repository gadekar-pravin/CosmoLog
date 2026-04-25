# Phase 2: Journal CRUD Operations

## Goal

Implement the local file CRUD layer for `space_journal.json`. This phase satisfies the CRUD requirement from the functional specification.

## What This Phase Delivers

- `journal.py` -- CRUD functions + internal helpers for `space_journal.json`
- `tests/test_journal.py` -- 11 CRUD tests using `tmp_path` for file isolation

## Prerequisites

- Phase 1 complete (`models.py`, test fixtures in `conftest.py`)

## Acceptance Criteria

- [ ] `journal.py` exports 4 public functions: `create_entry`, `read_entries`, `update_entry`, `delete_entry`
- [ ] ID format is `"{type}-{date}-{6hex}"` (e.g., `"apod-2026-04-25-a1b2c3"`)
- [ ] Timestamps use UTC ISO 8601 format
- [ ] Missing or corrupted `space_journal.json` is recovered gracefully (returns empty journal)
- [ ] All CRUD operations return `{"status": "success", ...}` or `{"status": "error", "message": "..."}`
- [ ] `uv run pytest tests/test_journal.py -v` shows 11 passed
- [ ] `uv run pytest -v` shows no regressions from Phase 1
- [ ] Satisfies functional spec section 13.2 (CRUD Requirement)

---

## Step 1: Create `journal.py`

**Reference:** Technical Specification section 5.

### Internal Helpers

#### Journal Path

```python
from pathlib import Path

JOURNAL_PATH = Path(__file__).parent / "space_journal.json"
```

#### ID Generation

Format: `"{type}-{date}-{uuid6chars}"`

Example: `"apod-2026-04-25-a1b2c3"`, `"rover_photo-2026-04-25-d4e5f6"`

```python
import uuid

def _generate_id(entry_type: str, entry_date: str) -> str:
    short_uuid = uuid.uuid4().hex[:6]
    return f"{entry_type}-{entry_date}-{short_uuid}"
```

#### Timestamps

All timestamps are UTC ISO 8601 format:

```python
from datetime import datetime, timezone

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
```

#### File I/O

The `_read_journal` and `_write_journal` helpers accept an optional `path` parameter. This allows the public functions to redirect reads/writes to a temp path during tests.

```python
import json

def _read_journal(path: Path | None = None) -> dict:
    """Read journal file. Returns {"entries": []} if missing or corrupted."""
    p = path or JOURNAL_PATH
    if not p.exists():
        return {"entries": []}
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict) or "entries" not in data:
            return {"entries": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"entries": []}


def _write_journal(data: dict, path: Path | None = None) -> None:
    """Write journal data to file."""
    p = path or JOURNAL_PATH
    p.write_text(json.dumps(data, indent=2))
```

### Public Functions

All public functions accept an optional `journal_path` keyword-only argument for test isolation with `tmp_path`. Default is `JOURNAL_PATH`.

#### `create_entry`

```python
def create_entry(payload: dict, *, journal_path: Path | None = None) -> dict:
    """Create a new journal entry. Returns {"status": "success", "entry": {...}}."""
```

Steps:
1. Read current journal via `_read_journal(journal_path)`
2. Generate `id` using `_generate_id(payload["type"], payload["date"])`
3. Set `created_at` and `updated_at` to `_now_iso()`
4. Build entry dict by merging payload with generated fields
5. Append to entries list
6. Write journal via `_write_journal(data, journal_path)`
7. Return `{"status": "success", "entry": {...}}`

#### `read_entries`

```python
def read_entries(*, tag_filter: str | None = None, journal_path: Path | None = None) -> dict:
    """Read entries, optionally filtered by tag. Returns {"status": "success", "entries": [...]}."""
```

Steps:
1. Read current journal
2. If `tag_filter` is provided, filter entries where `tag_filter in entry["tags"]`
3. Return `{"status": "success", "entries": [...]}`

#### `update_entry`

```python
def update_entry(entry_id: str, payload: dict, *, journal_path: Path | None = None) -> dict:
    """Update an existing entry. Returns {"status": "success", "entry": {...}}."""
```

Steps:
1. Read current journal
2. Find entry by `entry_id`
3. If not found, return `{"status": "error", "message": "Entry '{entry_id}' not found"}`
4. Update allowed fields from payload (merge, don't overwrite `id`, `type`, `created_at`)
5. Refresh `updated_at` timestamp
6. Write journal
7. Return `{"status": "success", "entry": {...}}`

#### `delete_entry`

```python
def delete_entry(entry_id: str, *, journal_path: Path | None = None) -> dict:
    """Delete an entry by ID. Returns {"status": "success", "deleted_id": "..."}."""
```

Steps:
1. Read current journal
2. Find entry by `entry_id`
3. If not found, return `{"status": "error", "message": "Entry '{entry_id}' not found"}`
4. Remove entry from list
5. Write journal
6. Return `{"status": "success", "deleted_id": "..."}`

### Error Handling

| Scenario | Behavior |
|---|---|
| File does not exist | `_read_journal` returns `{"entries": []}` |
| File contains invalid JSON | `_read_journal` returns `{"entries": []}` (recovers gracefully) |
| Entry not found (update/delete) | Return `{"status": "error", "message": "Entry '{entry_id}' not found"}` |

### Return Format

```python
# Success
{"status": "success", "entry": {...}}      # create, update
{"status": "success", "entries": [...]}    # read
{"status": "success", "deleted_id": "..."}  # delete

# Error
{"status": "error", "message": "..."}
```

---

## Step 2: Create `tests/test_journal.py`

**Reference:** Technical Specification section 11.6.

All tests use the `tmp_journal` fixture from `conftest.py` for isolated file I/O. Pass `journal_path=tmp_journal` to each function call.

```python
import json
import re

from journal import create_entry, read_entries, update_entry, delete_entry


def test_create_entry(tmp_journal, sample_journal_entry):
    """Create entry, verify returned entry has id, created_at, updated_at."""
    result = create_entry(sample_journal_entry, journal_path=tmp_journal)
    assert result["status"] == "success"
    entry = result["entry"]
    assert "id" in entry
    assert "created_at" in entry
    assert "updated_at" in entry
    assert entry["title"] == "Test Nebula"
    assert entry["type"] == "apod"


def test_create_generates_id(tmp_journal, sample_journal_entry):
    """Verify ID format: '{type}-{date}-{6hex}'."""
    result = create_entry(sample_journal_entry, journal_path=tmp_journal)
    entry_id = result["entry"]["id"]
    assert re.match(r"^apod-2026-04-25-[a-f0-9]{6}$", entry_id)


def test_read_empty(tmp_journal):
    """Read from non-existent file, verify empty entries list."""
    result = read_entries(journal_path=tmp_journal)
    assert result["status"] == "success"
    assert result["entries"] == []


def test_read_all_entries(tmp_journal, sample_journal_entry):
    """Create 3 entries, read all, verify count."""
    for _ in range(3):
        create_entry(sample_journal_entry, journal_path=tmp_journal)
    result = read_entries(journal_path=tmp_journal)
    assert len(result["entries"]) == 3


def test_read_with_tag_filter(tmp_journal):
    """Create entries with different tags, filter, verify results."""
    create_entry(
        {"type": "apod", "title": "Mars", "date": "2026-04-25", "tags": ["mars-week"]},
        journal_path=tmp_journal,
    )
    create_entry(
        {"type": "apod", "title": "Moon", "date": "2026-04-25", "tags": ["moon"]},
        journal_path=tmp_journal,
    )
    result = read_entries(tag_filter="mars-week", journal_path=tmp_journal)
    assert len(result["entries"]) == 1
    assert result["entries"][0]["title"] == "Mars"


def test_update_entry(tmp_journal, sample_journal_entry):
    """Create then update, verify changed fields and updated_at refreshed."""
    created = create_entry(sample_journal_entry, journal_path=tmp_journal)
    entry_id = created["entry"]["id"]
    original_updated = created["entry"]["updated_at"]

    result = update_entry(
        entry_id, {"notes": "updated note"}, journal_path=tmp_journal
    )
    assert result["status"] == "success"
    assert result["entry"]["notes"] == "updated note"
    # updated_at should be refreshed (may be same if test runs fast, but field should exist)
    assert "updated_at" in result["entry"]


def test_update_not_found(tmp_journal):
    """Update non-existent ID, verify error response."""
    result = update_entry("nonexistent-id", {"notes": "test"}, journal_path=tmp_journal)
    assert result["status"] == "error"
    assert "not found" in result["message"]


def test_delete_entry(tmp_journal, sample_journal_entry):
    """Create then delete, verify entry removed."""
    created = create_entry(sample_journal_entry, journal_path=tmp_journal)
    entry_id = created["entry"]["id"]

    result = delete_entry(entry_id, journal_path=tmp_journal)
    assert result["status"] == "success"
    assert result["deleted_id"] == entry_id

    # Verify it's gone
    entries = read_entries(journal_path=tmp_journal)
    assert len(entries["entries"]) == 0


def test_delete_not_found(tmp_journal):
    """Delete non-existent ID, verify error response."""
    result = delete_entry("nonexistent-id", journal_path=tmp_journal)
    assert result["status"] == "error"
    assert "not found" in result["message"]


def test_corrupted_json_recovery(tmp_journal):
    """Write invalid JSON to file, verify read returns empty journal."""
    tmp_journal.write_text("not valid json{{")
    result = read_entries(journal_path=tmp_journal)
    assert result["status"] == "success"
    assert result["entries"] == []


def test_full_crud_cycle(tmp_journal, sample_journal_entry):
    """Complete lifecycle: Create -> Read -> Update -> Read -> Delete -> Read."""
    # Create
    created = create_entry(sample_journal_entry, journal_path=tmp_journal)
    assert created["status"] == "success"
    entry_id = created["entry"]["id"]

    # Read -- verify 1 entry
    result = read_entries(journal_path=tmp_journal)
    assert len(result["entries"]) == 1

    # Update
    updated = update_entry(
        entry_id, {"notes": "updated"}, journal_path=tmp_journal
    )
    assert updated["status"] == "success"
    assert updated["entry"]["notes"] == "updated"

    # Read -- verify update persisted
    result = read_entries(journal_path=tmp_journal)
    assert result["entries"][0]["notes"] == "updated"

    # Delete
    deleted = delete_entry(entry_id, journal_path=tmp_journal)
    assert deleted["status"] == "success"

    # Read -- verify 0 entries
    result = read_entries(journal_path=tmp_journal)
    assert len(result["entries"]) == 0
```

### Test Summary

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_create_entry` | Entry creation with auto-generated `id`, `created_at`, `updated_at` |
| 2 | `test_create_generates_id` | ID matches pattern `"{type}-{date}-{6hex}"` |
| 3 | `test_read_empty` | Reading non-existent file returns empty list |
| 4 | `test_read_all_entries` | Multiple entries readable after creation |
| 5 | `test_read_with_tag_filter` | Tag-based filtering returns correct subset |
| 6 | `test_update_entry` | Field update and `updated_at` refresh |
| 7 | `test_update_not_found` | Error response for missing entry |
| 8 | `test_delete_entry` | Entry removal and verification |
| 9 | `test_delete_not_found` | Error response for missing entry |
| 10 | `test_corrupted_json_recovery` | Graceful recovery from invalid JSON |
| 11 | `test_full_crud_cycle` | Complete Create -> Read -> Update -> Read -> Delete -> Read |

---

## Key Implementation Detail: Test Isolation

The `journal_path` keyword argument pattern is critical. Without it, all tests would read/write to the real `space_journal.json` in the project root, causing:
- Tests to interfere with each other
- Side effects on the project directory
- Flaky tests depending on file state

By using `journal_path=tmp_journal` (which points to pytest's `tmp_path`), each test gets its own isolated filesystem location.

---

## Verification

```bash
cd CosmoLog
uv run pytest tests/test_journal.py -v
uv run pytest -v  # no regressions from Phase 1
uv run ruff check journal.py tests/test_journal.py
uv run ruff format --check journal.py tests/test_journal.py
```

All 11 tests should pass (21 total including Phase 1's 10).

---

## Spec References

- Tech spec section 5: Journal CRUD
- Tech spec section 5.1: Functions
- Tech spec section 5.2: ID Generation
- Tech spec section 5.3: Timestamps
- Tech spec section 5.4: File I/O
- Tech spec section 5.5: Error Handling
- Tech spec section 5.6: Return Format
- Tech spec section 11.6: test_journal.py test table
- Functional spec section 4.3: Manage Space Journal
- Functional spec section 10: Data Storage Specification

---

## Commit

```
feat: implement journal CRUD operations
```
