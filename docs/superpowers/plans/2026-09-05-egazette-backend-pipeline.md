# e-Gazette Query API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Supersedes an earlier draft of this file** that bundled ingestion (extraction, discovery, downloading, embedding-at-write-time) into this same plan. That's been pulled out into its own standalone plan — `docs/superpowers/plans/2026-09-05-egazette-ingestion-pipeline.md` — a separate Python package with zero dependency on this one, so it can run as a background process while this API is being built. This plan now covers **only** the query-serving side: it reads whatever the ingestion pipeline has already written to Postgres. It has no `extractor.py`, no `storage.py` write path, and no `/ingest` endpoint — retrieval and generation query the database directly.

**Goal:** Build the FastAPI service that answers questions over whatever Central Gazette Labour Codes notifications the (separately-running) ingestion pipeline has written to Postgres — hybrid (keyword + vector) retrieval with enforced citation-or-refusal generation, fully testable via `POST /ask` and the eval script.

**Architecture:** A single FastAPI service reads Postgres (`pgvector` extension) directly via a few SQL queries in `retrieval.py` — no ORM, no data-access layer beyond that, since this service only ever reads rows the ingestion pipeline already wrote. Hybrid retrieval (Postgres full-text search + pgvector cosine similarity, merged by reciprocal rank fusion) feeds a Gemini generation call that must cite a real passage or refuse.

**Tech Stack:** Python 3.11+, FastAPI, `psycopg` (v3), PostgreSQL 16 + `pgvector` extension (same database the ingestion pipeline writes to), NVIDIA NIM API (`nvidia/llama-nemotron-embed-vl-1b-v2` for embedding the user's question), `google-genai` SDK (`gemini-flash-latest` for generation), pytest + `httpx` (FastAPI `TestClient`), Docker Compose for a local Postgres used only by this plan's own tests.

**Spec:** `docs/superpowers/specs/2026-09-05-egazette-ux-architecture-design.md`

## Global Constraints

- **This service never writes to `notifications`/`relationships`.** No ingestion logic, no `extractor.py`, lives here — that's the ingestion pipeline plan's job entirely. If a task in this plan seems to need to insert a notification, that's a sign something has been designed wrong; stop and re-check against the ingestion plan instead.
- Every substantive answer must cite a real passage (gazette_id, part/section, source) **or** explicitly refuse (spec §1) — enforce this in code, not just in the prompt.
- Every answer response includes the fixed disclaimer text: `"This is not legal advice — verify against the original Gazette."` (spec §1, §4.3).
- No vector database service other than `pgvector` on the same Postgres instance (spec §5.3, §5.4) — relationship lookups (if ever added here) stay relational rows, never a graph database.
- Embedding model: `nvidia/llama-nemotron-embed-vl-1b-v2` at 768 dimensions via NVIDIA's NIM API (`https://integrate.api.nvidia.com/v1/embeddings`) — must match the ingestion pipeline's model exactly, or a query embedded differently than the stored documents is not comparable via cosine similarity. Retrieval embeds with `input_type="query"`; ingestion embeds with `input_type="passage"` — NV-Embed explicitly distinguishes the two and mismatching them degrades retrieval quality.
- Retrieval operates over `notification_chunks` (one or more chunks per notification, each independently embedded — see `docs/superpowers/specs/2026-09-06-notification-chunking-design.md`), joined back to `notifications` for citation metadata. A "hit" is a chunk; a "citation" is its parent notification.
- Deployment: this service deploys to **Railway** (FastAPI service, connecting via `DATABASE_URL` to the same managed Postgres the ingestion pipeline populated) — resolves the spec's open deployment-split question; the frontend (separate plan) deploys to Vercel.
- Local dev/test Postgres for this plan's own test suite is independent of the ingestion pipeline's local dev Postgres — each plan's `docker-compose.yml` runs its own container. Only the real deployed database is ever shared between the two.

---

## File Structure

```
backend/
  requirements.txt
  .env.example
  docker-compose.yml            # local Postgres+pgvector for this plan's own tests
  app/
    __init__.py
    config.py                   # env var loading
    models.py                   # Pydantic: AskRequest, AskResponse, Citation
    embeddings.py                # Gemini embedding wrapper (embeds the user's question)
    generation.py                 # Gemini generation wrapper + citation-or-refusal enforcement
    retrieval.py                 # hybrid search: FTS + vector + RRF merge, direct SQL
    main.py                      # FastAPI app: POST /ask, GET /health
  migrations/
    001_init.sql                # same schema as the ingestion plan — needed here only so this
                                 # plan's own local dev/test Postgres has somewhere to write
                                 # test fixture rows; never applied against the real shared DB
                                 # from here (the ingestion plan owns that application)
  tests/
    __init__.py
    conftest.py                 # pytest fixtures: test DB connection
    test_embeddings.py
    test_retrieval.py
    test_generation.py
    test_api.py
  eval/
    questions.md                # 15 locked test questions, written before any run
    run_eval.py                 # calls the running API for each question, prints results for manual review
```

---

### Task 1: Repo scaffold, local Postgres, config, and API models

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`
- Create: `backend/docker-compose.yml`
- Create: `backend/migrations/001_init.sql`
- Create: `backend/app/config.py`
- Create: `backend/app/models.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `get_connection() -> psycopg.Connection`, `GEMINI_API_KEY` from `app/config.py`; `AskRequest`, `AskResponse`, `Citation` Pydantic models from `app/models.py` — used by every later task in this plan.

- [ ] **Step 1: Scaffold directories**

```bash
mkdir -p backend/app backend/tests backend/migrations backend/eval
touch backend/app/__init__.py backend/tests/__init__.py
```

- [ ] **Step 2: Write `requirements.txt` and `.env.example`**

```
# backend/requirements.txt
fastapi==0.115.*
uvicorn[standard]==0.32.*
psycopg[binary]==3.2.*
google-genai==0.*
pydantic==2.*
python-dotenv==1.*
pytest==8.*
pytest-mock==3.*
httpx==0.27.*
```

```
# backend/.env.example
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/egazette
NVIDIA_API_KEY=
```

> In production, `DATABASE_URL` points at the same Railway Postgres the ingestion pipeline populated. Locally, it points at this plan's own `docker-compose.yml` container (port `5432`, distinct from the ingestion plan's local container on `5433`).

