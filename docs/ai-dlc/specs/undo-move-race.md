# Delta spec — fix undo/turn corruption from the async move-write race

**Goal:** A move-analysis response that arrives *after* the user has navigated
(undo / redo / jump) must never mutate move history. Kills the "wrong side to
move / one side gets an extra move" corruption in analysis (play) mode.

## Problem (confirmed, with live repro)

`static/app.js:onUserMove` is `async`: it drags → `await postJSON('/api/move')`
(Stockfish, ~1–2 s) → **then** writes history reading `state.cursor` *after* the
await (lines 474–487):

```js
state.moves = state.moves.slice(0, state.cursor);  // post-await cursor
state.moves.push(uci);
state.cursor += 1;
```

`undo()` / `redo()` / `goto()` and the ArrowLeft/ArrowRight shortcuts mutate
`state.cursor` synchronously with **no in-flight guard**. Undo during "Analyzing…"
→ the late response truncates+pushes against the moved cursor → history corrupts →
`syncBoard` derives `turnColor` from the replayed (now-wrong) history → turn flips.

Repro (Playwright-MCP, verified 2026-07-10):

| step | move list | state |
|------|-----------|-------|
| before | `1.e4 e5 2.Nf3 Nc6` | cursor=4, White to move |
| drag `Bf1-c4`, then undo mid-analysis | `1.e4 e5 2.Nf3 Bc4` | Nc6 dropped; White's bishop move lands in Black's column |

`refreshAnalysis` (app.js:383) already solved the *same* class of race for the
eval render with a stale-guard token (`analysisToken` / `analysisInFlight`); the
move-**write** path never got the equivalent guard.

## Fix — capture-at-drag-time + stale-drop (chosen approach)

In `onUserMove`, capture the insert position and a per-move token **before any
await** (before `askPromotion` too — undo can fire while the promotion `<dialog>`
is open, since ArrowLeft isn't in its Esc guard). After the `/api/move` await
resolves, bail without touching history if either changed:

```js
// module scope — a monotonic "play-state generation". Bumped by onUserMove AND by
// every wholesale play-state replacement (see "invalidation surface" below).
let moveToken = 0;

// onUserMove, at the top (line ~442, alongside `before`)
const insertAt = state.cursor;
const myMove   = ++moveToken;
// One predicate, checked after every await. Any of: mode left play, a newer move
// or a wholesale state swap bumped the token, or the cursor moved → this move is stale.
const stale = () => state.mode !== 'play' || myMove !== moveToken || state.cursor !== insertAt;

// promotion await — undo/mode-switch can happen while the <dialog> is open; check
// BEFORE we bother firing the network call / setting "Analyzing…"
if (isPromotion(before.pos, orig, dest)) {
  try { promo = await askPromotion(); } catch { syncBoard(); return; } // cancel
  if (stale()) { syncBoard(); return; }
}
...
let data;
try {
  data = await postJSON('/api/move', {...});
} catch (err) {
  if (stale()) { syncBoard(); return; }         // stale failure must not stomp status
  setStatus(err.message, true); syncBoard(); return;
}
if (stale()) { syncBoard(); return; }            // stale success → drop the write
// existing legal check + commit, but keyed off insertAt (not a re-read of cursor):
if (!data.legal) { setStatus('Illegal move.', true); syncBoard(); return; }
state.moves        = state.moves.slice(0, insertAt);
state.moveQuality  = state.moveQuality.slice(0, insertAt);
state.moveRetro    = state.moveRetro.slice(0, insertAt);
state.moves.push(uci);
state.moveQuality[insertAt] = ...;
state.moveRetro[insertAt]   = ...;
state.cursor = insertAt + 1;
```

**Why each clause of `stale()` is load-bearing:**
- `state.cursor !== insertAt` — the common navigate-away case (undo/redo/jump while
  analyzing).
- `myMove !== moveToken` — the cursor has *numerically* returned to `insertAt` but the
  history/base underneath changed: you navigate away and play a *different* move there,
  OR a wholesale swap (reset / loadFen / review enter-exit) replaced the state and
  something later put the cursor back at the same number. Without the token these
  false-negative into a garbage commit. A pure undo-then-redo does NOT trip it, which
  is correct — undo/redo never mutate `state.moves`, so that commit is byte-identical.
- `state.mode !== 'play'` — a cross-mode belt-and-suspenders: if a play move is still
  in flight when the user enters review / setup / a trap mode, its response never writes.

**Invalidation surface (Codex + refuter finding — wider than just undo/redo/goto):**
`moveToken` must be bumped by **every wholesale play-state replacement**, not only by
`onUserMove`, so an in-flight move is invalidated even when the cursor coincidentally
lands back on `insertAt` against a *different* base position or move list:
- `reset()` (app.js:585), `loadFen()` (app.js:628) — replace `baseFen`/`moves`/`cursor`.
- `enterReview()` / `exitReview()` (app.js:~750/808) — swap `baseFen`/`moves`/`cursor`
  and `mode`. (The `mode` clause already covers the *review* half; the token bump covers
  the return-to-play half, where mode is `play` again with a restored cursor.)
- session **restore** (app.js:~225) — replaces `moves`/`cursor` on load.
Each is a single `moveToken++;` (or `++moveToken`) at the point of replacement.

On bail (any clause), `syncBoard()` snaps the board back to the true position; status is
left to the navigating action's own `refreshAnalysis` (do not force `setStatus('')` — it
would stomp an in-flight analyze), and the `catch(err)` path is gated identically so a
stale *network error* can't stomp the status bar for an abandoned move.

