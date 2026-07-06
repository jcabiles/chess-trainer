# Delta spec — Blunder Trainer (re-solve own blunders + Leitner SR)

**Goal (one line):** turn recorded leaks into a drill loop — puzzles from your
own analyzed games, scheduled by Leitner boxes over motif buckets, solved by
engine eval-window check, living as a "Train" section in the Review tab.

Third head of the game-review coaching epic (deferred by
`specs/game-review-coaching.md:11-12`). Backlog #12 (Impact H).
Contract map: `docs/ai-dlc/contracts/blunder-trainer.md`.

**This spec explicitly authorizes the SQLite schema change** (profile
invariant "no DB schema change unless a spec says so").

## Core design

### Puzzle identity (contract 1 — leak ids are unstable)

A puzzle's durable identity is the natural key **`(game_id, ply,
threat_motif)`**. `leaks.id` is NEVER stored in trainer state — re-analysis
deletes+reinserts leaks with new autoincrement ids. Trainer state joins back
to the live `leaks` row by natural key at read time; a leak that vanished on
re-analysis (classification changed) simply drops out of the queue, and its
attempt history remains as an orphan-tolerant record.

### Data model (new tables in `_SCHEMA_DDL`, version bump)

```sql
CREATE TABLE IF NOT EXISTS trainer_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  ply INTEGER NOT NULL,
  threat_motif TEXT NOT NULL,
  attempted_uci TEXT NOT NULL,
  outcome TEXT NOT NULL,          -- 'solved' | 'solved_alt' | 'failed' | 'revealed'
  cp_delta INTEGER,               -- eval gap vs best at check time (White-POV cp)
  check_depth INTEGER NOT NULL,   -- depth the verdict was computed at
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS trainer_boxes (
  motif TEXT PRIMARY KEY,         -- bucket = motif category (closed 9-value vocab)
  box INTEGER NOT NULL DEFAULT 1, -- Leitner box 1..5
  last_reviewed TEXT,             -- ISO date of last completed bucket review
  cursor_key TEXT                 -- natural key of the last-served puzzle (rotation pointer)
);
```

Writes go through new `storage.py` functions (`record_trainer_attempt`,
`get_trainer_boxes`, `upsert_trainer_box`, `get_attempt_stats`) — sqlite3
stays in storage.py only. `trainer_attempts` cascades with game deletion.

### Scheduling — Leitner over MOTIF buckets (de la Maza-safe)

- The Leitner unit is the **bucket** (motif), not the position. Boxes 1-5 with
  review intervals in days: 1, 2, 4, 7, 14. A bucket is *due* when
  `today - last_reviewed >= interval(box)`.
- A bucket review serves the **next positions in rotation** (via
  `cursor_key`), so consecutive reviews of "fork" show *different* forks —
  the identical board resurfaces only after the whole bucket cycles.
  This is the de la Maza requirement implemented deterministically.
- Bucket outcome: ≥70% solved this session → box+1 (cap 5); <40% → box 1;
  else stay — **but only when ≥2 puzzles were served from the bucket this
  session; with fewer, the box carries over unchanged** (refuter: N=1 samples
  can only be 0%/100%, one unlucky puzzle would erase weeks of progress).
- Session assembly: up to 3 puzzles per due bucket, session cap ~10 total —
  **reserve ≥1 slot per due bucket FIRST, then fill remaining slots hardest
  first (`win_prob_drop` desc)** (refuter: a pure global hardest-first trim
  can starve an easier bucket forever, freezing its schedule).
- **`cursor_key` recovery:** if the stored key no longer matches a live leak
  in the bucket (re-analysis/deletion), restart rotation at the bucket's
  first item — never error, never skip the bucket.
- **Box hygiene:** at session assembly, any `trainer_boxes` row whose motif
  has zero live qualifying leaks is reset to box 1 / cleared — stale box-5
  schedules must not apply to a future, effectively-new weakness pool.
- Pure module **`app/trainer.py`**: box math, due computation, rotation,
  session assembly — engine-free, fully unit-testable; reads via read-only
  SQL on `storage._get_conn()` (profile.py precedent), writes via storage
  functions.

### Puzzle sourcing (qualification gate, contract 9)

Leaks from games with `my_color IS NOT NULL AND analysis_status='done'`,
`severity IN ('mistake','blunder')`, joined to `game_plies.fen_before` for the
puzzle FEN. Bucket = `threat_motif` (fallback `category`). Buckets with zero
live leaks are skipped (and shown as empty state, not errors).

### Solving — engine eval-window (contracts 4, 5, 6)

New route `POST /api/trainer/check` `{game_id, ply, threat_motif,
attempted_uci}`:
1. Rebuild `fen_before` server-side (never trust client FEN).
2. Validate legality (python-chess), then run the **two-call before/after
   pattern exactly like `/api/move` (`app/main.py:384-402`)**: analyze
   `fen_before` (best line) AND `fen_after_attempted` (the attempted move's
   real eval) at **interactive `DEFAULT_DEPTH`** — both calls inside one
   `review.note_interactive_start()/end()` try/finally. A single multipv call
   cannot score moves outside the top-K (refuter HIGH).
3. Verdict via a **new pure helper `analysis.cp_loss(before_white_cp,
   after_white_cp, mover_is_white)`** refactored out of `classify()` so the
   mover-sign rule stays derived in exactly one place (never inline the
   sign flip):
   - attempted == engine best at check depth → `solved`
   - `cp_loss <= 50` (or both evals ≥ +300cp mover-POV) → `solved_alt`
   - else → `failed`, response includes `best_san` + narrator text
     (`coaching.get_narrator().narrate_leak(...)` accepts a
     LeakRecord/dict with only leaks-row columns — verified; no new
     narration).
4. Store attempt (`check_depth` recorded — stored `leaks.best_uci` came from
   BACKGROUND_DEPTH 10 and is a hint, not the judge; the check-time engine at
   depth 18 is authoritative). Mate scores flow through
   `pov_score_to_white_cp`'s existing mate clamping — cp_loss math operates
   on its output only.
5. Engine unavailable → 503 passthrough; frontend offers exact-match-vs-
   stored-`best_uci` as a degraded fallback labeled "offline check";
   offline attempts ARE recorded with sentinel `check_depth = 0` (refuter:
   NOT NULL column needs an explicit rule).

Other routes: `GET /api/trainer/session` (assembled due-session),
`GET /api/trainer/stats` (boxes + attempt aggregates for the Train section).
**Stats rule:** per-bucket displays join attempts back to LIVE leaks by
natural key (orphaned attempts from reclassified positions are excluded);
the all-time totals row may include orphans and is labeled "all attempts".
Zero-games / zero-attempts paths return explicit empty states (no
divide-by-zero).
Schemas in `app/models.py`; literal-before-`{id}` ordering respected;
`Depends(get_engine)`; all testable via `ScriptedEngine` fake.

### Frontend

- **`static/trainer.js`** (new, injected-api module; never imports app.js):
  Train section markup in the Review tab (due-bucket summary, Start button,
  per-bucket box levels), and the drill flow: serve puzzle → board at
  `fen_before` oriented to your color → your move → check → feedback
  (narrator text + threat highlight via `hung_square`/`threat_uci`) →
  next. One retry on `failed`, then reveal (`best_san`, counts as
  `revealed`).
- New mode **`blunder-practice`**; hub edits (single-owner app.js ticket):
  add to `persist()` transient early-return list, add to `PRACTICE_MODES`,
  and trainer.js calls `registerModeHandlers('blunder-practice', {onMove,
  exit})` — two positional args. Enter snapshots play state via
  `api.hub.snapshotPlay()` (module-held, like rep/traps); exit restores via
  `restorePlay`.
- `index.html`: Train section markup inside the Review tab panel + drill bar.

## Files / interfaces to touch

| File | Change |
|---|---|
| `app/storage.py` | 2 new tables (DDL), version bump, attempt/box read-write functions |
| `app/trainer.py` | NEW pure module: Leitner math, due/rotation/session assembly |
| `app/analysis.py` | refactor: extract pure `cp_loss(before, after, mover_is_white)` from `classify()` (classify delegates to it — zero behavior change, existing tests must stay green) |
| `app/main.py` | 3 routes (`/api/trainer/session`, `/check`, `/stats`) |
| `app/models.py` | request/response schemas |
| `static/trainer.js` | NEW injected-api module (section UI + drill mode) |
| `static/app.js` | import/init hook, `PRACTICE_MODES` + `persist()` mode entries |
| `static/index.html` | Train section + drill-bar markup |
| `static/review.css` (or new `trainer.css`) | section + drill styles, tokens-only |
| `tests/` | trainer.py pure tests; API tests via ScriptedEngine |

## Out of scope

External puzzle banks (lichess), synthetic position variation, SM-2, a new
top-level tab, any Insights change (stays read-only diagnostics), puzzles
from non-imported live games, LLM narration, `%clk` time features, changes
to review/leak detection itself.

## Constraints (from profile + contracts)

- sqlite3 in storage.py only; pure modules engine-free (trainer.py must pass
  pytest with no binary); reuse `pov_score_to_white_cp`/`classify`; one
  engine + lock + interactive yield; frontend one-directional api contract;
  tokens-only CSS, AA, :focus-visible; Conventional Commits + verified-
  before-commit; feature branches only.

## Verify-by (per `<profile.verify>`)

1. `.venv/bin/python -m pytest -q` — new pure tests (box transitions incl.
   the min-sample carry-over, due math, rotation never repeats a position
   within a cycle, cursor recovery on vanished key, box reset on empty
   motif pool, natural-key survival across simulated re-analysis,
   `cp_loss` sign correctness for BOTH colors + mate-clamped inputs,
   zero-games stats empty states) + API tests (check verdicts via
   ScriptedEngine scripting `fen_before` AND `fen_after` independently:
   solved/solved_alt/failed/503) all green, no Stockfish.
2. `.venv/bin/ruff check app tests` clean.
3. Playwright (user runs uvicorn :8001; real mouse): Review tab shows Train
   section with due buckets → Start → board shows blunder position → wrong
   move → retry → reveal shows best + narration → correct move on next
   puzzle → session summary → Return restores prior play state (movelist
   tints intact); reload mid-drill lands in play mode (transient, not
   persisted); cross-cutting: play move still analyzes, other trainers
   unaffected.

## Refuter findings (folded)

Verdict on draft: APPROVE_WITH_FIXES → all folded above:
- **HIGH** eval-window check requires the two-call before/after pattern +
  new pure `analysis.cp_loss` helper (single multipv can't score off-top-K
  moves; inline sign flips risk the Black-to-move bug).
- **MED** Leitner min-sample guard (≥2 served or box carries over).
- **MED** reserve ≥1 slot per due bucket before hardest-first trim.
- **MED** `cursor_key` recovery rule (restart cycle on vanished key).
- **MED** box hygiene: reset boxes whose motif pool is empty; zero-games
  stats empty states tested.
- **LOW** stats exclude orphaned attempts for per-bucket views (labeled
  all-time totals may include them).
- **LOW** offline-fallback attempts recorded with `check_depth = 0` sentinel.
- Ground-truthed by refuter: one leak per ply (natural key collision-free);
  `narrate_leak` callable from a leaks row alone; ScriptedEngine can script
  before/after FENs independently; baseline 552 green.
