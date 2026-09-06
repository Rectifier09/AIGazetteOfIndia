# e-Gazette Conversational Search — UX & Architecture Design

**Status:** Draft — awaiting review
**Date:** 2026-09-05

## 1. Product summary

"Ask the Gazette" instead of searching it. A conversational-search product over
India's official Government Gazette. Locked scope for this build (see
`Vault/Projects/AIGazetteOfIndia/Product/AIGazetteOfIndia-MVP-Solution-Context-and-Approach.md`
for the full original solution-space doc, and the handed-off
`PROJECT_CONTEXT_AND_BUILD_PLAN.md` for the locked MVP scope this design
implements):

- **Domain:** Labour Codes rollout tracking — Code on Wages (2019), Industrial
  Relations Code (2020), OSH Code (2020), Code on Social Security (2020).
- **Sources — exactly two:** Central Gazette (egazette.gov.in, Ministry of
  Labour & Employment) and Gujarat Government Gazette (Labour, Skill
  Development & Employment Department). No other ministries, no other states.
- **Language:** English only for v1.
- **Non-negotiable product requirements** (unchanged from the locked scope):
  1. Every substantive answer cites a real passage (Gazette ID, Part/Section,
     source URL) **or** explicitly says it couldn't find one.
  2. A persistent "not legal advice — verify against the original Gazette"
     disclaimer appears with every answer.
  3. Confidence-based refusal: if retrieval doesn't surface a genuinely
     matching passage, the system declines rather than guesses.
- **Locked target queries** (the acceptance test): "Is [Code] in force in
  Gujarat?" / "What does [provision] say?" / "Which notification amended
  [provision]?" / "When does [rule] take effect?" / "Show me the source for
  that answer."

## 2. Target users & deployment target

Dual audience on one product surface, not two modes: HR/compliance
professionals (need precision, comfortable with legal register) and general
public / journalists (need plain language). Same answer format serves both —
see §4.3.

Deployed for **~20 real users** as a real, running service — not a local-only
CLI prototype and not a one-off throwaway. This shaped the architecture
decisions in §5 (Postgres over SQLite, a real deployed stack) even though 20
users is still small enough that most "scale" infrastructure (queues,
microservices, a graph database) is explicitly out of scope — see §5.5.

## 3. What changed from the original build plan

The original `PROJECT_CONTEXT_AND_BUILD_PLAN.md` (Phase 7) called for "a CLI
or a short script... no UI investment until the retrieval/generation loop is
proven." This design **supersedes that sequencing** — building the real
web UI and the backend together, rather than CLI-first. Locked scope,
non-negotiables, data model, and `extractor.py` are all carried over
unchanged; only the "ship a CLI first" step is skipped.

## 4. UX design

### 4.1 Overall shape: stacked Q&A cards

One continuously scrolling page — not chat bubbles, not a separate
landing/chat page split. Each question becomes a card (bold question header,
answer, citation, disclaimer); new questions append new cards below. Chosen
over a ChatGPT-style bubble thread because bubble UIs compress citation
blocks awkwardly and read more casual/consumer than the "trustworthy &
official" tone this product needs (§4.10). Closest reference point:
Perplexity's answer-card pattern.

### 4.2 Page layout

```
┌────────────────────────────────────────────────┐
│  AI Gazette of India · Labour Codes             │  ← header, minimal
├────────────────────────────────────────────────┤
│  ℹ Covers: Code on Wages · Industrial Relations │  ← persistent scope banner,
│    Code · OSH Code · Code on Social Security    │    full-size before the first
│    Sources: Central Gazette + Gujarat Gazette   │    question, collapses to a
│                                                  │    one-line strip afterward
├────────────────────────────────────────────────┤
│  [ Q&A card 1 ]                                 │  ← scrollable card stream,
│  [ Q&A card 2 ]                                 │    grows downward
│  [ Q&A card 3 ]                                 │
├────────────────────────────────────────────────┤
│  [ Ask a question...                    ] [Ask] │  ← input bar, pinned to bottom
└────────────────────────────────────────────────┘
```

