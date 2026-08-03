"""One-shot ingest for a scheduled job (cron, GitHub Actions) instead of an
always-on worker. Backfills on first run, then fetches only what's new since
the last run and exits — see app.ingest.telegram.poll() for why."""

from app.ingest.telegram import main_once

if __name__ == "__main__":
    main_once()
