# Tickets — B7: clocks + time controls (bot mode)

Spec: [`../specs/bot-clocks.md`](../specs/bot-clocks.md).
Contracts: [`../contracts/bot-clocks.md`](../contracts/bot-clocks.md).
Branch: `feat/bot-clocks` off up-to-date main.
Waves (disjoint owners): **W1:** T1 ∥ T2 → **W2:** T3 (needs T2 descriptor +
T1 endpoint contract) → **W3:** T4 verify → T5 review → T6 close-out.
Refuter-only (Codex infra-down). All 5 refuter findings already folded into the spec.

> **Sequencing heads-up:** a separate held effort (`board-bots-redesign`, Gate-2 HOLD)
> restructures the bot-play UI + renames personas. It does NOT overlap B7's clock
> logic, but both touch `static/index.html`/`style.css`/`botplay.js` — whichever merges
> second rebases. B7 does not touch persona names.

## T1 — server `%clk` emission (W1) — backend, independent
`app/main.py`: `BotSaveRequest` gains `moveTimes: list[int] = []` (centis remaining
per ply, aligned to `movesUci`, pre-increment). In the existing server-side PGN replay
loop (`main.py:883-889`), when `moveTimes` is non-empty AND
`len(moveTimes) == len(movesUci)`, set `node.comment = "[%clk " + fmt(centis) + "]"`
where `fmt` emits `H:MM:SS.s` (tenths) matching the reader regex EXACTLY
(`pgn.py:30-32`) — e.g. 5730 → `0:00:57.3`. Empty or length-mismatch → emit no `%clk`
(no crash). Client sends data only; server writes the movetext.
- **Owns:** `app/main.py`, `tests/test_bot_clocks_api.py` (new)
- **Done:** `pytest tests/test_bot_clocks_api.py -q` green — a save with `moveTimes`
  yields a PGN whose movetext carries `%clk` matching the regex; **round-trip**
  (`pgn.parse` the saved game → `clock_centis` equals the sent centis ± tenths
  rounding); `moveTimes=[]` emits NO `%clk` (B3 back-compat); length-mismatch skipped
  not crashed; the flag-loss result strings (`0-1`/`1-0`) still pass the whitelist.
  Full `pytest -q` + `ruff` green. No schema change.

## T2 — `static/app.js` descriptor + takeback clock restore (W1) — HOTSPOT
Add `timeControl` (`null` | `{baseSec,incSec}`), `clockWhite`, `clockBlack`,
`moveTimes` (int[]) to ALL THREE descriptor shape sites — `persist()` (`:183-197`),
`restore()` (`:285-299`), `botSetGame()` (`:440-454`) — and update the doc comment
(`:389-392`). `restore()` stays defensive: a bad/missing clock field coerces to a safe
default (untimed / base), never crashes; `moveTimes` restores as an array (not coerced
to `0`). In `botTakeback()` (`:492-509`), alongside the existing 2-ply truncate + the
untouched `takebacksUsed`++ / `rated→false`/`ratedFlipped=true`: truncate `moveTimes`
by 2 and recompute `clockWhite`/`clockBlack` = each side's remaining after its last
SURVIVING move (**even ply index = White, odd = Black, 0-based, independent of
userColor**), else `baseSec*100`. Untimed (`timeControl===null`) → no clock recompute.
- **Owns:** `static/app.js`
- **Done:** `node --check static/app.js` clean. Reasoning trace: the 4 new fields
  round-trip through persist→restore→set (array not mangled); `botTakeback` restores
  the correct per-side clocks for a worked 6→4-ply example (White from idx 2, Black
  from idx 3) AND for a user-plays-Black game; `takebacksUsed`/`ratedFlipped` invariant
  intact; untimed games unaffected. `pytest -q` still green (no python touched).

