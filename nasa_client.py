from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

import httpx

from models import APODData, NASAImage, NearEarthObject, SpaceData

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300
NEGATIVE_CACHE_TTL_SECONDS = 60

APOD_URL = "https://api.nasa.gov/planetary/apod"
NASA_IMAGES_URL = "https://images-api.nasa.gov/search"
NEO_URL = "https://api.nasa.gov/neo/rest/v1/feed"

NASA_IMAGE_QUERIES = [
    "hubble deep field",
    "nebula",
    "saturn rings cassini",
    "international space station",
    "mars rover curiosity",
    "galaxy cluster",
    "earth from space",
    "james webb telescope",
    "apollo moon landing",
    "solar flare",
]


class NASAClient:
    """httpx-based NASA API client with in-memory caching."""

    def __init__(self, api_key: str = "DEMO_KEY") -> None:
        self.api_key = api_key
        self.client = httpx.Client(timeout=30.0)
        self._cache: dict[str, tuple[float, int, object]] = {}

    def _get_cached(self, key: str) -> object | None:
        if key in self._cache:
            timestamp, ttl, value = self._cache[key]
            if time.time() - timestamp < ttl:
                logger.debug("cache_hit key=%s", key)
                return value
            logger.debug("cache_expired key=%s", key)
            del self._cache[key]
        else:
            logger.debug("cache_miss key=%s", key)
        return None

    def _set_cached(self, key: str, value: object, ttl: int = CACHE_TTL_SECONDS) -> None:
        self._cache[key] = (time.time(), ttl, value)
        logger.debug("cache_set key=%s ttl=%d", key, ttl)

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

    def _normalize_nasa_image(self, item: dict[str, Any]) -> NASAImage:
        data = item["data"][0]
        links = item.get("links", [])
        img_src = ""
        for link in links:
            if link.get("rel") == "preview":
                img_src = link["href"]
                break
        return NASAImage(
            nasa_id=data["nasa_id"],
            title=data["title"],
            date_created=data["date_created"][:10],
            description=data.get("description", ""),
            center=data.get("center", ""),
            img_src=img_src,
            keywords=data.get("keywords", []),
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

        logger.info("fetch endpoint=apod date=%s", apod_date)
        params = {"api_key": self.api_key, "thumbs": "true"}
        if apod_date is not None:
            params["date"] = apod_date

        response = self.client.get(APOD_URL, params=params)
        response.raise_for_status()
        logger.info("fetch_done endpoint=apod status=%d", response.status_code)
        apod = self._normalize_apod(response.json())
        self._set_cached(cache_key, apod)
        return apod

    def _fetch_nasa_images(self, query: str, count: int) -> list[NASAImage]:
        cache_key = f"images:{query}:{count}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        logger.info("fetch endpoint=images query=%s count=%d", query, count)
        try:
            response = self.client.get(
                NASA_IMAGES_URL,
                params={"q": query, "media_type": "image"},
            )
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.info("images_negative_cache query=%s", query)
            self._set_cached(cache_key, [], ttl=NEGATIVE_CACHE_TTL_SECONDS)
            raise

        items = response.json().get("collection", {}).get("items", [])
        nasa_images: list[NASAImage] = []
        for item in items[:count]:
            try:
                nasa_images.append(self._normalize_nasa_image(item))
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                logger.debug("image_normalize_skip error=%s", exc)
                continue

        logger.info("fetch_done endpoint=images image_count=%d", len(nasa_images))
        self._set_cached(cache_key, nasa_images)
        return nasa_images

    def _fetch_neos(self, days: int, count: int) -> list[NearEarthObject]:
        start_date = date.today()
        start_date_str = start_date.isoformat()
        cache_key = f"neo:{start_date_str}:{days}:{count}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        logger.info("fetch endpoint=neo start=%s end_days=%d", start_date_str, days)
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
        logger.info("fetch_done endpoint=neo status=%d", response.status_code)

        neos: list[NearEarthObject] = []
        for neo_list in response.json()["near_earth_objects"].values():
            for neo in neo_list:
                try:
                    neos.append(self._normalize_neo(neo))
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    logger.debug("neo_normalize_skip id=%s error=%s", neo.get("id"), exc)
                    continue

        neos.sort(key=lambda n: (not n.is_potentially_hazardous, n.miss_distance_km))
        neos = neos[:count]

        logger.info("fetch_done endpoint=neo neo_count=%d", len(neos))
        self._set_cached(cache_key, neos)
        return neos

    def fetch_all(
        self,
        apod_date: str | None = None,
        image_query: str | None = None,
        image_count: int = 3,
        neo_days: int = 7,
        neo_count: int = 10,
    ) -> SpaceData:
        """Fetch all NASA data, collecting partial results and errors."""
        if image_query is None:
            import random

            image_query = random.choice(NASA_IMAGE_QUERIES)
            logger.info("image_query_rotated resolved=%s", image_query)
        logger.info(
            "fetch_all date=%s image_query=%s image_count=%d neo_days=%d neo_count=%d",
            apod_date,
            image_query,
            image_count,
            neo_days,
            neo_count,
        )
        errors: list[str] = []
        apod: APODData | None = None
        nasa_images: list[NASAImage] = []
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
            msg = self._format_error("APOD", exc)
            logger.warning("fetch_all_error api=APOD error=%s", msg)
            errors.append(msg)

        try:
            nasa_images = self._fetch_nasa_images(image_query, image_count)
        except (
            httpx.HTTPStatusError,
            httpx.RequestError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            msg = self._format_error("NASA Images", exc)
            logger.warning("fetch_all_error api=NASAImages error=%s", msg)
            errors.append(msg)

        try:
            neos = self._fetch_neos(neo_days, neo_count)
        except (
            httpx.HTTPStatusError,
            httpx.RequestError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            msg = self._format_error("NeoWs", exc)
            logger.warning("fetch_all_error api=NeoWs error=%s", msg)
            errors.append(msg)

        logger.info(
            "fetch_all_done apod=%s image_count=%d neo_count=%d error_count=%d",
            apod is not None,
            len(nasa_images),
            len(neos),
            len(errors),
        )
        return SpaceData(
            apod=apod,
            nasa_images=nasa_images,
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
