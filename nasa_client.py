from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

import httpx

from models import APODData, NearEarthObject, RoverPhoto, SpaceData

CACHE_TTL_SECONDS = 300

APOD_URL = "https://api.nasa.gov/planetary/apod"
MARS_BASE_URL = "https://api.nasa.gov/mars-photos/api/v1/rovers"
NEO_URL = "https://api.nasa.gov/neo/rest/v1/feed"


class NASAClient:
    """httpx-based NASA API client with in-memory caching."""

    def __init__(self, api_key: str = "DEMO_KEY") -> None:
        self.api_key = api_key
        self.client = httpx.Client(timeout=30.0)
        self._cache: dict[str, tuple[float, object]] = {}

    def _get_cached(self, key: str) -> object | None:
        if key in self._cache:
            timestamp, value = self._cache[key]
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return value
            del self._cache[key]
        return None

    def _set_cached(self, key: str, value: object) -> None:
        self._cache[key] = (time.time(), value)

    def _normalize_apod(self, data: dict[str, Any]) -> APODData:
        return APODData(
            title=data["title"],
            date=data["date"],
            explanation=data["explanation"],
            media_type=data["media_type"],
            url=data["url"],
            thumbnail_url=data.get("thumbnail_url"),
            copyright=data.get("copyright"),
        )

    def _normalize_rover_photo(self, photo: dict[str, Any]) -> RoverPhoto:
        return RoverPhoto(
            id=str(photo["id"]),
            rover=photo["rover"]["name"],
            camera=photo["camera"]["full_name"],
            earth_date=photo["earth_date"],
            sol=photo["sol"],
            img_src=photo["img_src"],
        )

    def _normalize_neo(self, neo: dict[str, Any]) -> NearEarthObject:
        approach = neo["close_approach_data"][0]
        return NearEarthObject(
            id=neo["id"],
            name=neo["name"],
            close_approach_date=approach["close_approach_date"],
            miss_distance_km=float(approach["miss_distance"]["kilometers"]),
            relative_velocity_kph=float(approach["relative_velocity"]["kilometers_per_hour"]),
            estimated_diameter_meters_min=neo["estimated_diameter"]["meters"][
                "estimated_diameter_min"
            ],
            estimated_diameter_meters_max=neo["estimated_diameter"]["meters"][
                "estimated_diameter_max"
            ],
            is_potentially_hazardous=neo["is_potentially_hazardous_asteroid"],
        )

    def _fetch_apod(self, apod_date: str | None = None) -> APODData:
        cache_key = f"apod:{apod_date or 'today'}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        params = {"api_key": self.api_key, "thumbs": "true"}
        if apod_date is not None:
            params["date"] = apod_date

        response = self.client.get(APOD_URL, params=params)
        response.raise_for_status()
        apod = self._normalize_apod(response.json())
        self._set_cached(cache_key, apod)
        return apod

    def _fetch_rover_photos(self, rover: str, sol: int | None, count: int) -> list[RoverPhoto]:
        cache_key = f"rover:{rover}:{sol or 'latest'}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        photos_data: list[dict[str, Any]]
        if sol is not None:
            photos_data = self._request_rover_endpoint(rover, sol)
            if not photos_data:
                photos_data = self._request_rover_latest_endpoint(rover)
        else:
            photos_data = self._request_rover_latest_endpoint(rover)

        rover_photos = [self._normalize_rover_photo(photo) for photo in photos_data[:count]]
        self._set_cached(cache_key, rover_photos)
        return rover_photos

    def _request_rover_endpoint(self, rover: str, sol: int) -> list[dict[str, Any]]:
        response = self.client.get(
            f"{MARS_BASE_URL}/{rover}/photos",
            params={"api_key": self.api_key, "sol": sol, "page": 1},
        )
        response.raise_for_status()
        return response.json()["photos"]

    def _request_rover_latest_endpoint(self, rover: str) -> list[dict[str, Any]]:
        response = self.client.get(
            f"{MARS_BASE_URL}/{rover}/latest_photos",
            params={"api_key": self.api_key, "page": 1},
        )
        response.raise_for_status()
        return response.json()["latest_photos"]

    def _fetch_neos(self, days: int) -> list[NearEarthObject]:
        start_date = date.today()
        start_date_str = start_date.isoformat()
        cache_key = f"neo:{start_date_str}:{days}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        end_date_str = (start_date + timedelta(days=days)).isoformat()
        response = self.client.get(
            NEO_URL,
            params={
                "api_key": self.api_key,
                "start_date": start_date_str,
                "end_date": end_date_str,
            },
        )
        response.raise_for_status()

        neos: list[NearEarthObject] = []
        for neo_list in response.json()["near_earth_objects"].values():
            for neo in neo_list:
                try:
                    neos.append(self._normalize_neo(neo))
                except (KeyError, IndexError, TypeError, ValueError):
                    continue

        self._set_cached(cache_key, neos)
        return neos

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
        apod: APODData | None = None
        rover_photos: list[RoverPhoto] = []
        neos: list[NearEarthObject] = []

        try:
            apod = self._fetch_apod(apod_date)
        except (
            httpx.HTTPStatusError,
            httpx.RequestError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            errors.append(self._format_error("APOD", exc))

        try:
            rover_photos = self._fetch_rover_photos(rover, sol, photo_count)
        except (
            httpx.HTTPStatusError,
            httpx.RequestError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            errors.append(self._format_error("Mars Rover Photos", exc))

        try:
            neos = self._fetch_neos(neo_days)
        except (
            httpx.HTTPStatusError,
            httpx.RequestError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            errors.append(self._format_error("NeoWs", exc))

        return SpaceData(
            apod=apod,
            rover_photos=rover_photos,
            near_earth_objects=neos,
            errors=errors,
        )

    def _format_error(self, api_name: str, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            if status_code == 429:
                return f"{api_name} rate limited (429). Try again later."
            if status_code == 403:
                return "Invalid NASA API key (403)."
            return f"{api_name} returned HTTP {status_code}"

        if isinstance(exc, httpx.RequestError):
            return f"{api_name} network error: {exc}"

        return f"{api_name} returned unexpected data format"