Undo stays **instant** — the abandoned move simply never commits, which is the
behavior the user wants ("I try a move and undo it when I realize it won't work").

## Files / interfaces to touch

- `static/app.js`:
  - `onUserMove` — the guard (add `moveToken` at module scope; capture
    `insertAt`/`myMove`; `stale()` check after promotion, in `catch`, and after the
    move await; key the commit off `insertAt`).
  - `reset` / `loadFen` / `enterReview` / `exitReview` / session **restore** — one
    `moveToken++;` each, at the wholesale play-state replacement, to invalidate any
    in-flight move (the invalidation surface — see the fix section).

## Sibling-path audit (result)

- `refreshAnalysis` — already guarded (`analysisToken`). No change.
- `refreshOpening` (app.js:649) — builds body **before** the await, only
  `renderOpening` **after**; never writes move/cursor state. Worst case a stale
  opening *name* renders (cosmetic). **Out of scope** (see below).
- `onUserMove` is the only path that writes move/cursor state *from a stale-able
  post-await point*. But `reset`/`loadFen`/`enterReview`/`exitReview`/`restore`
  **replace** that state synchronously, and a stale `onUserMove` response can land
  against the replaced state — so those sites must bump `moveToken` even though they
  are not themselves async writers. (Codex + refuter finding; corrects the earlier
  "onUserMove only" scoping.)

## Out of scope

- Cosmetic stale-render of the opening name / traps chip after fast navigation
  (non-corrupting).
- Any change to the *navigation* behavior of `undo/redo/goto` (they stay instant —
  the fix lives on the write side; they already move only `cursor`, caught by the
  `state.cursor !== insertAt` clause without needing a token bump).
- **Freezing the board during an in-flight request.** The board stays draggable
  while `/api/move` is pending, so a fast second drag is reachable via ordinary
  play (not just the undo race). The guard handles it correctly — the superseded
  move is dropped (last move wins) — but a dropped move shows only a board
  snap-back, no explanatory message. Freezing the board / a queued-move UX is a
  separate follow-up, not this fix.
- Backend / API / DB — none touched.

## Constraints (from profile)

- Change is entirely inside `static/app.js` (the hub). No module imports app.js;
  no injected-`api` contract changes. No CSS/markup, no a11y surface.
- Pure Python modules stay engine-free; `pytest` must stay green (no backend edit,
  so this is a regression guard, not a new expectation).
- No DB schema change.

## Verify-by (end-to-end)

1. `.venv/bin/python -m pytest -q` → green (proves no backend regression) and
   `.venv/bin/ruff check app tests` clean (no app-py change, sanity only).
2. **Playwright-MCP race regression** (the primary check — no automated JS harness
   exists in this repo, so this is a scripted MCP run, documented in the ticket):
   - Play `e4 e5 Nf3 Nc6`. Shim `window.fetch` to delay `/api/move` ~2.5 s.
   - Drag `Bf1-c4`; while "Analyzing…", press ArrowLeft (undo).
   - **PASS:** move list stays `1.e4 e5 2.Nf3` (Nc6 intact, Bc4 dropped), White to
     move, board FEN matches the 3-ply position. (Pre-fix: `…2.Nf3 Bc4`, corrupt.)
   - Restore `fetch`; confirm a normal drag (no undo) still commits + analyzes.
3. **Cross-mode invalidation** (Codex finding): with `/api/move` delayed, drag a
   move in play mode, then switch to review / open a game before the response lands.
   **PASS:** the review game's move list is untouched by the stale play-move response
   (and returning to play shows no phantom move).
