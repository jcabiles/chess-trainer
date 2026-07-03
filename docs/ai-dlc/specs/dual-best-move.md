# Delta Spec — Dual best move (retrospective + current, with 2nd-best)

Contracts: `docs/ai-dlc/contracts/dual-best-move.md`. Backend-assisted + frontend panel.
Related: `specs/analyze-my-color.md` (the White/Black-only skip this must coexist with).

## Problem (why)
The Analysis panel's "Best" move only shows the best move for the **current** position
(the side to move NOW = usually the opponent, right after you moved). The user can't see
**what they should have played** on their own last move. And in White/Black-only mode the
panel goes fully blank on the opponent's ply, hiding that retrospective too.

## Goal (one line)
Show **two** best moves in the play-mode Analysis panel — *"Your move — best: X"* (the move
the last mover should have played, from the position **before** the move) and *"Best now: Y"*
(current position, unchanged) — each with its **2nd-best** alternative (compact move + eval);
and on the opponent's **skipped** ply in color-only mode, **carry over** your last move's
retrospective so the panel isn't blank. Powered by data `/api/move` already computes plus one
`multipv=2` upgrade — **no new engine calls**.

## Locked decisions (from the requirements interview)
- **Retrospective is FREE on played moves.** `make_move` already runs `before` + `after`
  analyses; `before.pv[0]` (what you should have played) is currently discarded. Surface it.
- **2nd-best in BOTH spots**, shown as **move + eval** only (no second PV line). Requires
  `multipv=2` on the two existing `make_move` calls — **still exactly 2 engine calls**, each
  modestly heavier. `/api/analyze` + `/api/load` stay single-PV (new fields serialize null).
- **Keep the interactive soft-time cap.** Add multipv to a NEW soft-time-capped engine method
  (`analyze_interactive_multi`, `Limit(depth, time=INTERACTIVE_SOFT_TIME_S)`). Do **NOT** reuse
  `analyze_multi` (depth-only, no time cap → would run longer on hard positions). Wall-clock
  stays bounded; hardest positions land marginally shallower, never slower.
- **Retrospective primary = move + short PV**; **retrospective 2nd + current 2nd = move + eval**.
- **Color-only skipped ply → carry-over.** On the opponent's skipped ply, show the **nearest
  prior own-move's** retrospective (labeled to mark it's the earlier move) from a client-side
  cache — **no engine call**. Blank only when nothing is cached (e.g. FEN-restored history).
- **`both` mode**: both best-moves on every ply. (This feature intentionally makes `make_move`
  `multipv=2` for ALL modes — the analyze-my-color "both = bit-for-bit" clause governs the
  *skip* behavior, which is unchanged, not analysis richness.)
- **Scope guard:** retrospective only when a prior move exists (`cursor > 0`); null on
  start-position / book / `/api/analyze` / `/api/load`.

## In scope

### `app/engine.py`
- Add `async def analyze_interactive_multi(fen, depth=DEFAULT_DEPTH, multipv=1) -> list[AnalysisResult]`:
  build `chess.Board(fen)`, delegate to `_run_analyse(board, Limit(depth=depth,
  time=INTERACTIVE_SOFT_TIME_S), multipv=multipv)`. Returns a best-first list, length ≤ multipv
  (may be 1 when only one legal move). Reuses the SAME interactive limit `analyze` uses.
  `analyze()` is left unchanged (still used by `/api/analyze`, `/api/load`).

### `app/models.py`
- New `BestLine(BaseModel)`: `moveSan: str|None=None`, `moveUci: str|None=None`,
  `pvSan: list[str]=[]`, `evalCp: int|None=None` (White-POV cp; None iff mate),
  `mate: int|None=None` (White-POV signed).
- Extend `Analysis` (all additive, default None):
  - `secondLine: BestLine | None = None` — 2nd-best for the **current** (result) position.
  - `retroBest: BestLine | None = None` — best move the last mover **should have played**
    (from the position before the move; carries its short PV).
  - `retroSecond: BestLine | None = None` — 2nd-best for the retrospective position.

### `app/main.py`
- Helper `_to_best_line(result: AnalysisResult) -> BestLine` (White-POV eval like
  `_build_analysis`; `moveSan=pv_san[0]`, `moveUci=pv[0].uci()`, both None if pv empty).
- `_build_analysis(result, quality=None, second_line=None, retro_best=None, retro_second=None)`:
  new optional params map through `_to_best_line` (each `None`-safe). Existing top-level fields
  (current best) unchanged.
