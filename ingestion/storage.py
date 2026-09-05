# ingestion/storage.py
import psycopg
from extractor import NotificationRecord


def insert_notification(
    conn: psycopg.Connection,
    record: NotificationRecord,
    embedding: list[float] | None,
    file_hash: str,
) -> int:
    existing = conn.execute(
        "SELECT id FROM notifications WHERE source = %s AND gazette_id = %s AND file_hash = %s",
        (record.source, record.gazette_id, file_hash),
    ).fetchone()
    if existing:
        return existing[0]

    row = conn.execute(
        """
        INSERT INTO notifications
            (source, gazette_id, gazette_type, part, section, issuing_authority,
             notification_number, notification_date, act_reference, signatory,
             operative_text, file_hash, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            record.source, record.gazette_id, record.gazette_type, record.part,
            record.section, record.issuing_authority, record.notification_number,
            record.notification_date, record.act_reference, record.signatory,
            record.operative_text, file_hash, embedding,
        ),
    ).fetchone()
    notification_id = row[0]

    for rel in record.relationships:
        conn.execute(
            "INSERT INTO relationships (notification_id, rel_type, target) VALUES (%s, %s, %s)",
            (notification_id, rel.rel_type, rel.target),
        )
    return notification_id


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
