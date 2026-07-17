# Delta spec — B8: Personal ELO estimate

**Goal (one line):** show a **running bot-ELO** (standard Elo, seed 1350 / K=32,
updated per RATED bot-game result vs the persona's rating) in the bot hub,
alongside a user-entered **chess.com rating** as a reference — a
recompute-from-history read-model, **no DB schema change, no new tables**.

Slice: **B8** of [`../roadmap/training-and-portfolio.md`](../roadmap/training-and-portfolio.md)
Chapter 3 (N3 · P4). Depends on B3 + B4 (shipped — the ladder supplies per-opponent
`personaElo`). Contracts: [`../contracts/personal-elo.md`](../contracts/personal-elo.md).
Gate 1 confirmed 2026-07-17: **bot-ELO + chess.com anchor only** (no move-quality
est-Elo aggregate) · **seed 1350, K=32**.

## Decisions (Gate 1)

- **Bot-ELO** = a standard Elo rating recomputed from history every request:
  start `SEED_ELO = 1350`, `K = 32`; for each RATED bot game in chronological
  order, `expected = 1/(1 + 10**((opponentElo - cur)/400))`,
  `cur += K * (score - expected)` where `score` = the user's result
  (`1.0/0.5/0.0`). Display `round(cur)`.
- **chess.com rating** = a user-entered number (client-side, `prefs.js`), shown
  as a **display-only reference** next to the bot-ELO ("Bot rating 1420 ·
  chess.com 1500"). NOT sent to the server; NOT used to seed or calibrate the
  bot-ELO (keeps bot-ELO an independent cross-check).
- **No move-quality est-Elo aggregate** (Gate 1 — it overlaps chess.com and is
  uncalibrated; dropped to keep B8 tight and honest).
- **Recompute-from-history, stateless:** the server never persists a running Elo;
  it derives it from stored rows on each `/api/rating` call.
- **Ordering:** chronological by `imported_at` ASC. Bot games are saved once at
  finish, so `imported_at` ≈ play order (adequate; the exact `startedAt` lives
  only in the PGN `Event` header — not parsed here).
- **Skipped games:** rated bot games missing `personaElo` (pre-B4 rows) are
  skipped and counted in `gamesSkipped` (never a `KeyError`). Casual bot games
  and non-bot games are excluded.

## Server

### NEW `app/rating.py` (pure, engine-free read-model)
- `build_rating() -> dict`: query `storage._get_conn().execute("SELECT id,
  result, my_color, headers_json, imported_at FROM games WHERE source='bot' AND
  my_color IS NOT NULL ORDER BY imported_at ASC, id ASC")`. (The `my_color IS NOT
  NULL` filter is defensive — the save path always sets it, but `user_score(...,
  None)` returns a decisive score not `None`, so a null-color row would be
  miscounted rather than skipped; the `id ASC` tiebreak makes the
  path-dependent Elo order deterministic if two rows share a timestamp — refuter
  LOW.) For each row:
  (a) `headers = json.loads(headers_json or '{}')` inside `try/except
  JSONDecodeError` → skip on error; **require `isinstance(headers, dict)`** (a
  JSON list/scalar/`null` parses fine but has no `.get` → skip) — Codex MED.
  (b) require `headers.get("rated") is True` (exclude casual).
  (c) `opp = headers.get("personaElo")`; **valid only if `isinstance(opp, int)
  and not isinstance(opp, bool)`** (a string `"1500"`, a `bool` — `int` subclass
  in Python — or a NaN/inf float are all invalid) → else `gamesSkipped += 1`,
  continue (Codex MED). With `opp` a bounded int and `cur` moving in ≤K steps,
  `10**((opp-cur)/400)` cannot overflow.
  (d) `score = user_score(result, my_color)` — if `None` skip.
  (e) apply the Elo update. Returns
  `{"seedElo": 1350, "k": 32, "botElo": round(cur), "gamesCounted": n,
   "gamesSkipped": m, "history": [{"gameId", "opponentElo", "score",
   "eloAfter"} ...]}`. When no counted games: `botElo = None`, empty history
  (the UI shows "play a rated game to start your rating").
- **Pure helper `user_score(result, my_color)`** — **first require `my_color in
  {"white", "black"}` (else return `None`)** — do NOT blindly replicate
  `insights._user_score`, which treats any non-`white` value as Black and would
  miscount a `my_color=None` decisive row as a loss (Codex MED). Then map
  `1-0`/`0-1`/`1/2-1/2` → user POV `1.0/0.5/0.0`, else `None`. Keep it local to
  `rating.py` (avoid importing a private helper);
  unit-tested here.
- **Pure helper `elo_update(cur, opponent, score, k) -> float`** — the standard
  expected-score + update; unit-tested for symmetry (a win vs a higher-rated
  opponent gains more than vs a lower one; draw vs equal ≈ 0 change).
- Engine-free, no Stockfish, no `game_plies` access (bot results need no
  analysis). Import-safe.

### `app/main.py` — `GET /api/rating`
`@app.get("/api/rating", response_model=RatingResponse)` → `rating.build_rating()`
inside `try/except RuntimeError` returning the **full** empty state
(`seedElo=1350, k=32, botElo=None, gamesCounted=0, gamesSkipped=0, history=[]`
— all fields present or Pydantic validation fails; Codex LOW) when storage is
uninitialised — mirror `/api/profile` exactly. `RatingResponse` in
`app/models.py` (`seedElo:int, k:int, botElo:int|None, gamesCounted:int,
gamesSkipped:int, history:list[RatingPoint]`).

## Client

### `static/index.html` + `static/style.css` — ELO readout + chess.com input
- A small **rating readout** in `#botplay-body` near the rated hint
  (`index.html:151`): "Bot rating: **1420** (12 games)" + "chess.com: **1500**"
  (the second only when set). Stable ids (e.g. `#botplay-elo`,
  `#botplay-chesscom`). Token-only CSS, both themes.
- A **chess.com rating input** (`<input type="number" id="chesscom-rating">`,
  optional, small) with a label; persisted client-side. Locked state not needed
  (it's a setting, editable anytime).

### `static/botplay.js` — fetch + render + anchor persistence
- On `probeStatus()` (or right after it resolves), fetch `/api/rating` and render
  the readout: `botElo` + `gamesCounted` (or the "play a rated game" empty state);
  if `readUiPrefs().chessComRating` is set, show it too.
- The chess.com input: one **normalization function used on BOTH read and
  change** (Codex LOW — a stored `"NaN"`/`"abc"`/`null` must not render as a
  rating): accept only a finite positive integer; anything else (empty, NaN,
  non-numeric) → treat as unset. On `change`: if valid,
  `writeUiPref('chessComRating', n)`; if cleared/invalid, `writeUiPref(
  'chessComRating', null)` (define clear = store `null`, since `prefs.js` only
  assigns). Re-render the anchor line (hidden when unset). Never sent to the
  server.
- **Re-fetch `/api/rating` after ANY rated game is saved** — status is probed
  once at init with no auto-refresh, so hook the re-fetch onto every successful
  `saveGame` where the snapshot was `rated` — the finish paths AND the
  rated-abandon-loss `saveOnLeave` path (refuter LOW: an abandoned rated game
  saves a loss too, so it must refresh the readout, not just the finish paths).
  Casual saves never re-fetch.
- Injected `api` hub only; never import app.js; anchor via `prefs.js`.

## Out of scope
- Move-quality est-Elo aggregate over imported games (Gate 1 — dropped) ·
  seeding/calibrating from chess.com · any bot-vs-human insights segmentation ·
  parsing exact `startedAt` play-order · persisting a running Elo · provisional
  K-factor · clocks (B7) · causal blunder model (B5) · any DB schema change ·
  Maia install.

## Constraints (profile)
- Engine-free read-model (no Stockfish); `rating.py` pure/import-safe like
  `profile.py`. Server stateless except review — no persisted Elo.
- No DB schema change (derive from existing rows + client prefs).
- Frontend modules receive the injected `api` hub, never import app.js; chess.com
  anchor via `prefs.js` (`chess-training:ui:v1`), not raw localStorage, not a DB
  column.
- Reuse the established result→user-POV rule; don't invent a new one.

## Verify-by
1. `pytest -q` green (no engine): `rating.py` — `elo_update` symmetry (win vs
   higher > win vs lower; draw vs equal ≈ no change; seeded numeric example
   matches a hand-computed value); `user_score` maps all four result/color cases;
   `build_rating` over a fake DB — counts only rated bot games with a valid int
   `personaElo`, skips pre-B4 rated (no personaElo) into `gamesSkipped`, excludes
   casual + non-bot, orders by `imported_at,id`, produces the expected running
   `botElo` + history; empty DB → `botElo=None`; **`headers_json` that is `None`,
   `"[]"`, `"null"`, a scalar, or non-JSON does not crash (→ skip); a
   `personaElo` that is a string/`bool`/NaN/inf → `gamesSkipped`; `user_score`
   returns `None` for `my_color` None/empty/invalid even on a decisive result**. `/api/rating` returns the shape + the RuntimeError empty-state guard.
2. `ruff check app tests` green.
3. Browser (Playwright/manual, real engine): play a RATED game to a decisive
   result vs a known persona → the bot-ELO readout updates (without reload) by
   the expected direction (win → up); set the chess.com input → it persists
   across reload and shows next to the bot rating; a CASUAL game does not change
   the bot-ELO; `/api/rating` `gamesCounted` matches the rated-bot-game count.
