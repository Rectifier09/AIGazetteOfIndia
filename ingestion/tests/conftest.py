# ingestion/tests/conftest.py
import pytest
from config import get_connection


@pytest.fixture
def db_conn():
    conn = get_connection()
    yield conn
    # WARNING: this truncates notifications/relationships/notification_chunks
    # on whatever database DATABASE_URL (ingestion/.env) points at — this
    # project's tests intentionally run against the real database rather
    # than a separate local Postgres. Never run this suite against a
    # database holding real data you want to keep (e.g. right after a
    # production backfill) without re-running the backfill afterward.
    conn.execute("TRUNCATE notifications, relationships, notification_chunks RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()
