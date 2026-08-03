# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Kaki reads a Telegram group (`sg_badminton`) where badminton games get posted, parses free-text posts into structured, filterable game listings, and serves them through a FastAPI backend + React frontend. Joining a game still happens in Telegram — Kaki only finds it.

## Commands

**Backend** (from `backend/`, with `.venv` activated):
```bash
python -m scripts.init_db          # create tables
python -m scripts.seed_venues      # load venue_catalogue.py into DB
python -m scripts.login            # interactive Telegram sign-in (once)
python -m scripts.list_topics      # find TELEGRAM_TOPIC_ID
python -m scripts.run_ingest       # backfill, then watch live
uvicorn app.main:app --reload --port 8000
python -m scripts.reparse          # re-derive all games from stored source_messages
```

**Tests**:
```bash
cd backend && python -m pytest -q          # full suite
cd backend && python -m pytest tests/test_parser.py -q          # one file
cd backend && python -m pytest tests/test_parser.py -k name -q  # one test
```

**Frontend** (from `frontend/`):
```bash
npm run dev       # Vite proxies /api to backend:8000 in dev
npm run build
```

## Architecture

**Source messages and games are separate, immutable-vs-derived tables** (`backend/app/models.py`). `SourceMessage` is the verbatim Telegram post; `Game` is the parser's current interpretation of it. This split exists because the parser (`app/ingest/parser.py`) is the piece most likely to be wrong and most likely to improve — keeping raw text means `scripts/reparse.py` can re-derive all of history locally from what's already stored, with no re-fetch and no Telegram round trip. When changing parsing logic, always consider whether `reparse` needs to run afterward.

**Ingest flow**: `app/ingest/telegram.py` (Telethon client, backfill + live watch) → stores verbatim into `SourceMessage` → `app/ingest/parser.py` turns free text into a structured `Game`, using `app/ingest/venue_catalogue.py` to resolve venue names/aliases → `app/ingest/service.py` orchestrates storage and derivation. A post naming an unknown venue still appears, with raw text shown instead of a clean name, so gaps in the catalogue are visible rather than silently dropped.

**`app/core/types.py` — `UTCDateTime`**: every timestamp column in `models.py` uses this custom type. Read its docstring before touching any timestamp: SQLite has no native timestamp type and silently drops timezone offsets, so this type enforces timezone-aware-in, timezone-aware-out at the column level rather than relying on callers to get it right. Presentation-time conversion to Singapore time happens only at the render layer (`frontend/src/lib/format.js`), never in storage.

**Errors**: the service layer raises domain errors from `app/core/errors.py` (`NotFound`, `NotPermitted`, `Conflict`, etc.), which know nothing about HTTP. A single exception handler in `app/main.py` maps them to status codes, so routes (`app/api/routes/`) stay thin and status-code logic lives in one place.

**Discovery** (`app/services/discovery.py`): filtering happens in SQL, ranking happens in Python. Deliberate split — ranking rules change often and are easier to read/test as a function than as a hand-tuned `ORDER BY`; it's cheap because the filtered candidate set (one city, one fortnight) is small. If that candidate set ever stops being small, the fix is a stored ranking column updated on write, not a cleverer query — don't reach for SQL-side ranking as a first move.

**Config** (`app/config.py`): settings load from env / `.env` via pydantic-settings. `SECRET_KEY` still at its insecure default + `ENVIRONMENT=production` fails at startup (`app/main.py` lifespan) rather than booting silently insecure.

**DB portability**: SQLite locally/small-scale, Postgres supported via `DATABASE_URL=postgresql+psycopg://...` for multi-writer or managed-backup needs. `UTCDateTime` is part of what makes that switch safe — timestamps behave identically on both backends.

**Frontend**: `App.jsx` is the whole feed, with filter state living in the URL. `lib/api.js` is the single point of contact with the backend API; `lib/format.js` is the single point of UTC→Singapore time conversion. Keep both centralized rather than duplicating fetch or timezone logic in components.

## Adding a venue

Add an entry to `app/ingest/venue_catalogue.py`: `(id, display_name, region, [aliases], (lat, lng))`. Aliases matter more than the official name (people type "CCK", not the full venue name). Then run `seed_venues` and `reparse`.
