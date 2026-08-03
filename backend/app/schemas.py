"""Request and response shapes.

Response models are written by hand rather than dumped from the ORM. It is more
typing, and it means a column added to the database never leaks out of the API
by accident — password hashes and raw email addresses stay in.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import ParseConfidence, SkillLevel

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=60)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Pick a name people will recognise.")
        return cleaned


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str
    home_lat: float | None
    home_lng: float | None


class UpdateMeRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=60)
    home_lat: float | None = Field(default=None, ge=-90, le=90)
    home_lng: float | None = Field(default=None, ge=-180, le=180)


# ---------------------------------------------------------------------------
# Venues
# ---------------------------------------------------------------------------


class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    region: str
    lat: float
    lng: float


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


class GameOut(BaseModel):
    """One game as the feed shows it.

    `source_text` and `source_url` are always present because Kaki never becomes
    the source of truth: the deal is made in the Telegram thread, and every card
    has to be able to send you there.
    """

    id: int
    starts_at: datetime | None
    ends_at: datetime | None

    venue: VenueOut | None
    raw_venue: str | None

    price_cents: int | None
    spots_wanted: int | None
    skill: SkillLevel | None
    is_filled: bool
    confidence: ParseConfidence

    posted_at: datetime | None
    posted_by: str | None
    source_text: str
    source_url: str

    distance_km: float | None = None


class GameFeed(BaseModel):
    games: list[GameOut]
    total: int
    generated_at: datetime


# ---------------------------------------------------------------------------
# Saved searches
# ---------------------------------------------------------------------------


class SavedSearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    filters: dict = Field(default_factory=dict)


class SavedSearchOut(BaseModel):
    id: int
    name: str
    filters: dict
    created_at: datetime


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------


class IngestStatusOut(BaseModel):
    chat_id: str
    backfill_complete: bool
    last_run_at: datetime | None
    messages_seen: int
    games_extracted: int
    games_upcoming: int
