# Tickets — Insights / Analytics Dashboard

Spec: `docs/ai-dlc/specs/insights-dashboard.md`. Research:
`docs/ai-dlc/research/insights-dashboard.md`.

**Shared contract (all tickets agree):**
- New pure modules `app/insights.py` + `app/endgame.py` — no engine, no DB migration;
  post-processing of stored `games` / `game_plies` / `leaks` rows. Reuse `analysis.*`,
  `accuracy.summarize`, `repertoire.tree()`, `book.is_book_move`, `openings.identify`,
  `coaching.name_cluster`, `profile.py` patterns.
- Builders return `{value, n, sufficient}`-style records; min-sample gate default = 5
  (prefer ECO-family aggregation); cluster naming gate = 4.
- All insights gated on `my_color` set + `analysis_status='done'`.
- API mirrors `GET /api/profile`; namespaced `GET /api/insights/{openings,mistakes,endgames}`.
- New tab wiring: `index.html` button + panel; `'insights'` added to **both** `app.js:2005`
  and `review.js:515`; `static/insights.js` (`initInsights(api)`) + `static/insights.css`.
- Deep-link via `api.actions.openGameAtPly(gameId, ply)` and/or `loadFen`.
- Tokens-only CSS, no raw hex; verify via pytest (`TestClient`) + Playwright-MCP.

## Foundation (T0) — build before Phase 1 UI

| # | Ticket | Owned files | Done-condition | Deps |
|---|--------|-------------|----------------|------|
| T0.1 | Insights tab scaffold: tab button + `#tab-insights` panel div + `insights.js` (`initInsights` empty-state render) + `insights.css` link + both hardcoded-array edits + import/init wiring in `app.js`. | `static/index.html`, `static/insights.js` (new), `static/insights.css` (new), `static/app.js`, `static/review.js` | Clicking Insights shows an empty-state panel; switching away hides it (proves both arrays updated); 0 console errors. | — |
| T0.2 | Deep-link action: expose `api.actions.openGameAtPly(gameId, ply)` (wraps `openGame` + post-load `goto`); confirm `loadFen`-style board load callable from a module. | `static/app.js`, `static/review.js` | A temporary insights button opens a known game at a given ply on the board. | T0.1 |
| T0.3 | Honesty/min-sample util: shared gate helper (`{value, n, sufficient}`, min 5; family aggregation) + a muted "not enough games yet (n=…)" UI convention + the single de-emphasized long-run trend slot. | `app/insights.py` (new), `static/insights.js` | Builders return the gated shape; UI renders the muted thin-data state. | T0.1 |

## Phase 1 — Openings

| # | Ticket | Owned files | Done-condition | Deps |
|---|--------|-------------|----------------|------|
| T1.1 | Win% by opening (pure): group games by ECO family + deep name; score from `games.result` vs `games.my_color`; sample counts; per-line min-sample gate. | `app/insights.py` | Per-family + per-line `{opening, color, w/d/l, score, n, sufficient}`; color from the user's perspective. | T0.3 |
| T1.2 | Repertoire adherence (pure): for games matching a prepared line, walk vs `repertoire.tree()`; emit `followed_prep_depth`, `deviation_ply`, `deviation_move` per line + aggregated. | `app/insights.py` | Deviation ply/move correct on a follow-then-deviate fixture; off-repertoire games excluded here. | T0.3 |
| T1.3 | Theory fallback (pure): off-repertoire games → named-theory book-exit ply via `book.is_book_move` + opening-phase accuracy (`accuracy.summarize` filtered to opening plies). | `app/insights.py` | Book-exit ply = last in-theory move; accuracy restricted to opening phase; "named ≠ endorsed" copy. | T0.3 |
| T1.4 | Openings API: `GET /api/insights/openings` typed response bundling T1.1–T1.3 + coverage. | `app/main.py`, `app/models.py` | 200 with populated sections on analyzed games; empty-safe; no engine/migration. | T1.1–T1.3 |
| T1.5 | Openings panel UI: win% (family default, expand to lines, muted sub-min rows), repertoire adherence (prep-depth bar + earliest-deviation), theory/soundness section; row deep-links (deviation → `openGameAtPly`). | `static/insights.js`, `static/insights.css` | Renders from the API; deep-link opens the right game+ply; honest empty/thin states. | T0.2, T1.4 |

