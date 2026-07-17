# Tickets — B8: Personal ELO estimate

Spec: [`../specs/personal-elo.md`](../specs/personal-elo.md).
Branch: `feat/personal-elo` off up-to-date main.
Wave plan (disjoint owners): **W1:** T1 ∥ T3 → **W2:** T2 (needs T1) → **W3:**
T4 (needs T2+T3) → **W4:** T5 verify → T6 review → T7 close-out.

## T1 — `app/rating.py` read-model + Elo math + tests (W1)
New PURE, engine-free module. `elo_update(cur, opponent, score, k) -> float`
(standard expected-score + update); `user_score(result, my_color) -> float|None`
(`1-0`/`0-1`/`1/2-1/2` → user POV `1.0/0.5/0.0`, else None — replicate the
`insights._user_score` rule locally). `build_rating() -> dict`: query
`storage._get_conn()` for `source='bot'` games ordered by `imported_at ASC`;
count only `rated is True` with numeric `personaElo` (skip pre-B4 → `gamesSkipped`;
guard NULL/malformed `headers_json`); run the running Elo from `SEED_ELO=1350`,
`K=32`; return `{seedElo, k, botElo(round|None), gamesCounted, gamesSkipped,
history:[{gameId,opponentElo,score,eloAfter}]}`.
- **Owns:** `app/rating.py`, `tests/test_rating.py`
- **Done:** `pytest tests/test_rating.py -q` green — `elo_update` symmetry (win vs
  higher > win vs lower; draw vs equal ≈ 0) + a hand-computed numeric example;
  `user_score` maps the four result cases AND returns None for `my_color`
  None/empty/invalid even on a decisive result; `build_rating` over a fake DB
  counts only rated bot games with a valid int `personaElo`, skips pre-B4 into
  gamesSkipped, excludes casual + non-bot, orders by `imported_at,id`, correct
  running botElo + history; empty → botElo None; **`headers_json` None/`"[]"`/
  `"null"`/scalar/non-JSON → skip (no crash); personaElo string/bool/NaN/inf →
  gamesSkipped**. Full `pytest -q` + `ruff` green.

## T2 — `GET /api/rating` endpoint + models (W2, after T1) — HOTSPOT
`@app.get("/api/rating", response_model=RatingResponse)` → `rating.build_rating()`
inside `try/except RuntimeError` → empty state (`botElo=None`, counts 0, `[]`),
mirroring `/api/profile`. `RatingResponse` + `RatingPoint` in `app/models.py`.
- **Owns:** `app/main.py`, `app/models.py`, `tests/test_rating_api.py` (new)
- **Done:** `pytest -q` green — `/api/rating` returns the shape; empty-DB
  RuntimeError guard returns the empty state (not 500); a seeded fake DB yields
  the expected botElo/counts. `ruff` green.

## T3 — rating readout + chess.com input UI (W1)
`static/index.html`: a rating readout in `#botplay-body` near the rated hint —
`#botplay-elo` ("Bot rating: — (0 games)") + `#botplay-chesscom` (hidden until
set) + a `<input type="number" id="chesscom-rating">` with label.
`static/style.css`: token-only, both themes; keep the three numbers visually
distinct (bot rating vs chess.com reference).
- **Owns:** `static/index.html`, `static/style.css`
- **Done:** elements render with stable ids for T4; token CSS both themes;
  `pytest -q` still green (sanity).

## T4 — `static/botplay.js` fetch + render + anchor (W3, after T2+T3)
Fetch `/api/rating` on/after `probeStatus()`; render `#botplay-elo`
(botElo + gamesCounted, or the empty "play a rated game" state). Init
`#chesscom-rating` from `readUiPrefs().chessComRating`; on change
`writeUiPref('chessComRating', v)` (NaN/empty → clear) + re-render
`#botplay-chesscom`; never send it to the server. **Re-fetch `/api/rating` after
a RATED game's `saveGame` succeeds** (not casual) so the bot-ELO updates without
reload.
- **Owns:** `static/botplay.js`
- **Done:** manual/browser: readout populates; chess.com input persists across
  reload; bot-ELO refreshes after a rated game; no B2/B3/B4 regression
  (busy/replyToken/save triggers/persona intact).

## T5 — Browser verification (W4)
Spec Verify-by-3: play a rated game to a decisive result → bot-ELO updates
(no reload) in the right direction; chess.com input persists across reload +
shows beside the bot rating; a casual game doesn't change bot-ELO; `/api/rating`
gamesCounted matches the rated-bot-game count. `pytest`/`ruff` green.
- **Done:** every Verify-by-3 item observed; test games cleaned from the DB.

## T6 — Dual review of the diff (W4, after T5)
Refuter + Codex (gpt-5.6-sol): Elo math + POV sign, filters/skip, ordering,
empty states, statelessness/no-schema, client anchor never sent + re-fetch gating,
no B3/B4 regression. Fold findings; re-verify.
- **Done:** both resolved/accepted; suite green.

## T7 — Close-out (W4, after T6)
User pass/fail → mark B8 `[x]` (Phase A complete) + note B6 takebacks next in the
roadmap; `pytest`/`ruff`; commit; push; PR.
- **Done:** PR open; B6 flagged next.

## Notes
- Live-reload hazard: one feature branch, never switch mid-work under the user's
  uvicorn --reload.
- Appetite guard (~1 day): if over, cut order — history detail → chess.com anchor
  (bot-ELO number is the minimum). Never cut: Elo POV-sign correctness, skip
  pre-B4 rows, casual exclusion, stateless recompute.
