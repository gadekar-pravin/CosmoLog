from __future__ import annotations

import respx
from httpx import ConnectError, Response

import nasa_client as nc
from models import SpaceData
from nasa_client import NASAClient

APOD_URL = "https://api.nasa.gov/planetary/apod"
NASA_IMAGES_URL = "https://images-api.nasa.gov/search"
NEO_URL = "https://api.nasa.gov/neo/rest/v1/feed"


def _mock_empty_images() -> None:
    respx.get(NASA_IMAGES_URL).mock(return_value=Response(200, json={"collection": {"items": []}}))


def _mock_empty_neos() -> None:
    respx.get(NEO_URL).mock(return_value=Response(200, json={"near_earth_objects": {}}))


@respx.mock
def test_fetch_apod_success(sample_apod_response):
    """Mock APOD endpoint, verify APODData fields."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    _mock_empty_images()
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
    _mock_empty_images()
    _mock_empty_neos()

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert result.apod is not None
    assert result.apod.media_type == "video"
    assert result.apod.thumbnail_url is not None


@respx.mock
def test_fetch_nasa_images_success(sample_apod_response, sample_nasa_images_response):
    """Mock images endpoint, verify image list populated."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    respx.get(NASA_IMAGES_URL).mock(return_value=Response(200, json=sample_nasa_images_response))
    _mock_empty_neos()

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all(image_query="test query", image_count=3)

    assert len(result.nasa_images) == 1
    assert result.nasa_images[0].nasa_id == "PIA12345"
    assert result.nasa_images[0].title == "Curiosity Rover Self-Portrait"


@respx.mock
def test_fetch_neo_success(sample_apod_response, sample_neo_response):
    """Mock NeoWs, verify flattening of date-keyed response."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    _mock_empty_images()
    respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert len(result.near_earth_objects) == 1
    assert result.near_earth_objects[0].name == "2026 AB1"


@respx.mock
def test_fetch_neo_hazardous_flag(sample_apod_response, sample_neo_response):
    """Verify is_potentially_hazardous maps from is_potentially_hazardous_asteroid."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    _mock_empty_images()
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
    _mock_empty_images()
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
    respx.get(NASA_IMAGES_URL).mock(return_value=Response(429))
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
    respx.get(NASA_IMAGES_URL).mock(return_value=Response(403))
    respx.get(NEO_URL).mock(return_value=Response(403))

    client = NASAClient(api_key="INVALID_KEY")
    result = client.fetch_all()

    assert len(result.errors) > 0
    assert any("403" in error for error in result.errors)


@respx.mock
def test_network_error():
    """Mock httpx.ConnectError, verify graceful error collection."""
    respx.get(APOD_URL).mock(side_effect=ConnectError("Connection refused"))
    respx.get(NASA_IMAGES_URL).mock(side_effect=ConnectError("Connection refused"))
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
    respx.get(NASA_IMAGES_URL).mock(return_value=Response(200, json={}))
    respx.get(NEO_URL).mock(return_value=Response(200, json={}))

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert isinstance(result, SpaceData)
    # APOD and NEO raise KeyError on {}, but images gracefully returns []
    assert len(result.errors) == 2
    assert all("unexpected data format" in error for error in result.errors)


@respx.mock
def test_caching(sample_apod_response, sample_nasa_images_response, sample_neo_response):
    """Call fetch_all twice, verify only one HTTP request per endpoint."""
    apod_route = respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    images_route = respx.get(NASA_IMAGES_URL).mock(
        return_value=Response(200, json=sample_nasa_images_response)
    )
    neo_route = respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    client = NASAClient(api_key="TEST_KEY")
    client.fetch_all(image_query="test query")
    client.fetch_all(image_query="test query")

    assert apod_route.call_count == 1
    assert images_route.call_count == 1
    assert neo_route.call_count == 1


@respx.mock
def test_cache_expiry(
    monkeypatch, sample_apod_response, sample_nasa_images_response, sample_neo_response
):
    """Advance time past TTL (300s), verify cache miss triggers new request."""

    apod_route = respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    respx.get(NASA_IMAGES_URL).mock(return_value=Response(200, json=sample_nasa_images_response))
    respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    monkeypatch.setattr(nc.time, "time", lambda: 1000.0)
    client = NASAClient(api_key="TEST_KEY")
    client.fetch_all()

    monkeypatch.setattr(nc.time, "time", lambda: 1301.0)
    client.fetch_all()

    assert apod_route.call_count == 2


@respx.mock
def test_partial_failure(sample_apod_response):
    """APOD succeeds, images fail -- verify partial SpaceData."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    respx.get(NASA_IMAGES_URL).mock(return_value=Response(500))
    _mock_empty_neos()

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert result.apod is not None
    assert result.apod.title == "Test Nebula"
    assert result.nasa_images == []
    assert len(result.errors) >= 1
    assert "NASA Images returned HTTP 500" in result.errors


@respx.mock
def test_images_negative_caching(sample_apod_response, sample_neo_response):
    """Images 404 is cached: second fetch_all skips HTTP, returns no images error."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    images_route = respx.get(NASA_IMAGES_URL).mock(return_value=Response(404))
    respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    client = NASAClient(api_key="TEST_KEY")
    result1 = client.fetch_all(image_query="test query")

    assert images_route.call_count == 1
    assert any("404" in e for e in result1.errors)

    result2 = client.fetch_all(image_query="test query")

    assert images_route.call_count == 1
    assert result2.nasa_images == []
    assert not any("Images" in e for e in result2.errors)


@respx.mock
def test_images_negative_cache_expiry(monkeypatch, sample_apod_response, sample_neo_response):
    """After NEGATIVE_CACHE_TTL_SECONDS, images 404 is retried."""
    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    images_route = respx.get(NASA_IMAGES_URL).mock(return_value=Response(404))
    respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    monkeypatch.setattr(nc.time, "time", lambda: 1000.0)
    client = NASAClient(api_key="TEST_KEY")
    client.fetch_all()

    assert images_route.call_count == 1

    monkeypatch.setattr(nc.time, "time", lambda: 1000.0 + nc.NEGATIVE_CACHE_TTL_SECONDS + 1)
    client.fetch_all()

    assert images_route.call_count == 2


@respx.mock
def test_default_query_uses_pool(sample_apod_response, sample_neo_response):
    """When image_query is omitted, fetch_all picks from NASA_IMAGE_QUERIES."""
    from nasa_client import NASA_IMAGE_QUERIES

    respx.get(APOD_URL).mock(return_value=Response(200, json=sample_apod_response))
    respx.get(NASA_IMAGES_URL).mock(return_value=Response(200, json={"collection": {"items": []}}))
    respx.get(NEO_URL).mock(return_value=Response(200, json=sample_neo_response))

    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()

    assert isinstance(result, SpaceData)
    # The resolved query must come from the pool — verify via the cache key
    cache_keys = list(client._cache.keys())
    image_cache_keys = [k for k in cache_keys if k.startswith("images:")]
    assert len(image_cache_keys) == 1
    resolved_query = image_cache_keys[0].split(":")[1]
    assert resolved_query in NASA_IMAGE_QUERIES
