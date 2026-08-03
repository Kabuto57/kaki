"""Profile and saved searches."""

import json

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.errors import NotFound
from app.db import get_db
from app.models import SavedSearch, User
from app.schemas import MeOut, SavedSearchIn, SavedSearchOut, UpdateMeRequest

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeOut)
def read_me(user: User = Depends(current_user)) -> MeOut:
    return MeOut.model_validate(user)


@router.patch("", response_model=MeOut)
def update_me(
    payload: UpdateMeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MeOut:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return MeOut.model_validate(user)


def _to_out(row: SavedSearch) -> SavedSearchOut:
    return SavedSearchOut(
        id=row.id,
        name=row.name,
        filters=json.loads(row.filters_json or "{}"),
        created_at=row.created_at,
    )


@router.get("/searches", response_model=list[SavedSearchOut])
def list_searches(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[SavedSearchOut]:
    rows = db.execute(
        select(SavedSearch)
        .where(SavedSearch.user_id == user.id)
        .order_by(SavedSearch.created_at.desc())
    ).scalars().all()
    return [_to_out(row) for row in rows]


@router.post("/searches", response_model=SavedSearchOut, status_code=status.HTTP_201_CREATED)
def create_search(
    payload: SavedSearchIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SavedSearchOut:
    row = SavedSearch(
        user_id=user.id,
        name=payload.name.strip(),
        filters_json=json.dumps(payload.filters),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/searches/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search(
    search_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    row = db.execute(
        select(SavedSearch).where(
            SavedSearch.id == search_id, SavedSearch.user_id == user.id
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("That saved search is gone.")
    db.delete(row)
    db.commit()
