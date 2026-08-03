"""Venue lookup. Read-only — see models.Venue for why they are curated."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Venue
from app.schemas import VenueOut

router = APIRouter(prefix="/venues", tags=["venues"])


@router.get("", response_model=list[VenueOut])
def list_venues(
    region: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
) -> list[VenueOut]:
    stmt = select(Venue)
    if region:
        stmt = stmt.where(Venue.region == region)
    if search:
        stmt = stmt.where(Venue.name.ilike(f"%{search}%"))
    rows = db.execute(stmt.order_by(Venue.region, Venue.name)).scalars().all()
    return [VenueOut.model_validate(row) for row in rows]


@router.get("/regions", response_model=list[str])
def list_regions(db: Session = Depends(get_db)) -> list[str]:
    return list(
        db.execute(select(Venue.region).distinct().order_by(Venue.region)).scalars().all()
    )
