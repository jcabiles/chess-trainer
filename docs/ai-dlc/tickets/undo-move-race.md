# Tickets — fix undo/turn corruption (async move-write race)

Spec: `docs/ai-dlc/specs/undo-move-race.md`. Single owner of the hotspot
`static/app.js` throughout — tickets are sequential (T1 → T2), not parallel.

## T1 — Guard the move-write against stale navigation / state swaps (the fix)

**File (sole owner):** `static/app.js` — `onUserMove` + the wholesale-swap sites.

**Change (the guard, in `onUserMove`):**
- Add `let moveToken = 0;` at module scope (near the `analysisToken` guard fields).
- Before any `await` (at the point `before = positionAt(state.cursor)` is computed,
  which is before the `askPromotion` await), capture `const insertAt =
  state.cursor;`, `const myMove = ++moveToken;`, and define
  `const stale = () => state.mode !== 'play' || myMove !== moveToken ||
  state.cursor !== insertAt;`.
- After the promotion `await` resolves (before firing `setStatus`/`/api/move`):
  `if (stale()) { syncBoard(); return; }`.
- Gate the existing `catch (err)` block by `stale()`: on a stale error,
  `syncBoard(); return;` *without* `setStatus(err.message, true)`.
- After the `/api/move` await resolves (before the `!data.legal` check):
  `if (stale()) { syncBoard(); return; }`.
- Key the commit off `insertAt`, not a re-read of `state.cursor`: the three
  `.slice(0, insertAt)` calls, the two index-assigns `[insertAt]`, and
  `state.cursor = insertAt + 1`.
- Do **not** add `setStatus('')` on the bail path — the navigating action's own
  `refreshAnalysis` owns the status line.

**Change (the invalidation surface — Codex/refuter finding):** add a single
`moveToken++;` at each wholesale play-state replacement so an in-flight move is
dropped even if the cursor lands back on `insertAt` against different state:
- `reset()` (app.js:585), `loadFen()` success (app.js:~628),
  `enterReview()` / `exitReview()` (app.js:~750/808), session **restore**
  (app.js:~225).

**Acceptance:**
- Diff stays inside `static/app.js`; no other module or the injected-`api`
  contract changes.
- Happy path (no navigation, play mode) commits byte-identically to today: same
  indices, `moveQuality`/`moveRetro` lockstep, `cursor = insertAt + 1`.
- `.venv/bin/python -m pytest -q` green; `.venv/bin/ruff check app tests` clean
  (sanity — no backend edit).

**Done-condition (runnable):** T2's MCP script shows history intact after (a) the
drag-then-undo race and (b) a drag-then-switch-to-review race, and a normal drag
still commits + analyzes.

## T2 — Scripted Playwright-MCP race regression (guards against return)

**Artifact:** save the exact drag-then-undo repro as a re-runnable script at
`docs/ai-dlc/verify/undo-move-race.mcp.js` (a Playwright `page`-driven snippet;
no new npm/test-runner dependency — this repo has no JS harness, so it is a
documented MCP script run at verify time, not headless CI).

**Script does:**
1. Navigate to the live app; reset to a clean board.
2. Play `e4 e5 Nf3 Nc6` via trusted `page.mouse` drags (chessground needs real
   mouse events — see memory `chessground-needs-trusted-mouse`).
3. Shim `window.fetch` to delay `/api/move` ~2.5 s.
4. Drag `Bf1-c4`; wait for "Analyzing…"; press `ArrowLeft` (undo).
5. Read `#move-list` text + board FEN after the delayed response lands.
6. **Cross-mode case:** with the delay still in place, drag a move, then switch to
   review / open a game before it resolves; assert the review list is untouched.
7. Restore `fetch`; play one normal move; assert it commits + analyzes.

**Acceptance:**
- Run against **pre-fix** code → asserts the corruption (`…2.Nf3 Bc4`, Nc6
  dropped) — proves the script actually catches the bug.
- Run against **post-fix** code → `#move-list` == `1.e4 e5 2.Nf3`, White to move,
  board FEN == the 3-ply position; normal move still works.
- Leaves the board reset and `fetch` restored (no residue in the user's session).

**Done-condition (runnable):** the script prints PASS on post-fix and FAIL on
pre-fix (checked by temporarily stashing the T1 change).

---
_Reviews folded in:_
- _Refuter (APPROVE-WITH-CHANGES): catch-path gating; rationale + board-not-frozen note._
- _Codex/GPT-5 (sound-with-changes): early promotion check; widened invalidation
  surface (reset/loadFen/review-swap/restore bump `moveToken`); `mode !== 'play'`
  clause; cross-mode regression case. Design shape confirmed — no better approach._
