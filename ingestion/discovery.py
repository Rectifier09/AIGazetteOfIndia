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
import re

import requests
from bs4 import BeautifulSoup

MINISTRY_LABOUR_AND_EMPLOYMENT = "28"

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def bootstrap_session() -> tuple[requests.Session, str]:
    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT})
    resp = session.get("https://egazette.gov.in/", allow_redirects=False, verify=False)
    base_url = resp.headers["location"].rsplit("/", 1)[0] + "/"
    session.get(base_url + "default.aspx", verify=False)
    session.get(base_url + "SearchMenu.aspx", headers={"Referer": base_url + "default.aspx"}, verify=False)
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
    )
    menu_state = _extract_form_state(menu_page.text)
    menu_post = session.post(
        base_url + "SearchMenu.aspx",
        headers={"Referer": base_url + "SearchMenu.aspx"},
        data={**menu_state, "__EVENTTARGET": "", "__EVENTARGUMENT": "", "btnMinistry": "Search by Ministry"},
        verify=False,
        allow_redirects=False,
    )
    ministry_url = menu_post.headers["location"]

    form_page = session.get(ministry_url, headers={"Referer": base_url + "SearchMenu.aspx"}, verify=False)
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
    )
    return parse_results_table(results.text)


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
