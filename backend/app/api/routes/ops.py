"""Operational endpoints.

`/ingest/status` exists because the most common failure of this system is silent:
the worker dies, the feed slowly empties, and nothing reports an error because
the API is still perfectly healthy. Surfacing when ingestion last ran turns that
into something you can see and alert on.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Game, IngestCursor, ParseConfidence
from app.schemas import IngestStatusOut

router = APIRouter(tags=["ops"])
settings = get_settings()


@router.get("/healthz")
def healthz() -> dict:
    """Liveness only. Deliberately does not touch the database, so a slow query
    never takes the whole service out of the load balancer."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    return {"status": "ready"}


@router.get("/ingest/status", response_model=IngestStatusOut)
def ingest_status(db: Session = Depends(get_db)) -> IngestStatusOut:
    chat_id = settings.telegram_chat
    cursor = db.get(IngestCursor, chat_id)

    upcoming = db.execute(
        select(func.count())
        .select_from(Game)
        .where(Game.starts_at > datetime.now(timezone.utc), Game.confidence != ParseConfidence.LOW)
    ).scalar() or 0

    # Before the worker has ever run there is no cursor row. Column defaults
    # only apply on insert, so an unsaved instance would hand back None for
    # every counter — report explicit zeroes instead.
    return IngestStatusOut(
        chat_id=chat_id,
        backfill_complete=cursor.backfill_complete if cursor else False,
        last_run_at=cursor.last_run_at if cursor else None,
        messages_seen=cursor.messages_seen if cursor else 0,
        games_extracted=cursor.games_extracted if cursor else 0,
        games_upcoming=upcoming,
    )
