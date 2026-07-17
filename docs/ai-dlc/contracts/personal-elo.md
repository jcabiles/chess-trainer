# Contracts — B8: Personal ELO estimate

Read-only scan (contract-mapper, 2026-07-17). Evidence `file:line`.

## Read-model pattern to mirror
- Engine-free read-models query via `storage._get_conn().execute("SELECT ...
  FROM games WHERE ...").fetchall()` → `[dict(r) for r in rows]` (`profile.py:45-49`,
  `insights.py:280-284`). `row_factory = sqlite3.Row` (`storage.py:236`) → rows
  support `r["col"]` and `dict(r)`.
- Endpoint idiom (`main.py:1482-1508`): `@app.get("/api/profile",
  response_model=...)` → `profile.build_profile()` inside `try/except
  RuntimeError` returning an empty-state response (`_get_conn()` raises
  `RuntimeError` when the DB never opened, `storage.py:246-249`). **B8 must
  replicate the RuntimeError empty-state guard.**
- **`headers_json` is TEXT (a JSON string), NULL for all import/fetch games**
  (`main.py:966`). B8 is the FIRST reader — must `json.loads` and guard `None` +
  malformed. Bot rows: `json.dumps({"rated":bool[,personaId,personaElo]})`
  (`main.py:823,831-833`).

## Bot-ELO inputs (the genuinely new signal)
- User result: reuse `insights._user_score(result, my_color)` → `1.0/0.5/0.0/None`
  (`insights.py:287-295`).
- Opponent rating: `json.loads(headers_json)["personaElo"]` (int, server-resolved
  from the catalog, `main.py:825-833`; personas at `personas.py:66-69`).
- **Pre-B4 rated bot games lack `personaElo`** (the `personaId is None` branch
  stores only `{"rated":bool}`, `main.py:821-823`) → `headers.get("personaElo")`
  is `None`; **skip/default, never KeyError.**
- Rated filter: `headers_json["rated"] is True`; exclude casual.
- Bot-Elo does NOT need `analysis_status='done'` (result is known without
  analysis); the real-games aggregate DOES.

## Real-games est-Elo — OUT OF SCOPE (Gate 1 dropped it)
The move-quality est-Elo aggregate (`accuracy.summarize` over `game_plies` per
imported game) was **dropped at Gate 1** — it overlaps the chess.com anchor and is
uncalibrated. B8 does NOT touch `accuracy.py`/`game_plies`. This section is left
only to record the decision; do not implement it (Codex MED — the earlier text
risked steering toward the out-of-scope O(games×plies) aggregate).

## Ordering
- Only timestamp is `imported_at` (TEXT ISO, save time — `storage.py:66`,
  `main.py:968`; `list_games` orders DESC `storage.py:323`). For bot games (saved
  once at finish) `imported_at` ≈ play order — adequate for the running Elo. True
  `startedAt` lives only in the PGN `Event` header (`"Bot game <ISO>"`,
  `main.py:847`), not a column — parse it back only if exact play-order matters.

## UI seam
- Bot hub renders `#botplay-persona`/`#botplay-status`; the rated hint
  (`index.html:151`, "Rated games count toward your ELO…") is the natural anchor
  for an ELO readout. `probeStatus()` (`botplay.js:263-294`) fetches
  `/api/bot/status` ONCE at init (`botplay.js:690`) — **no auto-refresh**; B8 must
  re-fetch the ELO after a rated game saves (finish paths `botplay.js:481/577/606`).
- `botplay.js` gets the injected `api` hub, never imports app.js; chess.com anchor
  via `prefs.js` (`writeUiPref`/`readUiPrefs`, key `chess-training:ui:v1`) — not
  raw localStorage, not a DB column.

## Sharp edges
1. Pre-B4 rated bot games have no `personaElo` → skip into `gamesSkipped`.
2. `headers_json` TEXT needs `json.loads`; NULL for imports; a JSON
   list/scalar/`null` has no `.get` → require `isinstance(dict)`; `personaElo`
   must be a real `int` (exclude `bool`/str/NaN) → else skip.
3. `user_score` must require `my_color in {white,black}` — the `insights` rule
   treats unknown color as Black and would miscount a null-color decisive row.
4. Running-Elo order approximated by `imported_at` (save time); add `id ASC`
   tiebreak for determinism (Elo is path-dependent); exact = parse `Event`
   startedAt (out of scope).
5. **No DB schema change** — bot-Elo from result+my_color+headers_json; anchor in
   localStorage. Recompute-from-history every request (stateless); do NOT persist
   a running Elo. Bot-ELO + chess.com anchor are two distinct numbers (one a
   genuine Elo update, one user-entered) — keep them visually separate.