- [ ] **Step 3: Write `docker-compose.yml` and the migration (same schema as the ingestion plan, for local test use only)**

```yaml
# backend/docker-compose.yml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: egazette
    ports:
      - "5432:5432"
    volumes:
      - egazette_pgdata:/var/lib/postgresql/data
volumes:
  egazette_pgdata:
```

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

Run:
```bash
cd backend && docker compose up -d
docker compose exec -T db psql -U postgres -d egazette < migrations/001_init.sql
```
Expected: container healthy; `CREATE EXTENSION`, `CREATE TABLE` x2, `CREATE INDEX` x2 printed, no errors.

- [ ] **Step 4: Write `config.py` and `models.py`**

```python
# backend/app/config.py
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")


def get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)
```

```python
# backend/app/models.py
from pydantic import BaseModel


class Citation(BaseModel):
    source: str
    gazette_id: str | None
    part: str | None
    section: str | None
    notification_date: str | None
    passage: str
    source_url: str | None


class AskRequest(BaseModel):
    question: str
    history: list[dict] = []  # [{"question": str, "answer": str}, ...] from the current session only


class AskResponse(BaseModel):
    answer: str
    refused: bool
    citations: list[Citation]
    disclaimer: str = "This is not legal advice — verify against the original Gazette."
```

- [ ] **Step 5: Write the `db_conn` fixture used by every later test in this plan**

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

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/.env.example backend/app/__init__.py \
  backend/docker-compose.yml backend/migrations backend/app/config.py \
  backend/app/models.py backend/tests/__init__.py backend/tests/conftest.py
