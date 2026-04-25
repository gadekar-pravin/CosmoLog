# Phase 3: NASA API Client

## Goal

Implement the httpx-based NASA API client with in-memory caching, response normalization, and graceful error handling. This satisfies the internet/API requirement from the functional specification.

## What This Phase Delivers

- `nasa_client.py` -- `NASAClient` class with fetch methods, caching, normalization, and error handling
- `tests/test_nasa_client.py` -- 13 tests using `@respx.mock` to intercept httpx requests (no real API calls)

## Prerequisites

- Phase 1 complete (`models.py` with `APODData`, `RoverPhoto`, `NearEarthObject`, `SpaceData`)

## Acceptance Criteria

- [ ] `NASAClient` fetches from 3 NASA APIs: APOD, Mars Rover Photos, NeoWs
- [ ] In-memory cache with 5-minute TTL avoids redundant API calls
- [ ] All API responses are normalized into Pydantic model instances
- [ ] Errors are collected into `SpaceData.errors` -- the tool never raises exceptions
- [ ] Partial failures return partial results (e.g., APOD succeeds but NeoWs fails)
- [ ] Rover photos fall back to `/latest_photos` when a specific sol returns empty
- [ ] `uv run pytest tests/test_nasa_client.py -v` shows 13 passed
- [ ] `uv run pytest -v` shows no regressions from Phases 1-2
- [ ] Satisfies functional spec section 13.1 (Internet/API Requirement)

---

## Step 1: Create `nasa_client.py`

**Reference:** Technical Specification sections 4.1 -- 4.5.

### Endpoint Specifications

#### APOD (Astronomy Picture of the Day)

| Detail | Value |
|---|---|
| URL | `https://api.nasa.gov/planetary/apod` |
| Method | `GET` |
| Auth | `api_key` query parameter |
| Key params | `date` (YYYY-MM-DD, default: today), `thumbs` (boolean, default: true) |

#### Mars Rover Photos

| Detail | Value |
|---|---|
| URL (by sol) | `https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/photos` |
| URL (latest) | `https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/latest_photos` |
| Method | `GET` |
| Key params | `sol` (int), `page` (int, default: 1) |

**Fallback:** If a specific `sol` returns zero photos, retry using the `/latest_photos` endpoint.

#### NeoWs (Near Earth Object Web Service)

| Detail | Value |
|---|---|
| URL | `https://api.nasa.gov/neo/rest/v1/feed` |
| Method | `GET` |
| Key params | `start_date` (YYYY-MM-DD), `end_date` (YYYY-MM-DD) |

**Response structure:** `near_earth_objects` dict keyed by date string. Must be flattened into a single list.

### Class Skeleton

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
```

### Cache Methods

```python
def _get_cached(self, key: str) -> object | None:
    if key in self._cache:
        ts, value = self._cache[key]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return value
        del self._cache[key]
    return None

def _set_cached(self, key: str, value: object) -> None:
    self._cache[key] = (time.time(), value)
```

**Cache key format:**
- APOD: `"apod:{date}"` (e.g., `"apod:2026-04-25"`)
- Rover: `"rover:{rover}:{sol|latest}"` (e.g., `"rover:curiosity:latest"`)
- NEO: `"neo:{start_date}:{days}"` (e.g., `"neo:2026-04-25:7"`)

### Response Normalization

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

**Important:** `miss_distance_km` and `relative_velocity_kph` require explicit `float()` cast because NASA returns these as strings (e.g., `"7500000.123"`).

### Individual Fetch Methods

Each method should:
1. Check cache first (`_get_cached`)
2. Make HTTP request with `self.client.get(url, params={...})`
3. Call `response.raise_for_status()`
4. Normalize response
5. Store in cache (`_set_cached`)
6. Return normalized data

#### `_fetch_apod(date: str | None = None) -> APODData`

- URL: `https://api.nasa.gov/planetary/apod`
- Params: `{"api_key": self.api_key, "thumbs": "true"}`, add `"date": date` if provided
- Cache key: `"apod:{date or 'today'}"`

#### `_fetch_rover_photos(rover: str, sol: int | None, count: int) -> list[RoverPhoto]`

- If `sol` is provided: URL `https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/photos`, params include `sol`
- If `sol` is `None`: go directly to latest endpoint
- Response key: `"photos"` (sol endpoint) or `"latest_photos"` (latest endpoint)
- **Fallback:** If sol-specific result is empty, retry with URL `.../latest_photos`
- Slice to `[:count]` photos
- Cache key: `"rover:{rover}:{sol or 'latest'}"`

#### `_fetch_neos(days: int) -> list[NearEarthObject]`

- URL: `https://api.nasa.gov/neo/rest/v1/feed`
- Params: `{"api_key": self.api_key, "start_date": today_str, "end_date": end_str}`
- **Flattening:** Iterate all date keys in `response["near_earth_objects"]`, collect NEOs into flat list
- Skip NEOs with empty `close_approach_data` (wrap individual NEO normalization in try/except)
- Cache key: `"neo:{start_date}:{days}"`

### Main Entry Point

