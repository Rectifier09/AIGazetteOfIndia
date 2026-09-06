# Notification Chunking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split every notification's text into embeddable chunks (instead of one embedding per whole notification) so oversized documents no longer fail with `400 Bad Request` from the embedding API, and citations become paragraph-precise instead of whole-document dumps.

**Architecture:** This modifies the existing, already-built `ingestion/` package in place — no new package, no new plan for a new subsystem. A new pure `chunking.py` module splits text; `storage.py` gains a `notification_chunks` child table and an `insert_chunks` function; `ingest.py` is restructured to insert the notification row first and only chunk+embed when it's genuinely new (a real efficiency fix, not just a chunking side effect). The unimplemented Query API plan (`docs/superpowers/plans/2026-09-05-egazette-backend-pipeline.md`) is also revised in place, since no code has been written against its old one-embedding-per-notification design yet.

**Tech Stack:** Same as the existing ingestion package — Python 3.11, psycopg3, Postgres+pgvector on Railway, no new dependencies (chunking is pure-Python stdlib).

**Spec:** `docs/superpowers/specs/2026-09-06-notification-chunking-design.md`

## Global Constraints

- `ingestion/extractor.py` is not modified — chunking only affects what gets embedded, never how structured fields are extracted from the full raw text.
- `max_chars=6000` for chunking is deliberately conservative relative to the embedding model's real 8,192-token limit (~32,000 chars at the ratio observed on real bilingual text) — do not tune this upward without re-verifying against a real oversized document.
- One citation per notification in retrieval — when multiple chunks from the same document score well, keep only the best-scoring one. Do not expand the `Citation` model to multi-passage.
- The real Postgres database (Railway) already has 6 notifications from the completed 4-year backfill, embedded under the old schema. `002_chunking.sql` drops the `notifications.embedding` column entirely — there is no in-place migration for those 6 rows' old embeddings. The last task in this plan clears and re-runs the real backfill; do not write a data-migration script instead.
- `ingestion/.env` is real, gitignored, and must never be added to any commit — this applies throughout every task's `git add` step (never `git add -A` or `git add .`).

---

## File Structure

```
ingestion/
  chunking.py                    # NEW: chunk_text()
  storage.py                     # MODIFIED: insert_notification signature change, NEW insert_chunks()
  ingest.py                      # MODIFIED: restructured ingest_notification
  migrations/
    002_chunking.sql             # NEW: drops notifications.embedding, adds notification_chunks
  tests/
    test_chunking.py             # NEW
    test_storage.py              # MODIFIED: existing tests updated for new insert_notification signature, new tests added
    test_ingest.py                # MODIFIED: one new test added, no existing tests change

docs/superpowers/plans/
  2026-09-05-egazette-backend-pipeline.md   # MODIFIED: retrieval design revised for chunked schema
                                              # (also fixes a pre-existing bug: this plan still said
                                              # gemini-embedding-001, but ingestion switched to NVIDIA
                                              # days ago — query and document embeddings must come from
                                              # the same model or cosine similarity is meaningless)
```

---

### Task 1: The chunking module

**Files:**
- Create: `ingestion/chunking.py`
- Create: `ingestion/tests/test_chunking.py`

**Interfaces:**
- Produces: `chunk_text(text: str, max_chars: int = 6000, overlap: int = 200) -> list[str]` from `chunking.py`, used by `ingest.py` (Task 3).

- [ ] **Step 1: Write the failing tests**

```python
# ingestion/tests/test_chunking.py
from chunking import chunk_text


def test_short_text_produces_one_chunk():
    text = "A short single-paragraph notification."
    assert chunk_text(text) == [text]


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_long_text_splits_on_paragraph_boundaries():
    paragraphs = ["Paragraph one. " * 100, "Paragraph two. " * 100, "Paragraph three. " * 100]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=2000, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 2000 for c in chunks)
    assert "Paragraph one." in chunks[0]
    assert "Paragraph three." in chunks[-1]


def test_oversized_single_paragraph_is_hard_split():
    text = "x" * 20000  # one giant "paragraph", no blank lines at all
    chunks = chunk_text(text, max_chars=6000, overlap=200)
    assert len(chunks) > 1
    assert all(len(c) <= 6000 for c in chunks)
    assert all(c.strip("x") == "" for c in chunks)  # every chunk is pure "x" (overlap repeats some)


def test_overlap_is_present_between_consecutive_packed_chunks():
    paragraphs = ["A" * 3000, "B" * 3000, "C" * 3000]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=6000, overlap=200)
    assert len(chunks) >= 2
    assert chunks[0][-200:] in chunks[1]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ingestion && .venv/bin/python -m pytest tests/test_chunking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chunking'`

