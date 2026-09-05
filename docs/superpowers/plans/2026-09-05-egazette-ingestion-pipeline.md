# e-Gazette Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A fully standalone Python utility — no FastAPI, no frontend, no dependency on any other part of this repo — that discovers Central Gazette Labour Codes notifications, downloads their PDFs, extracts and embeds them, and writes them into Postgres. Runnable from a plain terminal (`python cli.py --start-year 2022 --end-year 2025`) and safe to kick off in the background and leave running while the Query API and frontend (separate plans) are built in parallel.

**Architecture:** One flat Python package (`ingestion/`) with its own `requirements.txt` and its own venv — it imports nothing from `backend/` or `frontend/`, and nothing in those two imports from it. The only thing it shares with the Query API is the Postgres database itself (same `DATABASE_URL`, same schema) — that's a deliberate, minimal coupling: this pipeline's whole job is to populate rows the Query API later reads.

**Tech Stack:** Python 3.11+, `requests` + `beautifulsoup4` (site scraping), `pdfplumber` (PDF text extraction), `psycopg` (v3), PostgreSQL 16 + `pgvector`, `google-genai` SDK (`gemini-embedding-001`), `argparse` (CLI), pytest, Docker Compose for local Postgres.

**Spec:** `docs/superpowers/specs/2026-09-05-egazette-ux-architecture-design.md`

## Global Constraints

