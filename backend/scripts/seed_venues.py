"""Load the venue catalogue into the database.

Idempotent: re-run it after adding venues to `app/ingest/venue_catalogue.py`
and it updates existing rows rather than duplicating them.
"""

from sqlalchemy import select

from app.db import SessionLocal
from app.ingest import venue_catalogue as catalogue
from app.models import Venue


def main() -> None:
    db = SessionLocal()
    created = updated = 0
    try:
        for slug, name, region, _aliases, (lat, lng) in catalogue.VENUES:
            venue = db.execute(select(Venue).where(Venue.slug == slug)).scalar_one_or_none()
            if venue is None:
                db.add(Venue(slug=slug, name=name, region=region, lat=lat, lng=lng))
                created += 1
            else:
                venue.name, venue.region, venue.lat, venue.lng = name, region, lat, lng
                updated += 1
        db.commit()
    finally:
        db.close()
    print(f"Venues: {created} added, {updated} refreshed.")


if __name__ == "__main__":
    main()
