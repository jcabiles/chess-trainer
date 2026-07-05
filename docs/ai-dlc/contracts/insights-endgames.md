# Contracts — Insights Phase 3 "Endgames" (pre-build map)

Slice of `specs/insights-dashboard.md` (roadmap tickets T3.1–T3.3). Read-only audit, branch main post-PR #12/#13.

## insights.py shape

- Module docstring (`insights.py:1-172`) documents every section's JSON shape verbatim — load-bearing; `build_endgame_insights()` needs an equally exhaustive docstring block (frontend + API models hand-sync to this text).
- `MIN_SAMPLE = 5` (`insights.py:187`), `CLUSTER_GATE = 4` (`:190`) — reuse `MIN_SAMPLE`, don't invent a new constant.
- Honesty gate: `gated(value, n, min_n=MIN_SAMPLE) -> {"value","n","sufficient"}` (`insights.py:215-221`). `InsightsGatedMetric` (models.py:406-415) and `renderGatedLine`/`renderThinData` (insights.js) assume this exact 3-key shape — use `gated()` unchanged.
- SQL-then-shape idiom: `_qualified_games()` (`insights.py:229-235`) = `SELECT * FROM games WHERE my_color IS NOT NULL AND analysis_status='done'` — the ONLY population gate; reuse. Per game, `storage.get_plies(game_id)` then pure-Python shaping.
- Coverage merge: `coverage = storage.coverage(); coverage["qualified"] = len(games)` (`insights.py:503-506, 729-730`) — do the same.
- Reusable helpers: `_qualified_games()`, `gated()`, `_user_score()` (`:238-246` — did user win), `_user_win_prob()` (`:676-687` — user-POV win prob per ply; REUSE, don't re-derive the mover-flip), `summarize` (imported `:183`), `game_phase` (imported `:184`).
- Builders raise `RuntimeError` when storage uninitialised (via `storage._get_conn()`, storage.py:212-216); main.py routes catch exactly that.

## Per-ply board availability — VERDICT: no replay needed

`game_plies.fen_before` is a stored column (`storage.py:88`), populated at import by `pgn.py::_replay_game` (`pgn.py:158-183`, captured before each push, written via `storage.write_plies()` storage.py:392-425). So `endgame_signature(chess.Board(row["fen_before"]))` works per stored ply — the exact pattern already used at `insights.py:419, 441, 683`.

Columns per row (storage.py:83-95): `ply, san, uci, fen_before, eval_cp_white, mate_white, win_prob, is_user_move, clock_centis`. No phase column; no after-FEN (ply i+1's `fen_before` is ply i's after-position).

**Guard contract:** `fen_before` can be None on incomplete rows — every existing consumer guards `if not fen: …` before `chess.Board(fen)` (`insights.py:420-423, 436-437, 679-681`). New call sites must too; `chess.Board(None)` raises.

## Phase tagging

`analysis.game_phase(board) -> str` (`analysis.py:191-230`): input is a `chess.Board`; N/B=3 R=5 Q=9, pawns excluded; ≥56 opening, ≥24 middlegame, <24 endgame. **Monotone non-increasing** over a game → endgame is always a contiguous SUFFIX (same invariant `_opening_accuracy` exploits as a prefix, `insights.py:429-431`).

Phase is NOT stored in `game_plies`; only `leaks.phase` (storage.py:105, written review.py:402-404) — insufficient for all-ply classification. Recompute per ply from `fen_before`.

## accuracy.summarize

`accuracy.py:123` — `summarize(plies, my_color)`; generic over any ordered ply-like rows exposing `fen_before/eval_cp_white/mate_white` (dict or attr via `_field()`, accuracy.py:59-68). Phase-subset filtering works today — `_opening_accuracy` (`insights.py:427-449`) passes a hand-sliced list. No new param.

**Load-bearing caveat:** `summarize` pairs `plies[i]`/`plies[i+1]` positionally and drops the final row (`accuracy.py:177-179`). The subset MUST be a contiguous run — a per-ply `phase==endgame` filter across gaps would pair non-adjacent positions and fabricate accuracy silently. Endgame suffix `plies[k:]` is safe (monotone). Boundary choice (start at first endgame ply vs one before, sentinel-style) is a design decision left open by the roadmap ticket.

## API pattern

`main.py:861-940` (comment at :861 already names `endgames`). Per route: `try: data = insights.build_X() except RuntimeError: data = <hand-built empty dict matching the model>` then `Response(**data)` — always 200, never 404/500; empty DB → typed zero-shape (frontend `renderEmptyState` triggers on falsy `coverage.qualified`).
- Drift hazard: except-branch dicts are hand-synced to Pydantic models; `main.py:909, 929` import `insights.CLUSTER_GATE` / `insights._CLOCK_BUCKETS` instead of re-hardcoding. New route must import the signature-list constant from `app/endgame.py` the same way.
- Models (models.py:406-668): reuse `InsightsGatedMetric`; per-slice coverage model (`InsightsMistakesCoverage` :556-571 is the stripped baseline `{total,tagged,analyzed,pending,qualified}`); `InsightsClusterExample` (:574-579) = `{game_id, ply}` deep-link shape to mirror; top-level flat-composition response (`OpeningsInsightsResponse` :542-548, `MistakesInsightsResponse` :660-667).

## Frontend seam

`static/insights.js` now 669 lines — the ux-refinement contracts doc's structural claims hold but its LINE NUMBERS are stale post-merges; re-verify before precise edits.
- Guards: `_shellBuilt` (:28), `_mistakesLoaded` (:29) → add `_endgamesLoaded`.
- `buildShell()` (`insights.js:592-631`) hand-builds exactly two sub-tab buttons + two panels; click handler toggles `.is-active` per-panel explicitly (:621-623) + one lazy-load gate (:624-627). Third sub-tab = third button, third panel, three-way toggle, third `if (name==='endgames' && !_endgamesLoaded)` branch. Manual duplicated code — no config array; easy to miss a site.
- Show/hide rides generic `[role="tabpanel"]:not(.is-active){display:none}` (style.css:435, shared with the 6 outer tabs — don't touch). New panel: `role="tabpanel"` + `.is-active` toggling, nothing else.
- Entrance: `playEntrance(root)` (insights.js:135-139) called ONLY from full-panel renders, which run once per load behind the guards. `renderEndgamesPanel()` must follow: call from the `_endgamesLoaded`-guarded loader only, `playEntrance(root)` at the end.
- Failure idiom: `try { fetchJSON } catch { renderEmptyState(root, "Couldn't load insights right now.") }` (:538-546, 572-580).

## Deep-link + representative pick

`renderDeepLinkButton(gameId, ply, label)` (insights.js:163-176) → `_api.actions.openGameAtPly(gameId, ply)` (app.js:1927, exposed :2008) — the sole cross-module action; fixed signature.
Representative-pick precedent: clusters pre-sort `ORDER BY g.imported_at DESC, l.game_id DESC, l.ply DESC` (`insights.py:540-548`) so first-seen per bucket = most recent, deterministic (`:559-561`); example shape `{game_id, ply}` (`InsightsClusterExample`). Phase-3 per-signature representative should reuse the same ordering convention + shape.

## Conversion inputs

Three POV conventions coexist per row: `win_prob` mover-POV (storage.py:91), `eval_cp_white`/`mate_white` White-POV. Sign-flip hazard (analysis.py:8-24 docstring warning) — go through `_user_win_prob` / `win_prob_white`, never raw.
Phase-2 capitalization template (`_capitalization`, `insights.py:690-717`): consecutive-ply run of `user_wp >= _CAP_WIN_PROB (0.8)`; `sustained` once run ≥ `_CAP_SUSTAIN_PLIES (4)`; `converted = score == 1.0`; returns `{winning_games, converted, rate: gated(), note}`. Phase-3 conversion = same logic scoped to the endgame suffix, bucketed per signature. Compositional reuse, no new eval-math.

## Risks (ranked)

1. **Highest** — non-contiguous phase slicing corrupts `summarize`: must slice `plies[k:]` (suffix), never filter row-by-row; misalignment fabricates accuracy with no error.
2. **High** — `fen_before` None guard at every new `chess.Board()` call site.
3. **High** — hand-synced empty-shape dict in main.py's except branch: import the signature-list constant from `app/endgame.py`; don't re-hardcode bucket names.
4. **Medium** — three-way sub-tab toggle is hand-duplicated JS; touch every site (button, panel, toggle, guard, fetch).
5. **Medium** — stale line numbers in `contracts/ux-refinement-ux.md` Insights section; structure valid, citations not.
6. **Low-Medium** — mover-POV vs White-POV sign-flip; use existing helpers only.