- **This package has zero dependency on `backend/` or `frontend/`.** It must be installable and runnable in its own venv on a machine that has never touched the rest of the repo. Do not import from `backend.app.*` anywhere in `ingestion/`.
- Structured field extraction and relationship extraction (`amends`/`supersedes`/`issued_under`) are **regex-based in `extractor.py`, never an LLM call** (spec §5.6) — do not route these through Gemini.
- Central Gazette ministry ID for Labour and Employment is **`28`** — never `163002` (a stale value from a pasted URL, corrected during live verification 2026-09-05).
- Domain is locked to Central Gazette only in this plan — the Gujarat portal has a different structure and is not covered here (spec §7 open item).
- PDF downloads (`download.py`) are stateless, unauthenticated GETs to `WriteReadData/{year}/{id}.pdf` — never route these through the session/postback machinery in `discovery.py`, which is only needed for the search step.
- Every live request to egazette.gov.in (discovery and download) must include the politeness delay (`REQUEST_DELAY_SECONDS`) — never remove it.
- Embedding model: `gemini-embedding-001`. Verify current free-tier rate limits at `aistudio.google.com/rate-limit` against the real key before running the full multi-year backfill — do not hardcode an assumed quota.
- This pipeline **writes only** — it never serves queries. `insert_notification` is the only storage function it needs; read-side queries (`get_notification` for the Query API's retrieval, `hybrid_search`, etc.) belong to the Query API plan, not here.
- The Postgres schema (`migrations/001_init.sql`) is identical to the one used in the Query API plan — this plan owns applying it against the real (Railway) database first, since ingestion is meant to start before the rest of the app exists. Local dev/test Postgres instances for each plan are independent (each has its own `docker-compose.yml`); only the real deployed database is actually shared.

---

## File Structure

```
ingestion/
  requirements.txt
  .env.example
  docker-compose.yml           # local Postgres+pgvector for dev/test
  migrations/
    001_init.sql                # same schema as the Query API plan
  extractor.py                  # brought in from handoff, unchanged logic
  config.py                     # env var loading, get_connection()
  storage.py                    # insert_notification only (write-side)
  embeddings.py                  # Gemini embedding wrapper
  ingest.py                      # ties extractor+embeddings+storage into one idempotent call
  discovery.py                    # session bootstrap, month/year search, discover_and_ingest orchestrator
  download.py                      # stateless PDF URL construction + fetch
  cli.py                            # standalone entry point: python cli.py --start-year Y --end-year Y
  samples/
    central_so_2455.txt
    central_so_2457.txt
    gujarat_wages.txt
  tests/
    __init__.py
    conftest.py
    test_extractor.py
    test_storage.py
    test_embeddings.py
    test_ingest.py
    test_discovery.py
    test_download.py
    fixtures/                    # captured live HTML fixture (Task 5)
```

---

### Task 1: Scaffold the standalone package + bring in the validated extractor

**Files:**
- Create: `ingestion/requirements.txt`
- Create: `ingestion/.env.example`
- Create: `ingestion/__init__.py`
- Create: `ingestion/extractor.py` (copied from the handoff, unchanged)
- Create: `ingestion/samples/central_so_2455.txt`, `ingestion/samples/central_so_2457.txt`, `ingestion/samples/gujarat_wages.txt`
- Create: `ingestion/tests/__init__.py`
- Create: `ingestion/tests/test_extractor.py`
- Test: `ingestion/tests/test_extractor.py`

**Interfaces:**
- Produces: `parse_central(raw_text: str) -> NotificationRecord`, `parse_gujarat(raw_text: str) -> NotificationRecord`, `extract_relationships(raw_text: str) -> list[Relationship]`, `normalize(text: str) -> str`, and dataclasses `NotificationRecord` / `Relationship` (fields: see spec §5.2) — all from `extractor.py`, used by every later task in this plan.

- [ ] **Step 1: Create the ingestion directory and bring in the handed-off files verbatim**

```bash
mkdir -p ingestion/samples ingestion/tests ingestion/migrations
cp "/private/tmp/claude-501/-Users-prashantpratapsingh-Workspace-AIGazetteOfIndia-AIGazetteOfIndia/8415281f-1a52-4b2b-ba44-b952af2d3822/scratchpad/files_extracted/extractor.py" ingestion/extractor.py
cp "/private/tmp/claude-501/-Users-prashantpratapsingh-Workspace-AIGazetteOfIndia-AIGazetteOfIndia/8415281f-1a52-4b2b-ba44-b952af2d3822/scratchpad/files_extracted/central_so_2455.txt" ingestion/samples/
cp "/private/tmp/claude-501/-Users-prashantpratapsingh-Workspace-AIGazetteOfIndia-AIGazetteOfIndia/8415281f-1a52-4b2b-ba44-b952af2d3822/scratchpad/files_extracted/central_so_2457.txt" ingestion/samples/
cp "/private/tmp/claude-501/-Users-prashantpratapsingh-Workspace-AIGazetteOfIndia-AIGazetteOfIndia/8415281f-1a52-4b2b-ba44-b952af2d3822/scratchpad/files_extracted/gujarat_wages.txt" ingestion/samples/
touch ingestion/__init__.py ingestion/tests/__init__.py
```

- [ ] **Step 2: Write `requirements.txt` and `.env.example`**

```
# ingestion/requirements.txt
requests==2.32.*
beautifulsoup4==4.12.*
pdfplumber==0.11.*
psycopg[binary]==3.2.*
google-genai==0.*
python-dotenv==1.*
pytest==8.*
```

```
# ingestion/.env.example
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/egazette_ingestion
GEMINI_API_KEY=
```

Note the different local port (`5433`) and database name from the Query API plan's local dev Postgres — these are two independent local containers; only the real deployed `DATABASE_URL` (Railway) is ever shared between the two plans.

- [ ] **Step 3: Write the failing test capturing the already-validated extraction behavior**

```python
# ingestion/tests/test_extractor.py
from pathlib import Path
from extractor import parse_central, parse_gujarat

SAMPLES = Path(__file__).parent.parent / "samples"


def test_parse_central_extracts_core_fields():
    text = (SAMPLES / "central_so_2455.txt").read_text()
    rec = parse_central(text)
    assert rec.gazette_id == "CG-DL-E-14052026-272564"
    assert rec.gazette_type == "EXTRAORDINARY"
    assert rec.notification_number == "S.O. 2455(E)"
    assert rec.act_reference == "Code on Wages, 2019 (29 of 2019)"
    assert rec.issuing_authority == "Ministry of Labour And Employment"


def test_parse_central_detects_supersession_relationship():
    text = (SAMPLES / "central_so_2457.txt").read_text()
    rec = parse_central(text)
    assert len(rec.relationships) == 1
    rel = rec.relationships[0]
    assert rel.rel_type == "supersedes"
    assert "2765" in rel.target
    assert "1965" in rel.target


def test_parse_gujarat_extracts_core_fields():
    text = (SAMPLES / "gujarat_wages.txt").read_text()
    rec = parse_gujarat(text)
    assert rec.gazette_id == "Gujarat-Extra-62"
    assert rec.issuing_authority == "Labour, Skill Development And Employment Department"
    assert rec.act_reference == "Code on Wages, 2019 (29 of 2019)"
```

- [ ] **Step 4: Run the test to verify it passes against the copied, unmodified extractor**

Run: `cd ingestion && python -m pytest tests/test_extractor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/requirements.txt ingestion/.env.example ingestion/__init__.py \
  ingestion/extractor.py ingestion/samples ingestion/tests/__init__.py \
  ingestion/tests/test_extractor.py
git commit -m "Scaffold standalone ingestion package, bring in validated extractor.py"
```

---

### Task 2: Postgres schema + write-only storage

**Files:**
- Create: `ingestion/docker-compose.yml`
- Create: `ingestion/migrations/001_init.sql`
- Create: `ingestion/config.py`
- Create: `ingestion/storage.py`
- Create: `ingestion/tests/conftest.py`
- Test: `ingestion/tests/test_storage.py`

**Interfaces:**
- Consumes: `NotificationRecord`, `Relationship` from `extractor.py` (Task 1).
- Produces: `get_connection() -> psycopg.Connection` (`config.py`); `insert_notification(conn, record: NotificationRecord, embedding: list[float] | None, file_hash: str) -> int` and `get_notification(conn, notification_id: int) -> NotificationRecord | None` from `storage.py`, used by `ingest.py` (Task 4).

- [ ] **Step 1: Write `docker-compose.yml` for a local Postgres+pgvector**

```yaml
# ingestion/docker-compose.yml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: egazette_ingestion
    ports:
      - "5433:5432"
    volumes:
      - egazette_ingestion_pgdata:/var/lib/postgresql/data
volumes:
  egazette_ingestion_pgdata:
```

Run: `cd ingestion && docker compose up -d`
Expected: container running and healthy.

- [ ] **Step 2: Write the migration (identical schema to the Query API plan)**

```sql
-- ingestion/migrations/001_init.sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE notifications (
    id                   SERIAL PRIMARY KEY,
    source               TEXT NOT NULL CHECK (source IN ('central', 'gujarat')),
    gazette_id           TEXT,
    gazette_type         TEXT,
    part                 TEXT,
    section              TEXT,
    issuing_authority    TEXT,
    notification_number  TEXT,
    notification_date    TEXT,
    act_reference        TEXT,
    signatory            TEXT,
    operative_text       TEXT NOT NULL,
    source_url           TEXT,
    file_hash            TEXT NOT NULL,
    embedding            vector(768),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, gazette_id, file_hash)
);

CREATE TABLE relationships (
    id                SERIAL PRIMARY KEY,
    notification_id   INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    rel_type          TEXT NOT NULL CHECK (rel_type IN ('issued_under', 'supersedes', 'amends')),
    target            TEXT NOT NULL
);

CREATE INDEX notifications_fts_idx ON notifications
    USING GIN (to_tsvector('english', operative_text || ' ' || coalesce(act_reference, '')));

CREATE INDEX relationships_target_idx ON relationships (target);
```

Run: `cd ingestion && docker compose exec -T db psql -U postgres -d egazette_ingestion < migrations/001_init.sql`
Expected: `CREATE EXTENSION`, `CREATE TABLE` x2, `CREATE INDEX` x2, no errors.

> **Applying this against the real (Railway) database:** once a Railway Postgres exists with `pgvector` enabled, run this same file against its `DATABASE_URL` — this plan owns that first application since ingestion is meant to start before the Query API is built. The Query API plan's own copy of this migration is for its independent local dev database only; it should not re-apply this against the shared production database.

- [ ] **Step 3: Write `config.py`**

```python
# ingestion/config.py
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)
```

- [ ] **Step 4: Write the failing test for the storage layer**

```python
# ingestion/tests/conftest.py
import pytest
from config import get_connection


@pytest.fixture
def db_conn():
    conn = get_connection()
    yield conn
    conn.execute("TRUNCATE notifications, relationships RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()
```

```python
# ingestion/tests/test_storage.py
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
```

- [ ] **Step 5: Run to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'storage'`

- [ ] **Step 6: Implement `storage.py`**

```python
# ingestion/storage.py
import psycopg
from extractor import NotificationRecord


def insert_notification(
    conn: psycopg.Connection,
    record: NotificationRecord,
    embedding: list[float] | None,
    file_hash: str,
) -> int:
    existing = conn.execute(
        "SELECT id FROM notifications WHERE source = %s AND gazette_id = %s AND file_hash = %s",
        (record.source, record.gazette_id, file_hash),
    ).fetchone()
    if existing:
        return existing[0]

    row = conn.execute(
        """
        INSERT INTO notifications
            (source, gazette_id, gazette_type, part, section, issuing_authority,
             notification_number, notification_date, act_reference, signatory,
             operative_text, file_hash, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            record.source, record.gazette_id, record.gazette_type, record.part,
            record.section, record.issuing_authority, record.notification_number,
            record.notification_date, record.act_reference, record.signatory,
            record.operative_text, file_hash, embedding,
        ),
    ).fetchone()
    notification_id = row[0]

    for rel in record.relationships:
        conn.execute(
            "INSERT INTO relationships (notification_id, rel_type, target) VALUES (%s, %s, %s)",
            (notification_id, rel.rel_type, rel.target),
        )
    return notification_id


def get_notification(conn: psycopg.Connection, notification_id: int) -> NotificationRecord | None:
    row = conn.execute(
        """
        SELECT source, gazette_id, gazette_type, part, section, issuing_authority,
               notification_number, notification_date, act_reference, signatory, operative_text
        FROM notifications WHERE id = %s
        """,
        (notification_id,),
    ).fetchone()
    if row is None:
        return None
    return NotificationRecord(
        source=row[0], gazette_id=row[1], gazette_type=row[2], part=row[3], section=row[4],
        issuing_authority=row[5], notification_number=row[6], notification_date=row[7],
        act_reference=row[8], signatory=row[9], operative_text=row[10],
    )
```

- [ ] **Step 7: Run to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_storage.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add ingestion/docker-compose.yml ingestion/migrations ingestion/config.py \
  ingestion/storage.py ingestion/tests/conftest.py ingestion/tests/test_storage.py
git commit -m "Add Postgres+pgvector schema and write-only storage for ingestion"
```

---

### Task 3: Gemini embedding wrapper

**Files:**
- Create: `ingestion/embeddings.py`
- Test: `ingestion/tests/test_embeddings.py`

**Interfaces:**
- Consumes: `GEMINI_API_KEY` from `config.py` (Task 2).
- Produces: `embed_text(text: str) -> list[float]` from `embeddings.py`, used by `ingest.py` (Task 4).

- [ ] **Step 1: Write the failing test (mocking the Gemini client, never calling the real API in tests)**

```python
# ingestion/tests/test_embeddings.py
from unittest.mock import patch, MagicMock
from embeddings import embed_text


def test_embed_text_returns_vector_from_gemini_response():
    fake_response = MagicMock()
    fake_response.embeddings = [MagicMock(values=[0.1, 0.2, 0.3])]

    with patch("embeddings._client") as mock_client:
        mock_client.models.embed_content.return_value = fake_response
        result = embed_text("Code on Wages, 2019")

    assert result == [0.1, 0.2, 0.3]
    mock_client.models.embed_content.assert_called_once()
    call_kwargs = mock_client.models.embed_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-embedding-001"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'embeddings'`

- [ ] **Step 3: Implement `embeddings.py`**

```python
# ingestion/embeddings.py
from google import genai
from config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY)

EMBEDDING_MODEL = "gemini-embedding-001"


def embed_text(text: str) -> list[float]:
    response = _client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
    return list(response.embeddings[0].values)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_embeddings.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/embeddings.py ingestion/tests/test_embeddings.py
git commit -m "Add Gemini embedding wrapper to ingestion package"
```

---

### Task 4: Idempotent ingest pipeline

**Files:**
- Create: `ingestion/ingest.py`
- Test: `ingestion/tests/test_ingest.py`

**Interfaces:**
- Consumes: `parse_central`, `parse_gujarat` (Task 1); `insert_notification` (Task 2); `embed_text` (Task 3).
- Produces: `ingest_notification(conn, source: str, raw_text: str) -> int` from `ingest.py`, used by `discovery.py`'s orchestrator (Task 6).

- [ ] **Step 1: Write the failing test**

```python
# ingestion/tests/test_ingest.py
from unittest.mock import patch
from pathlib import Path
from ingest import ingest_notification
from storage import get_notification

SAMPLES = Path(__file__).parent.parent / "samples"


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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingest'`

- [ ] **Step 3: Implement `ingest.py`**

```python
# ingestion/ingest.py
import hashlib
import psycopg
from extractor import parse_central, parse_gujarat
from embeddings import embed_text
from storage import insert_notification

PARSERS = {"central": parse_central, "gujarat": parse_gujarat}


def ingest_notification(conn: psycopg.Connection, source: str, raw_text: str) -> int:
    if source not in PARSERS:
        raise ValueError(f"Unknown source: {source!r}. Must be 'central' or 'gujarat'.")

    file_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    record = PARSERS[source](raw_text)
    embedding = embed_text(record.operative_text)
    return insert_notification(conn, record, embedding=embedding, file_hash=file_hash)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_ingest.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/ingest.py ingestion/tests/test_ingest.py
git commit -m "Add idempotent ingest_notification tying extractor+embeddings+storage together"
```

---

### Task 5: Central Gazette discovery — session bootstrap and month/year search

**Files:**
- Create: `ingestion/discovery.py`
- Create: `ingestion/tests/fixtures/` (created on demand, holds the captured fixture from Step 1)
- Test: `ingestion/tests/test_discovery.py`

**Interfaces:**
- Produces: `bootstrap_session() -> tuple[requests.Session, str]`, `search_month(session, base_url: str, ministry_id: str, year: int, month: int) -> list[dict]` (each dict: `{gazette_id, subject, part_section, issue_date, publish_date}`) from `discovery.py`, used by Task 6's orchestrator.

**Confirmed mechanism (verified live 2026-09-05 — not guessed):** `GET /` → 302 to a fresh `(S(sid))/default.aspx`. Then `GET default.aspx` → `GET SearchMenu.aspx` (`Referer: .../default.aspx`) → `GET SearchMinistry.aspx` (`Referer: .../SearchMenu.aspx`) to get the form's `__VIEWSTATE`/`__VIEWSTATEGENERATOR`/`__EVENTVALIDATION`/`hidden1`. Ministry of Labour and Employment's dropdown value is **`28`**. Submitting requires `rdb_Option=0` (Month/Year Wise mode) plus `ddlMinistry`, `ddlmonth` (1-12), `ddlyear`. The exact live POST sequencing (whether the ministry selection needs its own intermediate postback before the final submit, or can be combined) needs one round of live capture — see Step 1 — because a blind replay attempt during this plan's research hit a generic ASP.NET 500 with no diagnostic detail (production `customErrors` hides it), while the same flow driven through an actual browser succeeded and returned real results (`Total No. of Gazettes : 6` for May 2025).

- [ ] **Step 1: Capture one real fixture by running the flow with a from-scratch `requests.Session` script (or a real browser), saving the final results HTML**

```python
# one-off, run manually from ingestion/, not part of the test suite
import requests

s = requests.Session()
ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
s.headers.update({"User-Agent": ua})

resp = s.get("https://egazette.gov.in/", allow_redirects=False, verify=False)
base = resp.headers["location"].rsplit("/", 1)[0] + "/"

s.get(base + "default.aspx", verify=False)
s.get(base + "SearchMenu.aspx", headers={"Referer": base + "default.aspx"}, verify=False)
form_page = s.get(base + "SearchMinistry.aspx", headers={"Referer": base + "SearchMenu.aspx"}, verify=False)

import re
def extract(name, text):
    m = re.search(rf'{name}" value="([^"]*)"', text)
    return m.group(1) if m else ""

viewstate = extract("__VIEWSTATE", form_page.text)
viewstategen = extract("__VIEWSTATEGENERATOR", form_page.text)
eventvalidation = extract("__EVENTVALIDATION", form_page.text)
hidden1 = extract('id="hidden1"[^>]*', form_page.text) or extract("hidden1", form_page.text)

data = {
    "__EVENTTARGET": "ddlMinistry", "__EVENTARGUMENT": "",
    "__VIEWSTATE": viewstate, "__VIEWSTATEGENERATOR": viewstategen,
    "__EVENTVALIDATION": eventvalidation, "hidden1": hidden1,
    "ddlMinistry": "28", "rdb_Option": "0",
}
after_ministry = s.post(base + "SearchMinistry.aspx",
                         headers={"Referer": base + "SearchMinistry.aspx"}, data=data, verify=False)

viewstate2 = extract("__VIEWSTATE", after_ministry.text)
viewstategen2 = extract("__VIEWSTATEGENERATOR", after_ministry.text)
eventvalidation2 = extract("__EVENTVALIDATION", after_ministry.text)
hidden1_2 = extract('id="hidden1"[^>]*', after_ministry.text) or extract("hidden1", after_ministry.text)

data2 = {
    "__EVENTTARGET": "", "__EVENTARGUMENT": "",
    "__VIEWSTATE": viewstate2, "__VIEWSTATEGENERATOR": viewstategen2,
    "__EVENTVALIDATION": eventvalidation2, "hidden1": hidden1_2,
    "ddlMinistry": "28", "rdb_Option": "0", "ddlmonth": "5", "ddlyear": "2025",
    "ImgSubmitDetails.x": "10", "ImgSubmitDetails.y": "10",
}
results = s.post(base + "SearchMinistry.aspx",
                  headers={"Referer": base + "SearchMinistry.aspx"}, data=data2, verify=False)

assert "gvGazetteList" in results.text, f"Did not reach results (status {results.status_code}); debug the postback fields."
open("tests/fixtures/searchministry_may2025_results.html", "w").write(results.text)
print("Saved fixture, found gvGazetteList:", "gvGazetteList" in results.text)
```

Run: `cd ingestion && python3 capture_fixture.py`. If the assertion fails, this is normal ASP.NET postback debugging (compare each hidden field against what `form_page.text`/`after_ministry.text` actually contain) — the mechanism is confirmed real via live browser testing; only the precise Python replication needs iteration. If it proves stubborn, capture the fixture via a real browser's "Save Page As" instead and skip straight to Step 2.

- [ ] **Step 2: Write the failing test against the captured fixture**

```python
# ingestion/tests/test_discovery.py
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
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_discovery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery'`

- [ ] **Step 4: Implement `discovery.py`**

```python
# ingestion/discovery.py
import re
import requests
from bs4 import BeautifulSoup

MINISTRY_LABOUR_AND_EMPLOYMENT = "28"


def bootstrap_session() -> tuple[requests.Session, str]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    resp = session.get("https://egazette.gov.in/", allow_redirects=False, verify=False)
    base_url = resp.headers["location"].rsplit("/", 1)[0] + "/"
    session.get(base_url + "default.aspx", verify=False)
    session.get(base_url + "SearchMenu.aspx", headers={"Referer": base_url + "default.aspx"}, verify=False)
    return session, base_url


def _extract_form_state(html: str) -> dict:
    def field(name):
        m = re.search(rf'{name}" value="([^"]*)"', html)
        return m.group(1) if m else ""
    return {
        "__VIEWSTATE": field("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": field("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION": field("__EVENTVALIDATION"),
        "hidden1": field("hidden1"),
    }


def search_month(session: requests.Session, base_url: str, ministry_id: str, year: int, month: int) -> list[dict]:
    form_page = session.get(
        base_url + "SearchMinistry.aspx",
        headers={"Referer": base_url + "SearchMenu.aspx"},
        verify=False,
    )
    state = _extract_form_state(form_page.text)
    after_ministry = session.post(
        base_url + "SearchMinistry.aspx",
        headers={"Referer": base_url + "SearchMinistry.aspx"},
        data={**state, "__EVENTTARGET": "ddlMinistry", "__EVENTARGUMENT": "",
              "ddlMinistry": ministry_id, "rdb_Option": "0"},
        verify=False,
    )
    state2 = _extract_form_state(after_ministry.text)
    results = session.post(
        base_url + "SearchMinistry.aspx",
        headers={"Referer": base_url + "SearchMinistry.aspx"},
        data={**state2, "__EVENTTARGET": "", "__EVENTARGUMENT": "",
              "ddlMinistry": ministry_id, "rdb_Option": "0",
              "ddlmonth": str(month), "ddlyear": str(year),
              "ImgSubmitDetails.x": "10", "ImgSubmitDetails.y": "10"},
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
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_discovery.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add ingestion/discovery.py ingestion/tests/test_discovery.py ingestion/tests/fixtures
git commit -m "Add Central Gazette discovery: session bootstrap + month/year search parsing"
```

---

### Task 6: Stateless PDF download + discovery-and-ingest orchestrator

**Files:**
- Create: `ingestion/download.py`
- Modify: `ingestion/discovery.py` (add the orchestrator)
- Test: `ingestion/tests/test_download.py`
- Test: `ingestion/tests/test_discovery.py` (extend)

**Interfaces:**
- Consumes: `search_month`, `bootstrap_session` (Task 5); `ingest_notification` (Task 4).
- Produces: `pdf_url_for(gazette_id: str) -> str` and `download_pdf(url: str) -> bytes` from `download.py`; `discover_and_ingest(conn, ministry_id: str, start_year: int, end_year: int) -> int` from `discovery.py`, used by `cli.py` (Task 7).

**Confirmed mechanism:** a Gazette ID like `CG-DL-E-22052025-263307` maps to `https://egazette.gov.in/WriteReadData/{year}/{trailing-numeric-segment}.pdf` — verified live with zero cookies on two different IDs (`263307` and `263276`, both `200`, `application/pdf`). No session needed for this step at all.

- [ ] **Step 1: Write the failing test for the URL construction (pure function, no network)**

```python
# ingestion/tests/test_download.py
from download import pdf_url_for

def test_pdf_url_for_extracts_year_and_trailing_id():
    assert pdf_url_for("CG-DL-E-22052025-263307") == "https://egazette.gov.in/WriteReadData/2025/263307.pdf"

def test_pdf_url_for_handles_different_id():
    assert pdf_url_for("CG-DL-E-21052025-263276") == "https://egazette.gov.in/WriteReadData/2025/263276.pdf"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_download.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'download'`

- [ ] **Step 3: Implement `download.py`**

```python
# ingestion/download.py
import re
import requests


def pdf_url_for(gazette_id: str) -> str:
    m = re.search(r"(\d{8})-(\d+)$", gazette_id)
    if not m:
        raise ValueError(f"Cannot parse year/id from gazette_id: {gazette_id!r}")
    ddmmyyyy, numeric_id = m.groups()
    year = ddmmyyyy[-4:]
    return f"https://egazette.gov.in/WriteReadData/{year}/{numeric_id}.pdf"


def download_pdf(url: str) -> bytes:
    response = requests.get(url, verify=False, timeout=30)
    response.raise_for_status()
    return response.content
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_download.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Implement the orchestrator (extends `discovery.py`), with a politeness delay**

```python
# add to ingestion/discovery.py
import pdfplumber
import io
import time
from download import pdf_url_for, download_pdf
from ingest import ingest_notification

REQUEST_DELAY_SECONDS = 1.0  # politeness delay between requests to a government server


def _pdf_to_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def discover_and_ingest(conn, ministry_id: str, start_year: int, end_year: int) -> int:
    session, base_url = bootstrap_session()
    ingested = 0
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            rows = search_month(session, base_url, ministry_id, year, month)
            time.sleep(REQUEST_DELAY_SECONDS)
            for row in rows:
                pdf_bytes = download_pdf(pdf_url_for(row["gazette_id"]))
                time.sleep(REQUEST_DELAY_SECONDS)
                raw_text = _pdf_to_text(pdf_bytes)
                ingest_notification(conn, "central", raw_text)
                ingested += 1
    return ingested
```

- [ ] **Step 6: Write a failing test for the orchestrator using mocked `search_month`/`download_pdf`**

```python
# add to ingestion/tests/test_discovery.py
from unittest.mock import patch
from discovery import discover_and_ingest

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
```

Add `beautifulsoup4` was already added in Task 5; add `pdfplumber` here:

```
# add to ingestion/requirements.txt
pdfplumber==0.11.*
```

(Already present from Task 1's initial requirements — verify it's there rather than duplicating the line.)

- [ ] **Step 7: Run to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_discovery.py -v`
Expected: PASS (3 passed — 2 from Task 5 plus this one)

- [ ] **Step 8: Commit**

```bash
git add ingestion/download.py ingestion/discovery.py ingestion/tests/test_download.py ingestion/tests/test_discovery.py
git commit -m "Add stateless PDF download and discovery-and-ingest orchestrator"
```

---

### Task 7: Standalone CLI + progress logging + running it in the background now

**Files:**
- Create: `ingestion/cli.py`
- Modify: `ingestion/discovery.py` (add progress logging)
- Test: `ingestion/tests/test_discovery.py` (extend)

**Interfaces:**
- Consumes: `discover_and_ingest`, `MINISTRY_LABOUR_AND_EMPLOYMENT` (Task 5/6); `get_connection` (Task 2).
- Produces: `ingestion/cli.py` — a standalone, arguments-driven entry point. Nothing later in this plan depends on it; it's the deliverable.

- [ ] **Step 1: Add progress logging to `discover_and_ingest`, and a failing test that it actually logs**

```python
# ingestion/tests/test_discovery.py — add this test
import logging
from unittest.mock import patch
from discovery import discover_and_ingest

def test_discover_and_ingest_logs_progress_per_month_and_row(db_conn, caplog):
    fake_row = {"gazette_id": "CG-DL-E-22052025-263307", "subject": "COW",
                "part_section": "Part II-Section 3", "issue_date": "22-May-2025", "publish_date": "22-May-2025"}
    with patch("discovery.bootstrap_session", return_value=(None, "")), \
         patch("discovery.search_month", side_effect=[[fake_row]] + [[]] * 11), \
         patch("discovery.download_pdf", return_value=b"%PDF-fake"), \
         patch("discovery._pdf_to_text", return_value="MINISTRY OF LABOUR AND EMPLOYMENT\nS.O. 1(E).— test"), \
         patch("discovery.time.sleep"), \
         patch("ingest.embed_text", return_value=[0.1] * 768), \
         caplog.at_level(logging.INFO):
        discover_and_ingest(db_conn, "28", 2025, 2025)
    assert any("2025-01" in r.message or "2025/1" in r.message for r in caplog.records)
    assert any("CG-DL-E-22052025-263307" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_discovery.py -v -k logs_progress`
Expected: FAIL — no log records produced yet.

- [ ] **Step 3: Add logging calls to `discover_and_ingest`**

```python
# modify ingestion/discovery.py — add near the top
import logging
logger = logging.getLogger(__name__)

# replace the body of discover_and_ingest with:
def discover_and_ingest(conn, ministry_id: str, start_year: int, end_year: int) -> int:
    session, base_url = bootstrap_session()
    ingested = 0
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            logger.info(f"Searching {year}-{month:02d} for ministry {ministry_id}...")
            rows = search_month(session, base_url, ministry_id, year, month)
            time.sleep(REQUEST_DELAY_SECONDS)
            logger.info(f"  Found {len(rows)} notification(s) for {year}-{month:02d}")
            for row in rows:
                pdf_bytes = download_pdf(pdf_url_for(row["gazette_id"]))
                time.sleep(REQUEST_DELAY_SECONDS)
                raw_text = _pdf_to_text(pdf_bytes)
                ingest_notification(conn, "central", raw_text)
                conn.commit()
                ingested += 1
                logger.info(f"  Ingested {row['gazette_id']} ({ingested} total so far)")
    return ingested
```

Note the added `conn.commit()` per row (not just once at the end as in earlier drafts) — for a long-running background process, committing after every successful ingest means a crash or Ctrl-C partway through loses nothing already ingested, and a rerun picks up cleanly via the existing idempotency check.

- [ ] **Step 4: Run to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_discovery.py -v`
Expected: PASS (4 passed — 3 from Tasks 5–6 plus this one)

- [ ] **Step 5: Write `cli.py`**

```python
# ingestion/cli.py
import argparse
import logging
from config import get_connection
from discovery import discover_and_ingest, MINISTRY_LABOUR_AND_EMPLOYMENT


def main():
    parser = argparse.ArgumentParser(
        description="Standalone e-Gazette ingestion pipeline. Runs independently of the "
                     "Query API and frontend — safe to start now and leave running while "
                     "those are built."
    )
    parser.add_argument("--ministry", default=MINISTRY_LABOUR_AND_EMPLOYMENT,
                         help="Ministry dropdown value (default: 28, Labour and Employment)")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    conn = get_connection()
    logging.info(f"Starting ingestion: ministry={args.ministry} years={args.start_year}-{args.end_year}")
    count = discover_and_ingest(conn, args.ministry, args.start_year, args.end_year)
    logging.info(f"Done. Ingested {count} notifications total.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify the CLI's argument parsing works (no network — just `--help`)**

Run: `cd ingestion && python cli.py --help`
Expected: prints usage showing `--ministry`, `--start-year`, `--end-year`.

- [ ] **Step 7: Commit**

```bash
git add ingestion/cli.py ingestion/discovery.py ingestion/tests/test_discovery.py
git commit -m "Add standalone CLI entry point with per-month/per-row progress logging"
```

- [ ] **Step 8: Start the real 4-year backfill now, in the background, independent of any other work**

This is the actual point of this plan — kick it off and let it run while the Query API and frontend plans are being built:

```bash
cd ingestion
nohup python cli.py --start-year 2022 --end-year 2025 > ingest.log 2>&1 &
echo "Started, PID $!"
```

Monitor progress at any time, from any terminal, without needing this session:
```bash
tail -f ingestion/ingest.log
```

If it needs to stop and resume later (`kill <PID>`, or just closing the terminal after disowning it), rerunning the same command is safe — every already-ingested notification is skipped via the `(source, gazette_id, file_hash)` uniqueness check in `insert_notification` (Task 2), and each row commits individually (Task 7 Step 3), so nothing already-ingested is lost or re-processed.

## Self-Review Notes

- **Spec coverage:** spec §5.6 (LLM call inventory — embedding only at ingest time, regex-based structuring never an LLM call) → Tasks 1, 3, 4. Spec §5.3 (no graph DB, relationships as relational rows) → Task 2. Spec §7's discovery/acquisition open item → Tasks 5–6, identical confirmed mechanism as originally verified live. The new requirement (independent, backgroundable utility) → Task 7 end-to-end: CLI, logging, per-row commits, and the actual background-launch command.
- **Placeholder scan:** no TBD/TODO. The migration's cross-plan note (apply once against the real Railway DB, not duplicated per environment) is spelled out explicitly rather than left implicit.
- **Type consistency:** `NotificationRecord`/`Relationship` from `extractor.py` (Task 1) are the only shared types across this whole package — no duplicate model definitions anywhere, unlike the original combined plan's `app/models.py` which mixed ingestion-irrelevant `AskRequest`/`AskResponse`/`Citation` in; those stay entirely in the Query API plan since ingestion never needs them.
- **Independence check:** grepped the plan for any `from app.` or `backend.` import — none present. Every module here is self-contained under `ingestion/`, importable and runnable with only `ingestion/requirements.txt` installed.
