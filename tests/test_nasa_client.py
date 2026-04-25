from __future__ import annotations

import respx
from httpx import ConnectError, Response

from models import SpaceData
from nasa_client import NASAClient

APOD_URL = "https://api.nasa.gov/planetary/apod"
ROVER_LATEST_URL = "https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos"
ROVER_SOL_URL = "https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/photos"
NEO_URL = "https://api.nasa.gov/neo/rest/v1/feed"


def _mock_empty_rover() -> None:
    respx.get(ROVER_LATEST_URL).mock(return_value=Response(200, json={"latest_photos": []}))


def _mock_empty_neos() -> None:
    respx.get(NEO_URL).mock(return_value=Response(200, json={"near_earth_objects": {}}))


@respx.mock
def test_fetch_apod_success(sample_apod_response):
    """Mock APOD endpoint, verify APODData fields."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    _mock_empty_rover()
    _mock_empty_neos()

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert result.apod is not None
    assert result.apod.title == "Test Nebula"
    assert result.apod.media_type == "image"
    assert result.apod.copyright == "Test Author"


@respx.mock
def test_fetch_apod_video(sample_apod_video_response):
    """Mock APOD with media_type='video', verify thumbnail_url is set."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_video_response))
    _mock_empty_rover()
    _mock_empty_neos()

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert result.apod is not None
    assert result.apod.media_type == "video"
    assert result.apod.thumbnail_url is not None


@respx.mock
def test_fetch_rover_photos_success(sample_apod_response, sample_rover_response):
    """Mock rover endpoint, verify photo list and count limit."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    respx.get(ROVER_LATEST_URL).mock(
        return_value=Response(200, json={"latest_photos": sample_rover_response["photos"]})
    )
    _mock_empty_neos()

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all(photo_count=3)

    assert len(result.rover_photos) == 1
    assert result.rover_photos[0].id == "12345"
    assert result.rover_photos[0].rover == "Curiosity"


@respx.mock
def test_fetch_rover_latest_fallback(sample_apod_response, sample_rover_response):
    """Mock sol endpoint returning empty, verify /latest_photos fallback is used."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    respx.get(ROVER_SOL_URL).mock(return_value=Response(200, json={"photos": []}))
    respx.get(ROVER_LATEST_URL).mock(
        return_value=Response(200, json={"latest_photos": sample_rover_response["photos"]})
    )
    _mock_empty_neos()

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all(sol=9999)

    assert len(result.rover_photos) == 1


@respx.mock
def test_fetch_neo_success(sample_apod_response, sample_neo_response):
    """Mock NeoWs, verify flattening of date-keyed response."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    _mock_empty_rover()
    respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert len(result.near_earth_objects) == 1
    assert result.near_earth_objects[0].name == "2026 AB1"


@respx.mock
def test_fetch_neo_hazardous_flag(sample_apod_response, sample_neo_response):
    """Verify is_potentially_hazardous maps from is_potentially_hazardous_asteroid."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    _mock_empty_rover()
    respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert result.near_earth_objects[0].is_potentially_hazardous is True
    assert result.near_earth_objects[0].miss_distance_km == 7500000.123


@respx.mock
def test_neo_count_sorts_and_slices(sample_apod_response):
    """Cap NEOs: hazardous first, then by closest distance, sliced to neo_count."""
    neo_response = {
        "near_earth_objects": {
            "2026-04-25": [
                {
                    "id": "1",
                    "name": "Hazardous Far",
                    "close_approach_data": [
                        {
                            "close_approach_date": "2026-04-25",
                            "miss_distance": {"kilometers": "9000000"},
                            "relative_velocity": {"kilometers_per_hour": "30000"},
                        }
                    ],
                    "estimated_diameter": {
                        "meters": {
                            "estimated_diameter_min": 100.0,
                            "estimated_diameter_max": 200.0,
                        }
                    },
                    "is_potentially_hazardous_asteroid": True,
                },
                {
                    "id": "2",
                    "name": "Safe Close",
                    "close_approach_data": [
                        {
                            "close_approach_date": "2026-04-25",
                            "miss_distance": {"kilometers": "1000000"},
                            "relative_velocity": {"kilometers_per_hour": "20000"},
                        }
                    ],
                    "estimated_diameter": {
                        "meters": {
                            "estimated_diameter_min": 50.0,
                            "estimated_diameter_max": 100.0,
                        }
                    },
                    "is_potentially_hazardous_asteroid": False,
                },
                {
                    "id": "3",
                    "name": "Safe Far",
                    "close_approach_data": [
                        {
                            "close_approach_date": "2026-04-25",
                            "miss_distance": {"kilometers": "8000000"},
                            "relative_velocity": {"kilometers_per_hour": "25000"},
                        }
                    ],
                    "estimated_diameter": {
                        "meters": {
                            "estimated_diameter_min": 75.0,
                            "estimated_diameter_max": 150.0,
                        }
                    },
                    "is_potentially_hazardous_asteroid": False,
                },
            ]
        }
    }
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    _mock_empty_rover()
    respx.get(NEO_URL).mock(return_value=Response(200, json=neo_response))

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all(neo_count=2)

    assert len(result.near_earth_objects) == 2
    assert result.near_earth_objects[0].name == "Hazardous Far"
    assert result.near_earth_objects[0].is_potentially_hazardous is True
    assert result.near_earth_objects[1].name == "Safe Close"
    assert result.near_earth_objects[1].miss_distance_km == 1_000_000.0


