"""Shared dependencies and the ORM-to-response mapping."""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.security import decode_token
from app.db import get_db
from app.models import Game, User
from app.schemas import GameOut, VenueOut

_bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthError("Sign in to do that.")
    user = db.get(User, decode_token(credentials.credentials, expect="access"))
    if user is None or not user.is_active:
        raise AuthError("That account is no longer available.")
    return user


def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """For routes that work signed out but get better signed in.

    The feed is the important one: browsing must work for someone who has never
    made an account, or a shared game link is useless.
    """
    if credentials is None:
        return None
    try:
        user_id = decode_token(credentials.credentials, expect="access")
    except AuthError:
        return None
    user = db.get(User, user_id)
    return user if user and user.is_active else None


def to_game_out(game: Game, *, distance_km: float | None = None) -> GameOut:
    message = game.source_message
    return GameOut(
        id=game.id,
        starts_at=game.starts_at,
        ends_at=game.ends_at,
        venue=VenueOut.model_validate(game.venue) if game.venue else None,
        raw_venue=game.raw_venue,
        price_cents=game.price_cents,
        spots_wanted=game.spots_wanted,
        skill=game.skill,
        is_filled=game.is_filled,
        confidence=game.confidence,
        posted_at=message.posted_at if message else None,
        posted_by=message.author_name if message else None,
        source_text=message.text if message else "",
        source_url=message.permalink if message else "",
        distance_km=round(distance_km, 1) if distance_km is not None else None,
    )
