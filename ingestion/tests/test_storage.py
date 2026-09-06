# ingestion/tests/test_storage.py
from dataclasses import replace

from extractor import parse_central, parse_gujarat
from storage import insert_notification, get_notification, notification_exists, insert_chunks
from pathlib import Path

SAMPLES = Path(__file__).parent.parent / "samples"


def test_insert_and_get_notification_round_trips(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    new_id, is_new = insert_notification(db_conn, record, file_hash="hash-2455")
    db_conn.commit()

    assert is_new is True
    fetched = get_notification(db_conn, new_id)
    assert fetched.gazette_id == "CG-DL-E-14052026-272564"
    assert fetched.notification_number == "S.O. 2455(E)"


def test_insert_is_idempotent_on_same_hash(db_conn):
    record = parse_gujarat((SAMPLES / "gujarat_wages.txt").read_text())
    first_id, first_is_new = insert_notification(db_conn, record, file_hash="hash-gj-62")
    db_conn.commit()
    second_id, second_is_new = insert_notification(db_conn, record, file_hash="hash-gj-62")
    db_conn.commit()

    assert first_id == second_id
    assert first_is_new is True
    assert second_is_new is False


def test_insert_is_idempotent_when_gazette_id_is_null(db_conn):
    # NULL = NULL is never true in Postgres, so a naive "gazette_id = %s" dedup
    # lookup would miss the existing row and insert a duplicate on every re-run.
    record = replace(parse_central((SAMPLES / "central_so_2455.txt").read_text()), gazette_id=None)
    first_id, _ = insert_notification(db_conn, record, file_hash="hash-null-gid")
    db_conn.commit()
    second_id, second_is_new = insert_notification(db_conn, record, file_hash="hash-null-gid")
    db_conn.commit()

    assert first_id == second_id
    assert second_is_new is False
    count = db_conn.execute(
        "SELECT count(*) FROM notifications WHERE gazette_id IS NULL AND file_hash = %s",
        ("hash-null-gid",),
    ).fetchone()[0]
    assert count == 1


def test_insert_stores_source_url(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    url = "https://egazette.gov.in/WriteReadData/2026/272564.pdf"
    new_id, _ = insert_notification(db_conn, record, file_hash="hash-url", source_url=url)
    db_conn.commit()

    stored = db_conn.execute(
        "SELECT source_url FROM notifications WHERE id = %s", (new_id,)
    ).fetchone()[0]
    assert stored == url


def test_insert_leaves_source_url_null_when_not_supplied(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    new_id, _ = insert_notification(db_conn, record, file_hash="hash-no-url")
    db_conn.commit()

    stored = db_conn.execute(
        "SELECT source_url FROM notifications WHERE id = %s", (new_id,)
    ).fetchone()[0]
    assert stored is None


def test_notification_exists_reports_presence_by_source_and_gazette_id(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())

    assert notification_exists(db_conn, "central", record.gazette_id) is False

    insert_notification(db_conn, record, file_hash="hash-exists")
    db_conn.commit()

    assert notification_exists(db_conn, "central", record.gazette_id) is True
    assert notification_exists(db_conn, "gujarat", record.gazette_id) is False
    assert notification_exists(db_conn, "central", "CG-DL-E-01011999-000000") is False


def test_insert_chunks_stores_one_row_per_chunk_in_order(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    notification_id, _ = insert_notification(db_conn, record, file_hash="hash-chunks")
    db_conn.commit()

    insert_chunks(
        db_conn, notification_id,
        [("first chunk text", [0.1] * 768), ("second chunk text", [0.2] * 768)],
    )
    db_conn.commit()

    rows = db_conn.execute(
        "SELECT chunk_index, chunk_text FROM notification_chunks "
        "WHERE notification_id = %s ORDER BY chunk_index",
        (notification_id,),
    ).fetchall()
    assert [r[1] for r in rows] == ["first chunk text", "second chunk text"]
    assert [r[0] for r in rows] == [0, 1]


def test_deleting_notification_cascades_to_its_chunks(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    notification_id, _ = insert_notification(db_conn, record, file_hash="hash-cascade")
    db_conn.commit()
    insert_chunks(db_conn, notification_id, [("chunk", [0.1] * 768)])
    db_conn.commit()

    db_conn.execute("DELETE FROM notifications WHERE id = %s", (notification_id,))
    db_conn.commit()

    count = db_conn.execute(
        "SELECT count(*) FROM notification_chunks WHERE notification_id = %s", (notification_id,)
    ).fetchone()[0]
    assert count == 0
