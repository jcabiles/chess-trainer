# Spec — B7: clocks + time controls (bot mode)

Last slice of Chapter 3 (play vs bots, N3). Contracts:
[`../contracts/bot-clocks.md`](../contracts/bot-clocks.md). Depends on B2 (bot mode)
+ B3 (saved-PGN path). Refuter-only review (Codex infra-down).

## Goal (one line)
Add client-side dual clocks to bot-play only (untimed default + 5+2/10+0/10+5); a
flag ends the game as a loss; saved bot PGNs emit `%clk` so the ALREADY-BUILT
time-trouble analytics light up. No schema change, no server clock state.

## Decisions (Gate-1)
- **Presets:** untimed (default) + **5+2, 10+0, 10+5** (min+increment sec).
- **Reload:** clocks PAUSE on reload — time spent away/reloading is NOT charged
  (forgiving local trainer; no auto-flag on return; no wall-clock reconciliation).
  **Accepted-by-design consequence** (state it in the ticket + a brief UI hint, so it
  is never filed as a bug): because clocks persist only at move commits, reloading
  mid-move resumes the active clock at its value at the last move — i.e. reloading
  refunds the current move's thinking time. Fine for a single-user local trainer.
- **Takeback:** restore both clocks to their values before the undone move pair.

## Design
### Clock model (client-owned, centiseconds)
- New descriptor fields: `timeControl` (`null` untimed, else `{baseSec:int, incSec:int}`),
  `clockWhite`/`clockBlack` (remaining centis, live), `moveTimes` (int[] — the mover's
  remaining centis at move completion, BEFORE that move's increment is added back,
  aligned to `movesUci`; this pre-increment value is what `%clk` records).
