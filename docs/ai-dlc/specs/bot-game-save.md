# Delta spec — B3: Bot games auto-save into the review pipeline

**Goal (one line):** on a bot game ending, persist it through the existing
`_import_pgn_batch` path with a bot `source` so the profiler / insights /
blunder-trainer pick it up like an imported game — with a **Rated/Casual**
toggle that decides whether the game counts (and whether abandoning it is a
loss) — **no DB schema change**.

Slice: **B3** of [`../roadmap/training-and-portfolio.md`](../roadmap/training-and-portfolio.md)
Chapter 3 (N3+N1). Depends on B2 (shipped). Contracts:
[`../contracts/bot-play.md`](../contracts/bot-play.md) §3. Requirements +
two review rounds confirmed at Gate 1 (2026-07-16). Codex + refuter
dual-reviewed the spec; findings folded (see the ticket review log).

## Decisions (Gate 1 + the Rated-game refinement)

- **Rated/Casual toggle** at game start, **default OFF (casual)**:
  - **Casual** — saved ONLY if the game reaches a real ending
    (mate/stalemate/draw/resign). Abandoning (exit / New-game mid-play)
    **discards** it.
  - **Rated** — always saved (given ≥1 move). A real ending saves the real
    result; **abandoning an unfinished rated game counts as a LOSS** (user's
    side loses). B8 later counts rated games toward the bot-ELO estimate.
  - **Encoding:** ALL bot games get `source='bot'` (provenance only); rated-
    ness lives in `headers_json` as `{"rated": <bool>}`. This keeps the two
    axes separate — `source` stays a clean provenance field for B4 personas,
    and B8 queries `headers_json`.`rated` (the no-gos bless `headers_json`;
    the contract §3 nominated it as the bot-metadata carrier). NOT encoded in
    `source` (that would collide with B4 appending persona identity to
    `source` and silently break a `source='bot-rated'` query).
- **No game is ever saved with `Result='*'`** — every saved game has a
  decisive/drawn result. (This removes the `*`-badge and abandoned-`*`
  profiler questions entirely.)
- **Auto** on game-end; the rated-abandon-as-loss save fires on the
  exit/New-game trigger.
- PGN names: persona label vs **"You"** by color; `my_color_override` =
  the user's color (names are display-only).
- Game Library shows a small **"vs Bot" badge** (any `source` starting
  `bot`). No insights segmentation (later slice).
- **Personal ELO math is B8, deferred** (roadmap reordered: B8 follows B3).
  B3 only CAPTURES rated-ness via `source`; it computes no rating.

## Server

### NEW `POST /api/bot/save` (`app/main.py`)

Request `{movesUci: [str], userColor: 'white'|'black', personaLabel: str,
result: str, startedAt: str, rated: bool}` (`result` ∈
{`1-0`,`0-1`,`1/2-1/2`} — **never `*`**; `startedAt` = ISO-8601 minted
client-side at game start).

- Build a `chess.pgn.Game` server-side (python-chess is present): replay
  `movesUci` onto a board for SAN; headers —
  - `White`/`Black`: persona vs `"You"`, ordered by `userColor`.
  - `Result`: the given result.
  - `Date`: date portion of `startedAt`.
  - `Event`: `"Bot game <startedAt>"` — carries the start timestamp into the
    dedup hash. `_compute_hash` (`pgn.py:143`) keys on
    White/Black/Date/Result/Event + movetext: distinct games get distinct
    `startedAt` → distinct hash (both saved); a re-save of the SAME game
    (e.g. after refresh) reuses the persisted `startedAt` → same hash →
    deduped, no duplicate row. This is the refresh-safety mechanism — **do
    not mint a fresh timestamp at save time.**
- `source='bot'`; `headers_json = json.dumps({"rated": rated})`.
- Extend `_import_pgn_batch` with an optional `headers_json: str | None =
  None` param (defaults to None = current behavior; the `fields` dict already
  has a `headers_json` slot at `main.py:822`, currently hardcoded None —
  thread the param into it). Call
  `_import_pgn_batch(pgn_text, userColor, engine, source='bot',
  headers_json=headers_json)`. Existing callers (import/fetch) are unaffected
  by the new default. Reuses dedup, per-ply writes, and the auto-analysis
  kick unchanged. Return its `ImportResponse`.
- Validation: empty `movesUci` → 400. The client NEVER posts a 0-move game
  (an immediate resign / abandon on a fresh board is discarded client-side).
  Unparseable/illegal move sequence → 400 (defensive).
- Engine dependency: `get_engine` like `/api/games/import` — this is the
  ANALYSIS engine (auto-analysis kick), unrelated to B2's isolated bot
  process.

### Expose `source` on the library model

`GameSummary` (`app/models.py`) gains `source: str | None`; `_game_summary`
(`app/main.py:771`) passes `row.get("source")`. Read-only surfacing of an
existing column — **no schema change**. Drives the badge; Pydantic default
keeps existing consumers (`ImportResponse`/`FetchResponse`) safe.

## Client

### `static/index.html` + `static/style.css` — Rated toggle + badge

