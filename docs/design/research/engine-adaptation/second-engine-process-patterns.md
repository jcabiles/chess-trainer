# Second-engine process patterns (vs option-toggling on a shared process)

Evidence for THE architecture decision of the bots epic: weaken the existing
shared Stockfish per-call, or run a second isolated engine process (weakened
Stockfish or lc0+Maia). Repo ground truth: ONE Stockfish (`SimpleEngine` +
thread-pool executor + one `asyncio.Lock`), process-global UCI options, a
`restart()` that re-applies only `Threads`/`Hash` — see
`../../../ai-dlc/contracts/bot-play.md` and `app/engine.py:1-30`.

## What python-chess supports (verified against docs + source)

- **Two APIs, don't mix**: sync `SimpleEngine` (blocking; the repo's choice,
  wrapped in an executor) and the native asyncio protocol
  (`await chess.engine.popen_uci(...)`)
  ([python-chess engine docs](https://python-chess.readthedocs.io/en/latest/engine.html)).
- **Multiple concurrent engine processes are supported.** Each
  `popen_uci` creates its own subprocess transport via
  `asyncio.get_running_loop().subprocess_exec(...)`; instances are independent
  ([engine.py source](https://github.com/niklasf/python-chess/blob/master/chess/engine.py)).
  Two `SimpleEngine`s work the same way — each owns its own background event
  loop and pipe. The repo's existing pattern (per-engine `asyncio.Lock` +
  executor + watchdog) replicates cleanly for a second engine object.
- **One command at a time per engine.** Whatever the API, a single engine
  instance processes one `go` at a time — concurrency comes from having
  multiple *processes*, never from multiplexing one.
- **`play()` vs `analyse()`**: a bot move is `engine.play(board, Limit(...))`
  (emits `bestmove`, which is where Stockfish's Skill/Elo move-swap happens —
  see `stockfish-weakening.md`). The repo currently has **no `play()` call at
  all** (eval-only surface, contract §1); this is new code either way.
- **Per-call options**: `play()`/`analyse()` accept an `options={...}` dict;
  the docs state "the previous configuration will be restored after the
  analysis is complete"
  ([docs](https://python-chess.readthedocs.io/en/latest/engine.html)) —
  python-chess tracks sent options and skips redundant `setoption`s. So
  mechanically, per-move toggling of `UCI_LimitStrength`/`UCI_Elo` on the
  shared engine is *possible* and self-restoring. Also note `MultiPV` is on
  the docs' "managed automatically — do not configure" list.
- **`game=` / `ucinewgame`**: python-chess sends `ucinewgame` only when the
  `game` identifier changes between calls
  ([docs](https://python-chess.readthedocs.io/en/latest/engine.html)). The
  repo deliberately never passes `game=` to keep the transposition table warm
  (contract §1, `engine.py:369-374`) — a bot sharing the process inherits
  that: no clean-slate per game without cold-starting the human's analysis
  too.

## What toggling on the shared process actually costs

Setting `UCI_Elo` per bot move does not reallocate anything (only
`Threads`/`Hash` changes trigger reallocation in Stockfish; strength options
have no such handler — no hash clear). The real costs are subtler:

1. **State leakage risk.** Options are process-global; a crash/timeout between
   set and restore, or the repo's `restart()` (which re-applies only
   `Threads`/`Hash`, `engine.py:284-332` per contract §1), leaves either the
   analysis path weakened (silently wrong eval labels) or the bot path at full
   strength. python-chess's auto-restore narrows but does not close this —
   the repo's watchdog can poison and rebuild the engine mid-sequence.
2. **TT cross-contamination — in BOTH directions.**
   - Analysis → bot: the shared warm transposition table contains deep entries
     from the human's `/api/move` evals of the *same positions the bot is
     about to search*. A skill-limited search picks from root moves scored at
     shallow depth (see `stockfish-weakening.md`), but TT hits let those
     shallow iterations return previously computed deep results — the bot
     plays effectively stronger/less erratic than its UCI_Elo calibration
     (which was measured in standalone matches). ⚠ mechanism-level inference,
     no external measurement found; but the calibration-context mismatch is
     factual ([commit a08b8d4](https://github.com/official-stockfish/Stockfish/commit/a08b8d4)).
   - Bot → analysis: weakened-search entries are merely shallow, and
     Skill-enabled searches force MultiPV≥4 (search.cpp), so bot searches are
     also ~4× wider than needed. Mostly a perf smell, not a correctness bug.
3. **Lock contention.** A bot move is a third consumer of the single lock
   (after interactive `/api/move` evals ×2 and the background reviewer). At
   human play cadence every bot reply queues behind — and delays — the
   player's own eval round-trip. Contract §5 already flags this as the
   epic's primary risk.
4. **Restart survival.** Any shared-process design must centralize "the full
   option set to re-apply on (re)start" — today that set is hardcoded as
   Threads/Hash. Forgetting this is a *silent* failure mode (contract §1).

## The isolated second-process pattern

Run the bot's engine as its own subprocess with its own wrapper (own lock,
own watchdog, own lifecycle), never touched by analysis traffic:

- **Resource sizing is trivial.** A weakened bot needs no horsepower:
  Stockfish-bot at `Threads=1, Hash=16` (it searches shallowly by design), or
  lc0+Maia at 1 CPU thread / `nodes=1` (single ~1.3 MB-net forward pass; see
  `maia-lc0.md`). No meaningful CPU competition with the analysis engine's
  `cpu_count-2` threads; memory cost is tens of MB.
- **Options set once at spawn** (`UCI_Elo`, weights path, threads) — nothing
  to toggle, nothing to restore, restart logic self-contained. Rating-band
  changes = respawn with different options/weights (cheap: lc0+maia loads in
  well under a second ⚠ unbenchmarked, weights are 1.3 MB).
- **Calibration validity.** UCI_Elo was calibrated with the engine playing
  standalone games ([a08b8d4](https://github.com/official-stockfish/Stockfish/commit/a08b8d4));
  an isolated process with its own cold-ish TT is the environment that
  calibration actually describes.
- **Engine-agnostic seam.** Both candidate bot brains (weakened Stockfish,
  lc0+Maia) are UCI subprocesses driven by `engine.play()` — an isolated
  `BotEngine` wrapper makes the Stockfish-vs-Maia choice (and future persona
  engines, → `../bot-personas/`) a config swap instead of a re-architecture.
- **Precedent**: driving multiple engines side by side from one program is
  the normal python-chess pattern (each instance independent, per docs/source
  above); GUIs do the analysis-engine + playing-engine split as standard
  practice.

Costs of isolation: a second process to babysit (spawn failure, poisoning,
shutdown ordering — must mirror `EngineUnavailable` import-safety,
`engine.py:22-25`), a little more memory, and bot evals can't reuse the
analysis TT (which is a *feature* for calibration, see above).

## Pitfalls checklist (either pattern)

- Re-apply the **complete** option set after any (re)spawn — never rely on a
  live process remembering `setoption`s.
- Keep one serialization primitive per engine instance; never share a lock
  across engines (defeats the purpose) or skip it (UCI protocol corruption,
  `engine.py:12-20`).
- Bot moves are interactive traffic → wrap in
  `review.note_interactive_start/end` regardless of which process serves them
  (contract §1).
- Don't send `ucinewgame`/`game=` on the shared analysis engine; on a
  dedicated bot engine it's harmless and can be used freely per game.
- `SimpleEngine.quit()` on shutdown for each process; orphaned lc0/stockfish
  processes survive uvicorn reloads otherwise (repo already handles this for
  the one engine — duplicate it, don't extend the singleton).

## Bottom line

Nothing in python-chess or Stockfish *prevents* per-move option toggling on
the shared process, and python-chess even auto-restores per-call options. But
the repo-specific failure modes (restart wipes options, watchdog poisoning
mid-toggle, warm-TT strength distortion, lock latency) all disappear under a
second, resource-tiny, options-set-once process — which is also the only shape
that admits lc0+Maia at all. The evidence weighs clearly toward process
isolation.
