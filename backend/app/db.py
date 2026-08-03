"""Engine and session wiring.

Postgres in production, SQLite locally. The two differ in ways that matter for
this app's concurrency story, so read `services/games.py` before assuming a
behaviour carries across both.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

if _is_sqlite:
    # SQLite needs this to be usable from FastAPI's threadpool.
    _connect_args = {"check_same_thread": False}
else:
    # A transaction-mode pgbouncer (e.g. Supabase's pooler) rotates the
    # underlying server connection between statements, so psycopg's
    # server-side prepared statement cache goes stale and Postgres rejects
    # the reused name. Disabling it costs a small amount of Postgres-side
    # query planning reuse, not correctness.
    _connect_args = {"prepare_threshold": None}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    # Recycle before typical managed-Postgres idle timeouts kill the socket.
    pool_pre_ping=not _is_sqlite,
    echo=False,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        # Foreign keys are off by default in SQLite, which silently defeats
        # every ondelete rule in models.py.
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
