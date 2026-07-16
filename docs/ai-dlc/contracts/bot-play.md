# Contracts — Play-vs-bots epic (pre-roadmap scan, 2026-07-16)

Read-only map for the bots chapter (roadmap: `../roadmap/training-and-portfolio.md`
Chapter 3). Cites, not repeats: engine-reliability.md · analysis-speed.md ·
appjs-split.md · game-review-coaching.md · auto-analyze.md · analyze-my-color.md ·
game-accuracy-elo.md · dual-best-move.md · blunder-trainer.md · eval-toggle.md ·
analysis-mode-panel.md.

## 1. Engine seam (`app/engine.py`)

- Public surface is **eval-only**: `analyze(fen, speed)` (`engine.py:545`),
  `analyze_interactive_multi` (`:480`), `analyze_multi` (`:416`) — all funnel
  through `_run_analyse` (`:336`) behind ONE `asyncio.Lock` (`:357`) + hard
  timeout watchdog (`:388-400`). **No bestmove-at-reduced-strength call exists.**
- **No strength limiting anywhere**: `start()` configures only `Threads`/`Hash`
  (`engine.py:235`); zero hits for `Skill Level`/`UCI_LimitStrength`/`UCI_Elo`.
  UCI options are **process-global** — toggling strength per bot move would
  degrade concurrent human evals unless carefully set/reset per call, and
  `restart()` (`:284-332`, can fire mid-call) re-applies only Threads/Hash, so
  bot options would be silently lost after any restart.
- Warm-TT rule (`:369-374`): no call site passes `game=`; a bot interleaving its
  positions on the same TT is fine, but any clean-slate need would cold-start
  the human's analysis too. Import-safety contract (`:22-25`) binds any new code.
- A live bot-move request is an interactive engine call → MUST wrap in
  `review.note_interactive_start/end` (pattern: `main.py:478-494`, `1413-1426`).
- **Net: the research spike's engine question is really "should bot strength be
  process-isolated" (second engine: Maia/lc0 or a second Stockfish) — the shared
  lock/TT/global-options model argues yes.**

## 2. Play-mode flow (`static/app.js`, `traps.js`)

- Plug-in seam: `registerModeHandlers('bot-play', {onMove, exit})`
  (`app.js:118-133`); add to `PRACTICE_MODES` (`:129`) for loud-fail dispatch
  (`:944-958`). Pattern: `traps.js:735`, `repertoire.js:418`, `trainer.js:616`.
- **Auto-opponent replies today are scripted replay, not engine calls**
  (`traps.js:440-501`: walks `trap.mainLine`, 400ms setTimeout, no server
  round-trip). A live "fetch bot move → apply" path is new; must mint/respect
  staleness tokens like `onUserMove` (`app.js:459-557`: capture-before-await +
  `stale()` re-check) including for the bot's own scheduled move.
- Takebacks: global `undo()`/`redo()` (`app.js:627-661`) are `mode==='play'`-gated
  with zero per-mode policy hooks — a bot mode needs its own undo semantics.
- `persist()` skips all practice modes (`app.js:152-156`); bot games plausibly
  WANT survive-refresh persistence → new `mode:'bot-play'` branch in the
  `STORAGE_KEY` discriminated union (`:149-180`) if so.
- Bot match settings (persona/time control/takebacks) → ui-prefs seam
  (`prefs.js`), consumer-side allowlist idiom (`app.js:73-86`).

## 3. Persistence + review pipeline

- Single save path: `_import_pgn_batch(pgn_text, my_color_override, engine,
  source=...)` (`main.py:641-711`) — needs a **well-formed PGN string**
  (White/Black/Result headers feed the dedup hash, `pgn.py:142-155`).
  `source TEXT` (`storage.py:64`) is unconstrained → can carry `"bot"` without
  schema change. `headers_json` (`storage.py:56`) exists but is **always None
  and never read** — possible bot-metadata carrier, currently dead/unvalidated.
  No columns for persona/ELO/time-control; anything more = real schema change
  (versioned migrations, `storage.py:39,193-212`) needing an explicit spec.
- Auto-analysis free if reusing `_import_pgn_batch` (`_kick_auto_analysis`
  guards, `main.py:236-262`); a bespoke save path must replicate both guards.
- Clock: `pgn._parse_clock_centis` (`pgn.py:97-106`) already stores
  `%clk` → `game_plies.clock_centis`; embed `%clk` in saved bot PGNs and the
  existing time-trouble insights light up **for free**.
- `app/accuracy.py` computes retrospective per-game est-Elo — a running
  personal rating updated by W/L/D vs graded bots is new logic (prefer a
  derived read-model over stored ratings history → no schema change).

## 4. Confirmed greenfield

Move-strength limiting · bestmove endpoint · live auto-reply mechanism ·
clock/timer enforcement (zero play-UI clock code; only post-hoc `%clk`
analytics) · persona/ELO metadata storage · running personal ELO ·
takeback policy. Takeback/clock enforcement is client-side by default
(consistent with client-owned move history); any server-side session concept
would be a first departure from "stateless per request except review".

## Primary risk

The bot's move generation is a **new consumer of the single engine lock** with
no existing analog; contention with interactive `/api/move` + the background
reviewer, process-global strength options, and restart-survival gaps make the
engine-isolation decision (research slice B1) the load-bearing choice of the
whole epic.
