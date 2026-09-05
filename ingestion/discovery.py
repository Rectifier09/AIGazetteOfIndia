"""Central Gazette discovery: session bootstrap + month/year search.

egazette.gov.in is a legacy ASP.NET WebForms site. Reaching the Ministry
search results requires replaying its real navigation/postback sequence:

1. GET https://egazette.gov.in/ -> 302 to a fresh (S(sessionid))/default.aspx.
   Strip the trailing "default.aspx" to get the reusable base_url prefix.
2. GET base_url + "default.aspx", then GET base_url + "SearchMenu.aspx"
   (with a Referer header) to establish the session's page-navigation state.
3. On SearchMenu.aspx, the "Search by Ministry" option is a real ASP.NET
   form-submit button (name="btnMinistry"), not a plain link. POSTing that
   button click is required: the server redirects to
   "SearchMinistry.aspx?id=<n>" and, in doing so, sets session-scoped state
   that the SearchMinistry.aspx postback handler depends on. Skipping this
   step and GETting SearchMinistry.aspx directly still renders the search
   form (200 OK) but makes the *next* POST throw an unhandled server
   exception, which the site's production customErrors settings mask as a
   generic, undiagnosable HTTP 500 "Runtime Error" page.
4. On the redirected SearchMinistry.aspx page, a single POST carrying
   ddlMinistry, rdb_Option=0 (Month/Year Wise mode), ddlmonth, ddlyear, the
   ImgSubmitDetails.x/y image-button coordinates, and the page's current
   ASP.NET postback hidden fields returns the results table
   (id="gvGazetteList"). No separate intermediate "ministry selected"
   postback is needed once step 3 has been done.

The full set of hidden postback fields the server requires on every POST is
__VIEWSTATE, __VIEWSTATEGENERATOR, __VIEWSTATEENCRYPTED, __EVENTVALIDATION,
__SCROLLPOSITIONX, __SCROLLPOSITIONY, and a custom "hidden1" field. Omitting
__SCROLLPOSITIONX/Y or __VIEWSTATEENCRYPTED (even as empty strings) also
causes the same generic 500 - the server apparently rejects postbacks
missing any of the hidden fields it rendered, not just ones with bad values.
"""
import io
import logging
import re
import time
from urllib.parse import urljoin

import pdfplumber
import requests
from bs4 import BeautifulSoup

from download import pdf_url_for, download_pdf
from ingest import ingest_notification, OutOfScopeError
from storage import notification_exists

logger = logging.getLogger(__name__)

MINISTRY_LABOUR_AND_EMPLOYMENT = "28"

REQUEST_DELAY_SECONDS = 1.0  # politeness delay between requests to a government server

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_TIMEOUT = 30  # seconds; without this a stalled government server hangs the run forever

# Present on every real results page, whether the result count is 0 or not, so
# it distinguishes "reached the results page, no rows" from "got a 500 / error
# page / failed postback", both of which otherwise parse to an empty row list.
_RESULTS_PAGE_MARKER = "Total No. of Gazettes"


def bootstrap_session() -> tuple[requests.Session, str]:
    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT})
    resp = session.get(
        "https://egazette.gov.in/", allow_redirects=False, verify=False, timeout=_TIMEOUT
    )
    base_url = resp.headers["location"].rsplit("/", 1)[0] + "/"
    session.get(base_url + "default.aspx", verify=False, timeout=_TIMEOUT)
    session.get(
        base_url + "SearchMenu.aspx",
        headers={"Referer": base_url + "default.aspx"},
        verify=False,
        timeout=_TIMEOUT,
    )
    return session, base_url


