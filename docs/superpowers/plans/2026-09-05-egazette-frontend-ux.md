# e-Gazette Frontend UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js chat-style UI — a single page of stacked Q&A cards with always-visible citations, persisted history, and the four card states (answer/refusal/error/loading) — that consumes the backend's `POST /ask` API.

**Architecture:** A single-page Next.js app (`app/page.tsx`) holds the card list in React state, persists it to `localStorage` with a session-boundary divider, and renders each card through one `QACard` component with a `variant` prop covering all four states. No routing, no auth, no server-side rendering of dynamic content — this is a client-heavy single page by design (spec §4.1).

**Tech Stack:** Next.js 15 (App Router) + TypeScript + Tailwind CSS, Jest + React Testing Library for component tests, deployed to Vercel.

**Spec:** `docs/superpowers/specs/2026-09-05-egazette-ux-architecture-design.md`

## Global Constraints

- No login, no accounts — history persists via `localStorage` only (spec §4.7), never cookies.
- Citations are **always visible** in an answer card, never collapsed behind a click (spec §4.3).
- Every answer card shows the fixed disclaimer text supplied by the API response's `disclaimer` field (spec §4.3) — never hardcode a different wording client-side.
- Restored history (above the session divider) is reference-only and must never be sent as `history` in a new `POST /ask` call — only same-visit cards count as context (spec §4.7).
- History cap: last ~50 exchanges or 30 days, pruning oldest first (spec §4.7).
- "View original PDF" always links out to the official source in a new tab — never an in-app PDF viewer (spec §4.3).
- Visual direction follows `docs/superpowers/specs/2026-09-06-egazette-design-system.md` in full — not spec §4.10's original one-paragraph placeholder. Concrete values: accent `#1B3A5B` (deep blue); IBM Plex Serif (headers/questions, 600 weight) + IBM Plex Sans (body/UI, 400/500) + IBM Plex Mono (citations, 400) as one family in three cuts; Lucide icons only — **no emoji anywhere in production UI**, including loading-state and disclaimer icons (the original UX spec's inline "🔍"/"✎"/"⚠" characters were a placeholder written before the design system existed and must not ship); full glassmorphism — header, pinned input bar, answer card, and citation block are all frosted-glass surfaces (`rgba(251,251,250,0.72)` general surface, `rgba(245,244,239,0.45)` citation surface, both with `backdrop-filter: blur(...)`) — a deliberate risk acceptance on citation legibility, made after seeing the trade-off directly, not an oversight; radius scale `--radius-sm` 8px / `--radius-md` 12px (citation blocks) / `--radius-lg` 20px (scope banner, pill-style) / `--radius-xl` 14px (header, input bar, card container); light mode only, no dark mode for v1.
- Deployment: Vercel (spec's open deployment-split item — resolved here; backend is a separate Railway service per the backend plan).

---

## File Structure

```
frontend/
  package.json
  tailwind.config.ts
  app/
    layout.tsx
    page.tsx
    globals.css
  components/
    ScopeBanner.tsx
    QACard.tsx
    InputBar.tsx
  lib/
    types.ts
    api.ts
    history.ts
  __tests__/
    history.test.ts
    api.test.ts
    QACard.test.tsx
    ScopeBanner.test.tsx
    InputBar.test.tsx
    page.test.tsx
```

---

### Task 1: Scaffold Next.js + Tailwind, deploy target

**Files:**
- Create: `frontend/` (via `create-next-app`)
- Create: `frontend/lib/types.ts`

**Interfaces:**
- Produces: `Citation`, `AskResponse`, `QACardData` types from `frontend/lib/types.ts`, used by every later task.

- [ ] **Step 1: Scaffold the app**

Run:
```bash
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*"
cd frontend && npm install --save-dev jest @testing-library/react @testing-library/jest-dom jest-environment-jsdom
```

- [ ] **Step 2: Configure Jest**

```js
// frontend/jest.config.js
const nextJest = require('next/jest')
const createJestConfig = nextJest({ dir: './' })
module.exports = createJestConfig({
  testEnvironment: 'jest-environment-jsdom',
  setupFilesAfterEach: ['@testing-library/jest-dom'],
})
```

Add to `frontend/package.json` scripts: `"test": "jest"`.

- [ ] **Step 3: Write the shared types (matches the backend's `AskResponse`/`Citation` exactly — see backend plan Task 2)**

```typescript
// frontend/lib/types.ts
export interface Citation {
  source: string;
  gazette_id: string | null;
  part: string | null;
  section: string | null;
  notification_date: string | null;
  passage: string;
  source_url: string | null;
}

export interface AskResponse {
  answer: string;
  refused: boolean;
  citations: Citation[];
  disclaimer: string;
}

export type CardStatus = "loading-searching" | "loading-drafting" | "answered" | "refused" | "error";

export interface QACardData {
  id: string;
  question: string;
  status: CardStatus;
  answer?: string;
  citations?: Citation[];
  disclaimer?: string;
  isHistorical: boolean; // true = restored from a prior visit, above the session divider
}
```

- [ ] **Step 4: Verify the scaffold builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with the default Next.js starter page.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "Scaffold Next.js+Tailwind frontend, add shared types"
```

---

### Task 2: API client

**Files:**
- Create: `frontend/lib/api.ts`
- Test: `frontend/__tests__/api.test.ts`

**Interfaces:**
- Consumes: `AskResponse` type (Task 1); backend `POST /ask` contract (backend plan Task 7).
- Produces: `askQuestion(question: string, history: {question: string, answer: string}[]) -> Promise<AskResponse>` from `frontend/lib/api.ts`, used by `page.tsx` (Task 6).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/__tests__/api.test.ts
import { askQuestion } from '@/lib/api'

describe('askQuestion', () => {
  beforeEach(() => {
    global.fetch = jest.fn()
  })

  it('posts the question and history, returns the parsed response', async () => {
    const mockResponse = {
      answer: 'Yes, in force.',
      refused: false,
      citations: [{ source: 'gujarat', gazette_id: 'Gujarat-Extra-62', part: 'Part IV-A', section: null, notification_date: '20th May, 2026', passage: '...', source_url: null }],
      disclaimer: 'This is not legal advice — verify against the original Gazette.',
    }
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    })

    const result = await askQuestion('Is it in force in Gujarat?', [])

    expect(result).toEqual(mockResponse)
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/ask'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ question: 'Is it in force in Gujarat?', history: [] }),
      })
    )
  })

  it('throws when the response is not ok', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({ ok: false, status: 500 })
    await expect(askQuestion('anything', [])).rejects.toThrow()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npm test -- api.test.ts`
Expected: FAIL — `Cannot find module '@/lib/api'`

- [ ] **Step 3: Implement `api.ts`**

```typescript
// frontend/lib/api.ts
import type { AskResponse } from './types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function askQuestion(
  question: string,
  history: { question: string; answer: string }[]
): Promise<AskResponse> {
  const response = await fetch(`${API_URL}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history }),
  })
  if (!response.ok) {
    throw new Error(`Ask request failed: ${response.status}`)
  }
  return response.json()
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npm test -- api.test.ts`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/__tests__/api.test.ts
git commit -m "Add API client for POST /ask"
```

