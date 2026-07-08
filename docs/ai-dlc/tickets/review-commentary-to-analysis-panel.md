# Tickets — Move AI game commentary into the Analysis panel

Spec: `docs/ai-dlc/specs/review-commentary-to-analysis-panel.md`
One logical change; small. Best done as a single commit, but split for clarity.
All tickets touch single-owner hotspots (index.html, app.js, review.js) — one
owner, do sequentially (T1→T4), no parallelism.

## T1 — Restructure the Analysis panel markup (`static/index.html`)
- Remove `#review-narrative` from `#review-bar` (line ~175).
- Wrap `.eval-block` + `.quality-block` + `.best-block` in
  `<div class="analysis-eval-col">`, inside a new
  `<div class="analysis-eval-row">`, and add `#review-narrative` (with its
  existing classes + `hidden`) as the second child of the row.
- **Done when:** markup parses; `#review-narrative` appears exactly once and is a
  child of `.analysis-eval-row`, not `#review-bar`.
- Depends on: none.

## T2 — Two-column layout CSS (`static/style.css`)
- Add `.analysis-eval-row` (flex, flex-wrap, gap, align-items:flex-start), the
  narrative column rule (flex:1 1 240px; min-width:0), and `.analysis-eval-col`
  **as a column flexbox with `gap: var(--space-5)`** — this re-supplies the
  vertical rhythm the eval blocks lose when nested (refuter high finding; without
  it Evaluation/Last move/Best now collapse to zero spacing). Tokens only.
- `review.css`: **no change expected** — the old separation came from `#review-bar`
  gap + `#review-game-summary` border, not `.review-narrative` itself. Touch only
  if the browser check shows a real gap. Keep `.review-narrative[hidden]{display:none}`.
- **Done when:** at 1920px the narrative sits right of the eval readouts with the
  three eval blocks still evenly spaced; when hidden the eval column fills the row
  (no leftover gap); AA contrast preserved.
- Depends on: T1.

## T3 — Hide narrative on review exit (`static/app.js`)
- In `showReviewUI(on)`, add `if (!on) byId('review-narrative').hidden = true;`
  (narrative no longer inherits `#review-bar`'s hidden).
- **Done when:** exiting review via Return-to-my-game AND via tab-switch both
  clear the commentary from the Analysis panel; play-mode load shows no
  commentary. (Confirm which exit paths call `showReviewUI(false)` — see refuter;
  if any path bypasses it, hide there too.)
- Depends on: T1.

## T4 — Fix stale comment (`static/review.js`)
- Update the `renderNarrativePanel` header comment (`:852-854`) — narrative now
  lives in the Analysis panel, no longer a sibling of `#review-game-summary`.
- **Done when:** comment matches reality; no logic change.
- Depends on: none (do with T1).

## Verify (whole change) — per spec "Verify-by"
- `.venv/bin/python -m pytest -q` green; `.venv/bin/ruff check app tests` clean.
- Playwright-MCP at 1920px: Generate commentary → renders right of eval, fills
  space; narrow → stacks below; Return to game → gone; re-open → back; center
  card shows only title + accuracy.

## Refuter verdict (folded)
- Baseline green: `pytest` 719 passed, `ruff` clean. Backend unaffected.
- HIDE-ON-EXIT sound: `exitReview()` is the single choke point for every exit
  path (Return button, tab-switch via requestModeExit→ensurePlay, entering
  another special mode). `#review-narrative` ships `hidden` in raw markup →
  hidden on initial play-mode load. T3 fix is correct and sufficient.
- SHOW-ON-ENTER: no conflict — `openGame()` calls `renderNarrativePanel()` after
  `showReviewUI(true)`; the `if(!on)` line only touches the off branch.
- FLEX empty-child, duplicate-id, cross-module import, focus-visible: all clean.
- **HIGH (fixed in T2):** `.analysis-eval-col` must add
  `display:flex; flex-direction:column; gap:var(--space-5)` — else eval blocks
  lose their spacing.
- **LOW (fixed in spec):** review.css needs no change; separation was structural.
