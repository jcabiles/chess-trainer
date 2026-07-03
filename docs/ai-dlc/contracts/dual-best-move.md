# Contracts — Dual "best move" (retrospective + current)

Scope: the Analysis "best move" data path, engine → API → panel, for adding a
**retrospective best move** ("what the last mover should have played") beside the
existing current-position best move.

## A. Data contract (`app/models.py`)
- `Analysis` fields: `evalCp?`, `mate?`, `evalWhitePov` (REQUIRED), `bestMoveSan?`,
  `bestMoveUci?`, `pvSan=[]`, `quality?`. Only `evalWhitePov` is required.
- **Adding an optional field (default None/[]) is additive-safe.** `Analysis` is
  never `model_validate()`'d from external JSON (grep-confirmed) — no strict schema
  rejects unknown/new fields. Frontend does plain `data.analysis.x` access; missing
  → renders `—`. Removing/renaming would silently blank the UI; adding won't.
- Embedded in `MoveResponse.analysis?`, `AnalyzeResponse.analysis` (req),
  `LoadResponse.analysis?`. Review/coaching JSON (`ReviewResponse`, `GameDetail`,
  `PlyDetail`, `NarratedLeak`) are INDEPENDENT schemas — zero risk from touching `Analysis`.

## B. The free retrospective (`app/main.py::make_move`)
- `make_move` already runs `before = engine.analyze(fen_before)` and
  `after = engine.analyze(fen_after)` (~L327-328). `before` feeds `classify()` then is
  **discarded**. Surfacing `before.pv_san` / `before.pv[0].uci()` = **zero** extra engine load.
- `_build_analysis` (L192) has 3 call sites: `analyze_position` (L249, quality=None),
  `load_fen` (L266, quality=None), `make_move` (L344, quality set — ONLY site with both
  before+after in scope).
- **The 2nd-best move requires `multipv=2`** (added after this scan). Do NOT reuse the depth-only
  `analyze_multi` (no soft-time cap → longer on hard positions). Plan: a NEW soft-time-capped
  `engine.analyze_interactive_multi(fen, multipv)` — **still exactly 2 engine calls** in
  `make_move`, each yielding `[best, 2nd]`. Because `make_move` no longer calls `analyze()`, every
  fake reached through it must gain `analyze_interactive_multi` (see C-4 for the full list).

## C. Frontend consumers (`static/`)
- `panel.js renderAnalysisPanel` reads `bestMoveSan` (L227), `pvSan` (L233-245),
  eval/quality. `renderBookMovePanel`/`renderSkippedPanel` blank best/PV to `—`.
- PV side-to-move math: `fenSideAtCursor(baseFen, state.cursor)` + `buildPvFragment`
  (module-private). Current PV uses `state.cursor`; a **retrospective PV needs
  `cursor-1`** (mover's own turn — different side/fullmove). Guard `cursor>0`
  (`fenSideAtCursor` silently no-ops on negative cursor → base position).
- `app.js`: thin delegates `renderAnalysis`/`renderBookMove`/`renderSkipped`;
  `applyMoveResponse` (L505) branches book → else renderAnalysis.
- `refreshAnalysis` (L339): cursor==0 → `/api/analyze` (no prior move → no retrospective);
  cursor>0 → `/api/move` (re-analyzes fresh every nav, quality never cached client-side).
- **13 refreshAnalysis call sites** across play/setup/trap/rep/review→play transitions;
  best-move panel reached in play + trap-practice (renderPracticeNote rides `/api/move`,
  would inherit the field). rep-practice engine-reply consumes `bestMoveUci` directly (inert
  to new field). Review mode = separate pipeline (own `best_san`/`best_uci`).

## D. Color-skip gap & risks
- **C-1 Skipped ply (color mode):** `analyze:false` → early return `app/main.py:317-323`,
  NO engine call — **pinned** by `tests/test_api.py:198-214` (must stay 0 calls). On a
  skipped opponent ply, neither before nor after exists → retrospective is **unrecoverable**
  there without a forbidden new call. Must degrade to blank/dash (like `renderSkippedPanel`).
  - Asymmetry: white-only → White's own move IS analyzed (retrospective available for it);
    the next Black ply is skipped (no data).
- **C-2 PV side-to-move:** retrospective PV from `cursor-1`; guard `cursor>0`.
- **C-3 Deserialization:** not a risk (no strict schema).
- **C-4 Engine-call count + fake churn:** keep exactly 2 calls (a 3rd breaks
  `test_move_analyze_omitted_still_analyzes`, pins `>=2` would fail at 3; and the analyze=false
  test pins 0). Switching `make_move` to `analyze_interactive_multi` means every `analyze()`-only
  fake reached through `make_move` **must** implement it (return a list, bump the same counter),
  or it `AttributeError`s → FastAPI 500 (not caught by `except EngineUnavailable`). Full list:
  `tests/test_api.py::FakeEngine`, `tests/test_repertoire_api.py::FakeEngine` + `NoPvEngine`,
  **`tests/test_book_api.py::BoomEngine`** (must re-raise `EngineUnavailable` + bump `self.calls`),
  and any shared `tests/engine_fakes.py`.
- **C-5 `both` bit-for-bit:** additive field only; render must ADD DOM, never mutate
  `#eval`/`#quality`/existing `#best-move`/`#pv` semantics.
- **C-6 book / cursor-0:** retrospective must be None there (like `quality:None`).

## D'. Tests pinning current behavior
- `test_move_analyze_false_skips_engine` (0 calls on analyze:false) — hard invariant.
- `test_move_analyze_omitted_still_analyzes` (>=2 calls) — tolerant of reuse, fails at 3.
- `/api/analyze` asserts `bestMoveSan` truthy + `quality None` — retrospective must be None here.
- No test enumerates exact `Analysis` keys → additive field trips nothing.
- No frontend/DOM automated test for `#best-move`/`#pv` → panel changes need manual/Playwright verify.
