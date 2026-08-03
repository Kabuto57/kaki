"""Database models.

The one structural decision worth understanding before changing anything here:
**raw messages and parsed games are separate tables.**

It would be simpler to parse each Telegram post on arrival and store only the
result. It would also mean that every improvement to the parser only applies to
posts that arrive after the deploy, and the months of history already collected
stay wrong forever. Since the parser is the part of this system most likely to
be wrong and most likely to be improved, that trade is unacceptable.

So `SourceMessage` is the immutable record of what the group actually said, and
`Game` is the current interpretation of it. Re-parsing is a local operation over
data we already hold: no re-fetching, no rate limits, no Telegram round trip.
`scripts/reparse.py` exists precisely to exploit this.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.types import UTCDateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SkillLevel(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

    @property
    def rank(self) -> int:
        return {"beginner": 0, "intermediate": 1, "advanced": 2}[self.value]


class GameSource(str, enum.Enum):
    """Where a game came from.

    Everything is TELEGRAM today. The field exists because the moment Kaki has
    its own users, some of them will want to post a game directly rather than
    going through the group, and retrofitting a source column onto a live table
    is a migration nobody enjoys. It costs one column now.
    """

    TELEGRAM = "telegram"
    NATIVE = "native"


class ParseConfidence(str, enum.Enum):
    """How much of a post the parser actually understood.

    Drives what the UI shows. A HIGH game can be displayed as a clean card; a
    PARTIAL one has to show the raw text alongside it, because we are guessing
    at something. Anything lower never reaches the feed.
    """

    HIGH = "high"          # date, time and a known venue
    PARTIAL = "partial"    # time plus one of date or venue
    LOW = "low"            # not enough to be useful


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


class SourceMessage(Base):
    """A message as it appeared in the group. Never edited, only superseded."""

    __tablename__ = "source_messages"
    __table_args__ = (
        UniqueConstraint("chat_id", "message_id", name="uq_source_chat_message"),
        Index("ix_source_posted", "posted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    chat_id: Mapped[str] = mapped_column(String(64), index=True)
    message_id: Mapped[int] = mapped_column(Integer)
    topic_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    author_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    author_username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    text: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(UTCDateTime)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    game: Mapped[Game | None] = relationship(
        back_populates="source_message", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def permalink(self) -> str:
        handle = self.chat_id.lstrip("@")
        if self.topic_id:
            return f"https://t.me/{handle}/{self.topic_id}/{self.message_id}"
        return f"https://t.me/{handle}/{self.message_id}"


class IngestCursor(Base):
    """Where the ingester got to, so restarts do not re-read the world."""

    __tablename__ = "ingest_cursors"

    chat_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_message_id: Mapped[int] = mapped_column(Integer, default=0)
    backfill_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )
    messages_seen: Mapped[int] = mapped_column(Integer, default=0)
    games_extracted: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# Core domain
# ---------------------------------------------------------------------------


class Venue(Base):
    """Curated, not parser-invented.

    Letting the parser mint venues from free text produces nine spellings of
    Choa Chu Kang and makes location filtering meaningless. Unmatched venue text
    is kept on the game as `raw_venue` instead, which keeps the post searchable
    without polluting the canonical list.
    """

    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(40), index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)

    games: Mapped[list[Game]] = relationship(back_populates="venue")


class Game(Base):
    """A playable session, as currently understood from its source message."""

    __tablename__ = "games"
    __table_args__ = (
        Index("ix_games_discovery", "starts_at", "confidence"),
        Index("ix_games_venue_time", "venue_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    source: Mapped[GameSource] = mapped_column(
        Enum(GameSource, native_enum=False), default=GameSource.TELEGRAM, index=True
    )
    source_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_messages.id", ondelete="CASCADE"), nullable=True, unique=True
    )

    # Parsed fields. All nullable: a post that omits the price is still a useful
    # game, and pretending otherwise would throw away most of the feed.
    starts_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, index=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    venue_id: Mapped[int | None] = mapped_column(
        ForeignKey("venues.id"), nullable=True, index=True
    )
    raw_venue: Mapped[str | None] = mapped_column(String(160), nullable=True)

    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spots_wanted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skill: Mapped[SkillLevel | None] = mapped_column(
        Enum(SkillLevel, native_enum=False), nullable=True
    )

    confidence: Mapped[ParseConfidence] = mapped_column(
        Enum(ParseConfidence, native_enum=False), default=ParseConfidence.LOW, index=True
    )

    # Set when a later post says the game filled up. We keep the row rather than
    # deleting it, because "this venue fills fast on Wednesdays" is worth knowing.
    is_filled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    parser_version: Mapped[int] = mapped_column(Integer, default=1)
    parsed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    source_message: Mapped[SourceMessage | None] = relationship(back_populates="game")
    venue: Mapped[Venue | None] = relationship(back_populates="games")


# ---------------------------------------------------------------------------
# Light accounts (saved searches only)
# ---------------------------------------------------------------------------


class User(Base):
    """Accounts exist for one reason: remembering what you are looking for.

    There is no host, no roster, and no joining inside Kaki, because joining
    happens in the Telegram thread where the game was offered. Building a
    parallel RSVP the host never sees would split the source of truth and get
    someone stood up.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(60))

    home_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_lng: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    saved_searches: Mapped[list[SavedSearch]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))

    # Stored as JSON text rather than columns because these are user-defined
    # filter shapes that will change as the app grows, and a schema migration
    # per new filter is not a reasonable cost.
    filters_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="saved_searches")