- `make_move` (the ONLY site with before+after): replace the two `engine.analyze(...)` calls
  with `before_lines = await engine.analyze_interactive_multi(fen_before, multipv=2)` and
  `after_lines = await engine.analyze_interactive_multi(fen_after, multipv=2)`; `before,
  after = before_lines[0], after_lines[0]` (quality unchanged). Build:
  `_build_analysis(after, quality=quality, second_line=after_lines[1] if len>1 else None,
  retro_best=before_lines[0], retro_second=before_lines[1] if len>1 else None)`.
- `analyze_position` / `load_fen`: unchanged (new fields null). book fast-path + `analyze=false`
  early-returns: unchanged (`analysis=None` → no retro, as today).

### `app/engine.py` fakes + tests (`tests/`)
- Every engine fake **reached through `make_move`** must gain `analyze_interactive_multi(fen,
  depth=..., multipv=1)` returning a list (≤ multipv) of its canned `AnalysisResult`s, and
  **increment the same call counter** `make_move` now hits (so `test_move_analyze_omitted_still_analyzes`'s
  `>= 2` still counts). Since `make_move` no longer calls `analyze()`, a fake that only defines
  `analyze()` will `AttributeError` → FastAPI 500 (NOT caught by `except EngineUnavailable`).
  Complete fake list (refuter [high]):
  - `tests/test_api.py` (`FakeEngine`),
  - `tests/test_repertoire_api.py` (`FakeEngine`, `NoPvEngine`),
  - **`tests/test_book_api.py` (`BoomEngine`)** — its `analyze_interactive_multi` must **raise
    `EngineUnavailable`** and bump `self.calls`, else `test_offbook_move_uses_engine` /
    `test_usebook_false_always_uses_engine` flip from 503→500 and `calls` stays 0,
  - any shared `tests/engine_fakes.py`.
  Derive this list from the contract's C-4 ("switching make_move's engine calls to a new method
  → update every `analyze()`-only fake"), not ad hoc.

### `static/index.html` + `static/panel.css` (+ `style.css` if needed)
- Add DOM in the Analysis panel: a **retrospective block** (label + `#retro-best` move,
  `#retro-pv` short PV, `#retro-second` "· or … (eval)") above/beside the current block; relabel
  the current best to "Best now" and add `#best-second` ("· or … (eval)"). Retro block hidden
  when empty. Tokens-only CSS, `:focus-visible` where interactive.

### `static/panel.js`
- `renderAnalysisPanel(a, opts)`:
  - **`opts.suppressRetro`** (refuter [high]): when set, hide/blank ALL new DOM — `#retro-best`,
    `#retro-pv`, `#retro-second`, `#best-second` — leaving today's `#best-move`/`#pv`/`#eval`/
    `#quality` behavior. (trap-practice passes it; keeps the drill non-revealing.)
  - Current block: existing `#best-move`/`#pv` unchanged; populate `#best-second` from
    `a.secondLine` (move + `formatEval`-style White-POV eval), hide if null or `suppressRetro`.
  - Retro block: if `a.retroBest` (and not `suppressRetro`), show `#retro-best` (moveSan) +
    `#retro-pv` built via `buildPvFragment(a.retroBest.pvSan, …)` using
    **`fenSideAtCursor(baseFen, cursor - 1)`** (the mover's own turn — different side/fullmove
    than the current PV); `#retro-second` from `a.retroSecond`. **Guard `cursor > 0`**; also
    guard empty `pvSan` (render the move alone). Hide the whole block when `retroBest` null.
- `renderBookMovePanel(data)`: also clear/hide the retro + 2nd-best DOM (book = no analysis).
- `renderSkippedPanel(carriedRetro, pvCursor)`: keep the "Not evaluated · opponent's move"
  quality badge and blank the CURRENT block; if `carriedRetro` present, render the retro block
  from it (label marks it the earlier move, e.g. "Your last move — best: …") with PV built via
  `fenSideAtCursor(baseFen, pvCursor)`; else blank the retro block.

### `static/app.js`
- **Retro cache** (runtime-only, NOT persisted — session `:v1` shape unchanged): a `moveRetro`
  array keyed by **move index** (same indexing as `moveQuality` — `moveQuality[state.cursor]` is
  set *before* `cursor += 1`, so the index is the move's own index). On every `/api/move`
  response carrying `data.analysis.retroBest`, store it at the move's index (`onUserMove` and the
  `refreshAnalysis` cursor>0 path).
- **Clear/restore/truncate `moveRetro` in lockstep with `moveQuality`** (refuter [high]) — else
  stale retros from a prior game/line surface on a skipped ply, mislabeled "your last move".
  Mirror `moveQuality` at **every** site that resets or diverges history:
  `onUserMove` divergence (`.slice(0, state.cursor)`), `reset()`, `beginGame()`, `cancelSetup()`,
  `loadFen()`, `exitTrap()`, `exitRepPractice()`, `repJump()`, and `restore()`
  (grep `moveQuality = \[\]|moveQuality = snap|moveQuality.slice` — moveRetro tracks each 1:1).