## Phase 2 — Mistakes / Blunders

| # | Ticket | Owned files | Done-condition | Deps |
|---|--------|-------------|----------------|------|
| T2.1 | Recurring-mistake clusters (pure): aggregate `leaks` by `(category, phase)` (± opening/color); rank by count; gate ≥4; name via `coaching.name_cluster`; generic `missed_threat` → "other tactical miss". | `app/insights.py` | Multi-dim ranked clusters w/ human names + counts; sub-threshold cells suppressed. | T0.3 |
| T2.2 | Foreseeable-rate (pure): fraction of `leaks` with `lead_in_ply < ply` + mode of `threat_motif`; honest narrow-definition caveat. | `app/insights.py` | Rate + dominant warning sign computed. | T0.3 |
| T2.3 | Time-trouble sub-insight (pure): JOIN `leaks` to `game_plies.clock_centis`; bucket by remaining clock; "blunders when <10s: X% vs Y% baseline"; graceful no-clock note. | `app/insights.py` | Rate per bucket; unclocked games excluded with a note. | T0.3 |
| T2.4 | (Optional) Advantage-capitalization card (pure): eval-curve scan (`win_prob` + `games.result`) for sustained winning stretches → converted%? Framed as a rate. *(Cut if slice grows.)* | `app/insights.py` | Rate with sustained-threshold logic (no single-ply spikes). | T0.3 |
| T2.5 | Mistakes API + UI: `GET /api/insights/mistakes` bundling T2.1–T2.4; panel renders ranked clusters (deep-link to a representative game+ply), foreseeable-rate headline, time-trouble card. | `app/main.py`, `app/models.py`, `static/insights.js`, `static/insights.css` | Route 200 + panel renders; cluster deep-links land on the right blunder. | T0.2, T2.1–T2.4 |

## Phase 3 — Endgames

| # | Ticket | Owned files | Done-condition | Deps |
|---|--------|-------------|----------------|------|
| T3.1 | Material-signature classifier (pure): `app/endgame.py::endgame_signature(board)` (incl. opposite- vs same-colored bishops); gate to endgame plies via `analysis.game_phase`. | `app/endgame.py` (new) | Correct buckets on a hand-picked FEN table. | — |
| T3.2 | Endgame accuracy + conversion by type (pure): per-signature accuracy (`accuracy.summarize` on endgame plies) + eval-based conversion; min-sample gated. | `app/insights.py`, `app/endgame.py` | Per-signature accuracy + conversion rate with sample counts. | T3.1, T0.3 |
| T3.3 | Endgames API + UI: `GET /api/insights/endgames` + panel; per-type accuracy/conversion, weakest type highlighted, deep-link to a representative endgame position. | `app/main.py`, `app/models.py`, `static/insights.js`, `static/insights.css` | Route 200 + panel renders honest thin-data states; deep-link works. | T0.2, T3.2 |

## Orchestration plan

- **Slices are sequential** (Openings → Mistakes → Endgames); verify + commit each before
  the next (CLAUDE.md commit policy). Within a slice, parallelize disjoint files.
- **Foundation first:** T0.1 → T0.2/T0.3 (T0.2 and T0.3 touch different files, parallel-safe).
- **Phase 1 wave A (parallel, all in `app/insights.py` — same file, so one owner or careful
  sequencing):** T1.1, T1.2, T1.3 as sections of the builder. **Wave B:** T1.4 (API/models),
  then T1.5 (UI). Maker≠checker for the pytest ticket.
- **Phase 2 / Phase 3** mirror the same shape (pure builders → API/models → UI → tests).
- **Backlog note:** this spec supersedes/absorbs backlog items #3 (eval graph — adjacent),
  #12 (Blunder Trainer → SR, kept as Phase-4/out-of-scope), and #13 (surface time-trouble
  from `%clk` → delivered by T2.3).
