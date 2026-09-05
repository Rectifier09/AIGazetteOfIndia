from pathlib import Path

from discovery import parse_results_table

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_results_table_extracts_gazette_rows():
    html = (FIXTURES / "searchministry_may2025_results.html").read_text()
    rows = parse_results_table(html)
    assert len(rows) == 6
    assert all(r["gazette_id"].startswith("CG-DL-E-") for r in rows)
    assert any("COW" in r["subject"] for r in rows)


def test_parse_results_table_returns_empty_list_when_no_gazettes():
    assert parse_results_table("<html>Total No. of Gazettes : 0</html>") == []
