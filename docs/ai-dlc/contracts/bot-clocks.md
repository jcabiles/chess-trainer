# Contracts — B7: clocks + time controls (bot mode)

Read-only scan (contract-mapper, 2026-07-18). Evidence `file:line`. Client-side
dual clocks in bot-play only; flag = loss; saved bot PGNs emit `%clk` so the
EXISTING time-trouble analytics light up.

## Headline
**The clock-analytics consumer is ALREADY BUILT + shipped** — B7 only needs to
EMIT `%clk`. `game_plies.clock_centis` column exists (`storage.py:95`), `pgn.py`
already PARSES `%clk` (`pgn.py:30-32,97-106,172`), `insights._time_trouble`
(`insights.py:670-709`) consumes it (buckets `<10s/10s-30s/30s-2m/>2m`,
`insights.py:246-251`), rendered in `static/insights.js:427-450`. Bot games flow
the identical `_import_pgn_batch`→auto-analyze pipeline; `is_user_move` is
source-agnostic (`review.py:297-298`). **No schema change. No new consumer.**

## 1. Bot-play move loop (`static/botplay.js`)
- Descriptor built at start: `botplay.js:566-578` `{baseFen,movesUci,cursor,userColor,
  personaLabel,personaId,seed,result,startedAt,rated,saved}` (takebacksUsed/
  ratedFlipped added later by app.js).
- User move commits at `hub().botAppendMove(uci)` `botplay.js:644`; bot move at
  `botplay.js:749`. Ordering contract `botAppendMove → botSetResult(if terminal) →
  persist → refreshAnalysis` (`botplay.js:642-643,747-748`) — **clock stop/start
  hooks slot here without reordering.**
- `scheduleBotReply` `botplay.js:675-693` = artificial 400-800ms think delay,
  ORTHOGONAL to a real clock; drive the clock off wall-clock time, not this timer
  (bot "thinking" naturally eats its clock).
- Terminal outcomes: `autoOutcome()` `botplay.js:68-77` (mate/stalemate/material);
  resign `botplay.js:775-794` (sets result 785-786, saves 788-790, freezes).
  **Flag-loss = NEW terminal path mirroring resign() almost verbatim**, triggered by
  a clock reaching 0 instead of a button.
- `snapshotGame()` `botplay.js:505-515` = fixed 7-field save payload; `saveGame()`
  POST body `botplay.js:476-483` — **widen both to carry per-move times.**
- `reflectControls` `botplay.js:231-239` = per-move control sync; clock DISPLAY
  needs per-second ticks (own interval), not just this.

## 2. Descriptor persistence (`static/app.js`) — 3 shape sites (move together)
`persist()` `app.js:183-197`, `restore()` `app.js:285-299`, `botSetGame()`
`app.js:440-454` (+ doc comment `app.js:389-392`). All explicit allow-listed field
copies — a new `timeControl` + clock state must be added to ALL THREE or it drops
silently. `restore()` is defensive (try/catch → null → clean boot `app.js:339-341`).
- **Reload/resume hazard:** `persist()` fires only on discrete state changes
  (`botplay.js:648,753,787`), NOT on a tick. No elapsed-time bookkeeping exists.
  A "charge wall-clock across reload" approach must reconcile vs `botResumePending`
  (`app.js:306-310`) — decide whether time runs while away (design decision).
- `botAppendMove()` `app.js:473-481`, `botTakeback()` `app.js:492-509` mutate botGame
  directly — clock-on-takeback hooks here.

## 3. Save path + PGN build (`app/main.py`, `app/pgn.py`)
- `BotSaveRequest` `main.py:830-848`: `movesUci,userColor,personaLabel,result,
  startedAt,rated,personaId`. **No clock field — add one (per-ply remaining centis).**
- **Server builds the PGN** by replaying movesUci `main.py:880-923` (SAN derived,
  headers set, `pgn_text=str(game)` 923). Client NEVER sends PGN text. **`%clk` must
  be injected server-side via `node.comment` in the replay loop `main.py:883-889`**,
  NOT client-assembled movetext.
- No existing `%clk` WRITER (only reader). Net-new: `node.comment = f"[%clk {H}:{MM}:
  {SS}]"` matching the reader regex `\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]`
  (`pgn.py:30-32`) EXACTLY or clock_centis stays None (feature stays dark).
- Result whitelist `main.py:866-872` = `{"1-0","0-1","1/2-1/2"}` only.

## 4. Downstream analytics — see Headline. Only EMIT needed.

## 5. Result / termination contract
- **No PGN `Termination` header anywhere** (repo-wide grep = 0). Result = the
  `Result` string only. `_import_pgn_batch` stores it verbatim (`main.py:1061`).
- Flag-loss = a plain decisive string (`0-1` White flags, `1-0` Black flags) —
  identical shape to resign. No termination-reason field exists or is needed
  (ELO/insights/storage key off result+my_color only, never WHY).

## 6. Rated/ELO + takeback interactions
- Flag counts as rated exactly like resign — `rating.py:88-105` keys off
  result+my_color+rated+personaElo, zero awareness of how the game ended. **No
  rating.py change.**
- **Takeback × clock has NO precedent** — `botTakeback()` `app.js:492-509` truncates
  2 plies + flips `rated→false`/`ratedFlipped=true` (`app.js:499-501`, load-bearing).
  Clock-restore-on-takeback is NEW logic; must not disturb takebacksUsed increment
  or ratedFlipped chain. (Since takeback already flips to casual, clock precision
  no longer affects ELO — design decision on whether/how to restore.)
- Casual/rated save: `saveOnLeave()` `botplay.js:521-534` synthesizes abandon-loss
  for RATED only; casual-unfinished discarded. **Flag-loss is a LIVE explicit result
  → always save via the resign path, NOT saveOnLeave.**

## Protect-list
1. app.js descriptor: all 3 shape sites + doc comment move together (drop-on-
   persist/restore otherwise).
2. `botTakeback()` rated-flip + takebacksUsed invariant undisturbed.
3. Move-commit ordering `botAppendMove→botSetResult→persist→refreshAnalysis` — clock
   hooks slot in without reordering (busy/replyToken staleness depends on it).
4. Result stays in `{1-0,0-1,1/2-1/2}` — no 4th value, no termination-reason field.
5. Server builds PGN; client sends structured per-move times only.
6. `%clk` writer format must match the reader regex exactly (`H:MM:SS[.f]`).
7. `_time_trouble` gate (`insights.py:677-678` is_user_move/my_color/analysis
   done/clock_centis) — bot games already satisfy it; add no source filter.
8. **No DB schema change** — `clock_centis` exists; write/read chain source-agnostic.
9. Flag-loss saves via resign-style immediate `saveGame()`, not saveOnLeave.
10. rating.py stays result-string-only — no clock/termination coupling.
