from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class APODData(BaseModel):
    """Astronomy Picture of the Day."""

    title: str
    date: str
    explanation: str
    media_type: Literal["image", "video"]
    url: str
    thumbnail_url: str | None = None
    copyright: str | None = None


class NASAImage(BaseModel):
    """A single image from the NASA Image and Video Library."""

    nasa_id: str
    title: str
    date_created: str
    description: str = ""
    center: str = ""
    img_src: str
    keywords: list[str] = Field(default_factory=list)


class NearEarthObject(BaseModel):
    """A near-Earth asteroid or comet."""

    id: str
    name: str
    close_approach_date: str
    miss_distance_km: float
    relative_velocity_kph: float
    estimated_diameter_meters_min: float
    estimated_diameter_meters_max: float
    is_potentially_hazardous: bool


class SpaceData(BaseModel):
    """Composite result from all NASA APIs."""

    apod: APODData | None = None
    nasa_images: list[NASAImage] = Field(default_factory=list)
    near_earth_objects: list[NearEarthObject] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class JournalEntry(BaseModel):
    """A single journal entry."""

    id: str
    type: Literal["apod", "rover_photo"]
    title: str
    date: str
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    source_url: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class JournalFile(BaseModel):
    """Top-level wrapper for space_journal.json."""

    entries: list[JournalEntry] = Field(default_factory=list)
