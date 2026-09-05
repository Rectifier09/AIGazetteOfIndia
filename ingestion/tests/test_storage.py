from dataclasses import replace

from extractor import parse_central, parse_gujarat
from storage import insert_notification, get_notification, notification_exists
from pathlib import Path

SAMPLES = Path(__file__).parent.parent / "samples"


def test_insert_and_get_notification_round_trips(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    new_id = insert_notification(db_conn, record, embedding=None, file_hash="hash-2455")
    db_conn.commit()

    fetched = get_notification(db_conn, new_id)
    assert fetched.gazette_id == "CG-DL-E-14052026-272564"
    assert fetched.notification_number == "S.O. 2455(E)"


def test_insert_is_idempotent_on_same_hash(db_conn):
    record = parse_gujarat((SAMPLES / "gujarat_wages.txt").read_text())
    first_id = insert_notification(db_conn, record, embedding=None, file_hash="hash-gj-62")
    db_conn.commit()
    second_id = insert_notification(db_conn, record, embedding=None, file_hash="hash-gj-62")
    db_conn.commit()
    assert first_id == second_id


def test_insert_is_idempotent_when_gazette_id_is_null(db_conn):
    # NULL = NULL is never true in Postgres, so a naive "gazette_id = %s" dedup
    # lookup would miss the existing row and insert a duplicate on every re-run.
    record = replace(parse_central((SAMPLES / "central_so_2455.txt").read_text()), gazette_id=None)
    first_id = insert_notification(db_conn, record, embedding=None, file_hash="hash-null-gid")
    db_conn.commit()
    second_id = insert_notification(db_conn, record, embedding=None, file_hash="hash-null-gid")
    db_conn.commit()

    assert first_id == second_id
    count = db_conn.execute(
        "SELECT count(*) FROM notifications WHERE gazette_id IS NULL AND file_hash = %s",
        ("hash-null-gid",),
    ).fetchone()[0]
    assert count == 1


def test_insert_stores_source_url(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    url = "https://egazette.gov.in/WriteReadData/2026/272564.pdf"
    new_id = insert_notification(
        db_conn, record, embedding=None, file_hash="hash-url", source_url=url
    )
    db_conn.commit()

    stored = db_conn.execute(
        "SELECT source_url FROM notifications WHERE id = %s", (new_id,)
    ).fetchone()[0]
    assert stored == url


def test_insert_leaves_source_url_null_when_not_supplied(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    new_id = insert_notification(db_conn, record, embedding=None, file_hash="hash-no-url")
    db_conn.commit()

    stored = db_conn.execute(
        "SELECT source_url FROM notifications WHERE id = %s", (new_id,)
    ).fetchone()[0]
    assert stored is None


def test_notification_exists_reports_presence_by_source_and_gazette_id(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())

    assert notification_exists(db_conn, "central", record.gazette_id) is False

    insert_notification(db_conn, record, embedding=None, file_hash="hash-exists")
    db_conn.commit()

    assert notification_exists(db_conn, "central", record.gazette_id) is True
    # Matching is scoped to the source, and unknown ids stay absent.
    assert notification_exists(db_conn, "gujarat", record.gazette_id) is False
    assert notification_exists(db_conn, "central", "CG-DL-E-01011999-000000") is False
