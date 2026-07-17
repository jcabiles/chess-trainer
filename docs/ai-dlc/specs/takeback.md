# Delta spec — B6: Takeback control (play-vs-bot)

**Goal (one line):** a per-match **takeback** for bot games — policy
**never / up to 3 / anytime** (persisted, default "up to 3") — that rewinds the
last **full move pair** so it's the user's turn again, with a visible counter;
**a takeback in a RATED game flips it to casual** so it can't inflate the bot-ELO.
**Entirely client-side — no server change, client-owned history.**

Slice: **B6** of [`../roadmap/training-and-portfolio.md`](../roadmap/training-and-portfolio.md)
Chapter 3 (N3 · P3) — the last Phase-A slice. Depends on B2 (shipped). Contracts:
[`../contracts/takeback.md`](../contracts/takeback.md). Gate 1 confirmed 2026-07-17:
**takeback flips rated→casual** · **only on the user's turn when the bot is idle**.

## Decisions (Gate 1)

- **Policy** (per match, persisted via `prefs.js` key `takebackPolicy`, default
  `"three"`): `"never"` · `"three"` (up to 3) · `"anytime"`. Read/normalized on
  init (unknown → default); the selector is a **pre-game setting locked mid-game**
  (like the persona/color pickers).
- **A takeback rewinds the last full move pair** (the user's last move + the bot's
  reply → 2 plies), leaving it the user's turn. Requires ≥2 plies played.
- **Allowed only when `!busy` AND it's the user's turn AND `!result`** (bot has
  already replied; not mid-think — no pending-reply cancellation). The takeback
  **button** is shown only in that state; hidden when policy `"never"`, when the
  count is exhausted (`"three"` + used ≥3), when it's not the user's turn, or when
  `<2` plies exist.
- **Rated → casual on first takeback:** if the game is `rated` when a takeback is
  taken, set `botGame.rated = false` (reuses the existing flag — the B3 save then
  writes `headers_json={"rated": false}`, so B8 excludes it). Show a one-time
  note: "Takeback used — this game no longer counts toward your rating." No
  schema change; no server-side takeback metadata.
