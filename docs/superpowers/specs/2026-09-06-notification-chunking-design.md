# Notification Chunking — Design

**Status:** Draft — awaiting review
**Date:** 2026-09-06

## 1. Problem

The ingestion pipeline (`docs/superpowers/plans/2026-09-05-egazette-ingestion-pipeline.md`,
built and merged) originally embedded one notification as one `vector(768)`
row directly on the `notifications` table — matching the spec's original
assumption that "real notifications are short — typically one paragraph"
(`docs/superpowers/specs/2026-09-05-egazette-ux-architecture-design.md`,
§5.4).

A real 4-year backfill (2022–2025, Central Gazette, Ministry of Labour and
Employment) falsified that assumption: 4 of 317 in-scope-checked documents
failed with `400 Bad Request` from the embedding API
(`nvidia/llama-nemotron-embed-vl-1b-v2`). Diagnosed live: one failing
document's extracted text was **190,230 characters (~47,000+ tokens)** —
far beyond the model's documented 8,192-token limit
([NVIDIA NIM docs](https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-embed-vl-1b-v2)).
These are large compiled/multi-entry gazette notifications (1.9MB PDFs),
not the short single-topic notifications the original samples represented.

This design supersedes the "one embedding per notification" assumption in
both the spec and the (unimplemented) Query API plan.

## 2. Decision

**Universal chunking** — every notification is split into one or more
chunks, each independently embedded. A short document (today's common case)
still produces exactly one chunk, so this isn't purely a workaround: it's
a genuine model upgrade. Rejected the narrower "only chunk when too large"
option to avoid maintaining two retrieval code paths (chunked vs.
non-chunked), and because uniform chunking also improves citation precision
for every document, not just the oversized outliers — a match can point to
the specific paragraph that matched instead of a whole-document dump.

## 3. Schema

`notifications` already exists on the live Railway database with
`001_init.sql` applied — this needs a new migration, not an edit to the
applied one:

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

`notifications.operative_text` is untouched — it remains the full,
canonical copy of the document (unchanged from `001_init.sql`), independent
of how it's chunked for embedding/retrieval. Only `embedding` moves off the
parent table. No `ivfflat`/`hnsw` vector index is added, consistent with
the original schema's decision — cosine distance (`<=>`) over an unindexed
column is fine at this corpus size.

## 4. Chunking algorithm

New module, `ingestion/chunking.py`:

```python
def chunk_text(text: str, max_chars: int = 6000, overlap: int = 200) -> list[str]:
```

- Split on paragraph boundaries (`\n\n`) first; greedily pack consecutive
  paragraphs into chunks up to `max_chars`.
- A single paragraph longer than `max_chars` (possible given the
  bilingual/watermark-garbled text already observed in this domain) is
  hard-split at the character limit as a fallback, rather than crashing or
  silently dropping content.
- `overlap` (200 chars) is carried from the end of one chunk into the start
  of the next, so a sentence split across a chunk boundary isn't lost to
  whichever chunk actually gets matched.
- **`max_chars = 6000`** is a deliberately conservative choice: the failing
  document was ~190,230 chars / ~47,000+ tokens, implying roughly 4
  chars/token on this bilingual Hindi/English text. The model's real limit
  is 8,192 tokens (~32,000 chars at that ratio) — 6,000 chars leaves
  substantial margin for tokenization variance (non-English text often
  tokenizes less efficiently per character than English) while still
  producing citation-sized chunks (a few paragraphs, not fragments).
- Pure function — no I/O, no external dependencies — fully unit-testable
  without a database or network call.
- Empty or whitespace-only input returns an empty list (`[]`), not a
  single empty-string chunk — `ingest.py` treats zero chunks as "nothing to
  embed" and calls `insert_chunks` with an empty list, which is a no-op.
  This shouldn't occur in practice (`extractor.py` always sets
  `operative_text = raw_text.strip()` from real PDF content), but the
  function must not crash on it.

## 5. Ingestion changes

`ingestion/storage.py`:
- `insert_notification` drops the `embedding` parameter entirely (embeddings
  no longer live on this table) and returns `(id: int, is_new: bool)`
  instead of just `id`, so callers can tell a genuinely new insert from a
  pre-existing duplicate.
