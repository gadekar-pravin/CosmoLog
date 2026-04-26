import pytest


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
def sample_nasa_images_response():
    """Raw NASA Image Library API response."""
    return {
        "collection": {
            "items": [
                {
                    "data": [
                        {
                            "nasa_id": "PIA12345",
                            "title": "Curiosity Rover Self-Portrait",
                            "date_created": "2026-04-20T00:00:00Z",
                            "description": "A self-portrait of the Curiosity rover.",
                            "center": "JPL",
                            "media_type": "image",
                            "keywords": ["Mars", "Curiosity"],
                        }
                    ],
                    "links": [
                        {
                            "href": "https://images-assets.nasa.gov/image/PIA12345/PIA12345~thumb.jpg",
                            "rel": "preview",
                            "render": "image",
                        }
                    ],
                }
            ]
        }
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