git commit -m "Scaffold Query API: config, models, local Postgres for tests"
```

---

### Task 2: Gemini embedding wrapper (for embedding the user's question)

**Files:**
- Create: `backend/app/embeddings.py`
- Test: `backend/tests/test_embeddings.py`

**Interfaces:**
- Consumes: `GEMINI_API_KEY` from `app/config.py` (Task 1).
- Produces: `embed_text(text: str) -> list[float]` from `app/embeddings.py`, used by `retrieval.py` (Task 3).

**Note:** this is the same wrapper (same model, same shape) as the ingestion pipeline's `embeddings.py` — duplicated deliberately, not shared, so the two remain genuinely independent packages. It's ~15 lines; the alternative (a shared internal package) would add more operational complexity than it saves at this size.

- [ ] **Step 1: Write the failing test (mocking the Gemini client, never calling the real API in tests)**

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

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.embeddings'`

- [ ] **Step 3: Implement `embeddings.py`**

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

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_embeddings.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/embeddings.py backend/tests/test_embeddings.py
git commit -m "Add Gemini embedding wrapper for query embedding"
```

---

### Task 3: Hybrid retrieval (keyword + vector, RRF merge)

**Files:**
- Create: `backend/app/retrieval.py`
- Test: `backend/tests/test_retrieval.py`

**Interfaces:**
- Consumes: `embed_text` (Task 2); Postgres schema from Task 1 (`notification_chunks` joined to `notifications`) — populated in production by the ingestion pipeline, populated in these tests by the `insert_test_notification` fixture.
- Produces: `hybrid_search(conn, question: str, top_k: int = 5) -> list[dict]` (each dict: `{id, source, gazette_id, part, section, notification_date, operative_text, source_url, score}` — `id` is the **notification's** id and `operative_text` is the **matching chunk's text**, kept under that key name deliberately so `generation.py` (Task 4) needs zero changes despite the underlying data now being a chunk, not a whole document — ordered best-first) from `app/retrieval.py`, used by `generation.py` (Task 4) and `main.py` (Task 5).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_retrieval.py
from unittest.mock import patch
from app.retrieval import hybrid_search


def test_hybrid_search_finds_notification_by_keyword(insert_test_notification, db_conn):
    insert_test_notification(
        gazette_id="Gujarat-Extra-62",
        operative_text="the Government of Gujarat hereby appoints the person specified as the "
                        "Authority for the purposes of the Code on Wages, 2019",
        embedding=[0.1] * 768,
        source="gujarat",
    )

    with patch("app.retrieval.embed_text", return_value=[0.1] * 768):
        results = hybrid_search(db_conn, "Code on Wages Gujarat appointing authority")

    assert len(results) >= 1
    assert results[0]["gazette_id"] == "Gujarat-Extra-62"


def test_hybrid_search_returns_empty_list_when_nothing_ingested(db_conn):
    with patch("app.retrieval.embed_text", return_value=[0.1] * 768):
        results = hybrid_search(db_conn, "anything at all")
    assert results == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_retrieval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.retrieval'`

