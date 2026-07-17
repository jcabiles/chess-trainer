# Contracts — B6: Takeback control (play-vs-bot)

Read-only scan (contract-mapper, 2026-07-17). Evidence `file:line`.

## Move history + descriptor
- `botGame` (app.js:74) shape agreed at THREE sites — `botSetGame` (`:436-448`),
  `persist` (`:183-195`), `restore` (`:283-295`). A new per-game field must be
  added to all three or it drops on persist/restore.
- `botAppendMove(uci)` (`app.js:467-475`) truncates redo suffix, pushes, advances
  cursor, and **mirrors `botGame.movesUci`/`cursor` into `state.moves`/`cursor`**
  (botGame↔state lockstep — the invariant). Board renders from history via
  `positionAt(count)` (`app.js:526`) → `syncBoard` (`app.js:552`).
- **No truncate/"set position from movesUci" seam exists** (hub surface
  `app.js:1286-1296`). A takeback needs a NEW hub method (`botTakeback()`):
  slice `movesUci` to `len-2`, set cursor, mirror into `state.moves`/`cursor`,
  bump `moveToken`+`analysisToken` (as `botSetGame` does `:455-456`, to drop
  stale evals), then a `syncBoard`-style full `ground.set` (turnColor+lastMove) —
  NOT bare `setBoardPosition` (`app.js:500`, board-part only → stale turn/lastMove).

## busy / replyToken (B2)
- `busy` (`botplay.js:25`) + `replyToken` (`:26`) + `thinkTimer` (`:27`).
  `invalidateReply()` (`:46-52`) bumps token + clears timer — the primitive a
  mid-think takeback must reuse.
- **Contract (`botplay.js:582-590`):** an invalidated timer/await callback returns
  WITHOUT clearing `busy` (assumes a newer op owns the gate) → a mid-think
  takeback must clear `busy=false` itself (like `resign` `:668-669`), else the
  board wedges.
- **Safe/simple contract:** enable takeback ONLY when `!busy` AND user's turn
  (`currentPos().turn === game.userColor`) AND `!game.result` — mirrors the
  `rollback`/color/persona guards. Avoids mid-think cancellation entirely.

## Global undo() — do NOT touch
- `undo()`/`redo()` (`app.js:894-910`) are hard-gated `mode!=='play'` → return,
  and pull in opening/trap refresh. Takeback stays bot-mode-local, reaching app
  state only via the hub; never call/extend `undo()`.

## Pref + per-game count
- Policy pref (never/up-to-3/anytime) via `prefs.js` (`readUiPrefs`/`writeUiPref`,
  key `chess-training:ui:v1`), mirror `botPersona`/`chessComRating`; default
  "up to 3" consumer-side; normalize on read.
- Per-game **count → `botGame` descriptor field** (`takebacksUsed`), init 0 in
  `startGame`'s `botSetGame` (resets on new game for free; survives refresh →
  closes the "refresh refunds takebacks" loophole a transient would open). Add to
  all three shape sites.

## Save + ELO integrity (THE decision)
- `snapshotGame` (`botplay.js:404-414`) copies `movesUci.slice()` + `result`
  **synchronously at save time**; save fires only at a terminal/leave
  (`:553,649,678`, `saveOnLeave:420-433`). `/api/bot/save` replays whatever
  `movesUci` it gets into the PGN (`main.py:806-817`).
- **A takeback mutates `movesUci` BEFORE the save snapshot** → the persisted game
  is the post-takeback (cleaned) line. B8 ELO is a read-model recomputed from
  saved rated games (`main.py:1517`, `rating.build_rating`) — so undoing a blunder
  in a RATED game inflates the bot-ELO. No server-side takeback metadata exists
  (`headers_json` is just `{"rated":bool}`); recording "takebacks used" would be a
  schema change. Options: disallow takeback when rated · accept cleaned-line ELO ·
  flip the game to casual on first takeback (reuse the `rated` flag, no schema).

## UI
- Policy selector near persona picker/rated toggle (`index.html:141,149`), locked
  mid-game like them (`botplay.js:240` guard + revert-to-pref). Takeback BUTTON
  near Resign/Retry (`.botplay-controls` `index.html:164-168`), enabled only
  mid-game on the user's turn, hidden when policy==="never"/exhausted (the
  `hidden`-attr idiom of `showResign`/`showRetry` `:120-128`). `reflectControls`
  (`:131-138`) is the hook to reflect button/counter state.

## Invariants at risk
- Client-owned history, no server enforcement (server stateless) · botplay.js
  never imports app.js (new hub method required) · botGame↔state lockstep ·
  three-site shape agreement · busy/replyToken discipline · save/ELO integrity ·
  bump moveToken/analysisToken on wholesale truncation.

## Sharp edges (ranked)
1. **Rated-game integrity** — takeback rewrites the saved PGN → ELO inflation.
2. **Takeback-while-thinking** — invalidateReply()+clear busy, or just gate on
   `!busy` (recommended).
3. **Re-render after truncation** — new hub method, full ground.set, bump tokens.
4. **Per-game count storage** — descriptor field (not transient).
5. **Selector lock parity** + button hidden-attr idiom.
6. **Do not touch global undo().**
