"""End-to-end tests: a Telegram message goes in, a filtered feed comes out.

These use a real (temporary) database and the real FastAPI app rather than
mocks, because the things most likely to break here are the seams — the parser
agreeing with the model, the model agreeing with the query, the query agreeing
with the response shape. Mocks would hide exactly those failures.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.ingest.parser import SGT
from app.ingest import venue_catalogue as catalogue
from app.ingest.service import IngestStats, ingest_message
from app.main import app
from app.models import Base, Game, ParseConfidence, Venue


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    session = Session()
    for slug, name, region, _aliases, (lat, lng) in catalogue.VENUES:
        session.add(Venue(slug=slug, name=name, region=region, lat=lat, lng=lng))
    session.commit()

    # The venue-id cache is module-level, so it must not leak between tests
    # holding ids from a database that no longer exists.
    from app.ingest import service

    service._venue_cache.clear()

    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def post(db, text: str, *, message_id: int, posted_at: datetime | None = None) -> None:
    """Feed one message through the real ingestion path."""
    ingest_message(
        db,
        stats=IngestStats(),
        chat_id="sg_badminton",
        message_id=message_id,
        text=text,
        posted_at=posted_at or datetime.now(timezone.utc),
        author_name="Test Poster",
    )
    db.commit()


def in_days(days: int) -> str:
    """A date string the parser will read, N days from now."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%d %b")


