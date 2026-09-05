"""
Gazette-aware extractor — MVP vertical slice.

Implements the structured data model from the solution doc (Gazette > Part >
Section > Notification > Clause) and per-source parsing adapters for:
  - Central Gazette (egazette.gov.in)
  - Gujarat Government Gazette

Each source has its own header format, so each gets its own adapter that
normalizes into the same NotificationRecord schema. This is the "one adapter
per source" pattern — the two source formats below are not similar enough
to share a single regex set.

Relationship extraction (amends / supersedes / issued_under) is done via
formulaic-phrase matching, since Indian gazette notifications reliably use a
small set of fixed legal phrases to reference other instruments.
"""

import re
import json
from dataclasses import dataclass, asdict, field
from typing import Optional
from pathlib import Path


@dataclass
class Relationship:
    rel_type: str          # issued_under | supersedes | amends
    target: str             # the referenced Act/Section/Notification, as text


@dataclass
class NotificationRecord:
    source: str                       # "central" | "gujarat"
    gazette_id: Optional[str] = None
    gazette_type: Optional[str] = None       # e.g. EXTRAORDINARY
    part: Optional[str] = None
    section: Optional[str] = None
    issuing_authority: Optional[str] = None  # Ministry / Department
    notification_number: Optional[str] = None  # S.O. / G.S.R. / GR number
    notification_date: Optional[str] = None
    act_reference: Optional[str] = None      # Act + year the power derives from
    signatory: Optional[str] = None
    operative_text: str = ""
    relationships: list[Relationship] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared relationship extraction — same formulaic phrases across both sources
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Collapse all whitespace runs (including line-wraps mid-phrase, which
    PDF text extraction introduces unpredictably) to single spaces before any
    phrase-matching. This is the general fix for line-wrap fragility, rather
    than patching each regex for each wrap position as it's discovered."""
    return re.sub(r"\s+", " ", text)


def extract_relationships(raw_text: str) -> list[Relationship]:
    text = normalize(raw_text)
    rels = []

    # issued_under: "in exercise of the powers conferred by ... of the <Act>"
    # NOTE: real gazette PDFs wrap mid-phrase (e.g. "Code on Wages,\n2019"), so
    # these patterns use \s (not literal space) to span line breaks.
    m = re.search(
        r"in exercise of the powers conferred by (.{0,120}?) of the ([A-Z][A-Za-z,\s()]+?\d{4}\s*\(\d+ of \d{4}\))",
        text,
    )
    if m:
        rels.append(Relationship("issued_under", f"{m.group(1).strip()} of {m.group(2).strip()}"))

    # supersedes: "in supersession of the notification ... number ... dated ..."
    m = re.search(
        r"in supersession of the notification[^.]*?number\s+([A-Za-z0-9.\s()]+?),\s*dated the ([\d]{1,2}(?:st|nd|rd|th)?\s+\w+,?\s+\d{4})",
        text,
    )
    if m:
        rels.append(Relationship("supersedes", f"{m.group(1).strip()} dated {m.group(2).strip()}"))

    return rels


# ---------------------------------------------------------------------------
# Central Gazette adapter
# ---------------------------------------------------------------------------

def parse_central(raw_text: str) -> NotificationRecord:
    rec = NotificationRecord(source="central")
    text = normalize(raw_text)  # field extraction runs on normalized text;
                                 # operative_text below keeps the original layout

    m = re.search(r"(CG-DL-E-\S+)", text)
    if m:
        rec.gazette_id = m.group(1)

    if "EXTRAORDINARY" in text:
        rec.gazette_type = "EXTRAORDINARY"

    m = re.search(r"PART\s+([IVX]+).+?Section\s+(.+?)(?:\n|PUBLISHED)", text)
    if m:
        rec.part = f"Part {m.group(1)}"
        rec.section = m.group(2).strip()

    m = re.search(r"MINISTRY OF ([A-Z][A-Z &]+?)(?=\s+NOTIFICATION|\s+New\b)", text)
    if m:
        rec.issuing_authority = f"Ministry of {m.group(1).title()}"

    m = re.search(r"(S\.O\.\s*\d+\s*\(E\))", text)
    if m:
        rec.notification_number = m.group(1)

    m = re.search(r"New Delhi, the (\d{1,2}(?:st|nd|rd|th)?\s+\w+,?\s+\d{4})", text)
    if m:
        rec.notification_date = m.group(1)

    m = re.search(r"the (Code on\s+[A-Za-z,\s]+?\d{4}\s*\(\d+ of \d{4}\))", text)
    if m:
        rec.act_reference = m.group(1)

    m = re.search(r"([A-Z][A-Z. ]+),\s*(?:Jt\.|Joint)\s*Secy?\.?", text)
    if m:
        rec.signatory = m.group(1).strip()

    rec.operative_text = raw_text.strip()
    rec.relationships = extract_relationships(raw_text)
    return rec


# ---------------------------------------------------------------------------
# Gujarat Gazette adapter — different header format entirely
# ---------------------------------------------------------------------------

def parse_gujarat(raw_text: str) -> NotificationRecord:
    rec = NotificationRecord(source="gujarat")
    text = normalize(raw_text)

    m = re.search(r"Extra No\.\s*(\d+)", text)
    if m:
        rec.gazette_id = f"Gujarat-Extra-{m.group(1)}"

    if "EXTRAORDINARY" in text:
        rec.gazette_type = "EXTRAORDINARY"

    m = re.search(r"PART\s+([IVXA-]+)", text)
    if m:
        rec.part = f"Part {m.group(1)}"

    m = re.search(r"([A-Z][A-Z, ]+DEPARTMENT)", text)
    if m:
        rec.issuing_authority = m.group(1).title()

    m = re.search(r"(No\.:?\s*GR/[\w/.-]+)", text)
    if m:
        rec.notification_number = m.group(1).rstrip(":-")

    m = re.search(r"Gandhinagar,\s*(\d{1,2}(?:st|nd|rd|th)?\s+\w+,?\s+\d{4})", text)
    if m:
        rec.notification_date = m.group(1)

    m = re.search(r"(Code on\s+[A-Za-z,\s]+?\d{4}\s*\(\d+ of \d{4}\))", text)
    if m:
        rec.act_reference = m.group(1)

    m = re.search(r"([A-Z][A-Z .]+),\s*Deputy Secretary", text)
    if m:
        rec.signatory = m.group(1).strip()

    rec.operative_text = raw_text.strip()
    rec.relationships = extract_relationships(raw_text)
    return rec


# ---------------------------------------------------------------------------

ADAPTERS = {"central": parse_central, "gujarat": parse_gujarat}

if __name__ == "__main__":
    samples = [
        ("central", "samples/central_so_2455.txt"),
        ("central", "samples/central_so_2457.txt"),
        ("gujarat", "samples/gujarat_wages.txt"),
    ]

    results = []
    for source, path in samples:
        text = Path(path).read_text()
        record = ADAPTERS[source](text)
        results.append(asdict(record))

    print(json.dumps(results, indent=2))