def _extract_form_state(html: str) -> dict:
    def field(name):
        m = re.search(rf'{name}"[^>]*value="([^"]*)"', html)
        return m.group(1) if m else ""

    return {
        "__VIEWSTATE": field("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": field("__VIEWSTATEGENERATOR"),
        "__VIEWSTATEENCRYPTED": field("__VIEWSTATEENCRYPTED"),
        "__EVENTVALIDATION": field("__EVENTVALIDATION"),
        "__SCROLLPOSITIONX": field("__SCROLLPOSITIONX") or "0",
        "__SCROLLPOSITIONY": field("__SCROLLPOSITIONY") or "0",
        "hidden1": field("hidden1"),
    }


def search_month(session: requests.Session, base_url: str, ministry_id: str, year: int, month: int) -> list[dict]:
    # Re-fetch SearchMenu.aspx for fresh postback state, then click "Search
    # by Ministry" (a real form-submit button) to reach SearchMinistry.aspx
    # via the server's own redirect. This step is required - see module
    # docstring for why a direct GET to SearchMinistry.aspx is not enough.
    menu_page = session.get(
        base_url + "SearchMenu.aspx",
        headers={"Referer": base_url + "default.aspx"},
        verify=False,
        timeout=_TIMEOUT,
    )
    menu_state = _extract_form_state(menu_page.text)
    menu_post = session.post(
        base_url + "SearchMenu.aspx",
        headers={"Referer": base_url + "SearchMenu.aspx"},
        data={**menu_state, "__EVENTTARGET": "", "__EVENTARGUMENT": "", "btnMinistry": "Search by Ministry"},
        verify=False,
        allow_redirects=False,
        timeout=_TIMEOUT,
    )
    ministry_url = urljoin(base_url, menu_post.headers["location"])

    form_page = session.get(
        ministry_url,
        headers={"Referer": base_url + "SearchMenu.aspx"},
        verify=False,
        timeout=_TIMEOUT,
    )
    state = _extract_form_state(form_page.text)
    results = session.post(
        ministry_url,
        headers={"Referer": ministry_url},
        data={
            **state,
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "ddlMinistry": ministry_id,
            "rdb_Option": "0",
            "ddlmonth": str(month),
            "ddlyear": str(year),
            "ImgSubmitDetails.x": "10",
            "ImgSubmitDetails.y": "10",
        },
        verify=False,
        timeout=_TIMEOUT,
    )
    # The site masks server-side failures as generic 500 "Runtime Error" pages,
    # and a failed ASP.NET postback re-renders the form with no results table.
    # Both parse to [] — indistinguishable from a genuinely empty month unless
    # we check the status and look for the results-page marker explicitly.
    results.raise_for_status()
    if _RESULTS_PAGE_MARKER not in results.text:
        raise RuntimeError(
            f"Search for {year}-{month:02d} did not reach a results page "
            f"(status {results.status_code})"
        )

    rows = parse_results_table(results.text)
    reported = _reported_gazette_count(results.text)
    if reported is not None and reported != len(rows):
        # Not fatal: most plausibly the results table is paginated and we only
        # ever read page one. Worth surfacing, not worth aborting the backfill.
        logger.warning(
            f"  {year}-{month:02d}: page reports {reported} gazette(s) but "
            f"{len(rows)} row(s) parsed — results may be paginated or truncated"
        )
    return rows


def _reported_gazette_count(html: str) -> int | None:
    m = re.search(r"Total No\. of Gazettes\s*:\s*(\d+)", html)
    return int(m.group(1)) if m else None


def parse_results_table(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find(id="gvGazetteList")
    if table is None:
        return []
    rows = []
    for tr in table.find_all("tr")[1:]:  # skip header row
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 10:
            continue
        rows.append({
            "subject": cells[4],
            "part_section": cells[6],
            "issue_date": cells[7],
            "publish_date": cells[8],
            "gazette_id": cells[9],
        })
    return rows


def _pdf_to_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def discover_and_ingest(conn, ministry_id: str, start_year: int, end_year: int) -> int:
    """Walk every month in [start_year, end_year] and ingest what it finds.

    A backfill spans dozens of months and hundreds of documents against a
    legacy government site, so no single bad document or transient network
    failure may abort the run: every per-month search and every per-row
    download/parse/ingest is isolated, counted, and logged.

    Returns the number of notifications actually ingested; skipped (already
    present or off-topic) and failed counts are logged in the final summary.
    """
    session, base_url = bootstrap_session()
    ingested = 0
    skipped = 0
    out_of_scope = 0
    failed = 0

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            logger.info(f"Searching {year}-{month:02d} for ministry {ministry_id}...")
            try:
                rows = search_month(session, base_url, ministry_id, year, month)
            except Exception as e:
                failed += 1
                logger.error(f"  Search failed for {year}-{month:02d}: {e}")
                time.sleep(REQUEST_DELAY_SECONDS)
                continue
            time.sleep(REQUEST_DELAY_SECONDS)
            logger.info(f"  Found {len(rows)} notification(s) for {year}-{month:02d}")

            for row in rows:
                gazette_id = row["gazette_id"]
                try:
                    # Cheap pre-check so a resumed run doesn't re-download,
                    # re-parse and re-embed documents it already has.
                    if notification_exists(conn, "central", gazette_id):
                        skipped += 1
                        logger.info(f"  Skipping {gazette_id} (already ingested)")
                        continue

                    source_url = pdf_url_for(gazette_id)
                    pdf_bytes = download_pdf(source_url)
                    time.sleep(REQUEST_DELAY_SECONDS)
                    raw_text = _pdf_to_text(pdf_bytes)
                    ingest_notification(
                        conn,
                        "central",
                        raw_text,
                        known_gazette_id=gazette_id,
                        source_url=source_url,
                    )
                    conn.commit()
                    ingested += 1
                    logger.info(f"  Ingested {gazette_id} ({ingested} total so far)")
                except OutOfScopeError as e:
                    conn.rollback()
                    out_of_scope += 1
                    logger.info(f"  Skipping {gazette_id} (not a Labour Code doc): {e}")
                except Exception as e:
                    conn.rollback()
                    failed += 1
                    logger.error(f"  Failed to ingest {gazette_id}: {e}")

    logger.info(
        f"Done. Ingested {ingested}, already present {skipped}, "
        f"out of scope {out_of_scope}, failed {failed}."
    )
    return ingested
