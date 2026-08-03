"""Turning Telegram messages into games.

Split deliberately into two halves that know nothing about each other:

* `record_message` stores what the group said. It talks to the database and has
  no opinion about badminton.
* `derive_game` interprets a stored message. It is pure with respect to
  Telegram: it never fetches anything, so it can be re-run over the whole table
  whenever the parser improves.

Keeping these apart is what makes `scripts/reparse.py` a five-line script
instead of a re-import.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ingest import parser
from app.ingest import venue_catalogue as catalogue
from app.models import (
    Game,
    GameSource,
    IngestCursor,
    ParseConfidence,
    SourceMessage,
    Venue,
)

log = logging.getLogger("kaki.ingest")


@dataclass
class IngestStats:
    messages_seen: int = 0
    messages_new: int = 0
    games_created: int = 0
    games_updated: int = 0
    skipped_unusable: int = 0

    def __str__(self) -> str:
        return (
            f"{self.messages_seen} seen, {self.messages_new} new, "
            f"{self.games_created} games, {self.skipped_unusable} not games"
        )


# ---------------------------------------------------------------------------
# Storing raw messages
# ---------------------------------------------------------------------------


def record_message(
    db: Session,
    *,
    chat_id: str,
    message_id: int,
    text: str,
    posted_at: datetime,
    topic_id: int | None = None,
    author_name: str | None = None,
    author_username: str | None = None,
    edited_at: datetime | None = None,
) -> tuple[SourceMessage, bool]:
    """Insert a message, or return the existing row. Second value is "was new".

    Idempotent on (chat_id, message_id), so re-running an import over a range
    already covered is harmless. That property is what lets the ingester crash
    halfway through a backfill and simply be restarted.
    """
    existing = db.execute(
        select(SourceMessage).where(
            SourceMessage.chat_id == chat_id, SourceMessage.message_id == message_id
        )
    ).scalar_one_or_none()

    if existing is not None:
        # Telegram lets people edit posts. If this one changed, keep the new
        # text so the next parse works from what the group can currently see.
        if edited_at and existing.edited_at != edited_at:
            existing.text = text
            existing.edited_at = edited_at
            db.flush()
        return existing, False

    message = SourceMessage(
        chat_id=chat_id,
        message_id=message_id,
        topic_id=topic_id,
        text=text,
        posted_at=posted_at,
        edited_at=edited_at,
        author_name=author_name,
        author_username=author_username,
    )
    db.add(message)
    try:
        db.flush()
    except IntegrityError:
        # Another worker inserted it between our check and our write.
        db.rollback()
        return record_message(
            db,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            posted_at=posted_at,
            topic_id=topic_id,
            author_name=author_name,
            author_username=author_username,
            edited_at=edited_at,
        )
    return message, True


# ---------------------------------------------------------------------------
# Deriving games
# ---------------------------------------------------------------------------


def derive_game(db: Session, message: SourceMessage) -> Game | None:
    """Parse a stored message into a game, replacing any previous reading.

    Returns None when the post is not an offer of a game, which is most of them:
    a badminton group is mostly conversation, and treating every message as a
    candidate game would fill the feed with "thanks bro".
    """
    parsed = parser.parse(message.text, posted_at=message.posted_at)

    existing = db.execute(
        select(Game).where(Game.source_message_id == message.id)
    ).scalar_one_or_none()

    if not parsed.is_usable:
        # A message that used to parse as a game and now does not — because the
        # parser got stricter — should stop being shown.
        if existing is not None:
            db.delete(existing)
        return None

    venue_id = _venue_id_for(db, parsed.venue_slug)

    game = existing or Game(source=GameSource.TELEGRAM, source_message_id=message.id)
    game.starts_at = parsed.starts_at
    game.ends_at = parsed.ends_at
    game.venue_id = venue_id
    game.raw_venue = parsed.raw_venue
    game.price_cents = parsed.price_cents
    game.spots_wanted = parsed.spots_wanted
    game.skill = parsed.skill
    game.is_filled = parsed.is_filled
    game.confidence = parsed.confidence
    game.parser_version = parser.PARSER_VERSION
    game.parsed_at = datetime.now(timezone.utc)

    if existing is None:
        db.add(game)
    return game


_venue_cache: dict[str, int] = {}


def _venue_id_for(db: Session, slug: str | None) -> int | None:
    if slug is None:
        return None
    if slug in _venue_cache:
        return _venue_cache[slug]
    venue_id = db.execute(
        select(Venue.id).where(Venue.slug == slug)
    ).scalar_one_or_none()
    if venue_id is not None:
        _venue_cache[slug] = venue_id
    else:
        # The catalogue knows this venue but the database was never seeded with
        # it. Loud, because it silently loses games otherwise.
        log.warning("Venue %r is in the catalogue but not the database — run seed_venues", slug)
    return venue_id


def ingest_message(db: Session, *, stats: IngestStats, **message_fields) -> None:
    """Record one message and derive its game. Commits nothing — the caller
    controls transaction size, which matters a lot during a large backfill."""
    message, was_new = record_message(db, **message_fields)
    stats.messages_seen += 1
    if was_new:
        stats.messages_new += 1

    had_game = message.game is not None
    game = derive_game(db, message)

    if game is None:
        stats.skipped_unusable += 1
    elif had_game:
        stats.games_updated += 1
    else:
        stats.games_created += 1


# ---------------------------------------------------------------------------
# Re-parsing stored history
# ---------------------------------------------------------------------------


def reparse_all(db: Session, *, batch_size: int = 500) -> IngestStats:
    """Re-derive every game from stored messages.

    Run after changing the parser. Batched because a busy group produces tens of
    thousands of messages and loading them all into one session is how you turn
    an improvement into an outage.
    """
    stats = IngestStats()
    total = db.execute(select(func.count()).select_from(SourceMessage)).scalar() or 0
    log.info("Re-parsing %s stored messages", total)

    offset = 0
    while offset < total:
        batch = db.execute(
            select(SourceMessage)
            .order_by(SourceMessage.id)
            .offset(offset)
            .limit(batch_size)
        ).scalars().all()

        for message in batch:
            stats.messages_seen += 1
            had_game = message.game is not None
            game = derive_game(db, message)
            if game is None:
                stats.skipped_unusable += 1
            elif had_game:
                stats.games_updated += 1
            else:
                stats.games_created += 1

        db.commit()
        offset += batch_size
        log.info("  %s/%s", min(offset, total), total)

    return stats


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------


def get_cursor(db: Session, chat_id: str) -> IngestCursor:
    cursor = db.get(IngestCursor, chat_id)
    if cursor is None:
        cursor = IngestCursor(chat_id=chat_id)
        db.add(cursor)
        db.flush()
    return cursor


def update_cursor(
    db: Session, cursor: IngestCursor, *, stats: IngestStats, last_message_id: int | None = None
) -> None:
    if last_message_id is not None:
        cursor.last_message_id = max(cursor.last_message_id, last_message_id)
    cursor.last_run_at = datetime.now(timezone.utc)
    cursor.messages_seen += stats.messages_seen
    cursor.games_extracted += stats.games_created