No sidebar, no nav, no hamburger menu — single-purpose tool, one screen's
worth of functionality on both desktop and mobile (§4.9).

### 4.3 Answer card anatomy

Citations are **always visible**, not collapsed behind a click — chosen over
a "plain answer + expandable evidence" pattern specifically because this
product serves both a citizen who wants plain language and a compliance
professional who needs the citation trail every time; hiding it by default
would under-serve the second audience.

```
┌────────────────────────────────┐
Q: Is the Code on Wages in force
   in Gujarat?

Yes — Gujarat notified the
appointing authority for the Code
on Wages, 2019 on 20 May 2026.

Source: Gujarat Govt Gazette
Extra No. 62 · Part IV-A · 20 May 2026
"...the Government of Gujarat hereby
appoints the person specified..."
[ View original PDF → ]

⚠︎ Not legal advice — verify against
   the original Gazette
└────────────────────────────────┘
```

"View original PDF" links **out** to the official source (egazette.gov.in or
the Gujarat portal) in a new tab — not an in-app PDF viewer. Keeps the
government site as the authoritative source of truth and avoids hosting/
redistributing gazette PDFs ourselves.

### 4.4 Refusal card

Distinct from both a normal answer and an error (§4.5). Plain refusal plus a
reminder of what IS in scope, turning a dead end into guidance:

```
Q: What's the minimum wage in Delhi?

I couldn't find a notification
matching this in the sources I
cover (Central Gazette + Gujarat
Gazette, Labour Codes only).

I can answer questions about:
Code on Wages · Industrial Relations
Code · OSH Code · Code on Social
Security — as notified centrally or
in Gujarat.
```

### 4.5 Error card (distinct from refusal)

Refusal is a *product* outcome (retrieval genuinely found nothing). This
covers actual failures — network drop, backend/LLM error, timeout — which
need a visually distinct treatment (e.g. warning-toned border, vs. neutral
for refusal, vs. none for a normal answer) so a user scrolling past can tell
"nothing matched" apart from "something broke":

```
Q: Is the Code on Wages in force in Gujarat?

⚠ Something went wrong answering this.
  [ Try again ]
```

- **Try again** re-runs that specific question in place, not a full retype.
- No auto-retry — a silent retry loop is worse than a clear failure with a
  manual retry.
- The question is preserved even on failure (never dropped from the
  localStorage history in §4.7).

### 4.6 Loading / in-flight state

RAG retrieval + generation takes a few seconds, not instant. The in-flight
card shows two progressive states rather than a blank spinner, in place
(the final card replaces this with no layout jump):

```
🔍 Searching Central & Gujarat notifications…
        ↓  (once retrieval returns)
✎ Drafting answer from 1 matching notification
```

The input bar stays enabled throughout — a user can queue a next question,
which sends after the current one resolves, rather than the whole UI locking.

### 4.7 History & persistence

No login, no accounts — history persists via **`localStorage`**, not cookies
(cookies are capped at ~4KB total per domain and ride along on every HTTP
request, a poor fit for growing conversation data; localStorage is
client-only, ~5-10MB, and never leaves the browser).

- On load, prior history restores above a visible divider:
  `── New session · <today's date> ──`.
- Only cards **below** the current divider count as live follow-up context
  for the current visit. Restored cards above it are reference-only, not
  silently reused as context for a new question — because this is a live,
  moving domain (rollout status changes over time) and reusing stale context
  could bias a new answer toward an outdated framing.
- A **"Clear history"** control near the scope banner wipes localStorage.
- Default cap: last ~50 exchanges or 30 days, pruning oldest first.

### 4.8 Input area & interaction

- Single-line input that grows for longer questions, pinned to the bottom of
  the viewport.
- Enter submits; Shift+Enter inserts a newline.
- Scope-banner example questions are clickable chips that populate the input
  (not auto-submit) — editable before sending.
