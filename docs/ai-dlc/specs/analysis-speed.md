# Delta spec — analysis-speed (faster Stockfish analysis + speed presets)

**Goal (one line):** cut analyzed-move latency from 1–6 s to a predictable sub-second
default by switching interactive engine limits to node budgets and using more CPU
threads — with a persisted Fast/Balanced/Deep preset control and a depth badge, while
keeping the 2nd-best line (multipv=2) intact.

**Refuter status:** APPROVE_WITH_FIXES (2026-07-11) — all findings folded in below
(warm-hash reframed as no-op, trainer-check call site added, test_engine pin listed,
cpu_count None guard, depth-param removal decided, pv-depth seam, ruff gap noted,
preset-flip race accepted as cosmetic).

Companion docs: `contracts/analysis-speed.md` (pipeline facts), `research/analysis-speed.md`
(evidence). Requirements confirmed at Gate 1 on 2026-07-11.

## Problem

Every analyzed move runs **2 sequential engine calls** (before + after) at
`Limit(depth=18, time=3.0)`, multipv=2 (`main.py:440-441`). Depth-limited search has
wildly position-dependent latency: quiet positions return fast, sharp middlegames grind
the full 3 s × 2 calls. Threads=2, Hash=128 MB, and the transposition table is not
deliberately kept warm.

## Change

### 1. Speed presets (server-owned limit table)

New preset table in `app/engine.py` — client sends a preset *name*, never raw numbers:

| Preset | Limit | Target per analyzed move (2 calls) |
|---|---|---|
| `fast` | `Limit(nodes=400_000, time=0.5)` | ~0.15–0.3 s |
| `balanced` (default) | `Limit(nodes=800_000, time=0.8)` | ~0.3–0.6 s |
| `deep` | `Limit(nodes=12_000_000, time=1.4)` | ~2–3 s (time cap binds on typical hardware) |

- `nodes` is the primary budget (consistent quality/latency); `time` is a per-call safety
  ceiling (python-chess `Limit(nodes=…, time=…)` stops at whichever hits first).
- Node budgets are sized ~2× the single-line research numbers to compensate for multipv=2
  splitting search effort — a heuristic, not a UCI guarantee (engine-internal allocation);
  **verify empirically in verify-by #4 and tune the constants if labels feel shallow.**
- `depth` is REMOVED from interactive Limits and from the `analyze`/
  `analyze_interactive_multi` signatures (presets own the Limit entirely; `DEFAULT_DEPTH`
  survives only if still referenced elsewhere — review's `analyze_multi(depth=10)` path
  is untouched).
- **multipv=2 stays** on `/api/move` (`secondLine`/`retroBest`/`retroSecond` unchanged).
  `/api/analyze`/`/api/load` stay multipv=1 but use the same preset table.
- Unknown/absent preset → `balanced` (server-side default; invalid strings rejected by
  Pydantic `Literal`).
- **Matched-limit contract preserved:** both calls within one `/api/move` request use the
  identical preset limit, so cpLoss/quality labels stay internally consistent
  (`analysis.py:105-109` contract). Labels are only ever computed within a single request.
- `INTERACTIVE_SOFT_TIME_S`/`ENGINE_SOFT_TIME` is retired from the interactive path
  (preset table owns time caps). `ENGINE_HARD_TIMEOUT` 8 s watchdog unchanged.
  Background review (`Limit(depth=10)`) unchanged.
- **Fourth call site (refuter finding):** `/api/trainer/check` (`main.py:1321-1328`) also
  calls `analyze_interactive_multi` (before/after, multipv=1). It gets NO speed control —
  pinned to `balanced` server-side; add a test asserting it survives the signature change.
- **Known cosmetic race (accepted):** `onUserMove` renders its own response outside the
  `analysisToken` check (`app.js:530-537`). Flipping the preset while a move is in flight
  can paint one eval computed at the old preset. Acceptable — cpLoss stays internally
  consistent within that request (matched-limit contract); the depth badge will even show
  what happened. No new guard.

### 2. Threads + Hash

- `ENGINE_THREADS`: env override wins; else `max(1, (os.cpu_count() or 4) - 2)` detected
  at startup (was hardcoded 2). **The `or 4` guard is mandatory** — `os.cpu_count()` can
  return `None`, and a module-level `TypeError` would break engine.py's import-safety
  invariant and the whole test suite. Add a unit test for the None case.
- `ENGINE_HASH_MB`: 128 → 256 (constant; env override `ENGINE_HASH_MB` added for parity).

### 3. Warm hash across moves — CONFIRMED ALREADY TRUE, documentation only

- Refuter verified against installed python-chess source (`chess/engine.py:1332, 1724`):
  no call site passes `game=` today, so every call uses `game=None`, `None != None` is
  never true, and `ucinewgame` is NEVER sent between calls — **the TT is already warm
  across moves.** This is NOT a latency lever and does not count toward the target.
- Change reduces to: a short comment in `engine.py` documenting the invariant (don't
  introduce `game=`/`ucinewgame` casually — it would cold-start the TT), nothing more.

### 4. Depth badge (schema + panel)

