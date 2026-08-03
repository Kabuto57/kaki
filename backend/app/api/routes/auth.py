"""Sign up, sign in, refresh."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthError, Conflict
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, RefreshRequest, SignUpRequest, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens_for(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/signup", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def sign_up(payload: SignUpRequest, db: Session = Depends(get_db)) -> TokenPair:
    existing = db.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict("There is already an account with that email.")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _tokens_for(user)


@router.post("/login", response_model=TokenPair)
def log_in(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPair:
    user = db.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()

    # Same message either way. Telling an attacker which half was wrong turns
    # this endpoint into a way to enumerate who has an account.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AuthError("That email and password do not match.")
    if not user.is_active:
        raise AuthError("That account is no longer available.")

    return _tokens_for(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    user_id = decode_token(payload.refresh_token, expect="refresh")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("That account is no longer available.")
    return _tokens_for(user)
