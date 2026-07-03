# Spec — Insights / Analytics Dashboard

Research: `docs/ai-dlc/research/insights-dashboard.md`. Tickets:
`docs/ai-dlc/tickets/insights-dashboard.md`. Backend-led (pure read-models over already-
stored review data) + a new frontend tab. Ships as **independent vertical slices** in
priority order: **Openings → Mistakes → Endgames**.

## Goal (one line)

A new top-level **Insights** tab that turns the already-persisted game-review data into a
**triage router** — openings / recurring-mistakes / endgames diagnostics, each linking to
the exact position to study — honest about thin data, with no per-game vanity scoreboard.

## Locked decisions (from interview)

1. **Openings adherence** = *your repertoire first, theory fallback*. Adherence measured
   against the user's prepared lines (reuse `repertoire.py`); named-theory book-exit +
   opening-phase accuracy for games outside the curated repertoire.
2. **Router scope** = read-only diagnostics that **deep-link** into existing surfaces
   (analysis-board FEN load; game-review replay at a ply). **No new trainers**, no SR.
3. **Placement** = new top-level **Insights** tab (not grown inside the Review profiler).
4. **Metric honesty** = no per-game accuracy/Elo scoreboard; family-level aggregation +
   min-sample gates ("not enough games yet"); one *de-emphasized* long-run trend allowed.
5. **Motif depth** = ship current `motifs.py` taxonomy; expansion is a Phase-4 fast-follow.
6. **Time-trouble** = a sub-insight card *inside* the Mistakes panel (not its own panel).
7. **Endgame depth** = MVP is Stockfish-only (material-type accuracy/conversion); Syzygy
   WDL-flip detection is opt-in **Phase 4** behind a settings toggle + one-time download.
8. **Sequencing** = vertical slices, each independently shippable (backend + API + UI + tests).

## Architecture

**Backend (pure / unit-testable, mirroring `analysis.py`/`accuracy.py`/`profile.py`):**
- `app/insights.py` (NEW) — pure read-model builders `build_openings_insights`,
  `build_mistakes_insights`, `build_endgame_insights`, following the SQL-then-shape idiom
  in `profile.py::build_profile`. Each returns `{value, n, sufficient}`-style records so the
  UI can render honesty gates.
- `app/endgame.py` (NEW) — pure `endgame_signature(board) -> str` (material bucket: `KP`,
  `rook`, `two-rook`, `opposite-bishops`, `same-bishops`, `knight`, `queen`, `R+minor`, …;
  bishop square color via `(rank+file)%2`) + phase-filter helpers.
- **Reuse (do not rebuild):** `repertoire.py` (`tree()`, deviation semantics),
  `book.py::is_book_move` (book.py:207), `openings.py::identify`, `accuracy.py::summarize`
  (filterable to a phase subset), `analysis.py` (`game_phase`, `win_prob_white`,
  `win_prob_from_cp`, `pov_score_to_white_cp`, `leak_severity`), `coaching.name_cluster`,
  `profile.py` patterns, and `storage.py` tables `games` / `game_plies` / `leaks` + `coverage()`.
- **API** (`app/main.py`, mirror `GET /api/profile` at `main.py:779-806`): one namespaced
  route per slice — `GET /api/insights/openings`, `/api/insights/mistakes`,
  `/api/insights/endgames` — each a typed Pydantic response incl. coverage/sample metadata.
  **No engine calls, no DB migration** (pure post-processing of stored rows).

**Frontend (vanilla ES modules, no build step):**
- NEW tab: button in `index.html:161-167` (`data-tab="insights"`), panel div near `:251`,
  add `'insights'` to the **two** hardcoded arrays (`app.js:2005` **and** `review.js:515`).
- NEW `static/insights.js` (`initInsights(api)`, imported/called in `app.js` alongside
  `initReview`) + `static/insights.css` linked at `index.html:26-30`.
