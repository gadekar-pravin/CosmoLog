import re

from journal import create_entry, delete_entry, read_entries, update_entry


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

    result = update_entry(entry_id, {"notes": "updated note"}, journal_path=tmp_journal)
    assert result["status"] == "success"
    assert result["entry"]["notes"] == "updated note"
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
    created = create_entry(sample_journal_entry, journal_path=tmp_journal)
    assert created["status"] == "success"
    entry_id = created["entry"]["id"]

    result = read_entries(journal_path=tmp_journal)
    assert len(result["entries"]) == 1

    updated = update_entry(entry_id, {"notes": "updated"}, journal_path=tmp_journal)
    assert updated["status"] == "success"
    assert updated["entry"]["notes"] == "updated"

    result = read_entries(journal_path=tmp_journal)
    assert result["entries"][0]["notes"] == "updated"

    deleted = delete_entry(entry_id, journal_path=tmp_journal)
    assert deleted["status"] == "success"

    result = read_entries(journal_path=tmp_journal)
    assert len(result["entries"]) == 0
