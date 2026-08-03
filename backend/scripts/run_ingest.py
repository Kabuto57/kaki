"""The ingestion worker. Backfills on first run, then watches for new posts."""

from app.ingest.telegram import main

if __name__ == "__main__":
    main()
