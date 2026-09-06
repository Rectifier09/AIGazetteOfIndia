# e-Gazette Design System

**Status:** Draft — awaiting review
**Date:** 2026-09-06

## 1. Relationship to the UX architecture spec

This extends `docs/superpowers/specs/2026-09-05-egazette-ux-architecture-design.md`
§4.10 (Visual & brand direction), which locked the *register* — "trustworthy
& official," not "modern & approachable" — but left it as one paragraph of
direction rather than a real system. Nothing here changes any decision from
that spec's §4.1–§4.9 (card layout, answer/refusal/error/loading states,
history/persistence, input behavior, mobile reflow) or its non-negotiables
(§1). This document is the missing systematic layer underneath §4.10: exact
color tokens, a type scale, a spacing scale, and component-state rules that
a frontend implementation can build directly against.

Developed via interactive visual brainstorming (mockup comparisons, not just
text descriptions) — see `.superpowers/brainstorm/1919-1788696785/content/`
in this worktree for the actual comparison screens this was decided against,
if the reasoning behind a specific choice needs to be re-examined later.

## 2. Starting point and the one deliberate reopening

§4.10's original two constraints — one restrained accent on white/off-white,
serif headers + sans body, monospace citations, no mascot/illustration —
are all carried forward unchanged. The brainstorm additionally pulled in
selected *mechanics* from Apple's design system (spacing/type discipline,
restrained color, precise component treatment) without adopting its
consumer-brand *voice* (all-sans-serif, hero photography, big marketing
type). One specific piece of that brand voice — dropping the serif header
entirely — was explicitly considered and explicitly rejected: it was the
one change that would have reversed §4.10's original "reads as document,
not consumer chatbot" reasoning, and that reasoning still holds. Everything
else adopted from Apple's system (rounded/glass surfaces, a bigger type
scale, a dedicated external-link color, more generous whitespace) is
additive polish, not a register change.

## 3. Color tokens

| Token | Value | Usage |
|---|---|---|
| `--color-accent` | `#1B3A5B` (deep blue) | Header text, question headers, banner icon/border tint, focus rings, primary button background |
| `--color-link-external` | `#0071E3` | "View original PDF" and any other link that leaves the site — deliberately distinct from `--color-accent` so an outbound link is visually recognizable at a glance, independent of hover state |
| `--color-refusal` | `#B8860B` (muted amber) | Refusal card accent (spec §4.4) — desaturated, not alarm-bright |
| `--color-error` | `#A13B3B` (muted red) | Error card accent (spec §4.5) — desaturated, not alarm-bright |
| `--color-bg` | `#FBFBFA` | Page background |
| `--color-bg-banner` | `rgba(238, 242, 246, 0.7)` + `backdrop-filter: blur(6px)` | Scope banner surface (frosted-glass treatment) |
| `--color-bg-citation` | `#F5F4EF` | Citation block background |
| `--color-text-primary` | `#171717` | Question text, primary answer body text |
| `--color-text-secondary` | `#4A4A44` | Citation block text |
| `--color-text-muted` | `#9A9A94` | Disclaimer text, secondary metadata |
| `--color-border` | `#EAE8E1` | Header underline, card dividers |

Deep blue was chosen over the alternative deep green candidate (`#1F4B3F`)
after a direct side-by-side in the answer-card mockup — both were viable
("official" registers either way), blue was the more decisive preference.

## 4. Typography

**One type family, three cuts** — IBM Plex Serif, IBM Plex Sans, IBM Plex
Mono — chosen over Georgia+system-sans and Source Serif 4+Inter
specifically because a single family across all three roles keeps the
letterforms visually related (shared proportions, shared design language)
while still giving each role — heading, body, citation — a distinct enough
treatment to read as intentional, not accidental. All three cuts are
open-source (SIL Open Font License), so there's no licensing cost or
restriction.

| Role | Family | Weight |
|---|---|---|
| Headers, question text | IBM Plex Serif | 600 (semibold) |
| Body text, UI chrome | IBM Plex Sans | 400 (regular), 500 (medium for links/labels) |
| Citation blocks | IBM Plex Mono | 400 (regular) |

**Type scale:**

