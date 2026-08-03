"""The Telegram side of ingestion.

Reading a group's history requires signing in as a user account, not a bot.
This is not a workaround: the Bot API deliberately does not expose message
history, so a bot can only ever see messages posted after it joins. Since the
whole point of Kaki is searching what has already been offered, a user session
is the only option. `scripts/login.py` does that once and writes a session file.

The session file is a credential. It is in .gitignore, it must never be
committed, and on a server it should be readable only by the service user.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timezone

from telethon import TelegramClient, events
from telethon.tl.types import Message

from app.config import get_settings
from app.db import SessionLocal
from app.ingest.service import IngestStats, get_cursor, ingest_message, update_cursor

log = logging.getLogger("kaki.telegram")
settings = get_settings()

# Commit every N messages during backfill. Small enough that a crash loses
# almost nothing, large enough that we are not paying a transaction per row.
BACKFILL_COMMIT_EVERY = 200


def build_client() -> TelegramClient:
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise RuntimeError(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH are not set. "
            "Get them from https://my.telegram.org and put them in .env"
        )
    return TelegramClient(
        settings.telegram_session_path,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )


def _topic_id_of(message: Message) -> int | None:
    reply = getattr(message, "reply_to", None)
    if reply is None:
        return None
    if getattr(reply, "forum_topic", False):
        return getattr(reply, "reply_to_top_id", None) or getattr(reply, "reply_to_msg_id", None)
    return None


def _in_watched_topic(message: Message) -> bool:
    if not settings.telegram_topic_id:
        return True
    return _topic_id_of(message) == settings.telegram_topic_id


async def _message_fields(message: Message, chat_id: str) -> dict:
    sender = None
    try:
        sender = await message.get_sender()
    except Exception:  # deleted accounts, privacy settings
        pass

    name = ""
    username = None
    if sender is not None:
        parts = [getattr(sender, "first_name", "") or "", getattr(sender, "last_name", "") or ""]
        name = " ".join(part for part in parts if part).strip()
        username = getattr(sender, "username", None)

    posted_at = message.date
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)

    return {
        "chat_id": chat_id,
        "message_id": message.id,
        "topic_id": _topic_id_of(message),
        "text": message.message or "",
        "posted_at": posted_at,
        "edited_at": message.edit_date,
        "author_name": name or None,
        "author_username": username,
    }


async def backfill(client: TelegramClient, *, limit: int | None = None) -> IngestStats:
    """Pull historical messages.

    Safe to interrupt and re-run: `record_message` is idempotent, so a second
    pass over the same range simply finds everything already stored.
    """
    chat_id = settings.telegram_chat
    entity = await client.get_entity(chat_id)
    stats = IngestStats()

    kwargs: dict = {"limit": limit or settings.backfill_limit}
    if settings.telegram_topic_id:
        kwargs["reply_to"] = settings.telegram_topic_id

    db = SessionLocal()
    try:
        cursor = get_cursor(db, chat_id)
        highest_seen = cursor.last_message_id
        pending = 0

        async for message in client.iter_messages(entity, **kwargs):
            if not (message.message or "").strip():
                continue
            if not _in_watched_topic(message):
                continue

            ingest_message(db, stats=stats, **await _message_fields(message, chat_id))
            highest_seen = max(highest_seen, message.id)
            pending += 1

            if pending >= BACKFILL_COMMIT_EVERY:
                db.commit()
                pending = 0
                log.info("  backfill: %s", stats)

        cursor.backfill_complete = True
        update_cursor(db, cursor, stats=stats, last_message_id=highest_seen)
        db.commit()
    finally:
        db.close()

    log.info("Backfill finished: %s", stats)
    return stats


async def poll(client: TelegramClient) -> IngestStats:
    """Fetch and ingest whatever has arrived since the last run, then return.

    For hosts that can't keep a socket open all day (a scheduled CI job rather
    than an always-on worker), this replaces watch()'s live event stream: it
    is meant to be called on a timer, e.g. every 15 minutes, not held open.
    """
    chat_id = settings.telegram_chat
    entity = await client.get_entity(chat_id)
    stats = IngestStats()

    db = SessionLocal()
    try:
        cursor = get_cursor(db, chat_id)
        since_id = cursor.last_message_id
        highest_seen = since_id

        kwargs: dict = {"min_id": since_id, "reverse": True}
        if settings.telegram_topic_id:
            kwargs["reply_to"] = settings.telegram_topic_id

        async for message in client.iter_messages(entity, **kwargs):
            if not (message.message or "").strip():
                continue
            if not _in_watched_topic(message):
                continue

            ingest_message(db, stats=stats, **await _message_fields(message, chat_id))
            highest_seen = max(highest_seen, message.id)

        update_cursor(db, cursor, stats=stats, last_message_id=highest_seen)
        db.commit()
    finally:
        db.close()

    log.info("Poll finished: %s", stats)
    return stats


async def watch(client: TelegramClient) -> None:
    """Stay connected and ingest new posts as they arrive."""
    chat_id = settings.telegram_chat
    entity = await client.get_entity(chat_id)
    log.info(
        "Watching %s%s",
        chat_id,
        f" topic {settings.telegram_topic_id}" if settings.telegram_topic_id else " (all topics)",
    )

    @client.on(events.NewMessage(chats=entity))
    async def _on_new(event) -> None:  # pragma: no cover - needs a live socket
        await _handle_live(event.message, chat_id)

    @client.on(events.MessageEdited(chats=entity))
    async def _on_edit(event) -> None:  # pragma: no cover
        await _handle_live(event.message, chat_id)

    await client.run_until_disconnected()


async def _handle_live(message: Message, chat_id: str) -> None:
    if not (message.message or "").strip() or not _in_watched_topic(message):
        return

    db = SessionLocal()
    try:
        stats = IngestStats()
        ingest_message(db, stats=stats, **await _message_fields(message, chat_id))
        cursor = get_cursor(db, chat_id)
        update_cursor(db, cursor, stats=stats, last_message_id=message.id)
        db.commit()
        if stats.games_created or stats.games_updated:
            log.info("Message %s → game", message.id)
    except Exception:
        db.rollback()
        log.exception("Failed to ingest message %s", message.id)
    finally:
        db.close()


async def run_forever() -> None:
    """Backfill once if needed, then watch. This is the worker's whole job."""
    client = build_client()
    await client.start()

    if not await client.is_user_authorized():
        raise SystemExit("Not signed in. Run: python -m scripts.login")

    db = SessionLocal()
    try:
        cursor = get_cursor(db, settings.telegram_chat)
        needs_backfill = not cursor.backfill_complete
        db.commit()
    finally:
        db.close()

    if needs_backfill:
        log.info("First run — backfilling history. This takes a few minutes.")
        await backfill(client)

    await watch(client)


async def run_once() -> None:
    """Backfill once if needed, otherwise poll for what's new, then exit.

    This is the entry point for a scheduled job (cron, GitHub Actions) rather
    than a long-lived process — see poll() for why.
    """
    client = build_client()
    await client.start()

    if not await client.is_user_authorized():
        raise SystemExit("Not signed in. Run: python -m scripts.login")

    db = SessionLocal()
    try:
        cursor = get_cursor(db, settings.telegram_chat)
        needs_backfill = not cursor.backfill_complete
        db.commit()
    finally:
        db.close()

    if needs_backfill:
        log.info("First run — backfilling history. This takes a few minutes.")
        await backfill(client)
    else:
        await poll(client)

    await client.disconnect()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        log.info("Stopped.")


def main_once() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)
    asyncio.run(run_once())
