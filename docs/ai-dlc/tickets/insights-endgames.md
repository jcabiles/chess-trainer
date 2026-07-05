# Tickets — Insights Phase 3: Endgames

4 tickets, serial (T3.1 → T3.2 → T3.3 → T3.4). Spec: `specs/insights-endgames.md`;
contracts: `contracts/insights-endgames.md`. Maker ≠ checker: implementation by worker
agent(s); independent review + browser pass before commit. Baseline: 515 tests green.

### T3.1 — `app/endgame.py` (pure classifier)
**Owns:** `app/endgame.py` (new), `tests/test_endgame.py` (new).
**Does:** `SIGNATURES` tuple (exported); `endgame_signature(board)` implementing the
spec's binding precedence table exactly; `endgame_start_index(plies)` = stable-suffix
index (after last non-endgame ply; bad/None `fen_before` breaks the suffix
conservatively; `None` when the game never stably reaches an endgame).
**Acceptance:** hand-picked FEN table matching the precedence table (≥1 FEN per bucket,
incl. same/opposite bishops, queen-on-board endgame, R vs minor asymmetric, mixed
fallback assertion); stable-suffix tests incl. the promotion-reversion sequence
(refuter blocker), no-endgame game, bad-FEN row, empty list.
**Done-condition:** `pytest tests/test_endgame.py -q` green with NO Stockfish binary;
`ruff check app tests` clean.
**Deps:** none.

### T3.2 — `build_endgame_insights()` (pure builder)
**Owns:** `app/insights.py` (additive section only), `tests/test_insights.py` (additive).
**Does:** builder per spec: games sorted `(imported_at DESC, id DESC)`; stable suffix →
entry signature → per-signature accuracy (`f"{my_color}_accuracy"`, ≥4 my-side moves
floor, `gated(avg, n)`), conversion (capitalization semantics on the suffix, zero-guarded
rate), most-recent `{game_id, ply}` example; coverage + `reached_endgame`; `note` with
short-suffix + no-endgame exclusion counts; `types` sorted (worst sufficient first,
ties n desc / name asc); `weakest`; exhaustive docstring block (module convention);
raises `RuntimeError` when storage uninitialised (inherited).
**Acceptance:** seeded temp-DB tests — thin + sufficient buckets, conversion won/lost/
drawn cases, floor exclusion, deterministic ordering, no-endgame-only DB (types empty,
coverage explains).
**Done-condition:** `pytest -q` full suite green, no engine; ruff clean.
**Deps:** T3.1.

### T3.3 — API route + models
**Owns:** `app/main.py` (insights section), `app/models.py` (additive),
`tests/test_insights_api.py` (additive).
**Does:** `GET /api/insights/endgames` mirroring openings/mistakes: `response_model`,
`try/except RuntimeError` → hand-built empty shape that imports `endgame.SIGNATURES`
(never re-hardcodes bucket names); models `InsightsEndgameType`,
`InsightsEndgameConversion`, `InsightsEndgamesCoverage` (baseline + `reached_endgame`),
example reusing the `{game_id, ply}` shape, `EndgameInsightsResponse`.
**Acceptance:** TestClient — 200 + typed shape on empty DB; 200 with data on seeded DB;
fallback dict validates against the model in a test (drift guard).
**Done-condition:** `pytest -q` green; ruff clean.
**Deps:** T3.2.

### T3.4 — UI + verify + commit
**Owns:** `static/insights.js`, `static/insights.css`; orchestrator glue + commits.
**Does:** third sub-tab per contracts §Frontend seam — extend `buildShell()` at every
hand-coded site (button, panel, aria/`.is-active` three-way toggle, `_endgamesLoaded`
guard, lazy `loadEndgames()`); `renderEndgamesPanel()` reusing Phase-2 visual language
(gated metric rows, azure accuracy bars, weakest-type severity-stripe card, conversion
text + mini bar, `renderGatedLine` thin-data, `renderDeepLinkButton` per type,
`playEntrance` once); `role=tabpanel` + `.is-active` only (generic hide rule untouched);
tokens-only CSS additive in `insights-*` namespace; bump `?v=` on insights assets in
index.html.
**Acceptance:** browser (design-reviewer, maker ≠ checker): lazy loads once; no
re-animation on sub-tab switches; deep-link lands at entry ply in review mode; honest
thin/empty states; both themes × {375, 1440}; zero console errors. Then independent
diff review; commit series (pure module → builder → API → UI or cohesive grouping),
feature branch `feat/insights-endgames`.
**Done-condition:** spec Verify-by all green; commits made.
**Deps:** T3.1–T3.3.
