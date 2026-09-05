# ingestion/tests/test_ingest.py
import pytest
from unittest.mock import patch
from pathlib import Path
from ingest import ingest_notification, OutOfScopeError
from storage import get_notification

SAMPLES = Path(__file__).parent.parent / "samples"

# Minimal Central-Gazette-shaped text with no "Code on <name>, <year> (<n> of
# <year>)" citation — i.e. one of the many ministry-28 notifications that are
# not Labour Code documents.
OFF_TOPIC_TEXT = (
    "MINISTRY OF LABOUR AND EMPLOYMENT\n"
    "NOTIFICATION\n"
    "New Delhi, the 3rd June, 2025\n"
    "S.O. 9(E).— In exercise of the powers conferred by the Mines Act, 1952, "
    "the Central Government hereby appoints an inspector.\n"
)


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


def test_known_gazette_id_overrides_the_id_parsed_out_of_the_pdf_text(db_conn):
    # Real gazette PDFs carry a watermark that garbles the ID during text
    # extraction, so the discovery-supplied ID must win over the parsed one.
    text = (SAMPLES / "central_so_2455.txt").read_text()
    with patch("ingest.embed_text", return_value=[0.1] * 768):
        notification_id = ingest_notification(
            db_conn, "central", text, known_gazette_id="CG-DL-E-22052025-263307"
        )
    db_conn.commit()

    stored = get_notification(db_conn, notification_id)
    assert stored.gazette_id == "CG-DL-E-22052025-263307"


def test_known_gazette_id_is_used_even_when_the_text_yields_none(db_conn):
    text = (SAMPLES / "gujarat_wages.txt").read_text().replace("Extra No. 62", "Extra No. ~")
    with patch("ingest.embed_text", return_value=[0.2] * 768):
        notification_id = ingest_notification(
            db_conn, "gujarat", text, known_gazette_id="Gujarat-Extra-62"
        )
    db_conn.commit()

    assert get_notification(db_conn, notification_id).gazette_id == "Gujarat-Extra-62"


def test_source_url_is_stored_when_supplied(db_conn):
    text = (SAMPLES / "central_so_2455.txt").read_text()
    url = "https://egazette.gov.in/WriteReadData/2026/272564.pdf"
    with patch("ingest.embed_text", return_value=[0.1] * 768):
        notification_id = ingest_notification(db_conn, "central", text, source_url=url)
    db_conn.commit()

    stored = db_conn.execute(
        "SELECT source_url FROM notifications WHERE id = %s", (notification_id,)
    ).fetchone()[0]
    assert stored == url


def test_off_topic_document_is_rejected_without_embedding_or_insert(db_conn):
    with patch("ingest.embed_text") as mock_embed:
        with pytest.raises(OutOfScopeError):
            ingest_notification(db_conn, "central", OFF_TOPIC_TEXT)
    db_conn.commit()

    mock_embed.assert_not_called()
    count = db_conn.execute("SELECT count(*) FROM notifications").fetchone()[0]
    assert count == 0


def test_unknown_source_still_raises_value_error(db_conn):
    with pytest.raises(ValueError):
        ingest_notification(db_conn, "martian", "whatever")
