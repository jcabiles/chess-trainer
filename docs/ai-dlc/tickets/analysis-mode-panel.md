# Tickets — Collapsible Analysis-mode panel

Spec: [`../specs/analysis-mode-panel.md`](../specs/analysis-mode-panel.md).
Sequential T1→T6 (T2–T4 all edit `app.js` — single owner, no parallelism).
One feature branch, one PR; commit per ticket where each stands alone.

## T1 — Panel markup + collapse + styles
Add the collapsible "Analysis mode" section to `#tab-analysis`
(movelist-toggle pattern) with placeholder rows for the selector and bar
toggle; remove `#eval-toggle` markup + CSS; add segmented-control +
`.eval-bar-hidden` styles (incl. the mobile `calc(100vw - 32px)` override).
- **Owns:** `static/index.html`, `static/style.css` (⚠ hotspot: index.html)
- **Accept:** section renders collapsed by default, chevron rotates,
  `aria-expanded` toggles, `:focus-visible` rings on all controls, tokens-only
  CSS, old button gone.
- **Done-condition:** load page → expand/collapse works by mouse + keyboard;
  `grep -c 'eval-toggle' static/index.html static/style.css` → 0.

## T2 — `analysisMode` state + Off semantics + persistence
Replace `evalEnabled` with `analysisMode` (audit every read); wire the 3-way
selector + collapse pref + `VALID_ANALYSIS_MODES` allowlist; preserve Off
semantics incl. `analysisToken++`; add the current-mode render gate at
`app.js:543` (mid-flight race), the `loadFen` render gate (`app.js:691`),
out-of-Off catch-up `refreshAnalysis()` with the play-mode guard, the
`analysis-mode:change` emit, `actions.getAnalysisMode()`, and the
collapsed-header status hint.
- **Owns:** `static/app.js` (⚠ hotspot)
- **Accept:** Full/Off behave exactly as pre-change On/Off; Off persists with
  header hint; mid-flight switch to Off leaves panel frozen; selector flip
  during review fires no engine call.
- **Done-condition:** `grep -c 'evalEnabled' static/app.js` → 0; manual: spec
  Verify-by steps (d), (f), (g).

## T3 — Blunders-only panel filter
Add `analysisOpts(analysis)` helper; thread at `app.js:416` and inside
`applyMoveResponse` (585); gate `renderSkipped`'s carried retro on the carried
move being a blunder. No `panel.js` changes.
- **Owns:** `static/app.js` (sequential after T2)
- **Accept:** non-blunder → no badge/retro, eval visible; blunder → full
  panel; checkmate/draw/book unaffected; traps + review rendering untouched
  (`git diff --stat` shows no panel.js/traps.js/review.js).
- **Done-condition:** manual: spec Verify-by step (b).

## T4 — Blunders-only move-list dots
Filter `q-*` classes in `movelist.js` render via `getAnalysisMode()`
(blunders → only blunder/checkmate/draw/book); subscribe to
`analysis-mode:change` for live re-render.
- **Owns:** `static/movelist.js`
- **Accept:** dots vanish/reappear on mode flip without moving a piece;
  `state.moveQuality` history intact (Full restores all dots).
- **Done-condition:** manual: spec Verify-by step (c).

## T5 — Win-chances bar toggle
Wire the bar toggle: `.eval-bar-hidden` class + `evalBarHidden` pref;
`setEvalBar` keeps updating while hidden.
- **Owns:** `static/app.js` (sequential after T2)
- **Accept:** hide/show instant; re-show reflects current position; 375px
  viewport shows no dead gutter/overflow; persists across reload.
- **Done-condition:** manual: spec Verify-by step (e) + reload check.

## T6 — Docs + verification sweep
Add superseded-by note to `contracts/eval-toggle.md`; run full verify:
pytest + ruff + complete browser pass (Verify-by a–g); update CLAUDE.md only
if a non-obvious rule emerged.
- **Owns:** `docs/ai-dlc/contracts/eval-toggle.md`, verification
- **Accept:** all Verify-by steps pass; no debug artifacts in diff.
- **Done-condition:** `.venv/bin/python -m pytest -q` green;
  `.venv/bin/ruff check app tests` clean; browser checklist recorded in PR.

## Dependencies
T1 → T2 → {T3, T5} → T4 → T6. T3/T5 both edit app.js — keep sequential.
No parallelizable tickets (app.js single-owner dominates); single agent
implements ticket-by-ticket.