- `Analysis` model (`models.py:46-116`) gains `depth: int | None` — the reached depth of
  the after-position primary line (from the engine info dict). White-POV/classify code
  untouched.
- `panel.js` surfaces it via the EXISTING inline `pv-depth` caption seam
  (`panel.js:117-120`, fed by the defensive `a.depth` read at `panel.js:315`) — extend
  that caption, not a new header badge. Tokens-only CSS, AA contrast.

### 5. Preset UI (frontend)

- Three-state control **Fast / Balanced / Deep** next to the existing Evaluate toggle in
  the Analysis panel, following the `analyzeColor` Both/White/Black precedent
  (`app.js:1075-1083`).
- Persisted via `prefs.js` `writeUiPref('engineSpeed', …)` (persisted precedent, NOT the
  session-only eval-toggle precedent). Default `balanced`.
- `MoveRequest`/`AnalyzeRequest` (`models.py:122-148`) gain optional
  `speed: Literal['fast','balanced','deep'] = 'balanced'`; `app.js` sends the current
  preset on `/api/move` and `/api/analyze`; `main.py` threads it into the engine calls
  (`main.py:356, 370, 440-441`).
- Changing preset bumps `analysisToken` and triggers `refreshAnalysis()` so the current
  position re-evaluates at the new speed (same pattern as the eval toggle's re-enable
  path). `:focus-visible` on the buttons.

## Files / interfaces to touch

- `app/engine.py` — preset table, threads autodetect, hash 256, `game=` sentinel,
  `analyze`/`analyze_multi`/`analyze_interactive_multi` signatures accept a preset/limit.
- `app/main.py` — thread `speed` from requests into engine calls (3 call sites:
  `main.py:356, 370, 440-441`) + adapt the 4th `analyze_interactive_multi` caller
  `/api/trainer/check` (`main.py:1321-1328`, pinned to `balanced`).
- `app/models.py` — `speed` on `MoveRequest`/`AnalyzeRequest`; `depth` on `Analysis`.
- `static/app.js` — preset state + prefs wiring + request field + refresh-on-change.
- `static/index.html` — preset button group markup.
- `static/panel.js` — depth badge.
- CSS file that styles the Evaluate/analyzeColor controls — matching preset styles.
- `tests/test_engine.py` — **`TestSoftCapAndMultiPVLimit` (lines ~203-233) pins the
  retired contract** (`limit.time == INTERACTIVE_SOFT_TIME_S`); rewrite deliberately to
  assert the new preset→Limit mapping (e.g. balanced → nodes=800_000, time=0.8), plus a
  None-cpu-count threads test.
- `tests/test_api.py` (or equivalent) — `speed` accepted + defaulted, invalid preset →
  422, `depth` present in `Analysis`, trainer-check still works; engine-free via the
  `get_engine` fake seam.

## Out of scope (explicit)

- Eval caching / instant undo-redo navigation (approach #3 of the ideation).
- Streaming/SSE progressive eval (#2). Speculative pre-analysis / pondering (#4).
- Any change to the background review job's depth/limits or `pos_cache`.
- True continuous slider; WASM engine; NNUE toggle; DB schema changes.
- Changing `useBook` semantics or trap/repertoire trainer paths.

## Constraints (from profile + contracts)

- One engine process behind the single `asyncio.Lock`; no concurrency changes; no lock
  bypass (`engine.py:16-20`).
- Before/after evals of one move: identical limit (cpLoss contract, `analysis.py:105-109`).
- White-POV normalization via `analysis.pov_score_to_white_cp`/`classify` — reuse, never
  re-derive.
- Pure modules stay engine-free; full pytest passes with no Stockfish binary
  (`get_engine` fake seam); `engine.py` stays import-safe without the binary.
- `analysisToken`/`moveToken` guards stay load-bearing; preset changes route through the
  existing refresh path. `note_interactive_start/end` pairing untouched.
- New schema fields optional-with-defaults → existing clients/tests unaffected.
- Frontend modules receive injected `api`; tokens-only CSS; AA contrast; `:focus-visible`.
- No DB schema change.

## Verify-by (what /verify-change checks)

1. `.venv/bin/python -m pytest -q` passes with no Stockfish binary (fake-seam tests cover:
   `speed` accepted + defaulted, invalid preset → 422, preset maps to expected `Limit`
   nodes/time per call site, `depth` present in `Analysis`).
2. `.venv/bin/ruff check app tests` clean — **note: ruff is not currently installed in
   the venv (pre-existing gap, refuter-verified); install it or mark this gate skipped.**
3. Live server + Playwright-MCP: preset control renders next to Evaluate toggle; selection
   persists across reload; changing preset re-evaluates the current position; depth badge
   visible on an eval; 2nd-best line + retro block still render on an analyzed move.
4. Latency evidence: with a real engine, time an analyzed move on `fast`, `balanced`,
   `deep` (e.g. curl timing or browser network tab) — fast/balanced sub-second, deep ≈ 2–3 s,
   and all far below the old 6 s worst case.
5. Environment report (no code): installed Stockfish version ≥ 17 and native ARM build
   (`stockfish` binary check) — report findings to the user.
