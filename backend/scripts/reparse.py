"""Re-read every stored message with the current parser.

This is the payoff for keeping raw messages separate from parsed games: after
improving the parser you fix all of history locally, without touching Telegram.
"""

import logging

from app.db import SessionLocal
from app.ingest.service import reparse_all

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    db = SessionLocal()
    try:
        stats = reparse_all(db)
        print(f"\nDone: {stats}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