```python
def fetch_all(
    self,
    apod_date: str | None = None,
    rover: str = "curiosity",
    sol: int | None = None,
    photo_count: int = 3,
    neo_days: int = 7,
) -> SpaceData:
    """Fetch all NASA data, collecting partial results and errors."""
    errors: list[str] = []
    apod = None
    rover_photos: list[RoverPhoto] = []
    neos: list[NearEarthObject] = []

    # Fetch APOD -- try/except, append to errors on failure
    # Fetch rover photos -- try/except, append to errors on failure
    # Fetch NEOs -- try/except, append to errors on failure

    return SpaceData(
        apod=apod,
        rover_photos=rover_photos,
        near_earth_objects=neos,
        errors=errors,
    )
```

### Error Handling

Each individual API call is wrapped in try/except within `fetch_all`. The tool never raises exceptions.

| Error Type | Source | Error Message |
|---|---|---|
| `httpx.HTTPStatusError` (429) | Rate limit exceeded | `"{api_name} rate limited (429). Try again later."` |
| `httpx.HTTPStatusError` (403) | Invalid API key | `"Invalid NASA API key (403)."` |
| `httpx.HTTPStatusError` (other) | Server errors | `"{api_name} returned HTTP {status}"` |
| `httpx.RequestError` | Network failure | `"{api_name} network error: {message}"` |
| `KeyError` / `IndexError` | Unexpected response shape | `"{api_name} returned unexpected data format"` |

---

## Step 2: Create `tests/test_nasa_client.py`

**Reference:** Technical Specification section 11.5.

All tests use `@respx.mock` decorator to intercept httpx requests. No real NASA API calls are made.

```python
import respx
from httpx import ConnectError, Response

from nasa_client import NASAClient


@respx.mock
def test_fetch_apod_success(sample_apod_response):
    """Mock APOD endpoint, verify APODData fields."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json=sample_apod_response)
    )
    # Mock rover and NEO endpoints too (fetch_all calls all three)
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(200, json={"latest_photos": []})
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json={"near_earth_objects": {}})
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()
    assert result.apod is not None
    assert result.apod.title == "Test Nebula"
    assert result.apod.media_type == "image"
    assert result.apod.copyright == "Test Author"


@respx.mock
def test_fetch_apod_video(sample_apod_video_response):
    """Mock APOD with media_type='video', verify thumbnail_url is set."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json=sample_apod_video_response)
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(200, json={"latest_photos": []})
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json={"near_earth_objects": {}})
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()
    assert result.apod is not None
    assert result.apod.media_type == "video"
    assert result.apod.thumbnail_url is not None


@respx.mock
def test_fetch_rover_photos_success(sample_apod_response, sample_rover_response):
    """Mock rover endpoint, verify photo list and count limit."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json=sample_apod_response)
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(200, json={"latest_photos": sample_rover_response["photos"]})
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json={"near_earth_objects": {}})
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all(photo_count=3)
    assert len(result.rover_photos) == 1  # only 1 photo in fixture
    assert result.rover_photos[0].id == "12345"
    assert result.rover_photos[0].rover == "Curiosity"


@respx.mock
def test_fetch_rover_latest_fallback(sample_apod_response, sample_rover_response):
    """Mock sol endpoint returning empty, verify /latest_photos fallback is used."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json=sample_apod_response)
    )
    # Sol-specific endpoint returns empty
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=Response(200, json={"photos": []})
    )
    # Latest endpoint has photos
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(200, json={"latest_photos": sample_rover_response["photos"]})
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json={"near_earth_objects": {}})
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all(sol=9999)  # sol that returns empty
    assert len(result.rover_photos) == 1  # got photo from fallback


@respx.mock
def test_fetch_neo_success(sample_apod_response, sample_neo_response):
    """Mock NeoWs, verify flattening of date-keyed response."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json=sample_apod_response)
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(200, json={"latest_photos": []})
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json=sample_neo_response)
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()
    assert len(result.near_earth_objects) == 1
    assert result.near_earth_objects[0].name == "2026 AB1"


@respx.mock
def test_fetch_neo_hazardous_flag(sample_apod_response, sample_neo_response):
    """Verify is_potentially_hazardous maps from is_potentially_hazardous_asteroid."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json=sample_apod_response)
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(200, json={"latest_photos": []})
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json=sample_neo_response)
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()
    assert result.near_earth_objects[0].is_potentially_hazardous is True
    assert result.near_earth_objects[0].miss_distance_km == 7500000.123


@respx.mock
def test_rate_limit_429():
    """Mock 429 response, verify error message in SpaceData.errors."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(429)
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(429)
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(429)
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()
    assert result.apod is None
    assert len(result.errors) > 0
    assert any("429" in e for e in result.errors)


@respx.mock
def test_invalid_key_403():
    """Mock 403 response, verify error message."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(403)
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(403)
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(403)
    )
    client = NASAClient(api_key="INVALID_KEY")
    result = client.fetch_all()
    assert len(result.errors) > 0
    assert any("403" in e for e in result.errors)


@respx.mock
def test_network_error():
    """Mock httpx.ConnectError, verify graceful error collection."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        side_effect=ConnectError("Connection refused")
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        side_effect=ConnectError("Connection refused")
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        side_effect=ConnectError("Connection refused")
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()
    assert result.apod is None
    assert len(result.errors) >= 3
    assert any("network error" in e.lower() for e in result.errors)


@respx.mock
def test_empty_response():
    """Mock empty JSON body, verify no crash."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json={})
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(200, json={})
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json={})
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()
    # Should not crash; errors collected for unexpected format
    assert isinstance(result, type(result))  # SpaceData returned


@respx.mock
def test_caching(sample_apod_response, sample_rover_response, sample_neo_response):
    """Call fetch_all twice, verify only one HTTP request per endpoint (cache hit)."""
    apod_route = respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json=sample_apod_response)
    )
    rover_route = respx.get(
        "https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos"
    ).mock(
        return_value=Response(200, json={"latest_photos": sample_rover_response["photos"]})
    )
    neo_route = respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json=sample_neo_response)
    )
    client = NASAClient(api_key="TEST_KEY")
    client.fetch_all()
    client.fetch_all()
    assert apod_route.call_count == 1
    assert rover_route.call_count == 1
    assert neo_route.call_count == 1


@respx.mock
def test_cache_expiry(monkeypatch, sample_apod_response, sample_rover_response, sample_neo_response):
    """Advance time past TTL (300s), verify cache miss triggers new request."""
    import nasa_client as nc

    apod_route = respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json=sample_apod_response)
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(200, json={"latest_photos": sample_rover_response["photos"]})
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json=sample_neo_response)
    )

    # First call at time T
    monkeypatch.setattr(nc.time, "time", lambda: 1000.0)
    client = NASAClient(api_key="TEST_KEY")
    client.fetch_all()

    # Second call at time T + 301 (past TTL)
    monkeypatch.setattr(nc.time, "time", lambda: 1301.0)
    client.fetch_all()

    # APOD route should be called twice (cache expired)
    assert apod_route.call_count == 2


@respx.mock
def test_partial_failure(sample_apod_response):
    """APOD succeeds, rover fails -- verify partial SpaceData."""
    respx.get("https://api.nasa.gov/planetary/apod").mock(
        return_value=Response(200, json=sample_apod_response)
    )
    respx.get("https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos").mock(
        return_value=Response(500)
    )
    respx.get("https://api.nasa.gov/neo/rest/v1/feed").mock(
        return_value=Response(200, json={"near_earth_objects": {}})
    )
    client = NASAClient(api_key="TEST_KEY")
    result = client.fetch_all()
    # APOD should succeed
    assert result.apod is not None
    assert result.apod.title == "Test Nebula"
    # Rover should fail
    assert result.rover_photos == []
    # Should have at least one error for rover
    assert len(result.errors) >= 1
```

