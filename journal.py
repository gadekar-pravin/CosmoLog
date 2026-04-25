from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

JOURNAL_PATH = Path(__file__).parent / "space_journal.json"

PROTECTED_UPDATE_FIELDS = {"id", "type", "created_at", "updated_at"}


def _generate_id(entry_type: str, entry_date: str) -> str:
    short_uuid = uuid.uuid4().hex[:6]
    return f"{entry_type}-{entry_date}-{short_uuid}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _read_journal(path: Path | None = None) -> dict[str, Any]:
    """Read journal file. Returns an empty journal if missing or corrupted."""
    p = path or JOURNAL_PATH
    if not p.exists():
        return {"entries": []}

    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("journal_corrupted path=%s", p)
        return {"entries": []}

    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        logger.warning("journal_corrupted path=%s", p)
        return {"entries": []}

    return data


def _write_journal(data: dict[str, Any], path: Path | None = None) -> None:
    """Write journal data to file."""
    p = path or JOURNAL_PATH
    p.write_text(json.dumps(data, indent=2))
    logger.debug("journal_write path=%s", p)


def create_entry(payload: dict[str, Any], *, journal_path: Path | None = None) -> dict[str, Any]:
    """Create a new journal entry. Returns {"status": "success", "entry": {...}}."""
    logger.info("create_entry type=%s title=%s", payload.get("type"), payload.get("title"))
    try:
        data = _read_journal(journal_path)
        now = _now_iso()
        entry = {
            **payload,
            "id": _generate_id(payload["type"], payload["date"]),
            "created_at": now,
            "updated_at": now,
        }
        data["entries"].append(entry)
        _write_journal(data, journal_path)
    except KeyError as exc:
        logger.warning("create_entry_missing_field field=%s", exc.args[0])
        return {"status": "error", "message": f"Missing required field: {exc.args[0]}"}
    except OSError as exc:
        logger.error("create_entry_error", exc_info=True)
        return {"status": "error", "message": str(exc)}

    logger.info("create_entry_success id=%s", entry["id"])
    return {"status": "success", "entry": entry}


def read_entries(
    *, tag_filter: str | None = None, journal_path: Path | None = None
) -> dict[str, Any]:
    """Read entries, optionally filtered by tag."""
    logger.info("read_entries tag_filter=%s", tag_filter)
    data = _read_journal(journal_path)
    entries = data["entries"]

    if tag_filter is not None:
        entries = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and isinstance(entry.get("tags"), list)
            and tag_filter in entry["tags"]
        ]

    logger.info("read_entries_done count=%d", len(entries))
    return {"status": "success", "entries": entries}


def update_entry(
    entry_id: str, payload: dict[str, Any], *, journal_path: Path | None = None
) -> dict[str, Any]:
    """Update an existing entry. Returns {"status": "success", "entry": {...}}."""
    logger.info("update_entry id=%s fields=%s", entry_id, list(payload.keys()))
    data = _read_journal(journal_path)

    for entry in data["entries"]:
        if not isinstance(entry, dict) or entry.get("id") != entry_id:
            continue

        for key, value in payload.items():
            if key not in PROTECTED_UPDATE_FIELDS:
                entry[key] = value
        entry["updated_at"] = _now_iso()

        try:
            _write_journal(data, journal_path)
        except OSError as exc:
            logger.error("update_entry_error id=%s", entry_id, exc_info=True)
            return {"status": "error", "message": str(exc)}

        logger.info("update_entry_success id=%s", entry_id)
        return {"status": "success", "entry": entry}

    logger.warning("update_entry_not_found id=%s", entry_id)
    return {"status": "error", "message": f"Entry '{entry_id}' not found"}


def delete_entry(entry_id: str, *, journal_path: Path | None = None) -> dict[str, Any]:
    """Delete an entry by ID. Returns {"status": "success", "deleted_id": "..."}."""
    logger.info("delete_entry id=%s", entry_id)
    data = _read_journal(journal_path)

    for index, entry in enumerate(data["entries"]):
        if not isinstance(entry, dict) or entry.get("id") != entry_id:
            continue

        del data["entries"][index]
        try:
            _write_journal(data, journal_path)
        except OSError as exc:
            logger.error("delete_entry_error id=%s", entry_id, exc_info=True)
            return {"status": "error", "message": str(exc)}

        logger.info("delete_entry_success id=%s", entry_id)
        return {"status": "success", "deleted_id": entry_id}

    logger.warning("delete_entry_not_found id=%s", entry_id)
    return {"status": "error", "message": f"Entry '{entry_id}' not found"}
