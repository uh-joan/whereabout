from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class RawEvent(BaseModel):
    """Output of a source. Pre-normalisation, pre-geocoding."""
    source: str
    source_event_id: str
    source_url: str
    title: str
    date_start_utc: datetime
    date_end_utc: datetime | None = None
    venue_name: str
    venue_address: str | None = None
    venue_postcode: str | None = None
    venue_lat: float | None = None
    venue_lng: float | None = None
    artists: list[str] = Field(default_factory=list)
    genres_raw: list[str] = Field(default_factory=list)
    ticket_url: str | None = None
    price_text: str | None = None
    raw_payload: dict = Field(default_factory=dict)


class Venue(BaseModel):
    id: int | None = None
    name: str
    address: str | None = None
    postcode: str | None = None
    neighbourhood_id: int | None = None
    lat: float | None = None
    lng: float | None = None
    website: str | None = None
    source_url: str | None = None


class Artist(BaseModel):
    id: int | None = None
    name: str
    bio: str | None = None
    genres: list[str] = Field(default_factory=list)
    external_url: str | None = None
    last_enriched_at: datetime | None = None


class Neighbourhood(BaseModel):
    id: int | None = None
    name: str
    borough: str
    postcode_prefixes: list[str]
    lat: float
    lng: float
    aliases: list[str] = Field(default_factory=list)
    ward_aliases: list[str] = Field(default_factory=list)


class Event(BaseModel):
    """KB-stored event after normalisation."""
    id: int | None = None
    stable_hash: str
    title: str
    date_start_utc: datetime
    date_end_utc: datetime | None = None
    genres: list[str]
    venue: Venue
    artists: list[Artist] = Field(default_factory=list)
    ticket_url: str | None = None
    sources: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    scraped_at_utc: datetime


class EventDetail(Event):
    """Enriched view returned by detail command."""
    artist_bios: dict[str, str] = Field(default_factory=dict)
    venue_description: str | None = None
    similar_events: list[Event] = Field(default_factory=list)


class Query(BaseModel):
    raw_text: str
    genres: list[str] = Field(default_factory=list)
    neighbourhood: str | None = None
    date_range_start_utc: datetime
    date_range_end_utc: datetime
    limit: int = 50