class TestIngestion:
    def test_game_offer_becomes_a_game(self, db_session):
        post(db_session, f"📍 Bishan Sports Hall\n📅 {in_days(2)}\n⏰ 8pm-10pm\n$8/pax, need 2", message_id=1)

        game = db_session.query(Game).one()
        assert game.venue.slug == "bishan"
        assert game.price_cents == 800
        assert game.spots_wanted == 2
        assert game.confidence is ParseConfidence.HIGH

    def test_chatter_does_not_become_a_game(self, db_session):
        post(db_session, "anyone know where to restring rackets ah", message_id=1)
        post(db_session, "thanks bro", message_id=2)

        assert db_session.query(Game).count() == 0

    def test_ingesting_the_same_message_twice_is_safe(self, db_session):
        text = f"CCK {in_days(1)} 8-10pm, 2 slots"
        post(db_session, text, message_id=42)
        post(db_session, text, message_id=42)

        assert db_session.query(Game).count() == 1

    def test_editing_a_post_updates_the_game(self, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10pm $8", message_id=1)
        assert db_session.query(Game).one().price_cents == 800

        ingest_message(
            db_session,
            stats=IngestStats(),
            chat_id="sg_badminton",
            message_id=1,
            text=f"Bishan {in_days(2)} 8-10pm $10",
            posted_at=datetime.now(timezone.utc),
            edited_at=datetime.now(timezone.utc),
        )
        db_session.commit()

        assert db_session.query(Game).one().price_cents == 1000

    def test_post_marked_filled_is_flagged_not_deleted(self, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10pm — FILLED thanks", message_id=1)

        game = db_session.query(Game).one()
        assert game.is_filled is True


class TestFeed:
    def test_feed_returns_upcoming_games(self, client, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10pm $8", message_id=1)

        body = client.get("/games").json()
        assert body["total"] == 1
        assert body["games"][0]["venue"]["slug"] == "bishan"

    def test_past_games_are_excluded(self, client, db_session):
        post(
            db_session,
            "Bishan 8-10pm",
            message_id=1,
            posted_at=datetime.now(timezone.utc) - timedelta(days=40),
        )
        assert client.get("/games").json()["total"] == 0

    def test_filled_games_hidden_by_default(self, client, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10pm FILLED", message_id=1)

        assert client.get("/games").json()["total"] == 0
        assert client.get("/games?include_filled=true").json()["total"] == 1

    def test_filter_by_region(self, client, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10pm", message_id=1)          # North-East
        post(db_session, f"Choa Chu Kang {in_days(2)} 8-10pm", message_id=2)   # West

        west = client.get("/games?region=West").json()
        assert west["total"] == 1
        assert west["games"][0]["venue"]["slug"] == "choa_chu_kang"

    def test_filter_by_venue_slug(self, client, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10pm", message_id=1)
        post(db_session, f"Tampines {in_days(2)} 8-10pm", message_id=2)

        body = client.get("/games?venue=tampines").json()
        assert body["total"] == 1

    def test_filter_by_time_of_day(self, client, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10am", message_id=1)
        post(db_session, f"Bishan {in_days(2)} 8-10pm", message_id=2)

        evening = client.get("/games?after=17:00").json()
        assert evening["total"] == 1

        # The API serves UTC and the client localises; 8pm SGT is 12:00Z.
        starts = datetime.fromisoformat(evening["games"][0]["starts_at"].replace("Z", "+00:00"))
        assert starts.astimezone(SGT).hour == 20

    def test_a_selective_time_window_is_not_starved_by_a_busy_earlier_day(self, client, db_session):
        """Guards against the over-fetch trap: if the candidate fetch is capped
        relative to `limit` and sorted soonest-first, a flood of evening games on
        an early day can fill the whole candidate set before a morning game two
        weeks out is ever considered, even though it is well within the horizon
        and matches the filter."""
        for i in range(200):
            post(db_session, f"Bishan {in_days(1)} 8-10pm", message_id=i)
        post(db_session, f"Tampines {in_days(10)} 7-9am", message_id=999)

        morning = client.get("/games?after=06:00&before=11:59").json()
        assert morning["total"] == 1
        assert morning["games"][0]["venue"]["slug"] == "tampines"

    def test_stored_timestamps_survive_a_round_trip(self, client, db_session):
        """Guards the SQLite timezone trap: naive storage silently shifts an
        evening game into the small hours and breaks every time-of-day filter."""
        post(db_session, f"Bishan {in_days(2)} 8-10pm", message_id=1)

        game = db_session.query(Game).one()
        assert game.starts_at.tzinfo is not None
        assert game.starts_at.astimezone(SGT).hour == 20

    def test_price_filter_keeps_games_with_no_stated_price(self, client, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10pm $20", message_id=1)
        post(db_session, f"Tampines {in_days(2)} 8-10pm", message_id=2)  # no price

        body = client.get("/games?max_price_cents=1000").json()
        slugs = {game["venue"]["slug"] for game in body["games"]}
        assert slugs == {"tampines"}, "a game with no price should survive a price filter"

    def test_full_text_search(self, client, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10pm, mixed doubles", message_id=1)
        post(db_session, f"Tampines {in_days(2)} 8-10pm, singles only", message_id=2)

        body = client.get("/games?q=singles").json()
        assert body["total"] == 1

    def test_every_game_links_back_to_telegram(self, client, db_session):
        post(db_session, f"Bishan {in_days(2)} 8-10pm", message_id=77)

        game = client.get("/games").json()["games"][0]
        assert game["source_url"].endswith("/77")
        assert game["source_text"]

    def test_distance_appears_when_a_location_is_given(self, client, db_session):
        post(db_session, f"Choa Chu Kang {in_days(2)} 8-10pm", message_id=1)

        # Roughly Bukit Panjang, a few km from CCK.
        body = client.get("/games?near_lat=1.3774&near_lng=103.7639&radius_km=15").json()
        assert body["games"][0]["distance_km"] is not None
        assert body["games"][0]["distance_km"] < 15

    def test_filter_by_specific_date(self, client, db_session):
        post(db_session, f"Bishan {in_days(1)} 8-10pm", message_id=1)
        post(db_session, f"Bishan {in_days(5)} 8-10pm", message_id=2)

        target_date = (datetime.now(SGT) + timedelta(days=1)).date().isoformat()
        body = client.get(f"/games?date={target_date}").json()
        assert body["total"] == 1

    def test_calendar_counts_games_per_day(self, client, db_session):
        post(db_session, f"Bishan {in_days(1)} 8-10pm", message_id=1)
        post(db_session, f"Bishan {in_days(1)} 6-8pm", message_id=2)
        post(db_session, f"Tampines {in_days(3)} 8-10pm", message_id=3)

        today = datetime.now(SGT).date()
        day1 = (today + timedelta(days=1)).isoformat()
        day3 = (today + timedelta(days=3)).isoformat()

        body = client.get(
            f"/games/calendar?from_date={today.isoformat()}&to_date={(today + timedelta(days=7)).isoformat()}"
        ).json()
        assert body[day1] == 2
        assert body[day3] == 1
        assert day3 in body and day1 in body

    def test_calendar_rejects_an_oversized_range(self, client, db_session):
        today = datetime.now(SGT).date()
        resp = client.get(
            f"/games/calendar?from_date={today.isoformat()}&to_date={(today + timedelta(days=90)).isoformat()}"
        )
        assert resp.status_code == 400


class TestAuth:
    def test_signup_login_and_saved_search(self, client):
        credentials = {
            "email": "player@example.com",
            "password": "shuttlecock123",
            "display_name": "Wei Ming",
        }
        tokens = client.post("/auth/signup", json=credentials).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        assert client.get("/me", headers=headers).json()["display_name"] == "Wei Ming"

        created = client.post(
            "/me/searches",
            json={"name": "Weeknights west", "filters": {"region": ["West"], "after": "19:00"}},
            headers=headers,
        )
        assert created.status_code == 201
        assert client.get("/me/searches", headers=headers).json()[0]["name"] == "Weeknights west"

    def test_duplicate_email_is_rejected(self, client):
        credentials = {
            "email": "dupe@example.com",
            "password": "shuttlecock123",
            "display_name": "First",
        }
        assert client.post("/auth/signup", json=credentials).status_code == 201
        second = client.post("/auth/signup", json=credentials)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "conflict"

    def test_wrong_password_is_indistinguishable_from_unknown_email(self, client):
        client.post(
            "/auth/signup",
            json={"email": "real@example.com", "password": "shuttlecock123", "display_name": "Real"},
        )
        wrong_password = client.post(
            "/auth/login", json={"email": "real@example.com", "password": "nope-not-it"}
        )
        unknown_email = client.post(
            "/auth/login", json={"email": "ghost@example.com", "password": "nope-not-it"}
        )

        # Identical responses, so this endpoint cannot be used to discover who
        # has an account.
        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()

    def test_refresh_token_cannot_be_used_as_an_access_token(self, client):
        tokens = client.post(
            "/auth/signup",
            json={"email": "swap@example.com", "password": "shuttlecock123", "display_name": "Swap"},
        ).json()

        response = client.get(
            "/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
        )
        assert response.status_code == 401

    def test_saved_searches_require_signing_in(self, client):
        assert client.get("/me/searches").status_code == 401


class TestOps:
    def test_healthz_needs_no_database(self, client):
        assert client.get("/healthz").json() == {"status": "ok"}

    def test_ingest_status_reports_emptiness_honestly(self, client):
        body = client.get("/ingest/status").json()
        assert body["backfill_complete"] is False
        assert body["games_upcoming"] == 0