- A **Rated** toggle (checkbox/switch) in the "Play vs Bot" section near the
  color pick, default unchecked; a one-line hint ("Rated games count toward
  your ELO; quitting a rated game is a loss"). Token-only CSS, both themes.
- "vs Bot" badge in the game-row meta (`review.js:244`) when
  `game.source === 'bot'` (all bot games share this provenance; rated-ness
  is in `headers_json`, not surfaced in B3's library). Token-only, both
  themes.

### `static/botplay.js` — rated state + save triggers

- Read the Rated toggle at **game start**; store `rated` on the descriptor
  (persisted). Mint `startedAt` at start (persisted) for dedup stability.
- **`saveGame(snapshot)`** where `snapshot = {movesUci, userColor,
  personaLabel, result, startedAt, rated}` is **captured SYNCHRONOUSLY by
  the caller before any teardown** (never re-read via `botGetGame()` after
  an await — `botExit()` nulls the descriptor, New-game replaces it). Guard:
  `movesUci.length === 0` → return without posting.
  - POST `/api/bot/save`. **Success = an ImportResponse with
    `imported + duplicates >= 1`** — NOT merely that `postJSON` resolved
    (the injected `postJSON` only throws on 503; a 400 resolves with a
    non-ImportResponse body → treat as failure). On success,
    `botMarkSaved(snapshot.startedAt)`. On failure, log + leave unsaved.
  - Fire-and-forget after the synchronous capture; never blocks the UI.
- **`botMarkSaved(startedAt)` is identity-guarded** (app.js): marks the
  descriptor saved ONLY if the current `botGame.startedAt` still matches —
  a stale save completing after New-game must not mark the *new* game saved.
- **Finished trigger** (casual AND rated): after a real result is set (the
  `autoOutcome` branches in `onMove` + `requestBotMove`, and `resign()`),
  capture the snapshot and `saveGame` once. The finished game stays resident
  in bot-play state, so a failed POST is re-attempted at exit with the same
  `startedAt` + the REAL result (idempotent).
- **Exit / New-game trigger** — ONE predicate, ordered by whether the game
  already ended. This ordering is load-bearing: a finished-but-unsaved game
  must NOT be re-recorded as an abandon-loss (refuter HIGH — a rated game the
  user WON, whose finish-POST failed, would otherwise be posted as a loss).
  In `exit()` and `startGame()` re-entry, capture the snapshot synchronously,
  then:
  - ≥1 move AND unsaved AND **has a result** (finished, but finish-POST
    failed) → `saveGame` with the game's **REAL result** (finished retry;
    casual or rated).
  - else ≥1 move AND unsaved AND **no result yet** AND **rated** → genuine
    abandon of an unfinished rated game → `saveGame` with `result = loss`
    (`userColor==='white' ? '0-1' : '1-0'`).
  - else (casual with no result / 0 moves / already saved) → **discard, no
    save.**
  Then tear down. Durability caveat (honest): the single localStorage slot
  holds a bot-play OR a play entry; `botExit()` overwrites it and nulls
  `botGame`, so a failed exit-time POST is not retryable (that game is lost).
  Accepted — best-effort; the in-game finished path (game still resident)
  has no such exposure.
- **Idempotency:** the identity-guarded `saved` flag prevents redundant
  POSTs; the server stable-hash dedup is the backstop for any that slip
  through (finish-saved then exit).

### `static/app.js` — descriptor round-trip

`botGame` gains `startedAt`, `saved`, `rated`; all round-trip through the
persist/restore `bot-play` branch. New hub seam `botMarkSaved(startedAt)`
(identity-guarded set + persist). `botSetGame` mirrors the three fields.
No other app.js change.

## Out of scope

Personal ELO math / rating aggregate (B8 — B3 only tags `source`) ·
bot-vs-human insights SEGMENTATION (later) · personas beyond B2's one label
(B4) · `%clk`/time data (B7) · any DB schema/migration change · editing the
import/fetch routes · the pre-existing `resultBadge('*')` mislabel (B3
produces no `*` games, so it is not worsened here — left alone).

## Constraints (profile)

- No DB schema change (source/name/headers fields only). Never commit
  `data/games.db` / `data/games/`.
- Server stateless except the review pipeline (unchanged). Bot save is a
  normal request funnelling into the existing persist path.
- `_import_pgn_batch` stays the single save path (contract §3).
- Feature branch + PR; Conventional Commits; commit only
  implemented+verified+reviewed.

## Verify-by

1. `pytest -q` green with no engine binary (fake `get_engine`): new
   `/api/bot/save` tests — every bot game inserts `source='bot'` with correct
   `my_color`, names by color, and result; a CASUAL game →
   `headers_json` `{"rated": false}`, a RATED game → `{"rated": true}`; a
   rated-abandon posts a LOSS result for the user's color; a
   finished-but-unsaved re-save posts the REAL result (NOT a loss); a
   **1-ply game** persists (accuracy/Elo null is expected, not a bug); SAME
   `startedAt` dedups (2nd POST → `duplicates=1`, no new row); DISTINCT
   `startedAt` → two rows; empty `movesUci` → 400; `result='*'` → 400.
   `GameSummary` includes `source`; existing import/fetch callers still write
   `headers_json=None` (new param defaults preserve behavior).
2. `ruff check app tests` green.
3. Browser (Playwright/manual, real engine): play a CASUAL bot game to
   mate/resign → appears in the Library with a "vs Bot" badge, auto-analyzes
   to done, correct color; SQL `source='bot-casual'` present + profiler count
   increments. Abandon a casual game → NO new row. Play a RATED game, abandon
   it → a `source='bot-rated'` LOSS row appears. Refresh after a finished game
   then exit → no duplicate row (stable-hash dedup holds).
