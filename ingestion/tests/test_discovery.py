import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from discovery import parse_results_table, discover_and_ingest, search_month
from extractor import parse_central
from storage import insert_notification

FIXTURES = Path(__file__).parent / "fixtures"

FAKE_ROW = {
    "gazette_id": "CG-DL-E-22052025-263307",
    "subject": "COW",
    "part_section": "Part II-Section 3",
    "issue_date": "22-May-2025",
    "publish_date": "22-May-2025",
}

# Stands in for pdfplumber's output on a real gazette PDF: the security
# watermark garbles the gazette id past recognition (so parse_central yields
# gazette_id=None) while the act reference still comes through cleanly.
IN_SCOPE_TEXT = (
    "CG-DxLx-xEG-I2D2H0x5x2x0 25-263307\n"
    "MINISTRY OF LABOUR AND EMPLOYMENT\n"
    "NOTIFICATION\n"
    "New Delhi, the 22nd May, 2025\n"
    "S.O. 1(E).— In exercise of the powers conferred by section 67 of "
    "the Code on Wages, 2019 (29 of 2019), the Central Government hereby "
    "makes the following rules.\n"
)

OFF_TOPIC_TEXT = (
    "MINISTRY OF LABOUR AND EMPLOYMENT\n"
    "NOTIFICATION\n"
    "New Delhi, the 22nd May, 2025\n"
    "S.O. 2(E).— In exercise of the powers conferred by the Mines Act, 1952, "
    "the Central Government hereby appoints an inspector.\n"
)


def _one_month_of(rows):
    """search_month side_effect for a single year: `rows` in January, then empty."""
    return [rows] + [[]] * 11


# ---------------------------------------------------------------------------
# parse_results_table
# ---------------------------------------------------------------------------

def test_parse_results_table_extracts_gazette_rows():
    html = (FIXTURES / "searchministry_may2025_results.html").read_text()
    rows = parse_results_table(html)
    assert len(rows) == 6
    assert all(r["gazette_id"].startswith("CG-DL-E-") for r in rows)
    assert any("COW" in r["subject"] for r in rows)


def test_parse_results_table_returns_empty_list_when_no_gazettes():
    assert parse_results_table("<html>Total No. of Gazettes : 0</html>") == []


# ---------------------------------------------------------------------------
# search_month failure detection
# ---------------------------------------------------------------------------

def _fake_session(results_response):
    session = MagicMock()
    plain_page = MagicMock()
    plain_page.text = "<html></html>"
    session.get.return_value = plain_page

    redirect = MagicMock()
    redirect.headers = {"location": "SearchMinistry.aspx?id=3"}
    session.post.side_effect = [redirect, results_response]
    return session


def _results_response(text, status_code=200):
    response = MagicMock()
    response.text = text
    response.status_code = status_code
    response.raise_for_status.return_value = None
    return response


def test_search_month_returns_rows_from_a_real_results_page():
    html = (FIXTURES / "searchministry_may2025_results.html").read_text()
    session = _fake_session(_results_response(html))
    rows = search_month(session, "https://egazette.gov.in/(S(x))/", "28", 2025, 5)
    assert len(rows) == 6


def test_search_month_accepts_a_genuinely_empty_month():
    session = _fake_session(_results_response("<html>Total No. of Gazettes : 0</html>"))
    assert search_month(session, "https://egazette.gov.in/(S(x))/", "28", 2025, 5) == []


def test_search_month_raises_on_http_error():
    response = _results_response("<html>Runtime Error</html>", status_code=500)
    response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    session = _fake_session(response)
    with pytest.raises(requests.HTTPError):
        search_month(session, "https://egazette.gov.in/(S(x))/", "28", 2025, 5)


def test_search_month_raises_when_the_response_is_not_a_results_page():
    # A failed ASP.NET postback re-renders the form: HTTP 200, no results table,
    # and no "Total No. of Gazettes" marker. Without this check it would be
    # indistinguishable from a month with zero notifications.
    session = _fake_session(_results_response("<html><form>Search by Ministry</form></html>"))
    with pytest.raises(RuntimeError, match="did not reach a results page"):
        search_month(session, "https://egazette.gov.in/(S(x))/", "28", 2025, 5)


