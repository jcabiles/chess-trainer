# Contracts — Analysis-mode settings panel (collapsible toggles)

Scanned 2026-07-15 ahead of the "collapsible Analysis mode panel" feature
(full-analysis toggle · blunder-only mode · hide win-chances bar).
Overlapping docs: [`eval-toggle.md`](eval-toggle.md) (authoritative for the
PR #45 Evaluation On/Off toggle — reuse, don't re-derive),
[`analysis-speed.md`](analysis-speed.md) (/api/move shape, matched-limit cpLoss).

## Existing eval-toggle mechanics (PR #45)

- State `let evalEnabled = true` — `app.js:80`, **session-only by design**
  (eval-toggle.md contract #6).
- Gates: `shouldAnalyzeMove` (`app.js:82-85`), `shouldAnalyzeCursor` (`app.js:87-93`).
- Freeze semantics: `refreshAnalysis()` returns before any render when off
  (`app.js:411`) — leaves last-painted DOM untouched (freeze ≠ renderSkipped).
- `onUserMove` still round-trips `/api/move` for legality when off (`app.js:496`);
  suppresses status flash + post-commit render (`app.js:493,543`).
- Toggle-off bumps `analysisToken++` (`app.js:1123`) so late in-flight responses
  can't un-freeze the panel.
- Markup `#eval-toggle` in `.analyze-color-row` (`index.html:242-243`);
  CSS `style.css:1010-1029`; wiring `app.js:1106-1126`.

## Contracts the new toggles must respect

1. **Suppress-label seam exists**: `renderAnalysisPanel(a, opts)` supports
   `opts.suppressQuality` (badge → `—`, `panel.js:296,304-306`) and
   `opts.suppressRetro` (`panel.js:337-340`). Only caller today:
   `traps.js:685,693`, always both `true`. Natural seam for blunder-mode.
2. **Four render call sites, opts not threaded everywhere**:
   play path `applyMoveResponse` → `renderAnalysis(a)` at `app.js:585` with no
   opts (the wrapper *definition* is `app.js:555`), `traps.js:685,693`,
   `review.js:721,728` via `hub.renderAnalysis(a)` — **hub signature carries no
   opts** (`app.js:965`). A play-path-only opts flag won't reach review replay;
   needs a module-level flag in `panel.js` or an extended hub signature.
3. **Move-list quality dots are a separate unconditional consumer**:
   `state.moveQuality[insertAt]` written from raw server response
   (`app.js:527`); `movelist.js:41` colors cells unconditionally. Panel-only
   suppression leaves the move list fully color-coded — scope decision needed.
4. **Quality literal has 7 values** incl. `checkmate`/`draw`
   (`models.py:17-19`, `QUALITY_ICONS` `panel.js:134-175`; commit `f3ba053`
   made game-enders distinct from blunder). Blunder-mode must state whether
   checkmate/draw stay visible.
5. **Eval-bar update is unconditional**: `setEvalBar(evalBarFill(a))` at
   `panel.js:284`, before any opts check — no existing hide mechanism.
   `#eval-bar` DOM lives in `.board-wrap` next to `#board`
   (`index.html:93-95`), **outside** `#tab-analysis` — control and effect live
   in different page-tree branches (new cross-boundary interaction).
6. **Render-filters need no new engine work or supersede token** — but
   implementing blunder-mode by *skipping* renders reintroduces the
   freeze-vs-renderSkipped ambiguity eval-toggle.md warns about. Filter
   *inside* `renderAnalysisPanel` instead.
7. **Prefs precedent**: shared key `chess-training:ui:v1` (`prefs.js:3`);
   persisted examples `moveListCollapsed` (`movelist.js:124,134`),
   `analyzeColor` (`app.js:72,1086`), `engineSpeed` (`app.js:76-77,1097`);
   eval-toggle deliberately session-only. Each new toggle needs an explicit
   persistence decision.

## Collapsible precedents (pick one, don't invent a third)

- **`movelist-toggle`** (`index.html:302`, `movelist.js:117-140`,
  `movelist.css:1-54`): full-width `<button aria-expanded>` + rotating lucide
  chevron, `.collapsed` class on parent, persisted pref, `:focus-visible`
  outline. Closest sibling — already lives inside `#tab-analysis`.
- **`insights-fam-toggle`** (`insights.js:196-230`, `insights.css:280-311`):
  same conventions, render-tree-scoped.

## Insertion point

`#tab-analysis` spans `index.html:231-314`. Natural slot: between the control
rows (`.analyze-color-row`/`.engine-speed-row`, `index.html:235-253`) and
`.analysis-eval-row` (`index.html:255`). Reuse `.analyze-color-row` /
`.engine-speed-row` / `.eval-label` classes (`style.css:948-1029`).

## Backend

No new fields needed: `/api/move` already has `analyze: bool` + `speed`
(`models.py:135-170`). Server always computes true quality; suppression is
client-side display logic only (keeps `classify` engine-authoritative).

## Risks

- Move-list dots vs panel badge divergence if only panel is suppressed.
- Review-mode replay bypasses play-path opts plumbing (hub signature gap).
- Global panel.js flag could conflict with trap-practice's hardcoded
  `suppressQuality: true` (and must not leak into it).
- Eval-bar hide is cross-boundary (control in tab panel, effect in board col).
- Checkmate/draw suppression ambiguity (post-`f3ba053`).
- Persistence decision per toggle (precedent exists both ways).
