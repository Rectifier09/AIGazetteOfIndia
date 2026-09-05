# ingestion/tests/test_ingest.py
from unittest.mock import patch
from pathlib import Path
from ingest import ingest_notification
from storage import get_notification

SAMPLES = Path(__file__).parent.parent / "samples"


def test_ingest_notification_stores_record_with_embedding(db_conn):
    text = (SAMPLES / "central_so_2455.txt").read_text()
    with patch("ingest.embed_text", return_value=[0.1] * 768):
        notification_id = ingest_notification(db_conn, "central", text)
    db_conn.commit()

    stored = get_notification(db_conn, notification_id)
    assert stored.gazette_id == "CG-DL-E-14052026-272564"


def test_ingest_notification_is_idempotent(db_conn):
    text = (SAMPLES / "gujarat_wages.txt").read_text()
    with patch("ingest.embed_text", return_value=[0.2] * 768):
        first_id = ingest_notification(db_conn, "gujarat", text)
        db_conn.commit()
        second_id = ingest_notification(db_conn, "gujarat", text)
        db_conn.commit()
    assert first_id == second_id
