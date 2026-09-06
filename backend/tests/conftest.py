import pytest
from app.config import get_connection


@pytest.fixture
def db_conn():
    conn = get_connection()
    yield conn
    conn.execute("TRUNCATE notifications, relationships, notification_chunks RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()


@pytest.fixture
def insert_test_notification(db_conn):
    """Insert a minimal notification + one chunk directly via SQL — this plan
    has no write-path code of its own (that's the ingestion pipeline's job),
    so tests that need data to query against insert it directly. The call
    signature is unchanged from before chunking existed — only what it does
    internally changed (a chunk row now carries the embedding, not the
    notification row) — so no test that calls this fixture needs editing."""
    def _insert(gazette_id: str, operative_text: str, embedding: list[float] | None = None,
                source: str = "central", part: str = "Part II", section: str | None = None,
                notification_date: str = "22nd May, 2025", act_reference: str | None = None):
        row = db_conn.execute(
            """
            INSERT INTO notifications
                (source, gazette_id, part, section, notification_date, act_reference,
                 operative_text, file_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (source, gazette_id, part, section, notification_date, act_reference,
             operative_text, f"test-hash-{gazette_id}"),
        ).fetchone()
        notification_id = row[0]
        if embedding is not None:
            db_conn.execute(
                """
                INSERT INTO notification_chunks (notification_id, chunk_index, chunk_text, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                (notification_id, 0, operative_text, embedding),
            )
        db_conn.commit()
        return notification_id
    return _insert