@respx.mock
def test_rate_limit_429():
    """Mock 429 response, verify error message in SpaceData.errors."""
    respx.get(APOD_URL).mock(return_value=Response(429))
    respx.get(ROVER_LATEST_URL).mock(return_value=Response(429))
    respx.get(NEO_URL).mock(return_value=Response(429))

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert result.apod is None
    assert len(result.errors) > 0
    assert any("429" in error for error in result.errors)


@respx.mock
def test_invalid_key_403():
    """Mock 403 response, verify error message."""
    respx.get(APOD_URL).mock(return_value=Response(403))
    respx.get(ROVER_LATEST_URL).mock(return_value=Response(403))
    respx.get(NEO_URL).mock(return_value=Response(403))

    client = NASAClient(api_key="INVALID_KEY")
    result = client.fetch_all()

    assert len(result.errors) > 0
    assert any("403" in error for error in result.errors)


@respx.mock
def test_network_error():
    """Mock httpx.ConnectError, verify graceful error collection."""
    respx.get(APOD_URL).mock(side_effect=ConnectError("Connection refused"))
    respx.get(ROVER_LATEST_URL).mock(side_effect=ConnectError("Connection refused"))
    respx.get(NEO_URL).mock(side_effect=ConnectError("Connection refused"))

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert result.apod is None
    assert len(result.errors) >= 3
    assert any("network error" in error.lower() for error in result.errors)


@respx.mock
def test_empty_response():
    """Mock empty JSON body, verify no crash."""
    respx.get(APOD_URL).mock(return_value=Response(200, json={}))
    respx.get(ROVER_LATEST_URL).mock(return_value=Response(200, json={}))
    respx.get(NEO_URL).mock(return_value=Response(200, json={}))

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert isinstance(result, SpaceData)
    assert len(result.errors) == 3
    assert all("unexpected data format" in error for error in result.errors)


@respx.mock
def test_caching(sample_apod_response, sample_rover_response, sample_neo_response):
    """Call fetch_all twice, verify only one HTTP request per endpoint."""
    apod_route = respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    rover_route = respx.get(ROVER_LATEST_URL).mock(
        return_value=Response(200, json={"latest_photos": sample_rover_response["photos"]})
    )
    neo_route = respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    client = NASAClient(api_key="TEST_KEY")
    client.fetch_all()
    client.fetch_all()

    assert apod_route.call_count == 1
    assert rover_route.call_count == 1
    assert neo_route.call_count == 1


@respx.mock
def test_cache_expiry(
    monkeypatch, sample_apod_response, sample_rover_response, sample_neo_response
):
    """Advance time past TTL (300s), verify cache miss triggers new request."""
    import nasa_client as nc

    apod_route = respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    respx.get(ROVER_LATEST_URL).mock(
        return_value=Response(200, json={"latest_photos": sample_rover_response["photos"]})
    )
    respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    monkeypatch.setattr(nc.time, "time", lambda: 1000.0)
    client = NASAClient(api_key="TEST_KEY")
    client.fetch_all()

    monkeypatch.setattr(nc.time, "time", lambda: 1301.0)
    client.fetch_all()

    assert apod_route.call_count == 2


@respx.mock
def test_partial_failure(sample_apod_response):
    """APOD succeeds, rover fails -- verify partial SpaceData."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    respx.get(ROVER_LATEST_URL).mock(return_value=Response(500))
    _mock_empty_neos()

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert result.apod is not None
    assert result.apod.title == "Test Nebula"
    assert result.rover_photos == []
    assert len(result.errors) >= 1
    assert "Mars Rover Photos returned HTTP 500" in result.errors
