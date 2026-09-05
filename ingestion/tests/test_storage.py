from extractor import parse_central, parse_gujarat
from storage import insert_notification, get_notification
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
