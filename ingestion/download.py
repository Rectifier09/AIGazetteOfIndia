# ingestion/download.py
import re
import requests

# Same browser UA discovery.py sends: some government hosts filter out the
# default python-requests/... User-Agent.
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def pdf_url_for(gazette_id: str) -> str:
    m = re.search(r"(\d{8})-(\d+)$", gazette_id)
    if not m:
        raise ValueError(f"Cannot parse year/id from gazette_id: {gazette_id!r}")
    ddmmyyyy, numeric_id = m.groups()
    year = ddmmyyyy[-4:]
    return f"https://egazette.gov.in/WriteReadData/{year}/{numeric_id}.pdf"


def download_pdf(url: str) -> bytes:
    response = requests.get(
        url, headers={"User-Agent": _USER_AGENT}, verify=False, timeout=30
    )
    response.raise_for_status()
    return response.content
