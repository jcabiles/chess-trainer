# Tickets — Dual best move (retrospective + current, with 2nd-best)

Spec: `docs/ai-dlc/specs/dual-best-move.md` · Contracts: `docs/ai-dlc/contracts/dual-best-move.md`

DAG: T1, T2, T5 have no deps (parallelizable). T3←(T1,T2). T4←T3. T6←(T2,T5). T7←T6.
T8←all. Hotspots are single-owner (one ticket each). Recommend one agent, ticket order
T1→T2→T3→T4→T5→T6→T7→T8 (frontend T6/T7 couple tightly; keep serial).

---

## T1 — `analyze_interactive_multi` on the engine  ·  owns `app/engine.py`
Add `async def analyze_interactive_multi(fen, depth=DEFAULT_DEPTH, multipv=1) -> list[AnalysisResult]`
that builds `chess.Board(fen)` and delegates to `_run_analyse(board, Limit(depth=depth,
time=INTERACTIVE_SOFT_TIME_S), multipv=multipv)` — the SAME soft-time-capped limit `analyze()`
uses (NOT `analyze_multi`'s depth-only limit). `analyze()` unchanged.
- **Accept:** returns a best-first list length ≤ multipv (length 1 when only one legal move);
  serialized behind the existing lock; import-safe when the binary is absent.
- **Done:** `python -c "import app.engine"` OK; `.venv/bin/python -m pytest -q` still green
  (no caller yet). Deps: none.

## T2 — `BestLine` model + additive `Analysis` fields  ·  owns `app/models.py`
Add `BestLine(BaseModel)` = `{moveSan?, moveUci?, pvSan=[], evalCp?, mate?}` (White-POV eval,
None iff mate). Extend `Analysis` (all default None, additive): `secondLine: BestLine|None`,
`retroBest: BestLine|None`, `retroSecond: BestLine|None`.
- **Accept:** existing `Analysis` fields untouched; new fields optional/defaulted.
- **Done:** `.venv/bin/python -m pytest -q` green (nothing constructs the new fields yet);
  `ruff check app` clean. Deps: none.

## T3 — `make_move` surfaces retro + 2nd-best  ·  owns `app/main.py`
Add `_to_best_line(result) -> BestLine` (White-POV, `moveSan/moveUci` None when pv empty).
Extend `_build_analysis(result, quality=None, second_line=None, retro_best=None,
retro_second=None)` (each `None`-safe via `_to_best_line`). In `make_move`, replace the two
`engine.analyze(...)` with `before_lines = await engine.analyze_interactive_multi(fen_before,
multipv=2)` / `after_lines = await engine.analyze_interactive_multi(fen_after, multipv=2)`;
`before, after = before_lines[0], after_lines[0]` (quality unchanged); build
`_build_analysis(after, quality=quality, second_line=after_lines[1] if len>1 else None,
retro_best=before_lines[0], retro_second=before_lines[1] if len>1 else None)`.
`analyze_position`/`load_fen`/book/`analyze=false` paths unchanged.
- **Accept:** top-level `bestMoveSan` == `after_lines[0]` best (bit-for-bit); retro/second only
  on `/api/move`; single-legal-move & mate positions don't crash (empty pv → None).
- **Done:** manual `TestClient` POST `/api/move` shows `retroBest`, `secondLine`; `/api/analyze`
  shows them null. Deps: T1, T2.

## T4 — engine fakes + backend tests  ·  owns `tests/` (fakes + new assertions)
Give every fake reached through `make_move` an `analyze_interactive_multi(fen, depth=...,
multipv=1)` returning a list of its canned results and **bumping the same call counter**:
`tests/test_api.py::FakeEngine`, `tests/test_repertoire_api.py::FakeEngine`+`NoPvEngine`,
`tests/test_book_api.py::BoomEngine` (re-raise `EngineUnavailable`, bump `self.calls`), shared
`tests/engine_fakes.py` if present. Add tests: `/api/move` → `retroBest.moveSan` +
`retroBest.pvSan` non-empty + `secondLine.moveSan` set; `analyze=false` → 0-call delta unchanged;
`analyze` omitted → counter ≥ 2 via new method; `/api/analyze` → retro/second null; single-legal
→ second null.
- **Accept / Done:** `.venv/bin/python -m pytest -q` green incl. new cases;
  `test_move_analyze_false_skips_engine` + `test_move_analyze_omitted_still_analyzes` +
  `test_offbook_move_uses_engine` still pass. Deps: T3.

## T5 — panel DOM + CSS  ·  owns `static/index.html`, `static/panel.css` (+ `style.css` if needed)
Add to the Analysis panel: a **retrospective block** (label + `#retro-best` move, `#retro-pv`,
`#retro-second`) and a `#best-second` span in the current block; relabel current best to "Best
now". Retro block hidden by default (empty). Tokens-only CSS, no raw hex, `:focus-visible` on any
interactive element.
- **Accept / Done:** page loads, new elements present + hidden when empty; no raw hex (grep);
  no console errors. Deps: none.

## T6 — panel.js render + suppressRetro + skipped signature  ·  owns `static/panel.js`
`renderAnalysisPanel(a, opts)`: honor `opts.suppressRetro` (hide ALL new DOM); populate
`#best-second` from `a.secondLine`; render retro block from `a.retroBest`/`a.retroSecond` when
`cursor > 0` (PV via `fenSideAtCursor(baseFen, cursor-1)`, guard empty pvSan). `renderBookMovePanel`
clears the new DOM. Change `renderSkippedPanel(carriedRetro, pvCursor)` to render the carried retro
(labeled as the earlier move, PV via `fenSideAtCursor(baseFen, pvCursor)`) or blank it.
- **Accept / Done:** in `both` mode both blocks render with correct move numbering; retro hidden
  at cursor 0 / book / `suppressRetro`; 0 console errors (Playwright/manual). Deps: T2, T5.

## T7 — app.js cache + lockstep + carry-over + trap guard  ·  owns `static/app.js`
Add runtime `moveRetro` array (indexed like `moveQuality`); populate on `/api/move` responses
(onUserMove + refreshAnalysis cursor>0). **Clear/restore/truncate it in lockstep with
`moveQuality`** at all 9 sites (onUserMove divergence slice, reset, beginGame, cancelSetup,
loadFen, exitTrap, exitRepPractice, repJump, restore). `renderSkipped()` scans down for the
nearest `J` where `moveRetro[J]` is truthy → `renderSkippedPanel(moveRetro[J]||null, J)`
(guard `J>=0`). Thread current cursor into `renderAnalysis`. `renderPracticeNote` passes
`{ suppressQuality:true, suppressRetro:true }`.
- **Accept / Done (Playwright/manual):** Black-only — your move shows both blocks; opponent's
  skipped ply carries over "your last move — best: …" with correct PV, **no engine call** on that
  ply (network); new game / FEN-load / trap-exit clears stale carry-over; trap-practice shows no
  retro/2nd block. Deps: T6.

## T8 — verify + commit  ·  no new files
Run full verify-by: `.venv/bin/python -m pytest -q` green, `ruff check app` clean, and a
real-Stockfish browser pass (both mode dual blocks + numbering; Black-only carry-over + no
skipped-ply engine call; quality labels unshifted vs today; trap-practice suppressed). Commit
per policy (Conventional Commits, no debug artifacts) once implemented + verified + reviewed.
- **Done:** evidence captured; branch pushed (not `main`). Deps: T1–T7.
