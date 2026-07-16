# Delta spec — Collapsible Analysis-mode panel

**Goal (one line):** a collapsible settings section in the Analysis tab holding
a 3-way analysis-mode selector (Full / Blunders only / Off) and a
win-chances-bar hide toggle — collapsed by default, all states persisted.

Contracts: [`../contracts/analysis-mode-panel.md`](../contracts/analysis-mode-panel.md)
(supersedes parts of [`../contracts/eval-toggle.md`](../contracts/eval-toggle.md) — see
"Contract changes"). Requirements confirmed at Gate 1; **revised 2026-07-15
after dual adversarial review (Claude refuter + Codex Sol)** — revisions
marked ⚠.

## Behavior

### Collapsible panel
- New disclosure section inside `#tab-analysis`, slotted between the existing
  control rows (`.engine-speed-row`, ~`index.html:253`) and
  `.analysis-eval-row` (`index.html:255`).
- Copy the **movelist-toggle pattern** (`index.html:302`, `movelist.js:117-140`,
  `movelist.css:1-54`): full-width `<button aria-expanded>` + rotating lucide
  chevron + `.collapsed` class hiding the body. Header label: "Analysis mode".
- **Collapsed by default**; collapse state persisted (`analysisPanelCollapsed`).
- ⚠ **Collapsed-header status hint**: when the persisted mode ≠ Full, the
  collapsed header must show it (e.g. "Analysis mode · Off") — otherwise a
  persisted frozen panel at boot has no visible cause (Codex #6).
- Visuals reuse existing control-row classes/tokens (`style.css:948-1029`).
  Tokens-only CSS, AA contrast, `:focus-visible` on every interactive control.

### Analysis mode selector (Full / Blunders only / Off)
- 3-way segmented control styled like the engine-speed row.
- **Replaces `#eval-toggle`** (PR #45): remove button markup
  (`index.html:242-243`), CSS (`style.css:1010-1029`), wiring
  (`app.js:1106-1126`). Boolean `evalEnabled` (`app.js:80`) generalizes to
  `analysisMode: 'full' | 'blunders' | 'off'`; **audit every `evalEnabled`
  read** (`app.js:82-93,411,493,543` + any others grep finds) and map:
  `evalEnabled === true` → `analysisMode !== 'off'`.

**Full** — current default behavior, unchanged.

**Off** — PR #45 off semantics preserved:
- gates `shouldAnalyzeMove`/`shouldAnalyzeCursor` (`app.js:82-93`);
- `refreshAnalysis()` freeze-return before render (`app.js:411`);
- `onUserMove` still round-trips `/api/move` for legality; no status flash
  (`app.js:493`);
- switching **to Off** bumps `analysisToken++`.
- ⚠ **Mid-flight race** (Codex blocker): `onUserMove` captures `doAnalyze`
  pre-await (`app.js:489`) but the **render decision at `app.js:543` must read
  the CURRENT `analysisMode`**, not the captured value — switching to Off while
  `/api/move` is in flight must not repaint the frozen panel. (The engine
  request keeps the captured value; only the render gate re-reads.)
- ⚠ **FEN load** (Codex #5): `loadFen()` renders unconditionally
  (`app.js:691`) — gate that render on `analysisMode !== 'off'` (freeze).
  Server-side engine work in `/api/load` (`main.py:363-381`, no analyze flag)
  is a **pre-existing gap, out of scope** — no backend change.

**Blunders only** — engine analyzes every move exactly as Full (same requests,
same speed preset — matched-limit cpLoss contract untouched). Pure display
filter, live play only:
- **Non-blunder move** (quality ∈ best/good/inaccuracy/mistake): panel shows
  eval number/bar/status but no quality badge and no retrospective block;
  no move-list quality dot.
- **Blunder**: full panel — badge, eval, best move, retro — plus move-list dot.
- **Checkmate / Draw** labels render whenever the move was analyzed
  (⚠ scope per Codex #4: subject to the analyze-color skip exactly as today —
  a `doAnalyze:false` move stores no quality in Full mode either; unchanged).
- ⚠ **Book moves stay visible** (badge via `renderBookMovePanel`, `q-book`
  dot): book is theory information, not quality coaching. (Both reviewers
  flagged this as unspecified; decision = visible. Flagged at Gate 2.)

⚠ **Filter mechanism (resolves refuter blocker — this is the design, not a
suggestion):**
- NO module-level flag in `panel.js` — `renderAnalysisPanel` is shared by
  review replay (via `hub.renderAnalysis`, `review.js:728` → `app.js:555`) and
  trap practice (`traps.js:685,693`); a global flag would leak the filter into
  both, violating scope.
- Instead, an app.js helper `analysisOpts(analysis)`: returns
  `{suppressQuality:true, suppressRetro:true}` when `analysisMode==='blunders'`
  and `analysis?.quality` ∉ {`blunder`,`checkmate`,`draw`}; else `{}`. Reads
  current mode at call time (self-heals the mid-flight race for blunders too).
- Thread it at the **play-path call sites only**: inside `applyMoveResponse`
  (`app.js:585` — the real call site; the contract doc's "app.js:556" was the
  wrapper definition, now corrected) and the cursor-0 render in
  `refreshAnalysis` (`app.js:416`). `refreshAnalysis:426` flows through
  `applyMoveResponse` — covered. Review/traps paths untouched; `panel.js`
  needs **no changes** (existing `suppressQuality`/`suppressRetro` seams
  suffice, `panel.js:296-306,337-340`).
- ⚠ **`renderSkipped` retro carry-over** (Codex #3): the analyze-color-skipped
  panel carries the last cached retro (`app.js:571-577`) — in blunders mode,
  drop the carried retro unless `state.moveQuality[pvCursor] === 'blunder'`
  (otherwise a filtered mistake's "should've played" resurfaces after the next
  skipped opponent move).

⚠ **Move-list dots mechanism (resolves refuter major #2):**
- History stays intact: `state.moveQuality` writes (`app.js:527`) unchanged —
  filter at render only.
- `movelist.js` cannot see app.js module state (injected-api invariant). Add
  an **`api.actions.getAnalysisMode()` getter** (do NOT put mode into the
  persisted `state` object) and filter in `render()` (`movelist.js:~41`):
  in blunders mode add `q-*` classes only for
  {`blunder`,`checkmate`,`draw`,`book`}.
- **Re-render wiring**: no existing event fires on a settings change
  (`position:change` emits only at `app.js:296,308,852`). Emit a new
  **`analysis-mode:change`** event on selector change; `movelist.js`
  subscribes alongside its `position:change` listener (`movelist.js:138`).

**Mode switching:**
- ⚠ Any switch **out of Off** (to Full or Blunders) re-runs
  `refreshAnalysis()` to un-freeze (refuter minor: Off→Blunders included).
- Any switch bumps re-render of the move list (event above); switch **to Off**
  bumps `analysisToken++`.
- ⚠ **Play-mode guard** (Codex #2): the catch-up `refreshAnalysis()` runs only
  when live play state is active (guard on the app's play/review mode flag —
  same condition `showReviewUI` keys off), so flipping the selector during
  review replay never re-runs the live engine against play state. (The old
  eval-toggle had this same gap; fix it in the relocation.)

### Win-chances bar toggle
- Toggle row inside the new panel: "Win-chances bar" show/hide.
- Hide `#eval-bar` (`index.html:93-95`, in `.board-wrap`) via a class on the
  container — **not** by skipping `setEvalBar` updates (`panel.js:284` keeps
  running; bar must be current the instant it re-shows; verified: setEvalBar
  writes a CSS custom property, works under `display:none`).
- ⚠ **Mobile layout** (both reviewers): `@media (max-width:560px)` hardcodes
  board width `calc(100vw - 54px)` assuming "14px eval-bar + 8px gap"
  (`style.css:1440-1453`). Add a hidden-state override so the board reclaims
  the 22px (e.g. `.eval-bar-hidden #board { width: calc(100vw - 32px); ... }`)
  — no dead gutter, no overflow. Desktop flex reflow verified safe (no JS
  measures the bar).
- Independent of analysis mode (in Off the bar is frozen; hiding still works).

### Persistence
Shared ui-prefs seam (`prefs.js`, key `chess-training:ui:v1`):
- `analysisMode`: `'full' | 'blunders' | 'off'` (default `'full'`)
- `evalBarHidden`: bool (default `false`)
- `analysisPanelCollapsed`: bool (default `true`)

⚠ **Validation lives at the consumer, not prefs.js** (refuter major #3 —
`readUiPrefs` does zero validation): mirror the `VALID_ENGINE_SPEEDS` pattern
(`app.js:75-77`) with a `VALID_ANALYSIS_MODES` allowlist; coerce the booleans
(`=== true` style). Invalid/corrupt stored values fall back to defaults.

## Contract changes (deliberate)
- **eval-toggle.md contract #6 (session-only) superseded**: `analysisMode`
  persists, including `'off'`. Visible cause = collapsed-header status hint
  (above). Add a superseded-by note to `eval-toggle.md`.
- Boot with persisted `'off'`: init paths already flow through the
  `shouldAnalyze*`/`refreshAnalysis` gates — verify restored-session boot
  renders a calm empty/frozen panel, not an error.

## Files to touch
- `static/index.html` — remove `#eval-toggle`; add collapsible section markup.
- `static/app.js` — `evalEnabled`→`analysisMode` (full audit); `analysisOpts`
  helper + threading at 416/585; render gates at 543/691; `renderSkipped`
  retro gate; selector/bar/collapse wiring; prefs read/write + allowlist;
  `actions.getAnalysisMode()`; emit `analysis-mode:change`; play-mode guard.
- `static/movelist.js` — dot filter via `getAnalysisMode()`; subscribe to
  `analysis-mode:change`.
- `static/style.css` — panel styles, segmented control, `.eval-bar-hidden`
  (incl. mobile media-query override); remove eval-toggle CSS.
- `docs/ai-dlc/contracts/eval-toggle.md` — superseded-by note.
- `docs/ai-dlc/contracts/analysis-mode-panel.md` — citation fixes (Quality
  literal is `models.py:17-19` not analysis.py; play call site is
  `app.js:585` not 556).
- **NOT touched**: `static/panel.js`, `static/review.js`, `static/traps.js`,
  all of `app/`.

## Out of scope
- No backend changes (`app/*` untouched; `/api/load`'s unconditional engine
  run is a pre-existing gap, documented not fixed).
- Review replay and trap-practice rendering unchanged.
- No eval-number suppression in blunders mode.
- No new engine requests, speed presets, or `/api/move` fields.
- No hub `renderAnalysis` signature change.

## Constraints (from profile)
- Frontend modules receive injected `api`; never import from app.js.
- Tokens-only CSS (no raw hex), AA contrast, `:focus-visible`.
- Both `/api/move` evals share one speed preset (unchanged).
- No debug artifacts in commits.

## Verify-by
1. `.venv/bin/python -m pytest -q` green (735 baseline); `.venv/bin/ruff
   check app tests` clean.
2. Browser (Playwright-MCP on live server, or manual):
   a. Analysis tab shows "Analysis mode" section **collapsed**; old
      eval-toggle gone; expand → selector + bar toggle, focus rings present.
   b. Blunders only: reasonable move → no badge, no retro, no dot; eval
      number updates. Hang the queen → Blunder badge + retro + red dot.
      Book move → Book badge + dot still show.
   c. Switch Blunders→Full → dots for earlier moves repaint from stored
      quality (move list re-renders on the event).
   d. Off → panel freezes; move mid-flight + quick switch to Off → panel
      stays frozen (race gate). Off→Blunders → panel catches up without
      needing a move.
   e. Bar toggle → bar hides, board reclaims space at 375px width (no dead
      gutter); re-show → bar current immediately.
   f. Reload → mode, bar visibility, collapse state restored; with mode=Off
      the collapsed header shows the Off hint.
   g. During review replay, flip the selector → no live-engine call fires
      (network tab quiet), replay panel unchanged.
