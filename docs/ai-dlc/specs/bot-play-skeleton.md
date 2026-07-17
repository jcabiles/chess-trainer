# Delta spec — B2: Bot-play walking skeleton

**Goal (one line):** play one full untimed game against one default bot in
the browser — new `bot-play` mode + an isolated weakened-Stockfish
`BotEngine` — the thinnest end-to-end path for roadmap Chapter 3.

Slice: **B2** of [`../roadmap/training-and-portfolio.md`](../roadmap/training-and-portfolio.md)
(N3). Architecture per approved B1:
[`../research/chess-bots.md`](../research/chess-bots.md) §7. Contracts:
[`../contracts/bot-play.md`](../contracts/bot-play.md). Requirements
confirmed at Gate 1 (2026-07-16): play-area section · survive refresh ·
undo disabled until B6 · Maia detection included (user's explicit Gate-1
choice — install running; move source stays Stockfish until B4).
Dual-reviewed (refuter + Codex gpt-5.6-sol); findings folded throughout —
see the ticket file's review log.

## Server

### NEW `app/bot_engine.py` — isolated bot engine (B1 §7.1 lifecycle contract)

- Own Stockfish process, resolved like the analysis engine does:
  `STOCKFISH_PATH` env, else `shutil.which("stockfish")` (`engine.py`
  resolver pattern) — **completely separate from the analysis engine**:
  never touches its lock, options, or warm TT. Configured on every (re)spawn:
  `Threads=1`, `Hash=16`, `UCI_LimitStrength=true`, `UCI_Elo=1350`
  (fallback source B; floor is 1320 — B1 §1).
- **Lifecycle (mirrors `app/engine.py` discipline):** import-safe when the
  binary is absent; lazy start; ONE `asyncio.Lock` for all access; hard
  timeout + watchdog restart; restart re-applies **the full option set**
  (must not repeat the shared engine's restart-only-Threads/Hash gap — B1
  §7.1); clean shutdown in the FastAPI lifespan next to the existing engine.
- **Seam API (B1 §7.1: candidates, not bare bestmove):**
  `candidates(fen, k=1) -> [{uci, san, scoreCp}]` implemented as MultiPV=k
  at a small fixed budget (e.g. `movetime≈300ms`). B2 always calls `k=1`
  and plays `[0]`; B5's persona layer consumes `k>1` without an API break.
- `detect_maia() -> {lc0: bool, weights: [paths]}` — readiness signal only
  (user-mandated at Gate 1); no lc0 move path in B2.
- **Testability:** the bot route depends on a `get_bot_engine` FastAPI
  dependency in `app/main.py` (same idiom as the existing `get_engine`
  dependency, `main.py` ~231) — overridable in tests; suite green with no
  binary.

### `app/main.py` — two routes (JSON camelCase, matching `MoveResponse`)