- [ ] **Step 3: Implement `chunking.py`**

```python
# ingestion/chunking.py
def chunk_text(text: str, max_chars: int = 6000, overlap: int = 200) -> list[str]:
    """Split text into chunks under max_chars, preferring paragraph boundaries.

    Splits on blank-line-separated paragraphs first, then greedily packs
    consecutive paragraphs into a chunk until adding the next one would
    exceed max_chars. A single paragraph longer than max_chars is hard-split
    at the character limit (real gazette PDFs occasionally produce this via
    watermark-garbled text with no paragraph breaks at all). overlap
    characters from the end of each chunk are carried into the start of the
    next, so content split across a chunk boundary isn't lost to whichever
    chunk actually gets matched by a search. max_chars=6000 is deliberately
    conservative relative to the embedding model's 8,192-token limit — see
    the design spec for the token/char ratio this was measured against.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p for p in text.split("\n\n") if p.strip()] or [text]

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current.strip():
                chunks.append(current.strip())
                current = ""
            step = max_chars - overlap
            for start in range(0, len(paragraph), step):
                chunks.append(paragraph[start:start + max_chars])
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars:
            chunks.append(current.strip())
            carry = current[-overlap:] if current else ""
            restarted = f"{carry}\n\n{paragraph}" if carry.strip() else paragraph
            # Guard: if the carried-over overlap plus this paragraph would
            # itself exceed max_chars, drop the carry rather than violate the
            # max_chars contract on the next chunk (paragraph alone is
            # already known to be <= max_chars from the check above).
            current = restarted if len(restarted) <= max_chars else paragraph
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    return chunks
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ingestion && .venv/bin/python -m pytest tests/test_chunking.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/chunking.py ingestion/tests/test_chunking.py
git commit -m "Add paragraph-aware text chunking for oversized documents"
```

---

### Task 2: Schema migration + storage.py changes

**Files:**
- Create: `ingestion/migrations/002_chunking.sql`
- Modify: `ingestion/storage.py`
- Modify: `ingestion/tests/test_storage.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks.
- Produces: `insert_notification(conn, record, file_hash, source_url=None) -> tuple[int, bool]` (the `embedding` parameter is **removed**; return type changes from `int` to `(id, is_new)`) and `insert_chunks(conn, notification_id: int, chunks: list[tuple[str, list[float]]]) -> None` from `storage.py`, used by `ingest.py` (Task 3).

This is a breaking signature change to an existing, tested function — every existing caller/test of `insert_notification` in this codebase is updated in this task.

- [ ] **Step 1: Write the migration**

```sql
-- ingestion/migrations/002_chunking.sql
ALTER TABLE notifications DROP COLUMN embedding;
DROP INDEX IF EXISTS notifications_fts_idx;

CREATE TABLE notification_chunks (
    id                SERIAL PRIMARY KEY,
    notification_id   INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    chunk_index       INTEGER NOT NULL,
    chunk_text        TEXT NOT NULL,
    embedding         vector(768) NOT NULL,
    UNIQUE (notification_id, chunk_index)
);

CREATE INDEX notification_chunks_fts_idx ON notification_chunks
    USING GIN (to_tsvector('english', chunk_text));
```

Apply it against the real live database (the same one `001_init.sql` was applied to — see `ingestion/.env`, never commit that file):

```bash
cd ingestion
source .venv/bin/activate
python3 -c "
from config import get_connection
conn = get_connection()
conn.execute(open('migrations/002_chunking.sql').read())
conn.commit()
print('Migration applied')
tables = conn.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema='public'\").fetchall()
print('Tables:', tables)
"
```

Expected: prints `Migration applied` and a table list including `notification_chunks`.

- [ ] **Step 2: Update the existing `test_storage.py` tests for the new `insert_notification` signature, and write the new tests**

```python
# ingestion/tests/test_storage.py
from dataclasses import replace

from extractor import parse_central, parse_gujarat
from storage import insert_notification, get_notification, notification_exists, insert_chunks
from pathlib import Path

SAMPLES = Path(__file__).parent.parent / "samples"