- [ ] **Step 3: Implement `retrieval.py`**

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

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_retrieval.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval.py backend/tests/test_retrieval.py
git commit -m "Add hybrid keyword+vector retrieval with reciprocal rank fusion"
```

---

### Task 4: Generation with enforced citation-or-refusal

**Files:**
- Create: `backend/app/generation.py`
- Test: `backend/tests/test_generation.py`

**Interfaces:**
- Consumes: retrieval result dicts (Task 3's `hybrid_search` output shape).
- Produces: `generate_answer(question: str, passages: list[dict], history: list[dict]) -> AskResponse` from `app/generation.py` (uses `AskResponse`/`Citation` from `app/models.py`, Task 1), used by `main.py` (Task 5).

**Note on the refusal threshold (spec §7 open item):** this task implements refusal on **empty retrieval** (`passages == []`) as the hard floor — that much is unambiguous. The *similarity-score* floor for "retrieval found something, but not a good match" is deliberately left as a tunable constant (`MIN_RELEVANCE_SCORE` below, initially `0.0` — i.e. off) rather than guessed, per the spec: it must be set from real eval results in Task 6, once the ingestion pipeline has populated real data to evaluate against.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_generation.py
from unittest.mock import patch, MagicMock
from app.generation import generate_answer

SAMPLE_PASSAGE = {
    "id": 1, "source": "gujarat", "gazette_id": "Gujarat-Extra-62", "part": "Part IV-A",
    "section": None, "notification_date": "20th May, 2025",
    "operative_text": "...the Government of Gujarat hereby appoints the person specified...",
    "source_url": None, "score": 0.9,
}


def test_generate_answer_refuses_when_no_passages_found():
    result = generate_answer("What's the minimum wage in Delhi?", passages=[], history=[])
    assert result.refused is True
    assert "couldn't find" in result.answer.lower()
    assert result.citations == []
    assert "not legal advice" in result.disclaimer.lower()


def test_generate_answer_cites_a_real_passage_when_found():
    fake_response = MagicMock()
    fake_response.text = "Yes — Gujarat appointed the authority for the Code on Wages on 20 May 2025."

    with patch("app.generation._client") as mock_client:
        mock_client.models.generate_content.return_value = fake_response
        result = generate_answer(
            "Is the Code on Wages in force in Gujarat?", passages=[SAMPLE_PASSAGE], history=[]
        )

    assert result.refused is False
    assert len(result.citations) == 1
    assert result.citations[0].gazette_id == "Gujarat-Extra-62"
    assert "not legal advice" in result.disclaimer.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_generation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.generation'`

- [ ] **Step 3: Implement `generation.py`**

```python
# backend/app/generation.py
from google import genai
from app.config import GEMINI_API_KEY
from app.models import AskResponse, Citation

_client = genai.Client(api_key=GEMINI_API_KEY)

GENERATION_MODEL = "gemini-flash-latest"
MIN_RELEVANCE_SCORE = 0.0  # tune from eval results (Task 6) — do not guess a value here

REFUSAL_MESSAGE = (
    "I couldn't find a notification matching this in the sources I cover "
    "(Central Gazette + Gujarat Gazette, Labour Codes only). I can answer "
    "questions about Code on Wages, Industrial Relations Code, OSH Code, "
    "and Code on Social Security — as notified centrally or in Gujarat."
)


def _build_prompt(question: str, passages: list[dict], history: list[dict]) -> str:
    history_block = "\n".join(f"Q: {h['question']}\nA: {h['answer']}" for h in history)
    passages_block = "\n\n".join(
        f"[Passage {i + 1}] Source: {p['source']}, Gazette ID: {p['gazette_id']}, "
        f"Part: {p['part']}, Date: {p['notification_date']}\n{p['operative_text']}"
        for i, p in enumerate(passages)
    )
    return (
        "You answer questions about Indian Labour Codes using ONLY the passages below. "
        "Never use outside knowledge. Be concise and plain-language.\n\n"
        f"Prior conversation (may be empty):\n{history_block}\n\n"
        f"Passages:\n{passages_block}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )


def generate_answer(question: str, passages: list[dict], history: list[dict]) -> AskResponse:
    relevant = [p for p in passages if p.get("score", 0.0) >= MIN_RELEVANCE_SCORE]
    if not relevant:
        return AskResponse(answer=REFUSAL_MESSAGE, refused=True, citations=[])

    prompt = _build_prompt(question, relevant, history)
    response = _client.models.generate_content(model=GENERATION_MODEL, contents=prompt)

    citations = [
        Citation(
            source=p["source"], gazette_id=p["gazette_id"], part=p["part"], section=p["section"],
            notification_date=p["notification_date"], passage=p["operative_text"],
            source_url=p["source_url"],
        )
        for p in relevant
    ]
    return AskResponse(answer=response.text, refused=False, citations=citations)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_generation.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation.py backend/tests/test_generation.py
git commit -m "Add generation with enforced citation-or-refusal"
```

---

### Task 5: FastAPI app