- `renderSkipped()`: scan the current move index downward for the **nearest `J` where
  `moveRetro[J]` is truthy** (refuter [low] — the literal predicate is "cache entry exists," NOT
  "mover == analyzeColor": a *book* move by your color returns `analysis:null` so never populates
  `moveRetro[J]`, and the scan must walk past it). Call `renderSkippedPanel(moveRetro[J] || null,
  J)` (PV side-to-move from position index `J`); guard `J >= 0`.
- Thread the current cursor into `renderAnalysis` so `panel.js` can read `cursor - 1` for the
  retro PV (panel already reads state via `_api.actions.getState`).
- **`renderPracticeNote` (trap-practice)** must pass `{ suppressQuality: true, suppressRetro: true }`
  (refuter [high]) — it rides `/api/move`, which now returns `retroBest`/`secondLine`; without the
  guard the drill would display the engine's best move for the scripted ply (revealing the trap's
  refutation) with PV numbering computed from a **stale** `state.cursor`/`baseFen` (trap mode never
  updates them).

## Out of scope
- Review / opening / repertoire-practice panels (separate pipelines; `review.py` already
  computes its own retrospective `best_san`). rep-practice engine-reply keeps using `bestMoveUci`.
- **trap-practice** is NOT silently excluded — it rides `/api/move`, so it's explicitly guarded
  OFF via `suppressRetro` (see app.js/panel.js) to keep the drill non-revealing. New DOM stays
  hidden there.
- A **second PV** line for any 2nd-best (move + eval only, per decision).
- Persisting the retro cache across reload; retroactively recomputing skipped plies; any extra
  engine call to fill a skipped ply. 2nd-best on `/api/analyze`/`/api/load` (start position).
- An engine opponent; changes to `analyzeColor` skip semantics or the `:session:v1` shape.

## Constraints
- **No new engine calls.** Exactly 2 `analyze_interactive_multi` calls per analyzed move;
  `analyze=false` skipped plies stay at **0** calls (pinned by
  `tests/test_api.py::test_move_analyze_false_skips_engine`).
- Keep the interactive soft-time cap (bounded latency). Reuse `pov_score_to_white_cp` — all
  evals White-POV. One engine process behind the single lock.
- **Accepted tradeoff (refuter [med]):** `multipv=2` is costlier per node, so under the soft-time
  cap `before`/`after` may stop at slightly different depths more often than at `multipv=1`,
  marginally loosening `classify()`'s "same-depth cpLoss" premise. This is *more of an existing
  effect* (the soft cap already lets before/after diverge on complex positions), not a new class
  of bug, and quality is bucketed (tolerant of small noise). Accepted; spot-check with real
  Stockfish (Verify-by 5) that labels on a few known positions don't shift vs today.
- Additive fields only; render must ADD DOM, never mutate `#eval`/`#quality` semantics.
- Tokens-only CSS (no raw hex). Full suite green via the `get_engine` fake; verified in-browser
  before commit.

## Verify-by
1. **Backend (pytest):**
   - `/api/move` on a legal non-book move → `analysis.retroBest.moveSan` set, `analysis.retroBest.pvSan`
     non-empty, `analysis.secondLine.moveSan` set (when >1 legal move), and top-level
     `bestMoveSan` unchanged (= current-position best). `quality` still a valid `Quality`.
   - `analyze=false` → still `analysis:null`, engine call count **unchanged (0 delta)**.
   - `analyze` omitted → engine called (counter ≥ 2 via the new method), retro present.
   - `/api/analyze` → `retroBest`/`secondLine` null, `bestMoveSan` truthy, `quality` null.
   - Single-legal-move position → `secondLine`/`retroSecond` null (no crash).
2. **Browser, `both` mode:** after a move, panel shows "Your move — best: X (+ or X2)" AND
   "Best now: Y (+ or Y2)"; retro PV numbering correct (mover's side); start position shows no
   retro block; 0 console errors.
3. **Browser, Black-only:** your move → both blocks; **opponent's next ply** → "Best now" blank
   but "Your last move — best: …" carried over (correct move, correct PV); nav back to that ply
   keeps the carry-over; nav to a ply with no cache → retro blank; **network shows no engine call
   on the skipped ply**.
4. `pytest` green; `ruff check app` clean.
5. **Real-engine spot check (refuter [med]):** with actual Stockfish, play a few known positions
   and confirm quality labels don't shift vs today (depth-divergence under `multipv=2` doesn't
   change classification). Confirm trap-practice shows **no** retro/2nd-best block (suppressRetro).