- **Reuse UI idioms:** `el()` (`review.js:23-35`), `reviewStat` (`review.js:827`), design
  tokens (`style.css:48-53`), `prefs.js` `readUiPrefs`/`writeUiPref` for panel prefs.
- **Deep-link seam:** expose `api.actions.openGameAtPly(gameId, ply)` (wraps `openGame` +
  `goto`); `loadFen` for board FEN. All downstream loaders already exist.

## In scope (per phase — see tickets for the breakdown)

- **Foundation (T0):** Insights tab scaffold; `openGameAtPly` deep-link action; honesty/
  min-sample util.
- **Phase 1 — Openings:** win% by ECO family/line; repertoire adherence (prep-depth +
  earliest-deviation, reuse `repertoire.py`); theory fallback (book-exit + opening-phase
  accuracy) for off-repertoire games; `/api/insights/openings`; panel UI with deep-links.
- **Phase 2 — Mistakes:** recurring-mistake clusters (`coaching.name_cluster`); foreseeable-
  rate; time-trouble sub-insight (`clock_centis` JOIN); optional advantage-capitalization
  card; `/api/insights/mistakes`; panel UI with per-cluster deep-links.
- **Phase 3 — Endgames:** material-signature classifier; endgame accuracy + conversion by
  type; `/api/insights/endgames`; panel UI, weakest-type highlighted, deep-links.

## Out of scope (this roadmap)

- **Tablebase WDL-flips** (opt-in Phase 4: 5-man Syzygy behind a settings toggle + download;
  network/disk-gated, user-runtime only).
- **Motif taxonomy expansion** (`motifs.py`: overloaded/trapped-piece/removing-defender/
  in-between) — Phase 4 fast-follow; until then the generic bucket is labeled honestly.
- **Spaced-repetition on own blunders** (SM-2 + schema v2 + interactive puzzle UI) — the
  "Blunder Trainer" backlog item; deliberately excluded per the router-scope decision.
- **URL/hash router** for shareable deep-links (board/game loaders already exist).
- Any per-game accuracy/Elo scoreboard; cross-game live-play analytics.

## Constraints

- `app/insights.py` + `app/endgame.py` are **pure** — the full suite passes with **no
  Stockfish binary** (post-processing of stored rows only). Reuse `analysis.*`; don't
  re-derive the White-POV / mover-sign rule.
- **No DB schema change** in Phases 1–3; insights are read-models over existing tables.
- All insights gated on `my_color` tagged + `analysis_status='done'` (mirror `profile.py`).
- Honest data: default to ECO-family aggregation + min-sample gates; never fabricate a
  pattern from a 1–3 game sample. Depth-10 evals → avoid false precision in copy.
- Tokens-only CSS, no raw hex; AA contrast; visible `:focus-visible` on any control.
- Frontend follows the injected-`api` decoupling (modules never import from `app.js`); each
  module rolls its own small fetch helpers (per `review.js`).

## Verify-by

1. **Unit (pytest, no engine):** `tests/test_insights.py` — win% family aggregation +
   sub-min gating; repertoire deviation ply/move on a follow-then-deviate fixture; book-exit
   ply; mistake clusters + threshold suppression; foreseeable-rate; time-trouble buckets
   (clocked + unclocked fixtures); `endgame_signature` FEN→bucket table; endgame accuracy/
   conversion.
2. **API (pytest, `TestClient`):** each `/api/insights/*` returns 200 with populated
   sections on analyzed games and is empty-safe on none; no engine/DB migration triggered.
3. **Browser (Playwright-MCP):** each panel renders from its API against the live DB;
   deep-links land on the correct game+ply / FEN; thin-data + empty states show honestly;
   Insights tab hides when switching away (both hardcoded arrays); 0 console errors.
4. `pytest` green; `ruff` clean. Verify + commit **per slice** (implemented → verified →
   reviewed), not one big drop.