- Full multi-turn conversation within a session: follow-ups ("What about the
  OSH Code?") naturally reference prior questions/answers in the same visit,
  including the locked target query "Show me the source for that answer."

### 4.9 Mobile behavior

Direct reflow of the same single-column layout, not a separate design:
full-width cards with tighter padding, the scope banner becomes tap-to-expand
to save vertical space, citation blocks and the "View original PDF" link
behave identically to desktop.

### 4.10 Visual & brand direction

"Trustworthy & official," not "modern & approachable" — chosen because this
product cites government law for both a compliance professional and a
citizen, and needs to read as credible rather than like a consumer chatbot
toy.

- **Palette:** one restrained accent (deep blue or deep green) on a neutral
  white/off-white background. Refusal uses muted amber, error uses muted red
  — both desaturated, not alarm-bright.
- **Typography:** serif/slab-serif for questions and headers (reads as
  "document"), clean sans-serif for body/UI chrome.
- **Citation blocks** use a monospace/condensed treatment, visually marking
  them as quoted source material distinct from the generated plain-language
  answer.
- No mascot, no illustration, no decorative iconography beyond small
  functional line icons — a deliberate contrast with the playful
  mascot-driven style of EducatorsLearningPlatform/SahajAiVidya, since the
  audience and register here are different.

## 5. Architecture

### 5.1 Stack

- **Frontend:** Next.js + Tailwind. Chosen because the UX in §4 (in-place
  progressive loading, distinct per-outcome card styling, session-boundary
  rendering, input queuing) needs real component state, not server-rendered
  templates — and it matches the stack already proven on
  EducatorsLearningPlatform.
- **Backend is split into two independent packages, sharing only the
  database** (decided 2026-09-05, so ingestion could start running in the
  background while the rest of the app is built, rather than being coupled to
  the API server's build/deploy lifecycle):
  - **Ingestion pipeline** (`ingestion/`): a standalone Python utility — own
    `requirements.txt`, own venv, zero import dependency on the API — that
    wraps `extractor.py` directly (extend, don't rewrite — already validated
    against 3 real notifications, see `output.json`), discovers and downloads
    Gazette PDFs, embeds them, and writes to Postgres. Runs via a CLI
    (`python cli.py --start-year Y --end-year Y`), safe to background and
    leave running. See
    `docs/superpowers/plans/2026-09-05-egazette-ingestion-pipeline.md`.
  - **Query API** (`backend/`): FastAPI, read-only against the same Postgres
    — no `extractor.py`, no write path, no `/ingest` endpoint. See
    `docs/superpowers/plans/2026-09-05-egazette-backend-pipeline.md`.
- **Database:** **Postgres on Railway** (managed add-on), not SQLite. SQLite
  was the original build-plan choice for a single-process CLI prototype; a
  deployed service fielding concurrent requests from 20 real people needs
  proper concurrent connections and managed backups instead of a file on a
  volume. The `notifications` / `relationships` table shapes are unchanged
  from the original data model — this is a swap of engine, not schema.
- **Vector search: `pgvector` extension on the same Postgres instance** — no
  separate vector database service. See §5.4 for the reasoning and the
  trade-off explicitly accepted.
- **Embeddings + generation:** Gemini API for both, behind a swappable
  provider layer (same pattern as the Gemini-primary/Groq-fallback adapter in
  EducatorsLearningPlatform) so the project isn't hard-locked to one vendor.
  Embedding model: **`gemini-embedding-001`** (text-only; confirmed free tier
  as of 2026-09-05 per Google's own pricing page — not `text-embedding-004`,
  reportedly deprecated). Exact RPM/TPM/RPD quotas aren't published as fixed
  numbers — Google ties them to account usage tier — so verify live at
  `aistudio.google.com/rate-limit` against the actual key before building
  ingestion, same lesson as the free-tier model churn already hit in
  EducatorsLearningPlatform.

### 5.2 Data model (carried over, unchanged)

```
NotificationRecord:
  source, gazette_id, gazette_type, part, section, issuing_authority,
  notification_number, notification_date, act_reference, signatory,
  operative_text, embedding (new — vector(N), populated at ingestion)
  relationships: [Relationship]

Relationship:
  rel_type ("issued_under" | "supersedes" | "amends"), target (text)
```

Storage layering (from the original solution doc, unchanged): RAW (original
PDF) → PROCESSED (extracted text) → STRUCTURED (Gazette/Part/Section/
Notification/Clause/Entity/Relationship) → INDEXED (keyword + vector).

### 5.3 Why relationships are relational rows, not a graph database

**Explicitly rejected: Neo4j / any graph database.** Recorded here because it
was a live consideration this session, not just a default:

- The locked non-goals already list "a complete knowledge graph" as
  out-of-scope for v1 — Neo4j is infrastructure in service of a model already
  ruled out.
- Every relationship in the validated sample data (`output.json`) points to
  exactly one target (e.g. S.O. 2457(E) supersedes S.O. No. 2765(E)) — no
  question in this domain requires multi-hop graph traversal.
- At the scale of two sources and four labour codes, relationship lookups are
  `SELECT * FROM relationships WHERE target LIKE '%X%'` — one SQL query, not
  a graph-traversal problem.
- Introducing a database technology the project hasn't used, under a tight
  timeline, for zero required capability, is pure added risk.

### 5.4 Retrieval: hybrid keyword + vector

**Vector search was initially recommended against** (added engineering
surface — an embedding step at ingestion, embedding the query at retrieval,
a fusion/rerank step — working against a product whose central promise is
"never hallucinate, always cite or refuse," at a corpus size small enough
that keyword search alone can nearly brute-force the whole corpus). **The
call was made to build it anyway**, accepting that risk, because the
product's core hypothesis is that users describe what they need in their own
words without knowing official terminology — a gap pure keyword matching can
miss and vector similarity is well-suited to close. Recorded here as a
deliberate, informed trade-off rather than an oversight.

Given that decision, the design is:

- **Chunking:** one embedding per notification for v1 (real notifications are
  short — typically one paragraph of operative text per the samples) — no
  sub-clause chunking yet.
  **Superseded** by `docs/superpowers/specs/2026-09-06-notification-chunking-design.md`,
  which introduces multi-chunk embedding per notification.
- **Retrieval:** Postgres full-text search (on `operative_text`,
  `act_reference`, `notification_number`) and pgvector cosine similarity
  search run in parallel; results merged via **reciprocal rank fusion** (a
  simple, well-established way to combine two ranked lists without extra
  ML/tuning).
- **No separate query-expansion LLM call.** An earlier version of this design
  included one (rewrite a plain-language question into keyword search terms
  before hitting Postgres FTS). That step is dropped now that vector search
  exists: embedding the raw question already captures the semantic-match job
  query expansion was meant to do, and Postgres FTS runs directly against the
  raw question text. One fewer moving part, one fewer LLM call per question.
- **Confidence-based refusal** is keyed off the vector similarity score — a
  score floor below which the system refuses. This is one place the
  vector-search bet pays off directly: a similarity score is a materially
  better refusal signal than a keyword-match count alone.

### 5.5 What's explicitly still NOT being built (unchanged from the locked
scope, reaffirmed against the "20 users, build it to scale" framing)

All Gazette documents / all ministries / all state gazettes · Hindi-language
content · re-ranking beyond RRF · alerts, subscriptions, personalization ·
accounts/login (history is localStorage-only, see §4.7) · a complete
knowledge graph (§5.3) · multi-agent architecture · microservices, queues, or
Kubernetes · automatic legal advice or interpretation · numeric eval scoring
thresholds. 20 real users does not change any of these — "build the
foundation right" means picking Postgres and a clean provider-abstraction
layer, not adding infrastructure with no corresponding need.

### 5.6 LLM call inventory (every place the system calls an LLM)

Two stages only:

1. **Ingestion time** (per notification, when a Gazette document is first
   processed — scales with corpus size, not user traffic): **one embedding
   call** (Gemini) to populate the `embedding` column. Structured field
   extraction (`gazette_id`, `part`, `section`, `notification_number`,
   `act_reference`, `signatory`) and relationship extraction (`amends`/
   `supersedes`/`issued_under`) are **regex-based in `extractor.py`, not an
   LLM call** — deliberate, so structuring can't hallucinate a wrong Gazette
   ID or invent a relationship that isn't there. This boundary is
   load-bearing for the product's no-hallucination commitment and should not
   be crossed later without a specific reason.
2. **Query time** (per end-user question — scales with the 20 users' actual
   usage): **one embedding call** (embed the question, for the vector side of
   hybrid retrieval) + **one generation call** (retrieved passages + question
   → grounded answer, with citation-or-refusal enforced). Two LLM-adjacent
   calls per question, not three — see §5.4 for why query-expansion was
   dropped.

## 6. Evaluation approach (carried over, unchanged)

10–15 test questions, including the 5 locked target queries (§1), written
**before** running the system and not edited after seeing outputs. Human
checks each answer against the source PDF. No numeric pass/fail threshold for
v1 — pass/fail judged per-question.

## 7. Open questions / risks carried forward

- **OCR spot-check** (original build-plan Phase 0) — whether native-text PDF
  extraction is sufficient across ~15 real notifications from both sources —
  is still unconfirmed. This design assumes it resolves clean (no OCR needed
  for v1); if it doesn't, extraction and possibly chunking need revisiting.
- **RESOLVED (2026-09-05) — Central Gazette discovery/acquisition
  mechanism**, confirmed against the live site: session-in-URL bootstrap
  (`GET /` → 302 to a fresh `(S(...))/default.aspx`), a `Referer`-checked
  navigation chain (`default.aspx` → `SearchMenu.aspx` → `SearchMinistry.aspx`),
  then an ASP.NET WebForms postback (`__VIEWSTATE`/`__EVENTVALIDATION`/
  `hidden1` replayed each request) selecting `ddlMinistry=28` for "Ministry of
  Labour and Employment" (**not `163002`** — that value, taken from a pasted
  URL, was stale/wrong) plus `ddlmonth`/`ddlyear` (search is month+year
  granularity only, no free date range). Results render inline as a
  `GridView` table including a plain-text Gazette ID column (e.g.
  `CG-DL-E-22052025-263307`). **Downloading needs no session at all**: the
  PDF is at the stateless, unauthenticated URL
  `https://egazette.gov.in/WriteReadData/{year}/{trailing-numeric-id-from-
  gazette-id}.pdf` — verified with a bare `curl`, zero cookies, on two
  different Gazette IDs. Gujarat's equivalent access pattern (a separate
  state portal) is still unexplored — this resolves Central only.
- **Reciprocal rank fusion weighting** between keyword and vector results has
  no tuned values yet — will need adjustment once real answers are checked
  against the 15 locked test questions (§6).
- **Vector search was added as an accepted risk**, not a proven-safe choice
  (§5.4) — worth watching closely against the eval set specifically for
  false-confidence cases (a plausible-looking but wrong match surfacing above
  the refusal threshold).
- **The refusal similarity-score floor (§5.4) has no numeric value yet** —
  this is an eval-driven tuning decision, not a UX/architecture one, and
  should be set by running the 15 locked test questions (§6) and checking
  where genuine matches vs. genuine non-matches actually land.
- **Where the frontend and backend services actually run is not yet decided.**
  Postgres-on-Railway (§5.1) is confirmed; whether Next.js deploys to Vercel
  (as EducatorsLearningPlatform does) with FastAPI on Railway, or both
  application services run on Railway together, is still open and should be
  settled in the implementation plan.
