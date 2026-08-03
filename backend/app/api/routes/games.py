"""The feed. This is the endpoint the whole product is for.

Filters arrive as query parameters rather than a POST body so that a search is a
URL: shareable, bookmarkable, and back-button friendly. "Wednesdays at CCK after
7pm" should be something you can send to a friend.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import optional_user, to_game_out
from app.core.errors import DomainError, NotFound
from app.db import get_db
from app.models import Game, ParseConfidence, SkillLevel, User
from app.schemas import GameFeed, GameOut
from app.services import discovery

router = APIRouter(prefix="/games", tags=["games"])


def _parse_minute(value: str | None) -> int | None:
    """Accept "19:30" from an <input type=time> and return minutes past midnight."""
    if not value:
        return None
    try:
        hours, minutes = value.split(":")
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return None


@router.get("", response_model=GameFeed)
def list_games(
    db: Session = Depends(get_db),
    viewer: User | None = Depends(optional_user),
    weekday: list[int] = Query(default=[], description="0=Mon … 6=Sun, repeatable"),
    date_: list[date] = Query(default=[], alias="date", description="Specific calendar days, repeatable"),
    region: list[str] = Query(default=[]),
    venue: list[str] = Query(default=[], description="Venue slugs, repeatable"),
    after: str | None = Query(default=None, description="Earliest start, HH:MM"),
    before: str | None = Query(default=None, description="Latest start, HH:MM"),
    from_time: datetime | None = Query(default=None),
    to_time: datetime | None = Query(default=None),
    max_price_cents: int | None = Query(default=None, ge=0),
    skill: SkillLevel | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    include_filled: bool = Query(default=False),
    near_lat: float | None = Query(default=None, ge=-90, le=90),
    near_lng: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=discovery.DEFAULT_RADIUS_KM, gt=0, le=100),
    limit: int = Query(default=60, ge=1, le=200),
) -> GameFeed:
    # A signed-in player with a saved home location gets distance sorting for
    # free, without having to ask for it every time.
    if near_lat is None and near_lng is None and viewer is not None:
        near_lat, near_lng = viewer.home_lat, viewer.home_lng

    filters = discovery.Filters(
        from_time=from_time,
        to_time=to_time,
        weekdays=weekday,
        dates=date_,
        earliest_minute=_parse_minute(after),
        latest_minute=_parse_minute(before),
        venue_slugs=venue,
        regions=region,
        max_price_cents=max_price_cents,
        skill=skill,
        query=q,
        include_filled=include_filled,
        near_lat=near_lat,
        near_lng=near_lng,
        radius_km=radius_km,
    )

    hits = discovery.search(db, filters=filters, limit=limit)
    return GameFeed(
        games=[to_game_out(hit.game, distance_km=hit.distance_km) for hit in hits],
        total=len(hits),
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/stats")
def feed_stats(db: Session = Depends(get_db)) -> dict:
    """Small counts for the header. Cheap enough to compute per request."""
    now = datetime.now(timezone.utc)
    upcoming = db.execute(
        select(func.count())
        .select_from(Game)
        .where(
            Game.starts_at > now,
            Game.confidence != ParseConfidence.LOW,
            Game.is_filled.is_(False),
        )
    ).scalar() or 0

    return {"upcoming_games": upcoming}


@router.get("/calendar")
def calendar_counts(
    db: Session = Depends(get_db),
    viewer: User | None = Depends(optional_user),
    from_date: date = Query(...),
    to_date: date = Query(...),
    region: list[str] = Query(default=[]),
    venue: list[str] = Query(default=[]),
    after: str | None = Query(default=None, description="Earliest start, HH:MM"),
    before: str | None = Query(default=None, description="Latest start, HH:MM"),
    max_price_cents: int | None = Query(default=None, ge=0),
    skill: SkillLevel | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    include_filled: bool = Query(default=False),
    near_lat: float | None = Query(default=None, ge=-90, le=90),
    near_lng: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=discovery.DEFAULT_RADIUS_KM, gt=0, le=100),
) -> dict[str, int]:
    """Per-day game counts for the calendar's currently visible month, so
    empty days are visibly skippable before clicking."""
    if to_date < from_date or (to_date - from_date).days > 62:
        raise DomainError("Calendar range must be forwards and at most 62 days.")

    if near_lat is None and near_lng is None and viewer is not None:
        near_lat, near_lng = viewer.home_lat, viewer.home_lng

    filters = discovery.Filters(
        earliest_minute=_parse_minute(after),
        latest_minute=_parse_minute(before),
        venue_slugs=venue,
        regions=region,
        max_price_cents=max_price_cents,
        skill=skill,
        query=q,
        include_filled=include_filled,
        near_lat=near_lat,
        near_lng=near_lng,
        radius_km=radius_km,
    )

    counts = discovery.count_by_day(db, filters=filters, from_date=from_date, to_date=to_date)
    return {d.isoformat(): n for d, n in counts.items()}


@router.get("/{game_id}", response_model=GameOut)
def get_game(game_id: int, db: Session = Depends(get_db)) -> GameOut:
    game = db.execute(
        select(Game)
        .options(joinedload(Game.venue), joinedload(Game.source_message))
        .where(Game.id == game_id)
    ).unique().scalar_one_or_none()

    if game is None:
        raise NotFound("That game is not in our feed.")
    return to_game_out(game)
