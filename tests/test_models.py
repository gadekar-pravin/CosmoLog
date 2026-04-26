from models import (
    APODData,
    JournalEntry,
    JournalFile,
    NASAImage,
    NearEarthObject,
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


def test_nasa_image():
    """Construct NASAImage, verify fields."""
    image = NASAImage(
        nasa_id="PIA12345",
        title="Curiosity Rover Self-Portrait",
        date_created="2026-04-20",
        description="A self-portrait of the Curiosity rover.",
        center="JPL",
        img_src="https://images-assets.nasa.gov/image/PIA12345/PIA12345~thumb.jpg",
        keywords=["Mars", "Curiosity"],
    )
    assert image.nasa_id == "PIA12345"
    assert image.title == "Curiosity Rover Self-Portrait"
    assert "Mars" in image.keywords


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
    assert data.nasa_images == []
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