| Token | Size | Line-height | Usage |
|---|---|---|---|
| `--text-xs` | 11.5px | 1.4 | Disclaimer, fine print |
| `--text-sm` | 12.5px | 1.55 | Scope banner body, citation metadata line, link labels |
| `--text-base-mono` | 12px | 1.6 | Citation block quoted text |
| `--text-base` | 15px | 1.65 | Answer body text |
| `--text-lg` | 18px | 1.4 | Question headers, page/app header |

Sizes and line-heights are deliberately larger and airier than the
original one-paragraph §4.10 implied (which didn't specify numbers) — this
is the Apple-mechanics influence: the brainstorm's side-by-side comparison
showed the larger scale reading as more considered/less dense without
sacrificing the "document" register, since it's paired with serif headers
and monospace citations rather than an all-sans treatment.

## 5. Spacing & radius scale

| Token | Value |
|---|---|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-7` | 28px |

Card internal padding: `--space-6`/`--space-7` (26–28px) — noticeably more
generous than a typical dense web-app card, per the Apple-whitespace
ingredient adopted in the brainstorm.

| Token | Value | Usage |
|---|---|---|
| `--radius-sm` | 8px | Small UI elements |
| `--radius-md` | 12px | Citation blocks |
| `--radius-lg` | 20px | Scope banner (pill-style, per the Apple rounded-surface ingredient) |

## 6. Iconography

**Lucide** (MIT-licensed line icons) for every functional icon — info (scope
banner), warning triangle (refusal/error), external-link arrow (outbound
citation links). Default size 16px inline with text, 20px standalone.
Consistent with §4.10's "no mascot, no illustration, small functional line
icons only."

## 7. Component states

These weren't each individually walked through in the visual brainstorm
(only the base/default treatment of the answer card was mocked up
interactively) — they're proposed here as the direct, consistent extension
of the tokens above, following standard accessible interaction patterns.
Flag any of these specifically if they need their own mockup pass before
implementation.

- **Buttons** (e.g. "Ask", "Try again" in the error card):
  - Default: `--color-accent` background, white text, `--radius-sm`.
  - Hover: background darkened ~10% (`#152E48`).
  - Active/pressed: background darkened ~18% (`#0F2436`).
  - Focus (keyboard nav): 2px `--color-accent` ring, 2px offset — never
    rely on color change alone for focus, per WCAG 2.1 non-text contrast.
  - Disabled: 40% opacity, no hover/active response, `cursor: not-allowed`.
- **Links** (both `--color-accent` in-page links and `--color-link-external`
  outbound links):
  - Default: underline always present (not hover-only) — this product's
    "trustworthy & official" register favors clarity over minimalism here.
  - Hover: no color change; underline weight increases slightly (visual
    acknowledgment without relying on color, which also keeps behavior
    consistent for colorblind users).
- **Input field** (the pinned bottom input bar, spec §4.8):
  - Default: 1px `--color-border`, `--radius-sm`, `--color-bg` background.
  - Focus: border becomes `--color-accent`, same 2px ring treatment as
    buttons for consistency.
  - No error state needed — the input never validates client-side; a
    failed question surfaces via the error card (spec §4.5), not inline
    field validation.

## 8. Explicitly out of scope for v1

- **Dark mode.** The original UX spec never called for it, and citation
  legibility (monospace source-text blocks) is a more important constraint
  for this product than offering a dark theme — one fully-tuned light
  theme beats two half-tuned ones at this stage. Revisit only if user
  feedback specifically asks for it.
- **Illustration, hero imagery, product photography** — explicitly rejected
  per §4.10's original reasoning (playful/consumer register mismatch), and
  nothing in this brainstorm reopened that.
- **The full Apple brand voice** (all-sans-serif, marketing-scale
  typography) — considered directly, explicitly not adopted; see §2.

## 9. Open questions

- The component-states in §7 are proposed, not independently visually
  validated — worth a quick pass once real interactive components exist
  (hover/focus states are hard to fully judge from a static mockup).
- Font-loading strategy (self-hosted IBM Plex webfonts vs. Google Fonts CDN
  vs. `next/font` optimization) isn't decided — this is an implementation
  detail for the frontend plan, not a design-system decision, but should be
  resolved there before the first `next/font` setup.