- `POST /api/bot/move` `{fen}` → `{moveUci, moveSan, fen}` (fen = after the
  bot's move). Validates: parseable FEN; **valid position**
  (`board.is_valid()` — rejects syntactically-fine-but-illegal positions);
  **not terminal** (mate/stalemate/insufficient material → 400 with
  reason). Stateless — client owns history. 503 when the bot engine is
  unavailable (binary missing or spawn failed) — the analysis engine's
  health is irrelevant and unaffected either way.
- `GET /api/bot/status` → `{available, personaLabel, maia}`.
  `available` **means: binary resolvable** (lazy engine may not be running
  yet); runtime failures surface as 503 on `/api/bot/move`, not here.

## Client

### NEW `static/botplay.js` (module pattern: injected `api`, never imports app.js)

- `registerModeHandlers('bot-play', {onMove, exit})` + `PRACTICE_MODES`
  entry (loud-fail dispatch). Note: `PRACTICE_MODES` does NOT control
  persistence — see the persistence contract below.
- **Start flow:** pick color; board orients to the user's color; if the bot
  is White, request its first move on start. **Single-flight rule:** one
  in-flight bot request max — Start/color clicks, user moves, and resign
  are inert while a request or think-timer is pending (busy gate).
- **User-move path (owned by botplay's `onMove`, NOT `onUserMove` — the
  play path treats every non-play response as stale):** legality +
  promotion via chessops exactly like the play path; append to
  client-owned history (truncate redo suffix at cursor); persist; then
  schedule the bot reply. On any failure, roll the board back to the
  pre-move position.
- **Auto-reply:** think-delay timer (~400–800ms fixed) + fetch
  `/api/bot/move`. **Staleness protection** (mint token before the timer,
  re-check inside the timer callback AND after the fetch — the traps.js
  scheduled-callback idiom): invalidated by mode exit, new game, color
  change, **resign**, **an already-recorded terminal result**, restart, and
  undo-of-state (n/a in B2 but the guard is cheap). While the bot is to
  move, the board rejects user input (chessground movable = user's color
  and only on the user's turn).
- **Engine-down handling (client):** on 503/network failure the user's move
  stays committed; show an error line + **Retry** button that re-requests
  the bot move; the game remains persisted and resumable.
- **Game end:** automatic ends only — checkmate, stalemate, insufficient
  material (chessops over the client history) — plus **resign**. Claimable
  draws (threefold, 50-move) are OUT of scope for the skeleton (needs a
  claim UI; note in ticket). Result shown; "New game" offered; finished
  games accept no moves.
- **Exit:** restores the prior play session (mechanism below).

### `static/app.js` — persistence + gating (single-owner hotspot)

**Persistence contract (rewritten after review — the single `STORAGE_KEY`
slot means bot-play must EMBED the prior play snapshot, not coexist with
it):**

- **Entry:** capture the prior play session via the in-memory
  snapshot/restore seam the trainers use (`snapshotPlay()`/`restorePlay()`
  pattern) **and serialize that snapshot into the persisted bot-play
  entry**.
- **`persist()`:** new `mode:'bot-play'` branch ABOVE the practice-mode
  early-returns, writing
  `{mode:'bot-play', botGame:{baseFen, movesUci, cursor, userColor,
  personaLabel, result|null}, priorPlay:{...play-shape snapshot}}`.
- **`restore()`:** new explicit `bot-play` branch (today the union only
  handles 'setup' and falls through to `mode='play'` — without this branch
  refresh would silently load the bot game as plain play): validate the
  shape, restore the bot game, re-enter bot-play mode, hand `priorPlay` to
  botplay.js for exit-restore. **Turn check on restore:** if it's the
  bot's turn (refresh killed a pending reply), schedule the bot move.
- **Exit:** restore the prior play session — from the in-memory snapshot
  (same-session exit) or from the persisted `priorPlay` (exit after a
  refresh) — then normal play `persist()` resumes ownership of the slot.
- **Undo/redo:** `undo()`/`redo()` already no-op outside play mode; the
  B2 work is UI-only — disable the buttons + keyboard shortcuts while in
  bot-play (until B6). No "redo stack" exists (redo = cursor < moves.length).

### Analysis during bot games — **available, user-toggled (Gate-1 decision)**

The analysis panel (Full / Blunders / Off) stays live during bot games —
the user toggles it as they like. Review established the eval pipeline is
`mode==='play'`-gated in three places (refresh trigger on selector change
~`app.js:1176-1185`; the analysis response-write staleness check ~`:512`;
the analysis-mode gate ~`:477`). **B2 widens those gates to accept
`bot-play`** so the current position is evaluated exactly as in play mode,
with the SAME staleness discipline — every eval response re-checks it's
still the same mode + position before writing, so a late eval from a
superseded position (after a bot reply, undo-n/a, mode exit) is dropped.
Eval calls go to the shared analysis engine; the bot process is untouched.
Owned by T3 (gate widening) + T5 (trigger a refresh after the user's move
and after the bot's reply lands).

### `static/index.html` + `static/style.css`

"Play vs Bot" collapsible section in the play area (analysis-mode panel is
the look/feel template): persona line (fuzzy label, no precise Elo claim —
B1 §7.6; e.g. "Casual sparring bot"), color pick, Start, Resign, Retry
(hidden unless needed), status/result line, subtle Maia-ready indicator.
Start disabled with a hint when `/api/bot/status.available` is false.

## Out of scope

More personas/styles · Maia as move source · clocks · save-to-DB (B3) ·
blunder/error model (B5) · takeback control (B6) · think-time realism ·
personal ELO (B8) · claimable draws. No changes to `app/engine.py` or any
shared-engine invariant (analysis eval in bot-play reuses the existing
shared-engine path — only the client-side mode gates widen).

## Constraints (profile)

- Stateless server (history client-side); only client-side localStorage
  persistence.
- Never commit `data/games.db` / `data/games/`.
- Feature branch + PR; Conventional Commits; commit only
  implemented+verified+reviewed.

## Verify-by

1. `pytest -q` green with **no engine binary** (fake `get_bot_engine`
   dependency override). New tests:
   - `/api/bot/move`: legal reply (bot-as-White first move included);
     unparseable FEN 400; **valid-syntax-but-illegal position 400**;
     terminal 400 with distinct reasons (mate/stalemate/insufficient);
     engine-down 503; SAN/FEN response consistency.
   - `/api/bot/status`: available true/false; maia detection shape.
   - `bot_engine` unit: lock serializes concurrent calls; hard-timeout →
     restart → **full option set re-applied**; lazy-start failure →
     `EngineUnavailable` (import-safe); lifespan shutdown clean;
     **isolation: bot-engine failure leaves the analysis engine's state
     untouched** (fake-seam assertion).
2. `ruff check app tests` green.
3. Browser (Playwright/manual, real engine) — the roadmap pass/fail plus
   the review-flagged races:
   - start as White AND as Black; bot replies arrive automatically +
     legally; play to a real end (mate or resign).
   - **refresh while the bot is thinking** → game resumes AND the bot
     completes its move; refresh on user's turn → resumes waiting.
   - **exit after a refreshed bot game** → prior play session restored
     (the localStorage-collision case).
   - resign while a bot request is in flight → reply discarded, result
     stands; double-click a move / rapid Start clicks → single-flight
     holds.
   - undo/redo buttons + keyboard inert in bot mode.
   - analysis panel usable during a bot game: toggle Full/Blunders/Off,
     eval refreshes for the live position after user + bot moves; a late
     eval from a superseded position never writes (staleness holds).