def test_insert_and_get_notification_round_trips(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    new_id, is_new = insert_notification(db_conn, record, file_hash="hash-2455")
    db_conn.commit()

    assert is_new is True
    fetched = get_notification(db_conn, new_id)
    assert fetched.gazette_id == "CG-DL-E-14052026-272564"
    assert fetched.notification_number == "S.O. 2455(E)"


def test_insert_is_idempotent_on_same_hash(db_conn):
    record = parse_gujarat((SAMPLES / "gujarat_wages.txt").read_text())
    first_id, first_is_new = insert_notification(db_conn, record, file_hash="hash-gj-62")
    db_conn.commit()
    second_id, second_is_new = insert_notification(db_conn, record, file_hash="hash-gj-62")
    db_conn.commit()

    assert first_id == second_id
    assert first_is_new is True
    assert second_is_new is False


def test_insert_is_idempotent_when_gazette_id_is_null(db_conn):
    # NULL = NULL is never true in Postgres, so a naive "gazette_id = %s" dedup
    # lookup would miss the existing row and insert a duplicate on every re-run.
    record = replace(parse_central((SAMPLES / "central_so_2455.txt").read_text()), gazette_id=None)
    first_id, _ = insert_notification(db_conn, record, file_hash="hash-null-gid")
    db_conn.commit()
    second_id, second_is_new = insert_notification(db_conn, record, file_hash="hash-null-gid")
    db_conn.commit()

    assert first_id == second_id
    assert second_is_new is False
    count = db_conn.execute(
        "SELECT count(*) FROM notifications WHERE gazette_id IS NULL AND file_hash = %s",
        ("hash-null-gid",),
    ).fetchone()[0]
    assert count == 1


def test_insert_stores_source_url(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    url = "https://egazette.gov.in/WriteReadData/2026/272564.pdf"
    new_id, _ = insert_notification(db_conn, record, file_hash="hash-url", source_url=url)
    db_conn.commit()

    stored = db_conn.execute(
        "SELECT source_url FROM notifications WHERE id = %s", (new_id,)
    ).fetchone()[0]
    assert stored == url


def test_insert_leaves_source_url_null_when_not_supplied(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    new_id, _ = insert_notification(db_conn, record, file_hash="hash-no-url")
    db_conn.commit()

    stored = db_conn.execute(
        "SELECT source_url FROM notifications WHERE id = %s", (new_id,)
    ).fetchone()[0]
    assert stored is None


def test_notification_exists_reports_presence_by_source_and_gazette_id(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())

    assert notification_exists(db_conn, "central", record.gazette_id) is False

    insert_notification(db_conn, record, file_hash="hash-exists")
    db_conn.commit()

    assert notification_exists(db_conn, "central", record.gazette_id) is True
    assert notification_exists(db_conn, "gujarat", record.gazette_id) is False
    assert notification_exists(db_conn, "central", "CG-DL-E-01011999-000000") is False


def test_insert_chunks_stores_one_row_per_chunk_in_order(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    notification_id, _ = insert_notification(db_conn, record, file_hash="hash-chunks")
    db_conn.commit()

    insert_chunks(
        db_conn, notification_id,
        [("first chunk text", [0.1] * 768), ("second chunk text", [0.2] * 768)],
    )
    db_conn.commit()

    rows = db_conn.execute(
        "SELECT chunk_index, chunk_text FROM notification_chunks "
        "WHERE notification_id = %s ORDER BY chunk_index",
        (notification_id,),
    ).fetchall()
    assert [r[1] for r in rows] == ["first chunk text", "second chunk text"]
    assert [r[0] for r in rows] == [0, 1]


def test_deleting_notification_cascades_to_its_chunks(db_conn):
    record = parse_central((SAMPLES / "central_so_2455.txt").read_text())
    notification_id, _ = insert_notification(db_conn, record, file_hash="hash-cascade")
    db_conn.commit()
    insert_chunks(db_conn, notification_id, [("chunk", [0.1] * 768)])
    db_conn.commit()

    db_conn.execute("DELETE FROM notifications WHERE id = %s", (notification_id,))
    db_conn.commit()

    count = db_conn.execute(
        "SELECT count(*) FROM notification_chunks WHERE notification_id = %s", (notification_id,)
    ).fetchone()[0]
    assert count == 0
```

- [ ] **Step 3: Run to verify the updated/new tests fail**

Run: `cd ingestion && .venv/bin/python -m pytest tests/test_storage.py -v`
Expected: FAIL — `insert_notification()` still has the old `embedding` parameter and returns a bare `int`, so every test in this file fails (`TypeError` on the missing/unexpected argument, or unpacking a non-tuple).

- [ ] **Step 4: Implement the new `storage.py`**

```python
# ingestion/storage.py
import psycopg
from extractor import NotificationRecord


def notification_exists(conn: psycopg.Connection, source: str, gazette_id: str) -> bool:
    """Cheap "have we already ingested this gazette_id?" check.

    Deliberately looser than insert_notification's idempotency check (which also
    matches on file_hash): this exists so a resumed run can skip downloading,
    parsing and embedding a document it already has, using only the gazette_id
    the discovery step hands us before any of that work happens.
    """
    row = conn.execute(
        "SELECT 1 FROM notifications WHERE source = %s AND gazette_id = %s LIMIT 1",
        (source, gazette_id),
    ).fetchone()
    return row is not None


def insert_notification(
    conn: psycopg.Connection,
    record: NotificationRecord,
    file_hash: str,
    source_url: str | None = None,
) -> tuple[int, bool]:
    """Returns (notification_id, is_new). is_new is False when an existing row
    with the same (source, gazette_id, file_hash) already matched — callers use
    this to skip chunking/embedding work entirely for duplicates."""
    # gazette_id IS NOT DISTINCT FROM %s rather than = %s: Postgres evaluates
    # NULL = NULL as NULL (never true), so a record with no gazette_id would
    # never match an existing row and every re-run would insert a duplicate.
    existing = conn.execute(
        "SELECT id FROM notifications "
        "WHERE source = %s AND gazette_id IS NOT DISTINCT FROM %s AND file_hash = %s",
        (record.source, record.gazette_id, file_hash),
    ).fetchone()
    if existing:
        return existing[0], False

    row = conn.execute(
        """
        INSERT INTO notifications
            (source, gazette_id, gazette_type, part, section, issuing_authority,
             notification_number, notification_date, act_reference, signatory,
             operative_text, source_url, file_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            record.source, record.gazette_id, record.gazette_type, record.part,
            record.section, record.issuing_authority, record.notification_number,
            record.notification_date, record.act_reference, record.signatory,
            record.operative_text, source_url, file_hash,
        ),
    ).fetchone()
    notification_id = row[0]

    for rel in record.relationships:
        conn.execute(
            "INSERT INTO relationships (notification_id, rel_type, target) VALUES (%s, %s, %s)",
            (notification_id, rel.rel_type, rel.target),
        )
    return notification_id, True


def insert_chunks(
    conn: psycopg.Connection, notification_id: int, chunks: list[tuple[str, list[float]]]
) -> None:
    for index, (chunk_text_value, embedding) in enumerate(chunks):
        conn.execute(
            """
            INSERT INTO notification_chunks (notification_id, chunk_index, chunk_text, embedding)
            VALUES (%s, %s, %s, %s)
            """,
            (notification_id, index, chunk_text_value, embedding),
        )


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

- [ ] **Step 5: Run to verify it passes**

Run: `cd ingestion && .venv/bin/python -m pytest tests/test_storage.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: Commit**

```bash
git add ingestion/migrations/002_chunking.sql ingestion/storage.py ingestion/tests/test_storage.py
git commit -m "Move embeddings from notifications to a chunks table; insert_notification reports is_new"
```

---

### Task 3: Restructure `ingest_notification` to chunk and embed only new documents

**Files:**
- Modify: `ingestion/ingest.py`
- Modify: `ingestion/tests/test_ingest.py`

**Interfaces:**
- Consumes: `chunk_text` (Task 1); `insert_notification` (returns `(id, is_new)` now), `insert_chunks` (Task 2).
- Produces: `ingest_notification(conn, source, raw_text, known_gazette_id=None, source_url=None) -> int` from `ingest.py` — **signature and return type are unchanged** from before this plan; only the internal behavior changes. `discovery.py`'s `discover_and_ingest` calls this function and needs **no changes** — it already only depends on this stable signature.

- [ ] **Step 1: Write the one new failing test (all existing tests in this file are unaffected — see explanation below)**

The existing `test_ingest.py` tests all pass a short, single-paragraph sample text (from `ingestion/samples/`), which `chunk_text()` reduces to exactly one chunk — so `embed_text` is still called exactly once per genuinely-new document, exactly as every existing test already asserts (directly or indirectly). Only the *duplicate* path changes behavior, so only one new test is needed:

```python
# add to ingestion/tests/test_ingest.py
def test_duplicate_notification_triggers_no_embedding_calls(db_conn):
    text = (SAMPLES / "central_so_2455.txt").read_text()
    with patch("ingest.embed_text", return_value=[0.1] * 768) as mock_embed:
        ingest_notification(db_conn, "central", text)
        db_conn.commit()
        mock_embed.reset_mock()
        ingest_notification(db_conn, "central", text)
        db_conn.commit()

    mock_embed.assert_not_called()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ingestion && .venv/bin/python -m pytest tests/test_ingest.py -v`
Expected: the new test FAILS (`embed_text` is currently called before the duplicate check, so it *is* called on the second, duplicate call) — every other test in the file still passes at this point, since `insert_notification`'s new `(id, is_new)` return isn't yet unpacked correctly by the still-old `ingest.py`. Actually run this and confirm: the old `ingest.py` calls `insert_notification(conn, record, embedding=embedding, file_hash=file_hash, source_url=source_url)` — Task 2 already removed the `embedding` parameter, so **every** test in this file now fails with a `TypeError` (unexpected keyword argument `embedding`). This is expected — Task 2 intentionally left `ingest.py` broken against the new `storage.py` until this task fixes it.

- [ ] **Step 3: Implement the restructured `ingest.py`**

```python
# ingestion/ingest.py
import hashlib
import psycopg
from chunking import chunk_text
from extractor import parse_central, parse_gujarat
from embeddings import embed_text
from storage import insert_notification, insert_chunks

PARSERS = {"central": parse_central, "gujarat": parse_gujarat}


class OutOfScopeError(Exception):
    """The document parsed fine but is not a Labour Code notification.

    Ministry 28's monthly listings mix Labour Code notifications in with
    unrelated ones (mines, uranium, fuel gas, ...) — empirically only about one
    in six is in scope. A non-None act_reference means the extractor matched a
    "Code on <name>, <year> (<n> of <year>)" citation, which is a reliable
    in-scope signal. Raising instead of inserting keeps off-topic documents out
    of the database and, because the check runs before any embedding work,
    avoids spending a paid embedding call on them.
    """


def ingest_notification(
    conn: psycopg.Connection,
    source: str,
    raw_text: str,
    known_gazette_id: str | None = None,
    source_url: str | None = None,
) -> int:
    if source not in PARSERS:
        raise ValueError(f"Unknown source: {source!r}. Must be 'central' or 'gujarat'.")

    file_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    record = PARSERS[source](raw_text)

    # The discovery step reads gazette_id straight out of the search results
    # table, which is far more trustworthy than the value regexed out of the
    # PDF text: real gazette PDFs carry a security watermark that makes
    # pdfplumber interleave characters, mangling the ID (or losing it entirely).
    if known_gazette_id is not None:
        record.gazette_id = known_gazette_id

    if record.act_reference is None:
        raise OutOfScopeError(
            f"No Labour Code act reference found in {record.gazette_id or 'document'} — "
            "not a Labour Code notification."
        )

    notification_id, is_new = insert_notification(
        conn, record, file_hash=file_hash, source_url=source_url
    )
    if is_new:
        # Only a genuinely new row pays for chunking/embedding — re-ingesting
        # an already-present notification now costs one cheap lookup-and-skip
        # instead of a wasted embedding API call per chunk.
        chunks = chunk_text(record.operative_text)
        embedded_chunks = [(chunk, embed_text(chunk)) for chunk in chunks]
        insert_chunks(conn, notification_id, embedded_chunks)
    return notification_id
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ingestion && .venv/bin/python -m pytest tests/test_ingest.py -v`
Expected: PASS (8 passed — the 7 pre-existing tests plus the new one)

- [ ] **Step 5: Run the full ingestion test suite**

Run: `cd ingestion && .venv/bin/python -m pytest tests/ -v`
Expected: all tests across the whole package pass (chunking, storage, ingest, discovery, download, embeddings, extractor — discovery.py itself needed no code changes since it only calls `ingest_notification` by its stable signature).

- [ ] **Step 6: Commit**

```bash
git add ingestion/ingest.py ingestion/tests/test_ingest.py
git commit -m "Chunk and embed only newly-inserted notifications"
```

---

### Task 4: Revise the Query API plan for chunked retrieval (plan-document edit, not code)

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-egazette-backend-pipeline.md`

**Interfaces:**
- No code exists yet for this plan — this task edits the plan's own text so that whenever it *is* implemented, it builds against the real chunked schema instead of a stale one-embedding-per-notification design.

This plan predates both this chunking design and the switch from Gemini to NVIDIA embeddings in `ingestion/` (`git log --oneline -- ingestion/embeddings.py` shows the switch happened days ago) — its Global Constraints still say `gemini-embedding-001`, which would make its vector search meaningless (a query embedded with a different model than the documents were embedded with is not comparable via cosine similarity). Both problems are fixed in this one task since they touch the same file and the same embedding call site.

- [ ] **Step 1: Fix the stale embedding-model reference in Global Constraints**

In `docs/superpowers/plans/2026-09-05-egazette-backend-pipeline.md`, find this line in **Global Constraints**:

```
- Embedding model: `gemini-embedding-001` (same one the ingestion pipeline used to embed the stored documents — a query embedded with a different model would not be comparable via cosine similarity). Verify current free-tier rate limits at `aistudio.google.com/rate-limit` against the real key.
```

Replace it with:

```
- Embedding model: `nvidia/llama-nemotron-embed-vl-1b-v2` at 768 dimensions via NVIDIA's NIM API (`https://integrate.api.nvidia.com/v1/embeddings`) — must match the ingestion pipeline's model exactly, or a query embedded differently than the stored documents is not comparable via cosine similarity. Retrieval embeds with `input_type="query"`; ingestion embeds with `input_type="passage"` — NV-Embed explicitly distinguishes the two and mismatching them degrades retrieval quality.
- Retrieval operates over `notification_chunks` (one or more chunks per notification, each independently embedded — see `docs/superpowers/specs/2026-09-06-notification-chunking-design.md`), joined back to `notifications` for citation metadata. A "hit" is a chunk; a "citation" is its parent notification.
```

- [ ] **Step 2: Replace the local migration copy in Task 1, Step 3, with the post-chunking schema**

Find the `backend/migrations/001_init.sql` code block inside Task 1's Step 3 (the one starting with `CREATE EXTENSION IF NOT EXISTS vector;`, containing the `notifications` and `relationships` tables). Since this plan has never been implemented, there's no need to model it as two sequential migrations for a throwaway local test database — replace the whole block with the final schema directly:

```sql
-- backend/migrations/001_init.sql
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
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, gazette_id, file_hash)
);

CREATE TABLE relationships (
    id                SERIAL PRIMARY KEY,
    notification_id   INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    rel_type          TEXT NOT NULL CHECK (rel_type IN ('issued_under', 'supersedes', 'amends')),
    target            TEXT NOT NULL
);

CREATE TABLE notification_chunks (
    id                SERIAL PRIMARY KEY,
    notification_id   INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    chunk_index       INTEGER NOT NULL,
    chunk_text        TEXT NOT NULL,
    embedding         vector(768) NOT NULL,
    UNIQUE (notification_id, chunk_index)
);

CREATE INDEX notification_chunks_fts_idx ON notification_chunks
    USING GIN (to_tsvector('english', chunk_text));

CREATE INDEX relationships_target_idx ON relationships (target);
```

Note there is no `notifications.embedding` column and no `notifications_fts_idx` — both moved to `notification_chunks` in this version, matching the real ingestion schema after `002_chunking.sql`.

- [ ] **Step 3: Replace Task 1 Step 5's `insert_test_notification` fixture body — its call signature stays identical**

Find `backend/tests/conftest.py`'s code block inside Task 1's Step 5. Replace it with:

```python
# backend/tests/conftest.py
import pytest
from app.config import get_connection


@pytest.fixture
def db_conn():
    conn = get_connection()
    yield conn
    conn.execute("TRUNCATE notifications, relationships, notification_chunks RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()


@pytest.fixture
def insert_test_notification(db_conn):
    """Insert a minimal notification + one chunk directly via SQL — this plan
    has no write-path code of its own (that's the ingestion pipeline's job),
    so tests that need data to query against insert it directly. The call
    signature is unchanged from before chunking existed — only what it does
    internally changed (a chunk row now carries the embedding, not the
    notification row) — so no test that calls this fixture needs editing."""
    def _insert(gazette_id: str, operative_text: str, embedding: list[float] | None = None,
                source: str = "central", part: str = "Part II", section: str | None = None,
                notification_date: str = "22nd May, 2025", act_reference: str | None = None):
        row = db_conn.execute(
            """
            INSERT INTO notifications
                (source, gazette_id, part, section, notification_date, act_reference,
                 operative_text, file_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (source, gazette_id, part, section, notification_date, act_reference,
             operative_text, f"test-hash-{gazette_id}"),
        ).fetchone()
        notification_id = row[0]
        if embedding is not None:
            db_conn.execute(
                """
                INSERT INTO notification_chunks (notification_id, chunk_index, chunk_text, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                (notification_id, 0, operative_text, embedding),
            )
        db_conn.commit()
        return notification_id
    return _insert
```

Because this fixture's call signature (`gazette_id=`, `operative_text=`, `embedding=`, `source=`, ...) is unchanged, **no test in Task 3 or Task 5 that calls it needs any edit** — only this fixture's internals and the schema underneath it changed.

- [ ] **Step 4: Replace Task 2's `embeddings.py` (Gemini → NVIDIA) and its test**

Find Task 2's `backend/app/embeddings.py` code block and its `backend/tests/test_embeddings.py` code block. Replace both:

```python
# backend/app/embeddings.py
import requests
from app.config import NVIDIA_API_KEY

NVIDIA_EMBEDDINGS_URL = "https://integrate.api.nvidia.com/v1/embeddings"
EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"
EMBEDDING_DIMENSIONS = 768


def embed_text(text: str, input_type: str = "query") -> list[float]:
    """input_type defaults to "query" here — this service only ever embeds the
    user's question, never a stored document (that's the ingestion pipeline's
    job, which defaults to "passage"). Mismatching the two degrades retrieval
    quality per NV-Embed's own documentation."""
    if not NVIDIA_API_KEY:
        raise RuntimeError("NVIDIA_API_KEY is not set — cannot call the embedding API.")
    response = requests.post(
        NVIDIA_EMBEDDINGS_URL,
        headers={
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={
            "input": [text],
            "model": EMBEDDING_MODEL,
            "input_type": input_type,
            "dimensions": EMBEDDING_DIMENSIONS,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
```

```python
# backend/tests/test_embeddings.py
import pytest
from unittest.mock import patch, MagicMock
from app.embeddings import embed_text, EMBEDDING_MODEL, NVIDIA_EMBEDDINGS_URL


def _fake_response(vector):
    fake = MagicMock()
    fake.json.return_value = {"data": [{"embedding": vector}]}
    fake.raise_for_status.return_value = None
    return fake


def test_embed_text_returns_vector_from_nvidia_response():
    with patch("app.embeddings.NVIDIA_API_KEY", "test-key"), \
         patch("app.embeddings.requests.post", return_value=_fake_response([0.1, 0.2, 0.3])) as mock_post:
        result = embed_text("Is the Code on Wages in force in Gujarat?")

    assert result == [0.1, 0.2, 0.3]
    call = mock_post.call_args
    assert call.args[0] == NVIDIA_EMBEDDINGS_URL
    assert call.kwargs["json"]["model"] == EMBEDDING_MODEL
    assert call.kwargs["json"]["dimensions"] == 768


def test_embed_text_defaults_to_query_input_type():
    with patch("app.embeddings.NVIDIA_API_KEY", "test-key"), \
         patch("app.embeddings.requests.post", return_value=_fake_response([0.0] * 768)) as mock_post:
        embed_text("Is the Code on Wages in force in Gujarat?")

    assert mock_post.call_args.kwargs["json"]["input_type"] == "query"


def test_embed_text_raises_a_clear_error_when_the_api_key_is_missing():
    with patch("app.embeddings.NVIDIA_API_KEY", ""):
        with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
            embed_text("anything")
```

Also update `backend/app/config.py` (Task 1, Step 4) and `backend/.env.example` (Task 1, Step 2): replace every `GEMINI_API_KEY` occurrence with `NVIDIA_API_KEY`.

- [ ] **Step 5: Replace Task 3's `retrieval.py` and its `Interfaces` line**

Find Task 3's **Interfaces** block and replace it with:

```
- Consumes: `embed_text` (Task 2); Postgres schema from Task 1 (`notification_chunks` joined to `notifications`) — populated in production by the ingestion pipeline, populated in these tests by the `insert_test_notification` fixture.
- Produces: `hybrid_search(conn, question: str, top_k: int = 5) -> list[dict]` (each dict: `{id, source, gazette_id, part, section, notification_date, operative_text, source_url, score}` — `id` is the **notification's** id and `operative_text` is the **matching chunk's text**, kept under that key name deliberately so `generation.py` (Task 4) needs zero changes despite the underlying data now being a chunk, not a whole document — ordered best-first) from `app/retrieval.py`, used by `generation.py` (Task 4) and `main.py` (Task 5).
```

Find Task 3's `backend/app/retrieval.py` code block and replace it with:

```python
# backend/app/retrieval.py
import psycopg
from app.embeddings import embed_text

RRF_K = 60  # standard reciprocal-rank-fusion constant


def _keyword_search(conn: psycopg.Connection, question: str, top_k: int) -> list[tuple[int, int]]:
    rows = conn.execute(
        """
        SELECT id, ts_rank(to_tsvector('english', chunk_text), plainto_tsquery('english', %s)) AS rank
        FROM notification_chunks
        WHERE to_tsvector('english', chunk_text) @@ plainto_tsquery('english', %s)
        ORDER BY rank DESC
        LIMIT %s
        """,
        (question, question, top_k),
    ).fetchall()
    return [(row[0], position) for position, row in enumerate(rows)]


def _vector_search(conn: psycopg.Connection, question: str, top_k: int) -> list[tuple[int, int]]:
    query_embedding = embed_text(question, input_type="query")
    rows = conn.execute(
        """
        SELECT id FROM notification_chunks
        ORDER BY embedding <=> %s
        LIMIT %s
        """,
        (query_embedding, top_k),
    ).fetchall()
    return [(row[0], position) for position, row in enumerate(rows)]


def hybrid_search(conn: psycopg.Connection, question: str, top_k: int = 5) -> list[dict]:
    keyword_hits = _keyword_search(conn, question, top_k)
    vector_hits = _vector_search(conn, question, top_k)

    chunk_scores: dict[int, float] = {}
    for chunk_id, rank in keyword_hits + vector_hits:
        chunk_scores[chunk_id] = chunk_scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)

    if not chunk_scores:
        return []

    rows = conn.execute(
        """
        SELECT c.id, c.notification_id, c.chunk_text, n.source, n.gazette_id, n.part,
               n.section, n.notification_date, n.source_url
        FROM notification_chunks c
        JOIN notifications n ON n.id = c.notification_id
        WHERE c.id = ANY(%s)
        """,
        (list(chunk_scores.keys()),),
    ).fetchall()

    # One citation per notification: if several of its chunks scored well,
    # keep only the best-scoring one (spec §6 — preserves the existing
    # one-passage-per-source Citation model rather than expanding it).
    best_per_notification: dict[int, dict] = {}
    for row in rows:
        chunk_id, notification_id = row[0], row[1]
        score = chunk_scores[chunk_id]
        candidate = {
            "id": notification_id, "source": row[3], "gazette_id": row[4], "part": row[5],
            "section": row[6], "notification_date": row[7], "operative_text": row[2],
            "source_url": row[8], "score": score,
        }
        existing = best_per_notification.get(notification_id)
        if existing is None or score > existing["score"]:
            best_per_notification[notification_id] = candidate

    return sorted(best_per_notification.values(), key=lambda r: r["score"], reverse=True)[:top_k]
```

The `test_retrieval.py` code in Task 3 (the two test functions using `insert_test_notification`) needs **no changes** — its assertions only ever checked `results[0]["gazette_id"]` and the empty-list case, which still hold given the unchanged fixture signature and the unchanged `operative_text`/`gazette_id` keys in the returned dict.

- [ ] **Step 6: Verify the edits landed correctly**

There's no code to run (this plan is still unimplemented) — verify the edit mechanically instead:

```bash
grep -c "gemini-embedding-001" docs/superpowers/plans/2026-09-05-egazette-backend-pipeline.md
grep -c "notification_chunks" docs/superpowers/plans/2026-09-05-egazette-backend-pipeline.md
grep -c "NVIDIA_API_KEY" docs/superpowers/plans/2026-09-05-egazette-backend-pipeline.md
```

Expected: the first command prints `0` (no stale Gemini references left); the second and third both print a positive count (the new schema and provider are referenced throughout).

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/plans/2026-09-05-egazette-backend-pipeline.md
git commit -m "Revise Query API plan for chunked retrieval and the NVIDIA embedding switch"
```

---

### Task 5: Re-run the real backfill against the chunked schema

**Files:**
- None (operational task — no code changes)

**Interfaces:**
- Consumes: `ingestion/cli.py` (unchanged by this plan) against the now-migrated real database.

- [ ] **Step 1: Clear the 6 notifications ingested under the old (pre-chunking) schema**

```bash
cd ingestion
source .venv/bin/activate
python3 -c "
from config import get_connection
conn = get_connection()
conn.execute('TRUNCATE notifications, relationships, notification_chunks RESTART IDENTITY CASCADE')
conn.commit()
print('cleared')
"
```

Expected: prints `cleared`. (These 6 rows' old embeddings are already unusable — `002_chunking.sql`, Task 2, already dropped the column they lived in.)

- [ ] **Step 2: Re-run the full 4-year backfill**

```bash
cd ingestion && source .venv/bin/activate && python cli.py --start-year 2022 --end-year 2025 2>&1 | tee ingest.log
```

Expected: completes with a `Done. Ingested N, already present 0, out of scope M, failed F.` summary line. `F` should be lower than the previous run's 4 embedding failures (the 190,230-character document that caused them now gets chunked instead of rejected outright) — confirm by checking `ingest.log` for `Failed to ingest` lines mentioning `400 Client Error` and comparing against the previous run's failures.

- [ ] **Step 3: Spot-check that the previously-failing large document now ingests successfully with multiple chunks**

```bash
cd ingestion
source .venv/bin/activate
python3 -c "
from config import get_connection
conn = get_connection()
row = conn.execute(\"SELECT id FROM notifications WHERE gazette_id = 'CG-DL-E-31122025-268946'\").fetchone()
print('notification row:', row)
if row:
    chunks = conn.execute('SELECT count(*) FROM notification_chunks WHERE notification_id = %s', (row[0],)).fetchone()[0]
    print('chunk count:', chunks)
"
```

Expected: the notification row exists (it failed entirely on the previous run) and its chunk count is greater than 1 (confirming the 190,230-character document was actually split, not just barely squeezed under the limit as one chunk).

There is no commit for this task — it changes data in the real database, not files in the repository.
