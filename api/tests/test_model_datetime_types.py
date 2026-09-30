"""Contract test: every ORM DateTime column must declare timezone=True.

WHY THIS TEST EXISTS
--------------------
The database stores ALL timestamp columns as `timestamp with time zone` (timestamptz).
This was verified against a live Postgres via `information_schema.columns` — there are
ZERO `timestamp without time zone` columns in the entire schema.

However, SQLAlchemy's `mapped_column(...)` with a bare `datetime` annotation infers
`DateTime()` **without** `timezone=True`. When the application writes an aware
datetime into such a column, asyncpg raises:

    asyncpg.exceptions.DataError: invalid input for query argument $N:
    datetime.datetime(2026, 9, 29, 12, 17, 2, tzinfo=datetime.timezone.utc)
    (can't subtract offset-naive and offset-aware datetimes)

This produced a real HTTP 500 on `POST /api/v1/ingest/entities` and would also hit
the Mes 4 job runner when writing `JobRun.started_at` / `finished_at`.

The existing test suite runs on SQLite (`sqlite+aiosqlite:///:memory:`), and SQLite
has no native timestamptz — aiosqlite stores text and never performs asyncpg's
offset arithmetic. That is exactly why 163 green tests, mypy clean and ruff clean
never caught this. A new behavioural test on SQLite will NOT catch it either.

This contract test asserts the ORM type declaration matches the schema contract:
every DateTime column in the ORM must have `timezone=True`. It runs fine on SQLite
because it only inspects the SQLAlchemy metadata, not the database.
"""

from app.models.base import Base
from sqlalchemy import DateTime


def test_all_datetime_columns_are_timezone_aware() -> None:
    """Assert every DateTime column in the ORM declares timezone=True.

    This encodes the real invariant: "every datetime column in this schema is
    timezone-aware, because the database stores them all as timestamptz".
    """
    offending = []

    for table in Base.metadata.tables.values():
        for column in table.columns:
            col_type = column.type
            # Only DateTime columns matter. The timezone attribute can be True, False,
            # or None (default=False); we require it to be explicitly True.
            if isinstance(col_type, DateTime) and not getattr(col_type, "timezone", False):
                offending.append(f"{table.name}.{column.name}")

    assert not offending, (
        "The following ORM columns are declared as DateTime without timezone=True, "
        "but the database stores them as timestamptz. Fix by using "
        "mapped_column(DateTime(timezone=True), ...):\n  - "
        + "\n  - ".join(offending)
    )