**Files:**
- Create: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `hybrid_search` (Task 3), `generate_answer` (Task 4), `AskRequest`/`AskResponse` (Task 1).
- Produces: `POST /ask` (body: `AskRequest`, returns: `AskResponse`), `GET /health` (returns: `{"status": "ok"}`) — the API contract the frontend plan consumes. No `/ingest` endpoint — ingestion happens entirely out-of-band via the separate pipeline.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api.py
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_returns_cited_answer_for_existing_notification(insert_test_notification, db_conn):
    insert_test_notification(
        gazette_id="Gujarat-Extra-62",
        operative_text="the Government of Gujarat hereby appoints the person specified as the "
                        "Authority for the purposes of the Code on Wages, 2019",
        embedding=[0.1] * 768,
        source="gujarat",
    )

    with patch("app.retrieval.embed_text", return_value=[0.1] * 768), \
         patch("app.generation._client") as mock_genai:
        mock_genai.models.generate_content.return_value.text = "Yes, it is in force."
        ask_response = client.post(
            "/ask", json={"question": "Is the Code on Wages in force in Gujarat?", "history": []}
        )

    assert ask_response.status_code == 200
    body = ask_response.json()
    assert body["refused"] is False
    assert body["citations"][0]["gazette_id"] == "Gujarat-Extra-62"
    assert "not legal advice" in body["disclaimer"].lower()


