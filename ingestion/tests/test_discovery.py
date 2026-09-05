from pathlib import Path
from unittest.mock import patch

from discovery import parse_results_table, discover_and_ingest

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_results_table_extracts_gazette_rows():
    html = (FIXTURES / "searchministry_may2025_results.html").read_text()
    rows = parse_results_table(html)
    assert len(rows) == 6
    assert all(r["gazette_id"].startswith("CG-DL-E-") for r in rows)
    assert any("COW" in r["subject"] for r in rows)


def test_parse_results_table_returns_empty_list_when_no_gazettes():
    assert parse_results_table("<html>Total No. of Gazettes : 0</html>") == []


def test_discover_and_ingest_ingests_each_found_row(db_conn):
    fake_row = {"gazette_id": "CG-DL-E-22052025-263307", "subject": "COW",
                "part_section": "Part II-Section 3", "issue_date": "22-May-2025", "publish_date": "22-May-2025"}
    with patch("discovery.bootstrap_session", return_value=(None, "")), \
         patch("discovery.search_month", side_effect=[[fake_row]] + [[]] * 11), \
         patch("discovery.download_pdf", return_value=b"%PDF-fake"), \
         patch("discovery._pdf_to_text", return_value="MINISTRY OF LABOUR AND EMPLOYMENT\nS.O. 1(E).— test"), \
         patch("discovery.time.sleep"), \
         patch("ingest.embed_text", return_value=[0.1] * 768):
        count = discover_and_ingest(db_conn, "28", 2025, 2025)
    assert count == 1