### Test Summary

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_fetch_apod_success` | APOD image fetch and normalization |
| 2 | `test_fetch_apod_video` | APOD video with `thumbnail_url` |
| 3 | `test_fetch_rover_photos_success` | Rover photo fetch, id cast to str, count limit |
| 4 | `test_fetch_rover_latest_fallback` | Empty sol -> fallback to `/latest_photos` |
| 5 | `test_fetch_neo_success` | NeoWs date-keyed dict flattening |
| 6 | `test_fetch_neo_hazardous_flag` | `is_potentially_hazardous_asteroid` -> `is_potentially_hazardous` |
| 7 | `test_rate_limit_429` | 429 error collected in `SpaceData.errors` |
| 8 | `test_invalid_key_403` | 403 error collected gracefully |
| 9 | `test_network_error` | `ConnectError` handled without crash |
| 10 | `test_empty_response` | Empty JSON body doesn't crash |
| 11 | `test_caching` | Second call uses cache (no duplicate HTTP request) |
| 12 | `test_cache_expiry` | Time past TTL invalidates cache |
| 13 | `test_partial_failure` | APOD OK + rover 500 -> partial results |

### Key Testing Pattern: Mocking All Three Endpoints

Since `fetch_all()` calls all three NASA APIs, every test must mock all three endpoints -- even if you're only testing one. Unmocked routes will cause `respx` to raise `ConnectionError` by default, which would pollute your error assertions.

---

## Verification

```bash
cd CosmoLog
uv run pytest tests/test_nasa_client.py -v
uv run pytest -v  # no regressions
uv run ruff check nasa_client.py tests/test_nasa_client.py
uv run ruff format --check nasa_client.py tests/test_nasa_client.py
```

All 13 tests should pass (34 total including Phases 1-2).

---

## Spec References

- Tech spec section 4.1: Endpoint Specifications (APOD, Rover, NeoWs)
- Tech spec section 4.2: Client Implementation
- Tech spec section 4.3: Response Normalization Logic
- Tech spec section 4.4: Error Handling
- Tech spec section 4.5: Caching Strategy
- Tech spec section 11.5: test_nasa_client.py test table
- Functional spec section 4.2: Fetch Space Data
- Functional spec section 13.1: Internet/API Requirement

---

## Commit

```
feat: implement NASA API client with caching and error handling
```