def test_ask_refuses_when_nothing_matches(db_conn):
    with patch("app.retrieval.embed_text", return_value=[0.1] * 768):
        response = client.post("/ask", json={"question": "What's the weather today?", "history": []})
    assert response.status_code == 200
    assert response.json()["refused"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Implement `main.py`**

```python
# backend/app/main.py
from fastapi import FastAPI
from app.config import get_connection
from app.retrieval import hybrid_search
from app.generation import generate_answer
from app.models import AskRequest, AskResponse

app = FastAPI(title="e-Gazette Conversational Search — Query API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    conn = get_connection()
    try:
        passages = hybrid_search(conn, request.question)
        return generate_answer(request.question, passages, request.history)
    finally:
        conn.close()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full test suite**

Run: `cd backend && python -m pytest -v`
Expected: all tests across every task pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "Add FastAPI app: POST /ask, GET /health (no /ingest — that's the ingestion pipeline's job)"
```

---

### Task 6: Eval harness with the 15 locked test questions

**Files:**
- Create: `backend/eval/questions.md`
- Create: `backend/eval/run_eval.py`

**Interfaces:**
- Consumes: the running API's `POST /ask` (Task 5), pointed at a `DATABASE_URL` that the ingestion pipeline (separate plan) has already populated with real Central Gazette data.
- Produces: a manual-review report (`stdout` + `eval_results.json`) — the last step in this plan.

**Prerequisite — this is a hard dependency on the other plan finishing its job first:** run this only after `ingestion/cli.py` (the standalone pipeline) has ingested real notifications into the same database this API's `DATABASE_URL` points at. Confirm with `SELECT COUNT(*) FROM notifications;` before running — an empty table means every question will (correctly) refuse, which is not a meaningful eval.

- [ ] **Step 1: Write the 15 locked questions — before running anything, per spec §6**

```markdown
# backend/eval/questions.md

Locked before evaluation. Do not edit after seeing outputs (spec §6).

## The 5 locked target queries (spec §1)
1. Is the Code on Wages in force in Gujarat?
2. What does the Code on Wages say about compounding offences under section 56?
3. Which notification amended or superseded S.O. No. 2765 (E)?
4. When does the Gujarat appointing-authority notification (GR/2026/54/LED/MWA) take effect?
5. Show me the source for that answer. (asked as a follow-up to question 1)

## 10 additional questions
6. Who is the appointing authority for the Code on Wages in Gujarat?
7. What is S.O. 2455(E) about?
8. What is S.O. 2457(E) about?
9. Which ministry issued S.O. 2455(E)?
10. Is there a notification about the Industrial Relations Code? (expect: refusal, unless the ingestion pipeline happened to find one — check against what was actually ingested)
11. What's the minimum wage in Delhi? (expect: refusal — out of scope, wrong state)
12. What does "in supersession of" mean in S.O. 2457(E)?
13. When was S.O. No. 2765 (E) originally dated?
14. Which department issued the Gujarat wages notification?
15. What powers does section 39 of the Code on Wages give the Central Government?
```

- [ ] **Step 2: Write `run_eval.py`**

```python
# backend/eval/run_eval.py
import json
import sys
from pathlib import Path
import requests

API_URL = "http://localhost:8000"
QUESTIONS_FILE = Path(__file__).parent / "questions.md"


def load_questions() -> list[str]:
    lines = QUESTIONS_FILE.read_text().splitlines()
    return [
        line.split(".", 1)[1].strip()
        for line in lines
        if line and line[0].isdigit() and "." in line
    ]


def main():
    questions = load_questions()
    results = []
    for question in questions:
        response = requests.post(f"{API_URL}/ask", json={"question": question, "history": []})
        response.raise_for_status()
        body = response.json()
        results.append({"question": question, **body})
        print(f"\nQ: {question}")
        print(f"Refused: {body['refused']}")
        print(f"A: {body['answer']}")
        for citation in body["citations"]:
            print(f"  Cite: {citation['gazette_id']} / {citation['part']} / {citation['notification_date']}")

    Path("eval_results.json").write_text(json.dumps(results, indent=2))
    print("\nWrote eval_results.json — check each answer against the source PDF manually.")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Confirm the shared database actually has ingested data, then run the eval script**

Run:
```bash
cd backend && docker compose up -d
uvicorn app.main:app --reload &
sleep 2
python -c "from app.config import get_connection; print(get_connection().execute('SELECT COUNT(*) FROM notifications').fetchone())"
python eval/run_eval.py
```
Expected: the count query prints a non-zero number (real data from the ingestion pipeline); then 15 printed Q/A/citation blocks. Manually verify each against the actual source PDFs per spec §6 (human-judged, no numeric threshold). Use question 5's and question 10/11's results specifically to set `MIN_RELEVANCE_SCORE` in `app/generation.py` (Task 4) — this is where that open item from the spec gets resolved, from real scores, not a guess.

- [ ] **Step 4: Commit**

```bash
git add backend/eval
git commit -m "Add eval harness with 15 locked test questions"
```

## Self-Review Notes

- **Spec coverage:** §1 (non-negotiables) → Task 4 (refusal, citation, disclaimer) + Task 6 (eval against locked queries). §5.1 (stack) → Tasks 1–5. §5.3 (no graph DB) → not exercised by this plan at all (relationship lookups aren't part of the Query API's retrieval path; if ever needed, would follow the same relational-not-graph rule). §5.4 (hybrid retrieval, RRF, no query-expansion call) → Task 3. §5.6 (LLM call inventory: this plan owns exactly the query-time half — one embedding call + one generation call per question) → Tasks 2, 4. §6 (eval) → Task 6. §7 open items (refusal threshold, deployment split) → both resolved: threshold deferred to real Task 6 data; deployment split resolved to Railway in Global Constraints.
- **Placeholder scan:** no TBD/TODO; `MIN_RELEVANCE_SCORE = 0.0` is a real, working default with an explicit instruction on how and when to set it.
- **Type consistency:** `AskResponse`/`Citation` defined once in `app/models.py` (Task 1) and used identically in Tasks 4 and 5. `hybrid_search`'s return dict shape (Task 3) matches exactly what `generation.py` (Task 4) and its test fixture (`SAMPLE_PASSAGE`) expect.
- **Independence check (the reason this plan was split from ingestion):** this plan has no `extractor.py`, no write-side `storage.py`, and no `/ingest` endpoint. Every test that needs a notification row inserts one directly via SQL (`insert_test_notification` fixture, Task 1) rather than importing anything from the ingestion package. Grepped for `from ingestion` / `import ingestion` — none present.