def test_search_month_warns_but_returns_rows_when_the_reported_count_disagrees(caplog):
    html = (FIXTURES / "searchministry_may2025_results.html").read_text().replace(
        "Total No. of Gazettes : 6", "Total No. of Gazettes : 9"
    )
    session = _fake_session(_results_response(html))
    with caplog.at_level(logging.WARNING):
        rows = search_month(session, "https://egazette.gov.in/(S(x))/", "28", 2025, 5)
    assert len(rows) == 6
    assert any("paginated or truncated" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# discover_and_ingest
# ---------------------------------------------------------------------------

def test_discover_and_ingest_ingests_each_found_row(db_conn):
    with patch("discovery.bootstrap_session", return_value=(None, "")), \
         patch("discovery.search_month", side_effect=_one_month_of([FAKE_ROW])), \
         patch("discovery.download_pdf", return_value=b"%PDF-fake"), \
         patch("discovery._pdf_to_text", return_value=IN_SCOPE_TEXT), \
         patch("discovery.time.sleep"), \
         patch("ingest.embed_text", return_value=[0.1] * 768):
        count = discover_and_ingest(db_conn, "28", 2025, 2025)
    assert count == 1


def test_discover_and_ingest_logs_progress_per_month_and_row(db_conn, caplog):
    with patch("discovery.bootstrap_session", return_value=(None, "")), \
         patch("discovery.search_month", side_effect=_one_month_of([FAKE_ROW])), \
         patch("discovery.download_pdf", return_value=b"%PDF-fake"), \
         patch("discovery._pdf_to_text", return_value=IN_SCOPE_TEXT), \
         patch("discovery.time.sleep"), \
         patch("ingest.embed_text", return_value=[0.1] * 768), \
         caplog.at_level(logging.INFO):
        discover_and_ingest(db_conn, "28", 2025, 2025)
    assert any("2025-01" in r.message or "2025/1" in r.message for r in caplog.records)
    assert any("CG-DL-E-22052025-263307" in r.message for r in caplog.records)


def test_discover_and_ingest_stores_the_discovered_gazette_id_and_source_url(db_conn):
    with patch("discovery.bootstrap_session", return_value=(None, "")), \
         patch("discovery.search_month", side_effect=_one_month_of([FAKE_ROW])), \
         patch("discovery.download_pdf", return_value=b"%PDF-fake"), \
         patch("discovery._pdf_to_text", return_value=IN_SCOPE_TEXT), \
         patch("discovery.time.sleep"), \
         patch("ingest.embed_text", return_value=[0.1] * 768):
        discover_and_ingest(db_conn, "28", 2025, 2025)

    row = db_conn.execute(
        "SELECT gazette_id, source_url FROM notifications"
    ).fetchone()
    # The PDF text yields no usable id; the discovery row's id is what's stored.
    assert row[0] == "CG-DL-E-22052025-263307"
    assert row[1] == "https://egazette.gov.in/WriteReadData/2025/263307.pdf"


def test_discover_and_ingest_continues_after_a_failing_row(db_conn):
    bad_row = {**FAKE_ROW, "gazette_id": "CG-DL-E-21052025-263276"}
    with patch("discovery.bootstrap_session", return_value=(None, "")), \
         patch("discovery.search_month", side_effect=_one_month_of([bad_row, FAKE_ROW])), \
         patch("discovery.download_pdf",
               side_effect=[requests.HTTPError("404 Not Found"), b"%PDF-fake"]), \
         patch("discovery._pdf_to_text", return_value=IN_SCOPE_TEXT), \
         patch("discovery.time.sleep"), \
         patch("ingest.embed_text", return_value=[0.1] * 768):
        count = discover_and_ingest(db_conn, "28", 2025, 2025)

    assert count == 1
    stored = db_conn.execute("SELECT gazette_id FROM notifications").fetchall()
    assert [r[0] for r in stored] == ["CG-DL-E-22052025-263307"]


def test_discover_and_ingest_continues_after_a_failing_month_search(db_conn):
    with patch("discovery.bootstrap_session", return_value=(None, "")), \
         patch("discovery.search_month",
               side_effect=[RuntimeError("did not reach a results page"), [FAKE_ROW]] + [[]] * 10), \
         patch("discovery.download_pdf", return_value=b"%PDF-fake"), \
         patch("discovery._pdf_to_text", return_value=IN_SCOPE_TEXT), \
         patch("discovery.time.sleep"), \
         patch("ingest.embed_text", return_value=[0.1] * 768):
        count = discover_and_ingest(db_conn, "28", 2025, 2025)
    assert count == 1


def test_discover_and_ingest_skips_already_ingested_without_downloading(db_conn, caplog):
    record = parse_central((Path(__file__).parent.parent / "samples" / "central_so_2455.txt").read_text())
    record.gazette_id = FAKE_ROW["gazette_id"]
    insert_notification(db_conn, record, embedding=None, file_hash="pre-existing")
    db_conn.commit()

    mock_download = Mock(return_value=b"%PDF-fake")
    with patch("discovery.bootstrap_session", return_value=(None, "")), \
         patch("discovery.search_month", side_effect=_one_month_of([FAKE_ROW])), \
         patch("discovery.download_pdf", mock_download), \
         patch("discovery._pdf_to_text", return_value=IN_SCOPE_TEXT), \
         patch("discovery.time.sleep"), \
         patch("ingest.embed_text", return_value=[0.1] * 768), \
         caplog.at_level(logging.INFO):
        count = discover_and_ingest(db_conn, "28", 2025, 2025)

    mock_download.assert_not_called()
    assert count == 0
    assert any("already ingested" in r.message for r in caplog.records)


def test_discover_and_ingest_skips_off_topic_documents_without_embedding(db_conn, caplog):
    mock_embed = Mock(return_value=[0.1] * 768)
    with patch("discovery.bootstrap_session", return_value=(None, "")), \
         patch("discovery.search_month", side_effect=_one_month_of([FAKE_ROW])), \
         patch("discovery.download_pdf", return_value=b"%PDF-fake"), \
         patch("discovery._pdf_to_text", return_value=OFF_TOPIC_TEXT), \
         patch("discovery.time.sleep"), \
         patch("ingest.embed_text", mock_embed), \
         caplog.at_level(logging.INFO):
        count = discover_and_ingest(db_conn, "28", 2025, 2025)

    assert count == 0
    mock_embed.assert_not_called()
    assert db_conn.execute("SELECT count(*) FROM notifications").fetchone()[0] == 0
    assert any("not a Labour Code doc" in r.message for r in caplog.records)
    # Skipped for scope, not counted or logged as a failure.
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)
