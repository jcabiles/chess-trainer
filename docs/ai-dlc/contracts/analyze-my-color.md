# Contracts — Skip-Opponent-Eval ("analyze my color") in play/analysis mode

Goal: let the user evaluate only their own color's moves, skipping Stockfish on the opponent's,
to cut engine load ~50% (latency + wedge risk). Frontend-led; tiny backend assist.

## Integration points
- `static/app.js`:
  - `onUserMove(orig,dest)` (~376) — live play path. The user drags pieces for BOTH colors (no
    engine opponent). Always calls `POST /api/move {fen, move, useBook:true}` (2 engine analyses),
    then `applyMoveResponse`. **Gate here:** the just-played move's color = `before.pos.turn`
    (`before = positionAt(state.cursor)` captured pre-move).
  - `refreshAnalysis()` (~325, coalesced) — navigation path (undo/redo/goto/move-list/reset). At
    cursor 0 → `/api/analyze`; cursor>0 → `/api/move`. **Gate here:** mover of current ply =
    `positionAt(state.cursor-1).pos.turn`.
  - Render seam: `applyMoveResponse` (~482) → `renderAnalysis`/`renderBookMove` (panel.js). A
    "no engine ran" state already exists (book badge) — reuse the pattern for "not evaluated".
  - `state.moveQuality[]` — per-ply quality tint in the move list; skipped plies → leave
    null/undefined (renders neutral, no tint).
  - `positionAt(cursor)` returns `{pos}` (chessops); `pos.turn` is side-to-move ('white'/'black').
    SAN is computed client-side (movelist.js) so a skipped move still lists correctly.
- `chess-training:ui:v1` localStorage (PR #4): `readUiPrefs()` / `writeUiPref(key,val)` — these
  are PRIVATE inside `movelist.js`; extract to a shared `prefs.js` so app.js can use them. Add
  `analyzeColor: 'both'|'white'|'black'` (default `'both'` = today's behavior).
- Backend `POST /api/move` (`app/main.py` ~262) — does 2 engine analyses + legality + book. For
  the live-play skip, add an optional `analyze: bool = true`; when false → validate legality +
  book only, **skip the engine**, return `analysis: null`. Preserves the "server is legality
  authority" contract (CLAUDE.md) without an engine call. Navigation skip needs NO server call
  (the move was already validated when played) — `refreshAnalysis` just renders the neutral state.

## Contracts to respect
- Server stays the legality + analysis authority (CLAUDE.md) → prefer `/api/move analyze=false`
  over client-only move recording for live play.
- `analyzeColor='both'` MUST reproduce today's behavior exactly (opt-in feature).
- Tokens-only CSS for the new control; persisted via the existing ui-prefs key (don't touch the
  `:session:v1` game-state shape).
- Only play mode (not setup/trap/rep/review).

## The semantics fork (resolved: A)
To get the QUALITY of my move ("did I blunder?"), `/api/move` analyzes both the before-position
(= after opponent's move) and the after-position. Decision: **A — analyze only my moves.** After I
move → quality + eval shown; the opponent's move shows nothing. ~50% fewer engine calls. Trade-off
(accepted): no eval/best-move hint while I'm deciding my move. Cursor 0 (start) is exempt — it
always shows the opening eval.