## T3 — `static/botplay.js` clock model + UI (W2, after T2+T1) — heavy
`static/botplay.js` (+ `static/index.html`, `static/style.css`):
- Time-control `<select>` `#bot-time-control` (Untimed default + 5+2 / 10+0 / 10+5),
  chosen at game start, persisted via `prefs.js` (`botTimeControl`); read into the
  descriptor `timeControl` at start.
- Clock model (centis) + **tick loop** (`setInterval ~200ms`): tick only when live
  (timed, not finished, cursor at tip, not viewing history); decrement the
  side-to-move's clock by real elapsed (`performance.now()` delta), NOT the
  `scheduleBotReply` think-delay; `<=0` → clamp 0 → **flag-loss**.
- Move-commit hook (user `:644`, bot `:749`) INSIDE the existing order, SYNCHRONOUS
  before the async `refreshAnalysis`: record `moveTimes[ply]` (pre-increment) → add
  `incSec` to the mover → switch side → reset tick reference.
- **Flag-loss** mirrors `resign()` (`:775-794`): White flags → `0-1`, Black → `1-0`;
  `botSetResult` + immediate `saveGame()` (NOT `saveOnLeave`) + freeze + status text.
- `saveGame()`/`snapshotGame()` (`:474-534`) send `moveTimes` + `timeControl`.
- `takeback()` (`:164-171`) calls the app.js `botTakeback` (restore handled there) then
  resets the tick reference + re-renders clocks.
- Clock DISPLAY: `#bot-clock-top` (opponent) / `#bot-clock-bottom` (user), timed games
  only, MM:SS (H:MM:SS ≥1h), active-side emphasis, <10s low-time emphasis. Tokens-only
  CSS, AA contrast, `:focus-visible` on the select. Untimed → clocks hidden, no ticks,
  no `%clk`. Add a brief hint that clocks pause on reload (accepted-by-design).
- **Owns:** `static/botplay.js`, `static/index.html`, `static/style.css`
- **Done:** `node --check static/botplay.js` clean. Browser (T4) confirms behavior.
  Reasoning trace: tick charges the correct side, never during history-view or after a
  terminal commit; flag result orientation correct for user-White AND user-Black;
  untimed path sends no `moveTimes`; move-commit ordering + busy/replyToken preserved.

## T4 — Browser verification (W3)
Playwright on :8002. Start a 5+2 game → both clocks show, side-to-move ticks,
increment adds per move; run the user clock to 0 → game ends as a loss with the right
result + saves; take back a pair → clocks restore to before it (try user-Black too);
untimed game shows no clocks + saves no `%clk`; reload mid-game → clock resumes without
charging away time (no auto-flag); user's eval/analysis untouched. A finished timed
game auto-analyzes → the **time-trouble insights card populates for bot games**
(previously dark). Clean up test games from the DB.
- **Done:** every item observed; test games removed.

## T5 — Refuter review of the diff (W3, after T4)
Fresh-context refuter: `%clk` regex round-trip (no None/wrong centis), moveTimes↔
movesUci alignment, tick-reset atomicity (no stray-tick mischarge), flag orientation,
takeback parity/clock-restore, descriptor round-trip (array not mangled), no
analysis/engine involvement, result whitelist, no schema change, B3 untimed
back-compat. Fold; re-verify. (Codex if it recovers.)
- **Done:** resolved/accepted; suite green.

## T6 — Close-out (W3, after T5)
User pass/fail → mark B7 `[x]` in the roadmap (Chapter 3 COMPLETE — whole chess-bots
chapter done); `pytest`/`ruff`/`node --check`; commit; push; PR.
- **Done:** PR open.

## Notes
- Live-reload hazard: one feature branch; don't leave commits unpushed under the live
  `--reload` server.
- Appetite (~2 days): if over, cut order — drop the <10s low-time visual emphasis →
  drop H:MM:SS (MM:SS only, games rarely ≥1h) → keep the take-back clock restore simple
  (it's cheap). Never cut: flag-loss correctness, `%clk` regex-exact emission, the 3
  descriptor shape sites, untimed back-compat, tick-reset atomicity.
