import json
from typing import Any

from prefab_ui.app import PrefabApp

from dashboard import build_dashboard

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


def find_components(data: Any, component_type: str) -> list[dict[str, Any]]:
    """Recursively find all components of a given type in a serialized tree."""
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


def test_build_dashboard_returns_prefab_app():
    result = build_dashboard()

    assert isinstance(result, PrefabApp)
    assert result.state == {"tag_filter": ""}


def test_build_dashboard_with_image_apod():
    result = build_dashboard(space_data=IMAGE_SPACE_DATA)
    tree = result.to_json()

    images = find_components(tree, "Image")
    embeds = find_components(tree, "Embed")

    assert len(images) >= 1
    assert not embeds
    assert "Test Nebula" in json.dumps(tree)


def test_build_dashboard_with_video_apod():
    result = build_dashboard(space_data=VIDEO_SPACE_DATA)
    tree = result.to_json()

    embeds = find_components(tree, "Embed")

    assert len(embeds) == 1
    assert embeds[0]["url"] == "https://www.youtube.com/embed/dQw4w9WgXcQ"


def test_build_dashboard_empty_data():
    result = build_dashboard(space_data=None, journal_entries=None)
    tree_str = json.dumps(result.to_json())

    assert isinstance(result, PrefabApp)
    assert "No APOD data available" in tree_str
    assert "No rover photos available" in tree_str
    assert "No journal entries yet" in tree_str


def test_build_dashboard_with_journal_entries():
    result = build_dashboard(journal_entries=SAMPLE_JOURNAL_ENTRIES, tag_filter="mars-week")
    tree = result.to_json()
    tree_str = json.dumps(tree)
    buttons = find_components(tree, "Button")

    assert result.state == {"tag_filter": "mars-week"}
    assert "Filter: mars-week" in tree_str
    assert "Test Nebula" in tree_str
    assert "toolCall" in tree_str
    assert "sendMessage" in tree_str
    assert "manage_space_journal" in tree_str
    assert any(button["label"] == "Edit" for button in buttons)
    assert any(button["label"] == "Delete" for button in buttons)


def test_build_dashboard_with_neo_data():
    result = build_dashboard(space_data=IMAGE_SPACE_DATA)
    tree = result.to_json()
    table_rows = find_components(tree, "TableRow")

    assert len(table_rows) >= 3
    assert "7,500,000" in json.dumps(tree)


def test_build_dashboard_hazardous_badges():
    result = build_dashboard(space_data=IMAGE_SPACE_DATA)
    tree_str = json.dumps(result.to_json())

    assert "Hazardous" in tree_str
    assert "Safe" in tree_str