- New `insert_chunks(conn, notification_id: int, chunks: list[tuple[str, list[float]]]) -> None` —
  inserts one row per `(chunk_text, embedding)` pair.

`ingestion/ingest.py`'s `ingest_notification` is restructured:
1. Parse (unchanged) → the existing Labour-Codes filter (`act_reference is
   None` → `OutOfScopeError`, unchanged) runs first, before any embedding
   work, exactly as today.
2. Insert the notification row **first** → get back `(notification_id,
   is_new)`.
3. **Only if `is_new`**: chunk `record.operative_text` via `chunk_text()`,
   call `embed_text()` once per chunk, then `insert_chunks`.

**Side effect worth naming explicitly**: today, `embed_text` is called
*before* the duplicate-check, so re-ingesting an already-present
notification wastes a real embedding API call before the DB dedup silently
discards it. Reordering to insert-then-check-then-embed means a duplicate
now costs one cheap INSERT-that-finds-a-conflict and zero embedding calls —
a real efficiency fix that falls out of the restructuring chunking already
requires, not a separately-requested feature.

## 6. Retrieval design (revises the unimplemented Query API plan)

`docs/superpowers/plans/2026-09-05-egazette-backend-pipeline.md`'s
`hybrid_search` design is revised, not left to conflict with this schema —
the mechanical edit to that plan file is a task in the implementation plan
that follows this spec, not performed during this design.

- Both keyword (Postgres FTS) and vector search now query
  `notification_chunks` joined back to `notifications` for citation
  metadata (`gazette_id`, `part`, `section`, `notification_date`,
  `source_url`) — a **chunk** is the unit that gets matched, a
  **notification** is the unit that gets cited.
- `Citation.passage` becomes the actual matching chunk's text — a specific
  paragraph — instead of the whole-document text. This is a direct quality
  improvement for the Query API's eventual answers, not merely a
  side effect of the schema change.
- **One citation per notification**, keeping only its best-scoring chunk
  when multiple chunks from the same document score well — preserves the
  existing one-passage-per-source `Citation` model
  (`2026-09-05-egazette-ux-architecture-design.md` §4.3) rather than
  expanding scope into multi-passage citations.

## 7. Testing

- `chunking.py`: paragraph-boundary splitting; the hard-split fallback for
  an oversized single paragraph; overlap content actually present at chunk
  boundaries; a short document producing exactly one chunk.
- `storage.py`: `insert_notification` returns `is_new=True` on first insert,
  `is_new=False` on a duplicate; `insert_chunks` inserts the right rows;
  `ON DELETE CASCADE` removes chunks when a notification is deleted.
- `ingest.py`: chunking + per-chunk embedding happens only when
  `is_new=True`; a duplicate notification triggers **zero** `embed_text`
  calls (the efficiency fix from §5, directly testable).

## 8. Re-ingesting existing data

The 6 documents already live in `notifications` were embedded under the old
one-embedding-per-notification schema, which `002_chunking.sql` removes
entirely (the `embedding` column is dropped). There is no in-place migration
path for old embeddings into the new chunk shape. Simplest correct approach:
clear `notifications`/`notification_chunks` and re-run the existing backfill
CLI (`ingestion/cli.py --start-year 2022 --end-year 2025`) once this ships —
chunking is deterministic per document, and `file_hash`-based idempotency is
unchanged, so this is a clean re-run, not a special migration script.

## 9. Non-goals

- No change to `extractor.py` (frozen, validated handoff file) — chunking
  only affects what gets embedded, not how structured fields are extracted
  from the full raw text.
- No multi-passage citations (one citation per notification, per §6).
- No `ivfflat`/`hnsw` vector index — unnecessary at this corpus size (§3).
- No structural (Section/Clause-boundary-aware) chunking — rejected in
  favor of the simpler, more robust paragraph/size-based approach (see the
  approaches comparison this design was approved against); the existing
  regex-based structure extraction in `extractor.py` already captures
  Part/Section/act_reference at the notification level, which is what
  citations need — chunking doesn't need to re-derive that.