- **Counter** on the `botGame` descriptor (`takebacksUsed`, int, **init 0 in
  `startGame`** → resets on new game for free; persisted → survives refresh, so a
  refresh can't refund takebacks under "up to 3"). Displayed: `"three"` →
  "Takebacks: n/3"; `"anytime"` → "Takebacks: n"; `"never"` → control hidden.
- **Global `undo()`/`redo()` are untouched** — takeback is bot-mode-local, reached
  only through a new hub method (botplay.js never imports app.js).

## Client (no server change)

### `static/app.js` — new hub method + descriptor field (HOTSPOT)
- `botGame` gains **`takebacksUsed`** (int, default 0) and **`ratedFlipped`**
  (bool, default false — set true when a takeback flips a rated game to casual;
  drives the note), both added to ALL THREE shape sites — `botSetGame` (`~:436`),
  `persist` (`~:183`), `restore` (`~:283`) — or they drop on persist/restore.
- New hub method **`botTakeback()`**: if `botGame.movesUci.length < 2` → no-op
  return `null`. Else: slice `movesUci` to `length-2`; set `cursor` to the new
  length; **mirror into `state.moves`/`state.cursor`** (same dual-write as
  `botAppendMove`); increment `botGame.takebacksUsed`; if `botGame.rated` was
  true, set it `false` and remember `flippedToCasual = true`; **bump
  `moveToken` + `analysisToken`** (drop stale evals, as `botSetGame` does);
  re-render the board with a **full `syncBoard`-style `ground.set`** (position +
  `turnColor` + clear/lastMove) — NOT bare `setBoardPosition` (which leaves a
  stale turn/lastMove); `persist()`. Return `{takebacksUsed, rated,
  flippedToCasual}` so botplay can update the UI. Expose on the hub
  (`~:1286-1296`) alongside the other `bot*` seams.

### `static/index.html` + `static/style.css` — controls
- **Policy selector** `<select id="bot-takeback-policy">` (Never / Up to 3 /
  Anytime) in `#botplay-body` near the persona picker + rated toggle; token CSS,
  both themes; locked mid-game.
- **Takeback button** `<button id="botplay-takeback" hidden>` in the in-game
  controls row (`.botplay-controls`, near Resign/Retry).
- **Counter + note**: a `#botplay-takeback-count` label (near the button or the
  rating readout) and a `#botplay-takeback-note` (hidden until a rated game flips
  to casual). Token CSS, both themes.

### `static/botplay.js` — policy, guard, handler, UI
- Read/persist the policy via `readUiPrefs().takebackPolicy` /
  `writeUiPref('takebackPolicy', v)`, normalized to the allowlist (default
  `"three"`). Wire the selector like `wirePersonaPicker` (locked mid-game via the
  `busy || live` guard + revert-to-pref; the disabled-attr pattern).
- **`canTakeback()`**: `g = botGetGame()`; return false unless `g && !g.result &&
  !busy && state().mode==='bot-play' && currentPos().turn === g.userColor &&
  g.movesUci.length >= 2`; then policy gate — `"never"` → false; `"three"` →
  `(g.takebacksUsed||0) < 3`; `"anytime"` → true.
- **`takeback()`** (button handler): if `!canTakeback()` return; `const res =
  hub().botTakeback()`; if `res` — `giveUserTurn()`-style restore of dests for the
  user (the board is already re-set by the hub); then **`hub().refreshAnalysis()`**
  — re-evaluate the rewound position. Bumping `analysisToken` in `botTakeback`
  only DROPS a stale in-flight eval; it does NOT fetch a fresh one, so without
  this the eval bar/Analysis panel freeze on the now-deleted position until the
  next move (refuter MED — mirror the user-move/bot-move ordering which each call
  `refreshAnalysis`). Then `reflectControls()`.
- **`reflectControls()`** (existing hook) also reflects: the takeback button
  `hidden` = `!canTakeback()`; the counter text; and the note `#botplay-takeback-
  note` `hidden` = **NOT `g.ratedFlipped`** — a persisted descriptor flag set in
  `botTakeback` ONLY when a takeback flips a RATED game to casual. This both
  survives a refresh (refuter LOW #1) AND never fires for a casual-from-start
  game (refuter LOW #2 — the earlier `takebacksUsed>0 && !rated` predicate wrongly
  showed "no longer counts" on games that never counted). **`reflectControls()`
  must run on the bot-reply handback** (`requestBotMove` non-terminal) and on the
  user's hand-to-bot (`onMove` non-terminal) — else the button never appears
  during live play / stays stale during bot-think (refuter HIGH, found in browser
  verification).
- Never touches `busy`/`replyToken` beyond reading `busy` in the guard (takeback
  is only allowed when idle, so no reply cancellation needed). Injected `api` hub
  only; never import app.js.

## Out of scope
- Server-side takeback enforcement or metadata (client-owned history) · a takeback
  column / any DB schema change · mid-think takeback (Gate 1 — idle-only) ·
  redo of a takeback · takeback in normal analysis play mode (global `undo()`
  unchanged) · takeback in the trap/repertoire trainers · B5/B7.

## Constraints (profile)
- Client-owned history, **no server change** — `/api/bot/*` untouched, server
  stateless. The rated→casual flip rides the existing `rated` flag (no schema).
- Frontend modules receive the injected `api` hub, never import app.js — the
  truncation is a NEW hub method on app.js; botplay.js calls it.
- Preserve botGame↔state lockstep + the three-site descriptor shape agreement +
  busy/replyToken discipline (B2) + save triggers (B3) + persona (B4) + ELO (B8).
  Bump `moveToken`/`analysisToken` on the wholesale truncation.
- Feature branch + PR; commit only implemented+verified+reviewed.

## Verify-by
1. `pytest -q` + `ruff check app tests` green (unaffected — no server change) and
   `node --check static/app.js static/botplay.js`.
2. Browser (Playwright/manual, real engine) — the pass/fail matrix:
   - **"up to 3":** play a few pairs; take back → board rewinds a full pair, it's
     the user's turn, counter "Takebacks: 1/3"; a 4th takeback is blocked (button
     hidden/disabled at 3/3).
   - **Counter resets on new game** (start a new game → 0/3).
   - **"never":** the takeback control is hidden/disabled; no button mid-game.
   - **"anytime":** unlimited takebacks; counter increments.
   - **Policy selector locked mid-game**, persists across reload (default "up to
     3").
   - **Rated flip:** in a RATED game, a takeback flips it to casual — the note
     shows; on finish the saved game has `headers_json {"rated": false}` and the
     bot-ELO (`/api/rating`) does NOT count it.
   - **No regression:** bot replies still work after a takeback (busy not wedged);
     persona/color pickers, resign, save triggers, and the ELO readout all intact.