- **Tick loop** (`setInterval` ~200ms in botplay.js): when the game is live (timed,
  not finished, cursor at the tip, not viewing history), decrement the side-to-move's
  clock by the real elapsed delta since the last tick (`performance.now()`), NOT by the
  artificial `scheduleBotReply` think-delay (the bot's clock runs while it "thinks").
  On reach `<= 0`: clamp to 0 → **flag-loss** (below). Reset the last-tick reference to
  "now" on every move commit and on restore, so reload/away time is never charged.
- **On each move commit** (user at `botplay.js:644`, bot at `:749`, slotted INTO the
  existing `botAppendMove → botSetResult → persist → refreshAnalysis` order without
  reordering): (1) record `moveTimes[ply] =` the mover's remaining centis **BEFORE
  adding increment** (the real time-pressure value — keeps the `_time_trouble` buckets
  honest; for no-increment presets like 10+0 this is identical), (2) THEN add `incSec`
  to the mover's live clock, (3) switch the active side, (4) reset the tick reference.
  **Steps 1-4 MUST run synchronously in the same block as `botAppendMove`, BEFORE the
  async `refreshAnalysis()`** — never after an `await`, or a stray `setInterval` tick
  in the gap charges wall-clock time to the wrong side / nobody.
- **Flag-loss:** mirror `resign()` (`botplay.js:775-794`) almost verbatim — White
  flags → result `0-1`, Black flags → `1-0`; `hub().botSetResult(result)`, immediate
  `saveGame()` (NOT `saveOnLeave`), freeze board, status text (e.g. "White flags —
  0-1"). Always saves (a live explicit result), rated or casual.
- **Untimed:** no tick loop, no clock display, `moveTimes` stays empty → server emits
  no `%clk` (back-compat; a bare/old client still valid).

### Takeback × clock (`app.js botTakeback` + `botplay.js takeback`)
Alongside the existing 2-ply truncate (do NOT disturb `takebacksUsed`++ or the
`rated→false`/`ratedFlipped=true` flip): truncate `moveTimes` by 2 and recompute
`clockWhite`/`clockBlack` = each side's remaining after its last SURVIVING move
(`moveTimes` at that ply), or `baseSec*100` if that side has no surviving move.
**Parity rule (state it explicitly):** ply index is 0-based from the game start —
**even index = White's move, odd index = Black's move, independent of `userColor`**
(the White clock restores from the last even-index surviving ply, Black from the last
odd-index). Reset the tick reference. (Free — `moveTimes` already snapshots per-ply
remaining.) NB the restored clocks must be correct **even for casual games** — a
casual takeback has no rated flag to flip, but the clocks still drive a live
flag-loss, so precision matters regardless of rated-ness.

### %clk emission (server, `app/main.py`)
- `BotSaveRequest` gains `moveTimes: list[int] = []` (centis remaining per ply,
  aligned to `movesUci`; empty = untimed).
- In the existing server-side replay loop (`main.py:883-889`), when `moveTimes` is
  non-empty, set `node.comment = "[%clk " + fmt(moveTimes[i]) + "]"` where `fmt` emits
  **`H:MM:SS.s`** (tenths) matching the reader regex `\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]`
  (`pgn.py:30-32`) EXACTLY — e.g. 5730 centis → `0:00:57.3`. Client sends structured
  data only; the server writes the movetext (existing precedent). Guard length
  mismatch (`len(moveTimes) != len(movesUci)` → skip `%clk`, don't crash).

### UI (`static/index.html`, `static/style.css`)
- `#bot-time-control` `<select>` in the bot-play controls: Untimed / 5+2 / 10+0 / 10+5;
  chosen at game start (like the persona picker), persisted via `prefs.js`
  (`botTimeControl`); changing it starts the next game (not mid-game).
- Two clock readouts near the board (`#bot-clock-top` = opponent, `#bot-clock-bottom`
  = user), shown only for a timed game; MM:SS (H:MM:SS if ≥1h); the side-to-move's
  clock visually active; low-time (<10s) emphasis. Tokens-only CSS, AA contrast,
  `:focus-visible` on the select.

## Out of scope
- No clock in ordinary analysis play mode (bot-play only).
- No bot think-time realism (the 400-800ms delay stays cosmetic).
- No server-side clock state (client-owned; stateless server invariant).
- **No DB schema change** — `game_plies.clock_centis` already exists; the parser +
  time-trouble consumer are already built (only emission is new).
- No `Termination` header / no 4th result value (`{1-0,0-1,1/2-1/2}` only).
- No changing the time control mid-game; no presets beyond the three.
- No `rating.py` change (a flag-loss round-trips as a plain decisive result).

## Constraints (invariants)
- app.js descriptor: add the new fields to ALL 3 shape sites (`persist` `:183-197`,
  `restore` `:285-299`, `botSetGame` `:440-454`) + the doc comment `:389-392` — or they
  drop silently. `restore` stays defensive (bad clock field → coerce/null, never crash).
- Preserve the move-commit ordering (`botAppendMove→botSetResult→persist→
  refreshAnalysis`) and the `busy`/`replyToken` staleness machinery.
- `botTakeback` rated-flip + `takebacksUsed` invariant undisturbed.
- Flag-loss saves via the resign-style immediate path, not `saveOnLeave`.
- `%clk` writer format matches the reader regex exactly (else `clock_centis` stays
  None and the feature stays dark).
- Frontend modules use the injected `api` hub; never import app.js. No engine
  involvement (pure client timing).

## Verify-by (end-to-end)
1. `pytest -q` + `ruff check app tests` green — new `main.py` test: a `BotSaveRequest`
   with `moveTimes` produces a PGN whose movetext carries `%clk` comments matching the
   `pgn.py` regex; round-trip (`pgn.parse` the emitted PGN) yields `clock_centis`
   equal to the sent centis (± rounding); `moveTimes=[]` emits NO `%clk` (back-compat);
   a length-mismatch is skipped, not crashed. `node --check static/botplay.js
   static/app.js` clean.
2. Live (Playwright on :8002): start a 5+2 game → both clocks show, the side-to-move's
   ticks down, increment adds on each move; let the user clock hit 0 → game ends as a
   loss with the right result + saves; take back a pair → clocks restore to before it;
   untimed game shows no clocks and saves no `%clk`; reload mid-game → clock resumes
   without charging the away time (no auto-flag). The user's analysis/eval is untouched.
3. A finished timed game auto-analyzes; the **time-trouble insights card populates**
   for bot games (previously dark). Clean up test games from the DB.
