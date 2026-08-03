"""A datetime column that is always timezone-aware UTC, on every backend.

The problem this solves is quiet and expensive. SQLite has no native timestamp
type: SQLAlchemy stores whatever naive wall-clock value it is handed and drops
the offset. So an 8pm Singapore kickoff written as `20:00+08:00` comes back as a
naive `20:00`, and code that reasonably assumes UTC turns it into 4am the next
day. Nothing errors. The game just quietly stops matching an evening filter.

Postgres does not have this problem, which is worse, not better: the bug only
appears in development and tests, and disappears in production, so it is very
easy to "fix" by adjusting a test until it passes.

`UTCDateTime` enforces the invariant in one place instead:

* on the way in, anything aware is converted to UTC and anything naive is
  rejected outright, because guessing at a missing offset is how this class of
  bug is created in the first place
* on the way out, values are always returned aware, tagged UTC

Every timestamp column in models.py uses this. Presentation-time conversion to
Singapore time belongs in the layer that renders, not in storage.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "Refusing to store a naive datetime. Attach a timezone at the point "
                "the value is created — guessing one here is how 8pm becomes 4am."
            )
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            # SQLite hands back what it stored, which process_bind_param has
            # already guaranteed was UTC.
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