---

### Task 3: localStorage history with session-boundary logic

**Files:**
- Create: `frontend/lib/history.ts`
- Test: `frontend/__tests__/history.test.ts`

**Interfaces:**
- Consumes: `QACardData` type (Task 1).
- Produces: `loadHistory() -> QACardData[]` (marks every loaded card `isHistorical: true`), `saveHistory(cards: QACardData[]) -> void` (prunes to last 50 or 30 days before saving), `clearHistory() -> void`, `getSessionDividerLabel() -> string` (e.g. `"New session · 5 September 2026"`) from `frontend/lib/history.ts`, used by `page.tsx` (Task 6).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/__tests__/history.test.ts
import { loadHistory, saveHistory, clearHistory, getSessionDividerLabel } from '@/lib/history'
import type { QACardData } from '@/lib/types'

const card = (id: string, isHistorical = false): QACardData => ({
  id, question: `Q${id}`, status: 'answered', answer: 'A', citations: [], disclaimer: 'd', isHistorical,
})

describe('history persistence', () => {
  beforeEach(() => localStorage.clear())

  it('returns an empty array when nothing is stored', () => {
    expect(loadHistory()).toEqual([])
  })

  it('round-trips saved cards and marks them historical on load', () => {
    saveHistory([card('1'), card('2')])
    const loaded = loadHistory()
    expect(loaded).toHaveLength(2)
    expect(loaded.every((c) => c.isHistorical)).toBe(true)
  })

  it('prunes to the most recent 50 exchanges', () => {
    const many = Array.from({ length: 60 }, (_, i) => card(String(i)))
    saveHistory(many)
    expect(loadHistory()).toHaveLength(50)
    expect(loadHistory()[0].id).toBe('10') // oldest 10 dropped
  })

  it('clearHistory empties storage', () => {
    saveHistory([card('1')])
    clearHistory()
    expect(loadHistory()).toEqual([])
  })

  it('getSessionDividerLabel includes today\'s date', () => {
    const label = getSessionDividerLabel()
    expect(label).toMatch(/New session/)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npm test -- history.test.ts`
Expected: FAIL — `Cannot find module '@/lib/history'`

- [ ] **Step 3: Implement `history.ts`**

```typescript
// frontend/lib/history.ts
import type { QACardData } from './types'

const STORAGE_KEY = 'egazette_history'
const MAX_EXCHANGES = 50
const MAX_AGE_DAYS = 30

export function loadHistory(): QACardData[] {
  const raw = localStorage.getItem(STORAGE_KEY)
  const savedAt = Number(localStorage.getItem(`${STORAGE_KEY}_savedAt`) || 0)
  const ageMs = Date.now() - savedAt
  if (!raw || (savedAt > 0 && ageMs > MAX_AGE_DAYS * 24 * 60 * 60 * 1000)) return []
  const cards: QACardData[] = JSON.parse(raw)
  return cards.map((c) => ({ ...c, isHistorical: true }))
}

export function saveHistory(cards: QACardData[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cards.slice(-MAX_EXCHANGES)))
  localStorage.setItem(`${STORAGE_KEY}_savedAt`, String(Date.now()))
}

export function clearHistory(): void {
  localStorage.removeItem(STORAGE_KEY)
  localStorage.removeItem(`${STORAGE_KEY}_savedAt`)
}

export function getSessionDividerLabel(): string {
  const today = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })
  return `New session · ${today}`
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npm test -- history.test.ts`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/history.ts frontend/__tests__/history.test.ts
git commit -m "Add localStorage history with pruning and session-divider label"
```

---

### Task 4: `ScopeBanner` component

**Files:**
- Create: `frontend/components/ScopeBanner.tsx`
- Test: `frontend/__tests__/ScopeBanner.test.tsx`

**Interfaces:**
- Produces: `<ScopeBanner collapsed={boolean} onClearHistory={() => void} exampleQuestions={string[]} onExampleClick={(q: string) => void} />` from `frontend/components/ScopeBanner.tsx`, used by `page.tsx` (Task 6).

- [ ] **Step 1: Install `lucide-react`** (first task in this plan that needs an icon — installed here rather than in Task 1, matching the install-when-first-needed pattern this plan already uses for `uuid` in Task 7)

Run: `cd frontend && npm install lucide-react`

- [ ] **Step 2: Write the failing test**

```tsx
// frontend/__tests__/ScopeBanner.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import ScopeBanner from '@/components/ScopeBanner'

const examples = ['Is the Code on Wages in force in Gujarat?', 'What does section 56 say?']

describe('ScopeBanner', () => {
  it('shows full scope text and example chips when not collapsed', () => {
    render(<ScopeBanner collapsed={false} onClearHistory={jest.fn()} exampleQuestions={examples} onExampleClick={jest.fn()} />)
    expect(screen.getByText(/Code on Wages/i)).toBeInTheDocument()
    expect(screen.getByText(examples[0])).toBeInTheDocument()
  })

  it('shows a compact one-line strip when collapsed', () => {
    render(<ScopeBanner collapsed={true} onClearHistory={jest.fn()} exampleQuestions={examples} onExampleClick={jest.fn()} />)
    expect(screen.queryByText(examples[0])).not.toBeInTheDocument()
  })

  it('clicking an example chip calls onExampleClick with that question', () => {
    const onExampleClick = jest.fn()
    render(<ScopeBanner collapsed={false} onClearHistory={jest.fn()} exampleQuestions={examples} onExampleClick={onExampleClick} />)
    fireEvent.click(screen.getByText(examples[0]))
    expect(onExampleClick).toHaveBeenCalledWith(examples[0])
  })

  it('clicking Clear history calls onClearHistory', () => {
    const onClearHistory = jest.fn()
    render(<ScopeBanner collapsed={false} onClearHistory={onClearHistory} exampleQuestions={examples} onExampleClick={jest.fn()} />)
    fireEvent.click(screen.getByText(/clear history/i))
    expect(onClearHistory).toHaveBeenCalled()
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npm test -- ScopeBanner.test.tsx`
Expected: FAIL — `Cannot find module '@/components/ScopeBanner'`

- [ ] **Step 4: Implement `ScopeBanner.tsx`** — glass surfaces and the accent-tinted `Info` icon per the design system (`docs/superpowers/specs/2026-09-06-egazette-design-system.md`), not plain white/emoji

```tsx
// frontend/components/ScopeBanner.tsx
'use client'

import { Info } from 'lucide-react'

interface ScopeBannerProps {
  collapsed: boolean
  onClearHistory: () => void
  exampleQuestions: string[]
  onExampleClick: (question: string) => void
}

export default function ScopeBanner({ collapsed, onClearHistory, exampleQuestions, onExampleClick }: ScopeBannerProps) {
  if (collapsed) {
    return (
      <div className="flex justify-between items-center gap-3 px-4 py-2 mx-3 my-2 text-sm text-[#33475b] bg-[rgba(238,242,246,0.72)] backdrop-blur-md rounded-full">
        <span className="flex items-center gap-2">
          <Info size={16} className="text-accent shrink-0" />
          Covers: Code on Wages · Industrial Relations Code · OSH Code · Code on Social Security — Central &amp; Gujarat Gazette only
        </span>
        <button onClick={onClearHistory} className="underline text-neutral-500 hover:text-neutral-800 shrink-0">Clear history</button>
      </div>
    )
  }

  return (
    <div className="px-4 py-4 mx-3 my-3 bg-[rgba(238,242,246,0.72)] backdrop-blur-md rounded-lg">
      <p className="text-sm text-[#33475b] flex gap-2">
        <Info size={16} className="text-accent shrink-0 mt-0.5" />
        <span>
          Covers: Code on Wages · Industrial Relations Code · OSH Code · Code on Social Security
          <br />
          Sources: Central Gazette + Gujarat Gazette
        </span>
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {exampleQuestions.map((q) => (
          <button
            key={q}
            onClick={() => onExampleClick(q)}
            className="text-sm border border-neutral-300 rounded-full px-3 py-1 hover:bg-white/50"
          >
            {q}
          </button>
        ))}
      </div>
      <button onClick={onClearHistory} className="mt-3 text-sm underline text-neutral-500 hover:text-neutral-800">
        Clear history
      </button>
    </div>
  )
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd frontend && npm test -- ScopeBanner.test.tsx`
Expected: PASS (4 passed) — the test file itself needs no changes; it asserts on text content and click behavior, both unchanged by the glass/icon styling.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/components/ScopeBanner.tsx frontend/__tests__/ScopeBanner.test.tsx
git commit -m "Add ScopeBanner component with collapse and example chips"
```

---

### Task 5: `QACard` component (all four states)

**Files:**
- Create: `frontend/components/QACard.tsx`
- Test: `frontend/__tests__/QACard.test.tsx`

**Interfaces:**
- Consumes: `QACardData` type (Task 1).
- Produces: `<QACard data={QACardData} onRetry={(id: string) => void} />` from `frontend/components/QACard.tsx`, used by `page.tsx` (Task 6). Visually distinct per `status`: `loading-searching`/`loading-drafting` show progress text, `answered` shows citation block + disclaimer, `refused` shows the refusal message plainly, `error` shows a retry button.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/__tests__/QACard.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import QACard from '@/components/QACard'
import type { QACardData } from '@/lib/types'

const base: QACardData = { id: '1', question: 'Is it in force in Gujarat?', status: 'answered', isHistorical: false }

describe('QACard', () => {
  it('shows the searching indicator while loading-searching', () => {
    render(<QACard data={{ ...base, status: 'loading-searching' }} onRetry={jest.fn()} />)
    expect(screen.getByText(/searching/i)).toBeInTheDocument()
  })

  it('shows the drafting indicator while loading-drafting', () => {
    render(<QACard data={{ ...base, status: 'loading-drafting' }} onRetry={jest.fn()} />)
    expect(screen.getByText(/drafting/i)).toBeInTheDocument()
  })

  it('shows the answer, an always-visible citation, and the disclaimer when answered', () => {
    render(
      <QACard
        data={{
          ...base,
          status: 'answered',
          answer: 'Yes, it is in force.',
          citations: [{ source: 'gujarat', gazette_id: 'Gujarat-Extra-62', part: 'Part IV-A', section: null, notification_date: '20th May, 2026', passage: 'quoted text', source_url: 'https://example.gov.in/doc.pdf' }],
          disclaimer: 'This is not legal advice — verify against the original Gazette.',
        }}
        onRetry={jest.fn()}
      />
    )
    expect(screen.getByText('Yes, it is in force.')).toBeInTheDocument()
    expect(screen.getByText(/Gujarat-Extra-62/)).toBeInTheDocument()
    expect(screen.getByText(/not legal advice/i)).toBeInTheDocument()
    expect(screen.getByText(/View original PDF/i)).toHaveAttribute('href', 'https://example.gov.in/doc.pdf')
    expect(screen.getByText(/View original PDF/i)).toHaveAttribute('target', '_blank')
  })

  it('shows the refusal message when refused', () => {
    render(<QACard data={{ ...base, status: 'refused', answer: "I couldn't find a notification matching this." }} onRetry={jest.fn()} />)
    expect(screen.getByText(/couldn't find/i)).toBeInTheDocument()
  })

  it('shows a retry button on error and calls onRetry with the card id', () => {
    const onRetry = jest.fn()
    render(<QACard data={{ ...base, status: 'error' }} onRetry={onRetry} />)
    fireEvent.click(screen.getByText(/try again/i))
    expect(onRetry).toHaveBeenCalledWith('1')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npm test -- QACard.test.tsx`
Expected: FAIL — `Cannot find module '@/components/QACard'`

- [ ] **Step 3: Implement `QACard.tsx`** — glass card and citation surfaces, IBM Plex Mono citations, and Lucide icons in place of every emoji character (design-system spec, not the older plain-Tailwind/emoji sketch)

```tsx
// frontend/components/QACard.tsx
'use client'

import { Search, PenLine, TriangleAlert, ExternalLink } from 'lucide-react'
import type { QACardData } from '@/lib/types'

interface QACardProps {
  data: QACardData
  onRetry: (id: string) => void
}

export default function QACard({ data, onRetry }: QACardProps) {
  const borderClass =
    data.status === 'error' ? 'border-[#A13B3B]/40' : data.status === 'refused' ? 'border-[#B8860B]/40' : 'border-white/60'

  return (
    <div
      className={`border ${borderClass} rounded-xl p-6 mb-3 bg-[rgba(251,251,250,0.72)] backdrop-blur-md ${data.isHistorical ? 'opacity-60' : ''}`}
    >
      <p className="font-serif font-semibold text-lg mb-2">Q: {data.question}</p>

      {data.status === 'loading-searching' && (
        <p className="text-neutral-500 flex items-center gap-2">
          <Search size={16} /> Searching Central &amp; Gujarat notifications…
        </p>
      )}
      {data.status === 'loading-drafting' && (
        <p className="text-neutral-500 flex items-center gap-2">
          <PenLine size={16} /> Drafting answer from matching notification(s)
        </p>
      )}

      {data.status === 'refused' && <p>{data.answer}</p>}

      {data.status === 'error' && (
        <div>
          <p className="text-[#A13B3B] flex items-center gap-2">
            <TriangleAlert size={16} /> Something went wrong answering this.
          </p>
          <button onClick={() => onRetry(data.id)} className="mt-2 underline text-[#A13B3B]">Try again</button>
        </div>
      )}

      {data.status === 'answered' && (
        <div>
          <p className="text-[15px] mb-4">{data.answer}</p>
          {data.citations?.map((c, i) => (
            <div
              key={i}
              className="font-mono text-xs bg-[rgba(245,244,239,0.45)] backdrop-blur-sm border border-white/40 rounded-md p-3 mb-2"
            >
              <p>Source: {c.source === 'central' ? 'Central Gazette' : 'Gujarat Government Gazette'} · {c.gazette_id} · {c.part}{c.section ? ` · ${c.section}` : ''} · {c.notification_date}</p>
              <p className="italic mt-1">&quot;{c.passage}&quot;</p>
              {c.source_url && (
                <a
                  href={c.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 underline text-[#0071E3] font-sans not-italic mt-1"
                >
                  View original PDF <ExternalLink size={12} />
                </a>
              )}
            </div>
          ))}
          <p className="text-[#9a9a94] text-xs mt-2 flex items-center gap-2">
            <TriangleAlert size={14} className="text-[#B8860B]" /> {data.disclaimer}
          </p>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npm test -- QACard.test.tsx`
Expected: PASS (5 passed) — the test file needs no changes; every assertion matches on text content (e.g. `/searching/i`, `/View original PDF/i`) which Testing Library resolves against the element's aggregate text, unaffected by an adjacent icon SVG contributing no text nodes.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/QACard.tsx frontend/__tests__/QACard.test.tsx
git commit -m "Add QACard component covering loading/answered/refused/error states"
```

---

### Task 6: `InputBar` component

**Files:**
- Create: `frontend/components/InputBar.tsx`
- Test: `frontend/__tests__/InputBar.test.tsx`

**Interfaces:**
- Produces: `<InputBar onSubmit={(question: string) => void} prefill={string} />` from `frontend/components/InputBar.tsx`, used by `page.tsx` (Task 7). `prefill` lets the `ScopeBanner`'s example chips populate the input without auto-submitting (spec §4.8).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/__tests__/InputBar.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import InputBar from '@/components/InputBar'

describe('InputBar', () => {
  it('submits the typed question on Enter and clears the input', () => {
    const onSubmit = jest.fn()
    render(<InputBar onSubmit={onSubmit} prefill="" />)
    const textbox = screen.getByRole('textbox')
    fireEvent.change(textbox, { target: { value: 'Is it in force?' } })
    fireEvent.keyDown(textbox, { key: 'Enter', shiftKey: false })
    expect(onSubmit).toHaveBeenCalledWith('Is it in force?')
    expect((textbox as HTMLTextAreaElement).value).toBe('')
  })

  it('does not submit on Shift+Enter', () => {
    const onSubmit = jest.fn()
    render(<InputBar onSubmit={onSubmit} prefill="" />)
    const textbox = screen.getByRole('textbox')
    fireEvent.change(textbox, { target: { value: 'line one' } })
    fireEvent.keyDown(textbox, { key: 'Enter', shiftKey: true })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('populates from prefill without auto-submitting', () => {
    const onSubmit = jest.fn()
    render(<InputBar onSubmit={onSubmit} prefill="Example question?" />)
    expect(screen.getByRole('textbox')).toHaveValue('Example question?')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('clicking Ask submits the current value', () => {
    const onSubmit = jest.fn()
    render(<InputBar onSubmit={onSubmit} prefill="" />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'typed question' } })
    fireEvent.click(screen.getByText('Ask'))
    expect(onSubmit).toHaveBeenCalledWith('typed question')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npm test -- InputBar.test.tsx`
Expected: FAIL — `Cannot find module '@/components/InputBar'`

- [ ] **Step 3: Implement `InputBar.tsx`** — the bar itself is a glass surface; the text field inside it is a distinct, slightly-more-opaque surface so the typing area stays visually separable from the glass bar around it (design-system spec §7)

```tsx
// frontend/components/InputBar.tsx
'use client'

import { useEffect, useState } from 'react'

interface InputBarProps {
  onSubmit: (question: string) => void
  prefill: string
}

export default function InputBar({ onSubmit, prefill }: InputBarProps) {
  const [value, setValue] = useState(prefill)

  useEffect(() => setValue(prefill), [prefill])

  function submit() {
    if (!value.trim()) return
    onSubmit(value)
    setValue('')
  }

  return (
    <div className="sticky bottom-0 p-3 flex gap-2 bg-[rgba(251,251,250,0.75)] backdrop-blur-md border-t border-white/50">
      <textarea
        role="textbox"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="Ask a question..."
        rows={1}
        className="flex-1 bg-white/60 border border-neutral-300 rounded-sm px-3 py-2 resize-none"
      />
      <button onClick={submit} className="bg-accent text-white rounded-sm px-4 py-2">Ask</button>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npm test -- InputBar.test.tsx`
Expected: PASS (4 passed) — the test file needs no changes; `role="textbox"` and the "Ask" button text are unchanged.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/InputBar.tsx frontend/__tests__/InputBar.test.tsx
git commit -m "Add InputBar with Enter/Shift+Enter and prefill support"
```

---

### Task 7: Wire it all together in `page.tsx`

**Files:**
- Modify: `frontend/app/page.tsx`
- Test: `frontend/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: `askQuestion` (Task 2), `loadHistory`/`saveHistory`/`clearHistory`/`getSessionDividerLabel` (Task 3), `ScopeBanner` (Task 4), `QACard` (Task 5), `InputBar` (Task 6).
- Produces: the assembled page — no further task consumes this; it's the integration point.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/__tests__/page.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Page from '@/app/page'
import * as api from '@/lib/api'

jest.mock('@/lib/api')

describe('Page', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  it('asking a question renders a loading state then the answered card, and only same-session history is sent as context', async () => {
    ;(api.askQuestion as jest.Mock).mockResolvedValue({
      answer: 'Yes.', refused: false,
      citations: [{ source: 'gujarat', gazette_id: 'Gujarat-Extra-62', part: 'Part IV-A', section: null, notification_date: '20th May, 2026', passage: 'x', source_url: null }],
      disclaimer: 'not legal advice',
    })

    render(<Page />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Is it in force?' } })
    fireEvent.click(screen.getByText('Ask'))

    expect(screen.getByText(/searching/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Yes.')).toBeInTheDocument())
    expect(api.askQuestion).toHaveBeenCalledWith('Is it in force?', [])
  })

  it('restored historical cards render above a session divider and are not sent as history context', async () => {
    localStorage.setItem(
      'egazette_history',
      JSON.stringify([{ id: 'old1', question: 'Old question?', status: 'answered', answer: 'Old answer', citations: [], disclaimer: 'd', isHistorical: false }])
    )
    ;(api.askQuestion as jest.Mock).mockResolvedValue({ answer: 'New answer', refused: false, citations: [], disclaimer: 'd' })

    render(<Page />)
    expect(screen.getByText(/New session/i)).toBeInTheDocument()
    expect(screen.getByText('Old question?')).toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New question?' } })
    fireEvent.click(screen.getByText('Ask'))
    await waitFor(() => expect(api.askQuestion).toHaveBeenCalled())

    expect(api.askQuestion).toHaveBeenCalledWith('New question?', [])
  })

  it('clicking Clear history removes stored cards', () => {
    localStorage.setItem('egazette_history', JSON.stringify([{ id: 'old1', question: 'Old?', status: 'answered', isHistorical: false }]))
    render(<Page />)
    fireEvent.click(screen.getByText(/clear history/i))
    expect(localStorage.getItem('egazette_history')).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npm test -- page.test.tsx`
Expected: FAIL — the default scaffolded page doesn't render a textbox/Ask button.

- [ ] **Step 3: Implement `page.tsx`**

```tsx
// frontend/app/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { v4 as uuidv4 } from 'uuid'
import ScopeBanner from '@/components/ScopeBanner'
import QACard from '@/components/QACard'
import InputBar from '@/components/InputBar'
import { askQuestion } from '@/lib/api'
import { loadHistory, saveHistory, clearHistory, getSessionDividerLabel } from '@/lib/history'
import type { QACardData } from '@/lib/types'

const EXAMPLE_QUESTIONS = [
  'Is the Code on Wages in force in Gujarat?',
  'Which notification amended a prior rule?',
  'When does a rule take effect?',
]

export default function Page() {
  const [historicalCards, setHistoricalCards] = useState<QACardData[]>([])
  const [sessionCards, setSessionCards] = useState<QACardData[]>([])
  const [prefill, setPrefill] = useState('')

  useEffect(() => {
    setHistoricalCards(loadHistory())
  }, [])

  useEffect(() => {
    if (sessionCards.length > 0) {
      saveHistory([...historicalCards, ...sessionCards])
    }
  }, [sessionCards])

  async function handleSubmit(question: string) {
    const id = uuidv4()
    setSessionCards((prev) => [...prev, { id, question, status: 'loading-searching', isHistorical: false }])

    const historyContext = sessionCards
      .filter((c) => c.status === 'answered')
      .map((c) => ({ question: c.question, answer: c.answer! }))

    try {
      setSessionCards((prev) => prev.map((c) => (c.id === id ? { ...c, status: 'loading-drafting' } : c)))
      const response = await askQuestion(question, historyContext)
      setSessionCards((prev) =>
        prev.map((c) =>
          c.id === id
            ? { ...c, status: response.refused ? 'refused' : 'answered', answer: response.answer, citations: response.citations, disclaimer: response.disclaimer }
            : c
        )
      )
    } catch {
      setSessionCards((prev) => prev.map((c) => (c.id === id ? { ...c, status: 'error' } : c)))
    }
  }

  function handleRetry(id: string) {
    const card = sessionCards.find((c) => c.id === id)
    if (card) handleSubmit(card.question)
  }

  function handleClearHistory() {
    clearHistory()
    setHistoricalCards([])
  }

  const allCards = [...historicalCards, ...sessionCards]

  return (
    <main className="max-w-2xl mx-auto flex flex-col h-screen bg-[#FBFBFA]">
      <header className="sticky top-0 z-10 px-4 py-3 bg-[rgba(251,251,250,0.72)] backdrop-blur-md border-b border-white/50">
        <h1 className="font-serif text-lg text-accent">
          AI Gazette of India <span className="font-sans text-sm font-normal opacity-50">· Labour Codes</span>
        </h1>
      </header>
      <ScopeBanner
        collapsed={allCards.length > 0}
        onClearHistory={handleClearHistory}
        exampleQuestions={EXAMPLE_QUESTIONS}
        onExampleClick={setPrefill}
      />
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {historicalCards.length > 0 && (
          <>
            {historicalCards.map((c) => <QACard key={c.id} data={c} onRetry={handleRetry} />)}
            <p className="text-center text-xs text-neutral-400 my-3">── {getSessionDividerLabel()} ──</p>
          </>
        )}
        {sessionCards.map((c) => <QACard key={c.id} data={c} onRetry={handleRetry} />)}
      </div>
      <InputBar onSubmit={handleSubmit} prefill={prefill} />
    </main>
  )
}
```

- [ ] **Step 4: Install the `uuid` dependency**

Run: `cd frontend && npm install uuid && npm install --save-dev @types/uuid`

- [ ] **Step 5: Run to verify it passes**

Run: `cd frontend && npm test -- page.test.tsx`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: all tests across every task pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/page.tsx frontend/__tests__/page.test.tsx frontend/package.json frontend/package-lock.json
git commit -m "Wire ScopeBanner, QACard, InputBar, API client, and history into page.tsx"
```

---

### Task 8: Design system tokens (fonts, color, radius scale)

**Files:**
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/app/layout.tsx`

**Interfaces:**
- Consumes: nothing new. Tasks 4–7 already wrote every component's markup and Tailwind classes directly against the design system's real values (glass surfaces, IBM Plex font-family names, accent/citation colors, `rounded-sm`/`md`/`lg`/`xl` radius classes) — none of that is a placeholder waiting on this task. This task's only remaining job is to make those class names actually resolve to the right values: load the three IBM Plex cuts as real fonts (not a fallback), and map the radius/color utility names Tasks 4–7 already used to the design system's exact token values.
- Produces: no new prop/interface — wires `next/font/google` + `tailwind.config.ts` so `font-serif`/`font-sans`/`font-mono`/`bg-accent`(-adjacent literals)/`rounded-sm`/`rounded-md`/`rounded-lg`/`rounded-xl` resolve correctly everywhere they're already used.

- [ ] **Step 1: Load IBM Plex Serif, Sans, and Mono via `next/font/google`** — one family, three cuts, per the design system (not Fraunces/Inter, which were an earlier, pre-design-system placeholder pairing)

```tsx
// frontend/app/layout.tsx
import { IBM_Plex_Serif, IBM_Plex_Sans, IBM_Plex_Mono } from 'next/font/google'
import './globals.css'

const plexSerif = IBM_Plex_Serif({ subsets: ['latin'], weight: ['600'], variable: '--font-serif' })
const plexSans = IBM_Plex_Sans({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-sans' })
const plexMono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400'], variable: '--font-mono' })

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${plexSerif.variable} ${plexSans.variable} ${plexMono.variable}`}>
      <body className="font-sans bg-[#FBFBFA] text-[#171717]">{children}</body>
    </html>
  )
}
```

- [ ] **Step 2: Wire the font variables, accent color, and radius scale into Tailwind config**

```typescript
// frontend/tailwind.config.ts
import type { Config } from 'tailwindcss'

export default {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        serif: ['var(--font-serif)'],
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },
      colors: {
        accent: '#1B3A5B',
      },
      borderRadius: {
        sm: '8px',
        md: '12px',
        lg: '20px',
        xl: '14px',
      },
    },
  },
} satisfies Config
```

`rounded-sm`/`md`/`lg`/`xl` now resolve to the design system's exact scale everywhere Tasks 4, 5, and 6 already used them (input field, citation blocks, scope banner, card/header/input-bar containers respectively) — no component file changes needed here, only this config.

- [ ] **Step 3: Manually verify in a browser**

Run: `cd frontend && npm run dev`
Expected: confirm at `localhost:3000` — IBM Plex Serif on question headers and the site title, IBM Plex Sans on body text, IBM Plex Mono on citation blocks, deep-blue `#1B3A5B` accent on the "Ask" button and header title, glass/frosted surfaces visible on the header, scope banner, cards, citation blocks, and the pinned input bar.

- [ ] **Step 4: Run the full test suite to confirm the config change didn't break behavior**

Run: `cd frontend && npm test`
Expected: all tests still pass (tests assert on text/roles, not class names or fonts).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/layout.tsx frontend/tailwind.config.ts
git commit -m "Wire IBM Plex fonts and design-system color/radius tokens into Tailwind config"
```

---

### Task 9: Mobile responsiveness

**Files:**
- Modify: `frontend/components/ScopeBanner.tsx`
- Test: `frontend/__tests__/ScopeBanner.test.tsx` (extend)

**Interfaces:**
- Consumes/Produces: extends `ScopeBanner`'s existing props (Task 4) with tap-to-expand behavior on the collapsed strip — no new external interface, `collapsed`/`onClearHistory`/`exampleQuestions`/`onExampleClick` unchanged.

- [ ] **Step 1: Write the failing test for tap-to-expand**

```tsx
// add to frontend/__tests__/ScopeBanner.test.tsx
it('tapping the collapsed strip expands it to show example chips', () => {
  render(<ScopeBanner collapsed={true} onClearHistory={jest.fn()} exampleQuestions={examples} onExampleClick={jest.fn()} />)
  fireEvent.click(screen.getByText(/Covers:/i))
  expect(screen.getByText(examples[0])).toBeInTheDocument()
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npm test -- ScopeBanner.test.tsx`
Expected: FAIL — clicking the collapsed strip currently does nothing.

- [ ] **Step 3: Implement tap-to-expand as internal state** — layered onto Task 4's glass-pill collapsed strip, not the older plain-Tailwind version

```tsx
// frontend/components/ScopeBanner.tsx — replace the collapsed branch
'use client'
import { useState } from 'react'
import { Info } from 'lucide-react'

// ...inside the component, before the collapsed check:
const [expanded, setExpanded] = useState(false)

if (collapsed && !expanded) {
  return (
    <div className="flex justify-between items-center gap-3 px-4 py-2 mx-3 my-2 text-sm text-[#33475b] bg-[rgba(238,242,246,0.72)] backdrop-blur-md rounded-full">
      <button onClick={() => setExpanded(true)} className="flex items-center gap-2 text-left">
        <Info size={16} className="text-accent shrink-0" />
        Covers: Code on Wages · Industrial Relations Code · OSH Code · Code on Social Security — Central &amp; Gujarat Gazette only
      </button>
      <button onClick={onClearHistory} className="underline text-neutral-500 hover:text-neutral-800 shrink-0">Clear history</button>
    </div>
  )
}
```

The full (non-collapsed, or collapsed-and-expanded) branch renders unchanged from Task 4 — `collapsed && !expanded` is the only new condition; `!collapsed || expanded` falls through to the existing example-chip block. The `Info` import moves up to join the existing `'use client'`/`useState` imports at the top of the file rather than living twice in the same file.

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npm test -- ScopeBanner.test.tsx`
Expected: PASS (6 passed — 5 from Task 4 plus this one)

- [ ] **Step 5: Manually verify mobile reflow**

Run: `cd frontend && npm run dev`, open Chrome DevTools device toolbar at a 375px width viewport, confirm cards go full-width with no horizontal scroll and the input bar stays pinned to the bottom of the viewport.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/ScopeBanner.tsx frontend/__tests__/ScopeBanner.test.tsx
git commit -m "Add tap-to-expand for the collapsed scope banner on mobile"
```

---

## Self-Review Notes

- **Spec coverage:** §4.1–4.2 (stacked cards, layout) → Tasks 5, 7. §4.3 (always-visible citation, link-out PDF) → Task 5. §4.4/4.5 (refusal/error cards) → Task 5. §4.6 (two-step loading) → Tasks 5, 7. §4.7 (localStorage, session divider, fresh-context rule, clear control, cap) → Tasks 3, 7 — the `page.test.tsx` "restored historical cards... not sent as history context" test directly verifies the fresh-context rule. §4.8 (input interaction, chips, multi-turn) → Tasks 6, 7. §4.9 (mobile) → Task 9. §4.10 / the full `2026-09-06-egazette-design-system.md` (visual tone, color tokens, type scale, glassmorphism, iconography) → Tasks 4, 5, 6, 7 (baked directly into each component's real markup and classes, revised 2026-09-06 against the actual design-system spec rather than the original placeholder pairing) plus Task 8 (fonts + Tailwind token wiring so those classes resolve correctly).
- **Placeholder scan:** no TBD/TODO. Caught during self-review: Task 3's original `saveHistory` had a dead-code age-pruning branch (`filter` predicate always `true`) — fixed in place so `loadHistory` gates on the real `_savedAt` timestamp instead. Caught during the 2026-09-06 design-system revision: the original Task 8 used `#1E3A5F` for the accent color and Fraunces/Inter fonts — both were an earlier placeholder guess made before the design-system brainstorm settled on the real values (`#1B3A5B`, IBM Plex) — corrected throughout Tasks 4–8, not just in Task 8's own code block.
- **Type consistency:** `QACardData`/`Citation`/`AskResponse` defined once in `lib/types.ts` (Task 1) and used identically across `api.ts`, `history.ts`, `QACard.tsx`, and `page.tsx`. `askQuestion`'s signature matches exactly between its Task 2 test, its Task 2 implementation, and its Task 7 call site in `page.tsx`. `lucide-react` is installed once, in Task 4 (first consumer), and imported identically (`import { X } from 'lucide-react'`) in Tasks 4, 5, and 9 — no duplicate install steps.
