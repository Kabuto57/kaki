"""Create tables. Run once on a fresh database.

Alembic is in requirements for when the schema starts changing under real data;
for a first deploy this is enough and avoids making you learn migrations to see
the app run.
"""

from app.db import engine
from app.models import Base


def main() -> None:
    Base.metadata.create_all(engine)
    print("Tables created.")


if __name__ == "__main__":
    main()
