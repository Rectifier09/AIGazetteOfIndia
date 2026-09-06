# ingestion/storage.py
import psycopg
from extractor import NotificationRecord


def notification_exists(conn: psycopg.Connection, source: str, gazette_id: str) -> bool:
    """Cheap "have we already ingested this gazette_id?" check.

    Deliberately looser than insert_notification's idempotency check (which also
    matches on file_hash): this exists so a resumed run can skip downloading,
    parsing and embedding a document it already has, using only the gazette_id
    the discovery step hands us before any of that work happens.
    """
    row = conn.execute(
        "SELECT 1 FROM notifications WHERE source = %s AND gazette_id = %s LIMIT 1",
        (source, gazette_id),
    ).fetchone()
    return row is not None


def insert_notification(
    conn: psycopg.Connection,
    record: NotificationRecord,
    file_hash: str,
    source_url: str | None = None,
) -> tuple[int, bool]:
    """Returns (notification_id, is_new). is_new is False when an existing row
    with the same (source, gazette_id, file_hash) already matched — callers use
    this to skip chunking/embedding work entirely for duplicates."""
    # gazette_id IS NOT DISTINCT FROM %s rather than = %s: Postgres evaluates
    # NULL = NULL as NULL (never true), so a record with no gazette_id would
    # never match an existing row and every re-run would insert a duplicate.
    existing = conn.execute(
        "SELECT id FROM notifications "
        "WHERE source = %s AND gazette_id IS NOT DISTINCT FROM %s AND file_hash = %s",
        (record.source, record.gazette_id, file_hash),
    ).fetchone()
    if existing:
        return existing[0], False

    row = conn.execute(
        """
        INSERT INTO notifications
            (source, gazette_id, gazette_type, part, section, issuing_authority,
             notification_number, notification_date, act_reference, signatory,
             operative_text, source_url, file_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            record.source, record.gazette_id, record.gazette_type, record.part,
            record.section, record.issuing_authority, record.notification_number,
            record.notification_date, record.act_reference, record.signatory,
            record.operative_text, source_url, file_hash,
        ),
    ).fetchone()
    notification_id = row[0]

    for rel in record.relationships:
        conn.execute(
            "INSERT INTO relationships (notification_id, rel_type, target) VALUES (%s, %s, %s)",
            (notification_id, rel.rel_type, rel.target),
        )
    return notification_id, True


def insert_chunks(
    conn: psycopg.Connection, notification_id: int, chunks: list[tuple[str, list[float]]]
) -> None:
    for index, (chunk_text_value, embedding) in enumerate(chunks):
        conn.execute(
            """
            INSERT INTO notification_chunks (notification_id, chunk_index, chunk_text, embedding)
            VALUES (%s, %s, %s, %s)
            """,
            (notification_id, index, chunk_text_value, embedding),
        )


def get_notification(conn: psycopg.Connection, notification_id: int) -> NotificationRecord | None:
    row = conn.execute(
        """
        SELECT source, gazette_id, gazette_type, part, section, issuing_authority,
               notification_number, notification_date, act_reference, signatory, operative_text
        FROM notifications WHERE id = %s
        """,
        (notification_id,),
    ).fetchone()
    if row is None:
        return None
    return NotificationRecord(
        source=row[0], gazette_id=row[1], gazette_type=row[2], part=row[3], section=row[4],
        issuing_authority=row[5], notification_number=row[6], notification_date=row[7],
        act_reference=row[8], signatory=row[9], operative_text=row[10],
    )
