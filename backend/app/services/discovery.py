"""Finding the games worth showing someone.

Filtering happens in SQL because it must; ranking happens in Python because the
rules change weekly and are far easier to read, test and argue about as a
function than as a hand-tuned ORDER BY. The filtered candidate set is one city's
games over a fortnight — small enough that the cost of ranking in the
application is irrelevant next to the clarity.

If that stops being true, the answer is a stored ranking column updated on
write, not a cleverer query.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Game, ParseConfidence, SkillLevel, SourceMessage, Venue

EARTH_RADIUS_KM = 6371.0088
DEFAULT_RADIUS_KM = 12.0
DEFAULT_HORIZON_DAYS = 21


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class Filters:
    """Everything the feed can be narrowed by.

    Defaults are chosen to answer the question people actually arrive with —
    "what can I play soon, near me, that still has space" — rather than dumping
    the whole table and making them work for it.
    """

    from_time: datetime | None = None
    to_time: datetime | None = None
    weekdays: list[int] = field(default_factory=list)   # 0 = Monday, SGT
    dates: list[date] = field(default_factory=list)     # specific calendar days, SGT
    earliest_minute: int | None = None                  # minutes past midnight
    latest_minute: int | None = None
    venue_slugs: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    max_price_cents: int | None = None
    skill: SkillLevel | None = None
    query: str | None = None
    include_filled: bool = False
    near_lat: float | None = None
    near_lng: float | None = None
    radius_km: float = DEFAULT_RADIUS_KM


@dataclass
class GameHit:
    game: Game
    distance_km: float | None
    score: float


def _tighten_to_dates(filters: Filters) -> Filters:
    """When specific calendar dates are selected, narrow the SQL-side window to
    just span them.

    Without this, a `dates` filter is applied only in Python after an
    over-fetched, soonest-first candidate set — so a busy day close to now can
    fill the whole candidate set and crowd out a selected date further out,
    making it look like there are no games that day when there are hundreds.
    """
    if not filters.dates:
        return filters

    from app.ingest.parser import SGT

    date_from = datetime.combine(min(filters.dates), time.min, tzinfo=SGT).astimezone(timezone.utc)
    date_to = datetime.combine(max(filters.dates), time.max, tzinfo=SGT).astimezone(timezone.utc)
    from_time = max(filters.from_time, date_from) if filters.from_time else date_from
    to_time = min(filters.to_time, date_to) if filters.to_time else date_to
    return replace(filters, from_time=from_time, to_time=to_time)


def _build_stmt(filters: Filters, now: datetime):
    stmt = (
        select(Game)
        .options(joinedload(Game.venue), joinedload(Game.source_message))
        .where(
            # A game we could not read a time for cannot be filtered, and a feed
            # of unfilterable rows is the problem this product exists to solve.
            Game.confidence != ParseConfidence.LOW,
            Game.starts_at.is_not(None),
            Game.starts_at > (filters.from_time or now),
        )
    )

    stmt = stmt.where(
        Game.starts_at <= (filters.to_time or now + timedelta(days=DEFAULT_HORIZON_DAYS))
    )

    if not filters.include_filled:
        stmt = stmt.where(Game.is_filled.is_(False))

    if filters.venue_slugs:
        stmt = stmt.join(Venue).where(Venue.slug.in_(filters.venue_slugs))
    elif filters.regions:
        stmt = stmt.join(Venue).where(Venue.region.in_(filters.regions))

    if filters.max_price_cents is not None:
        # A post with no stated price should not be hidden by a price filter —
        # free-to-us games and "pay at the door" are extremely common.
        stmt = stmt.where(
            or_(Game.price_cents.is_(None), Game.price_cents <= filters.max_price_cents)
        )

    if filters.skill is not None:
        # Untagged games are open to everyone, so they stay in.
        stmt = stmt.where(or_(Game.skill.is_(None), Game.skill == filters.skill))

    if filters.query:
        needle = f"%{filters.query.strip()}%"
        stmt = stmt.join(SourceMessage, Game.source_message_id == SourceMessage.id).where(
            SourceMessage.text.ilike(needle)
        )

    return stmt


def _passes_row_filters(game: Game, local: datetime, filters: Filters) -> tuple[bool, float | None]:
    """The predicates that are cheaper to apply in Python than in SQL. Returns
    (passes, distance_km) so callers that need distance don't recompute it."""
    if filters.weekdays and local.weekday() not in filters.weekdays:
        return False, None
    if filters.dates and local.date() not in filters.dates:
        return False, None

    minute_of_day = local.hour * 60 + local.minute
    if filters.earliest_minute is not None and minute_of_day < filters.earliest_minute:
        return False, None
    if filters.latest_minute is not None and minute_of_day > filters.latest_minute:
        return False, None

    distance = None
    if filters.near_lat is not None and filters.near_lng is not None and game.venue:
        distance = haversine_km(filters.near_lat, filters.near_lng, game.venue.lat, game.venue.lng)
        if distance > filters.radius_km:
            return False, None

    return True, distance


