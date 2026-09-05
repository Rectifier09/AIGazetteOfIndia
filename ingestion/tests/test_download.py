# ingestion/tests/test_download.py
from download import pdf_url_for


def test_pdf_url_for_extracts_year_and_trailing_id():
    assert pdf_url_for("CG-DL-E-22052025-263307") == "https://egazette.gov.in/WriteReadData/2025/263307.pdf"


def test_pdf_url_for_handles_different_id():
    assert pdf_url_for("CG-DL-E-21052025-263276") == "https://egazette.gov.in/WriteReadData/2025/263276.pdf"