def search(db: Session, *, filters: Filters, limit: int = 60) -> list[GameHit]:
    filters = _tighten_to_dates(filters)
    now = datetime.now(timezone.utc)
    stmt = _build_stmt(filters, now)

    # Fetch every SQL-side match in the date window, not just the soonest
    # `limit`-ish rows: the weekday/date/time-of-day/distance predicates below
    # are applied in Python, and capping the candidate set relative to `limit`
    # can starve a narrow predicate out entirely — e.g. an "evenings" surge
    # filling the top N soonest candidates and silently hiding every morning
    # game later in the window. The date window itself is what keeps this
    # bounded (see module docstring); MAX_CANDIDATES is just a safety valve.
    MAX_CANDIDATES = 5000
    candidates = (
        db.execute(stmt.order_by(Game.starts_at.asc()).limit(MAX_CANDIDATES)).unique().scalars().all()
    )

    hits: list[GameHit] = []
    for game in candidates:
        local = _to_sgt(game.starts_at)
        ok, distance = _passes_row_filters(game, local, filters)
        if not ok:
            continue
        hits.append(GameHit(game=game, distance_km=distance, score=_score(game, distance, now)))

    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def count_by_day(db: Session, *, filters: Filters, from_date: date, to_date: date) -> dict[date, int]:
    """Per-day game counts for a calendar month view.

    Reuses search()'s filter pipeline, swapping the date window for an explicit
    [from_date, to_date] range and ignoring any `dates` selection — the calendar
    shows counts for every day so people can see where to look before clicking.
    """
    from app.ingest.parser import SGT

    from_dt = datetime.combine(from_date, time.min, tzinfo=SGT).astimezone(timezone.utc)
    to_dt = datetime.combine(to_date, time.max, tzinfo=SGT).astimezone(timezone.utc)
    window = replace(filters, from_time=from_dt, to_time=to_dt, dates=[])

    now = datetime.now(timezone.utc)
    stmt = _build_stmt(window, now)
    candidates = db.execute(stmt).unique().scalars().all()

    counts: Counter[date] = Counter()
    for game in candidates:
        local = _to_sgt(game.starts_at)
        ok, _ = _passes_row_filters(game, local, window)
        if ok:
            counts[local.date()] += 1

    return dict(counts)


def _to_sgt(moment: datetime) -> datetime:
    from app.ingest.parser import SGT

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(SGT)


def _score(game: Game, distance_km: float | None, now: datetime) -> float:
    """Rank by how likely this is the game someone actually wants.

    Three beliefs are encoded here, and they are worth stating because they are
    what makes the feed feel right or wrong:

    1. Soon beats later. People open this app asking "what can I play tonight",
       not "what exists in three weeks".
    2. A clearly-parsed game beats a half-understood one. Showing a confident
       card above a vague one is a better experience than strict time ordering,
       because a card missing its venue costs the reader work.
    3. Near beats far, gently. In a city where nothing is more than an hour
       away, distance matters less than timing.
    """
    starts_at = game.starts_at
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=timezone.utc)

    hours_away = max((starts_at - now).total_seconds() / 3600.0, 0.0)
    imminence = 1.0 / (1.0 + hours_away / 24.0)

    clarity = 1.0 if game.confidence is ParseConfidence.HIGH else 0.6

    if distance_km is None:
        proximity = 0.5  # neutral when we have no location to compare against
    else:
        proximity = 1.0 / (1.0 + distance_km / 5.0)

    return imminence * 0.55 + clarity * 0.25 + proximity * 0.20
