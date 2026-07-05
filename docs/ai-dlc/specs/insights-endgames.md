# Delta Spec — Insights Phase 3: Endgames

Slice of `specs/insights-dashboard.md` (roadmap tickets T3.1–T3.3). Inherits the roadmap's
locked decisions: read-only diagnostics, deep-links only (no trainer), min-sample honesty
gates, **Stockfish-only MVP** (Syzygy WDL-flips = opt-in Phase 4, out of scope).

## Goal (one line)
Third Insights sub-tab answering "which endgame types do I play worst?": per-material-type
accuracy + conversion over the endgame suffix of every analyzed game, weakest type
highlighted, deep-link to a representative position.

## Design decisions (this slice — flagged at Gate 2)
1. **Suffix boundary (refuter BLOCKER resolved)**: `game_phase` is NOT monotone — pawn
   promotion adds material, so a position can dip into "endgame" then revert to
   "middlegame" when a pawn queens (refuter reproduced with a real FEN). Therefore the
   endgame slice is the **stable suffix**: `k = (index after the LAST ply whose
   `fen_before` is NOT endgame phase)`, i.e. every ply from `k` onward classifies as
   endgame — transient dips before a promotion are excluded by construction. Games whose
   final ply isn't endgame phase have no endgame slice. `summarize` scores `plies[k:]`
   (contiguous slice — never a row-filter; contracts risk #1). Regression test includes
   the promotion-reversion FEN sequence.
2. **Per-game signature = signature at stable-suffix entry** (`endgame_signature` of
   `plies[k].fen_before`). Morphing endgames (R+minor → R) count under the entry type —
   documented limitation; per-ply re-bucketing is Phase-4.
3. **Conversion**: reuse capitalization semantics scoped to the suffix — user held
   `user_wp ≥ 0.8` for ≥ `_CAP_SUSTAIN_PLIES` (4) consecutive suffix plies (via
   `_user_win_prob`) → "winning endgame"; `converted = _user_score(game) == 1.0`. Reuse
   the module constants; per-signature rate guards zero:
   `gated(converted/winning if winning else None, winning)` (mirrors `insights.py:715`).
4. **Accuracy floor (refuter major resolved)**: a game contributes to its signature's
   accuracy average only if `summarize(plies[k:], my_color)[f"{my_color}_moves"] >= 4`
   (mirrors `_CAP_SUSTAIN_PLIES` — 2-3-ply forced finishes are noise, not signal).
   Excluded-short-suffix count is reported in the section `note` (honesty-caveat pattern,
   like `theory.note`). Per-game averaging (not ply-pooling) is deliberate: `summarize`
   pairs rows positionally, so cross-game concatenation is structurally impossible.
   The accuracy key is `f"{my_color}_accuracy"` (there is NO generic "accuracy" key —
   match `_opening_accuracy`, `insights.py:449`).
5. **Weakest type** = lowest gated accuracy among signatures with `sufficient == true`;
   none sufficient → `weakest: None`, no highlight.
6. **Representative pick ordering**: `_qualified_games()` has NO `ORDER BY` — the builder
   explicitly sorts games by `(imported_at DESC, id DESC)` before iterating, so first-seen
   per signature = most recent, deterministic (do not rely on incidental row order).
7. **`types` sort**: worst gated accuracy first among sufficient; then insufficient;
   ties broken by `n` desc, then signature name asc (deterministic).

## Signature precedence table (binding — the FEN test table must match this)
Evaluate combined piece material of BOTH sides (kings and pawns aside), first match wins:
1. No pieces at all → `pawn` (pure king+pawn).
2. Any queen on board: queens are the only piece type → `queen`; queens + any other
   piece → `Q+piece`.
3. Any rook on board: rooks are the only piece type → `rook` if no side has two rooks,
   else `two-rook`; rooks + minors → `R+minor` (covers asymmetric R vs minor too —
   documented).
4. Minors only: exactly one bishop each side and no knights → `same-bishops` /
   `opposite-bishops` (square color via `(rank+file) % 2`); knights only → `knight`;
   any other minor-only mix (B vs N, two minors a side, …) → `minor`.
5. Anything else → `mixed` (defensive fallback; unreachable if 1-4 are exhaustive —
   asserted in tests).
Note: `game_phase < 24` admits queen-on-board positions — that's why `queen`/`Q+piece`
exist; they are reachable and the FEN table covers them.

## In scope

### T3.1 — `app/endgame.py` (NEW, pure)
- `SIGNATURES: tuple[str, ...]` — canonical bucket list (exported; main.py imports it for
  the empty-shape fallback — contracts risk #3).
- `endgame_signature(board: chess.Board) -> str` — material bucket of the position:
  `pawn` (K+P only), `rook`, `two-rook`, `queen`, `knight`, `same-bishops`,
  `opposite-bishops` (bishop square color via `(rank+file) % 2`), `minor` (N vs B / two
  minors), `R+minor`, `Q+piece`, `mixed` (fallback). Both sides' material considered;
  bucket by the dominant piece class present (exact mapping table in the module docstring;
  hand-picked FEN test table is the contract).
- `endgame_start_index(plies) -> int | None` — index of the **stable endgame suffix**
  (design decision 1): the index after the last ply whose `fen_before` is NOT endgame
  phase; `None` if the final classifiable ply isn't endgame phase (game never stably
  reaches one). Guards None/bad FENs (unclassifiable rows are treated conservatively —
  a bad-FEN row cannot prove "endgame", so it breaks the suffix like a non-endgame ply;
  contracts risk #2).

### T3.2 — `app/insights.py::build_endgame_insights()` (pure)
- Population: `_qualified_games()`; coverage via `storage.coverage()` + `qualified` splice.
- Games sorted `(imported_at DESC, id DESC)` first (decision 6). Per game:
  `storage.get_plies()` → `endgame_start_index` (stable suffix) → skip games with no
  endgame → bucket by entry signature → per signature accumulate:
  - **accuracy**: `summarize(plies[k:], my_color)[f"{my_color}_accuracy"]`, included only
    when `[f"{my_color}_moves"] >= 4` (decision 4); per-signature average,
    `gated(avg, n_contributing_games)`;
  - **conversion**: winning-endgame count (decision 3) + converted count,
    `rate: gated(converted/winning if winning else None, winning)`;
  - **example**: first-seen game per signature (= most recent, given the sort) with the
    entry ply, as `{game_id, ply}`.
- Returns (docstring documents the full shape verbatim, matching module convention):
  `{coverage (incl. reached_endgame count — refuter minor), types: [{signature, games,
  accuracy: gated, conversion: {winning, converted, rate: gated}, example}],
  weakest: str|None, note (mentions short-suffix exclusions + no-endgame games)}` —
  `types` sorted per decision 7.
- Raises `RuntimeError` when storage uninitialised (inherited via `_qualified_games`).

### T3.3 — API + UI
- `models.py`: `InsightsEndgameType`, `InsightsEndgameConversion`, reuse
  `InsightsGatedMetric` + `InsightsClusterExample` shape (new `InsightsEndgameExample`
  only if reuse is awkward), `InsightsEndgamesCoverage` mirroring
  `InsightsMistakesCoverage`, `EndgameInsightsResponse` (flat composition).
- `main.py`: `GET /api/insights/endgames` mirroring the openings/mistakes pattern —
  `try/except RuntimeError` → hand-built empty shape importing `endgame.SIGNATURES`
  (never re-hardcode bucket names); always 200.
- `static/insights.js`: third sub-tab "Endgames" — `_endgamesLoaded` guard,
  `loadEndgames()` lazy fetch on first click, `renderEndgamesPanel()` (stat rows +
  per-type bars reusing the Phase-2 visual language: azure accuracy bars, conversion as
  text+mini bar, weakest type carries the severity-stripe card treatment), thin-data
  lines per metric via `renderGatedLine`, deep-link buttons via `renderDeepLinkButton`,
  `playEntrance(root)` once. Extend `buildShell()`'s hand-coded toggle at EVERY site
  (button, panel, aria toggle, `.is-active` toggle, lazy gate — contracts risk #4).
- `static/insights.css`: only additive classes in the established `insights-*` namespace;
  tokens only.

## Out of scope (explicit)
Syzygy/tablebase WDL-flips · per-ply signature re-bucketing (morphing endgames) · any new
trainer/SR · DB schema changes · engine calls at request time · eval graph · changes to
openings/mistakes builders beyond zero-touch reuse · URL router.

## Constraints (binding)
- `app/endgame.py` + the new builder are **pure** — full pytest suite passes with no
  Stockfish binary (profile invariant).
- No DB migration; read-only over `games`/`game_plies` (+ optionally `leaks`).
- Contiguous-suffix slicing only (risk #1); `fen_before` None-guards at every
  `chess.Board()` site (risk #2); POV flips only via `_user_win_prob`/`win_prob_white`
  (risk #6).
- Frontend: injected `api` only; keep `role=tabpanel` + `.is-active` pattern; JSON reads
  in existing panels untouched; tokens-only CSS; entrance animation once per load.
- Wire format: every metric `{value, n, sufficient}` via `gated()`; `models.py` and the
  main.py fallback stay in sync with the builder docstring.

## Verify-by (end-to-end)
1. `pytest -q` green with no engine (new unit tests: signature FEN table incl.
   opposite/same-bishop cases; suffix-index on hand-built ply lists incl. no-endgame and
   bad-FEN rows; builder on a seeded temp DB with thin + sufficient buckets;
   API route 200 on empty DB with typed zero shape). `ruff check` clean.
2. TestClient: `GET /api/insights/endgames` on the real dev DB → 200, shape matches model.
3. Browser (design-reviewer): Endgames sub-tab lazy-loads once; per-type rows render with
   bars + gated thin-data lines; weakest-type highlight only when sufficient; deep-link
   opens review at the entry ply; sub-tab switching replays nothing; both themes,
   375 + 1440; zero console errors.
4. Independent diff review (maker ≠ checker) before commit; grep gate on CSS.

## Refuter resolutions (folded in above — summary)
Verdict was **needs-changes**; all resolved inline:
1. **(blocker)** `game_phase` non-monotone under promotion → "stable suffix" definition
   (index after last non-endgame ply) + promotion-reversion regression test. → decisions
   1, T3.1.
2. **(major)** No `"accuracy"` key in `summarize` → use `f"{my_color}_accuracy"` per
   `_opening_accuracy` precedent. → decision 4.
3. **(major)** Division-by-zero in conversion rate → `if winning else None` guard per
   `insights.py:715`. → decision 3.
4. **(major)** Tiny-suffix noise in per-game averaging → ≥4 my-side scored moves floor +
   excluded count in `note`; pooling rejected (summarize pairs positionally — cross-game
   concat structurally impossible). → decision 4.
5. **(major)** `_qualified_games()` unordered → explicit `(imported_at DESC, id DESC)`
   sort before representative pick. → decision 6.
6. **(major)** Bucket precedence deferred to implementation → binding precedence table
   now in the spec; FEN test table must match it. → §Signature precedence table.
7. **(minor)** `types` tie-break specified (n desc, name asc). → decision 7.
8. **(minor)** Coverage adds `reached_endgame`; `note` explains empty panels honestly.

Refuter-verified baselines: pytest **515 passed**; ruff clean; `_CAP_*` constants
module-level + importable; `summarize` returns None safely for ≤1-ply input;
`storage.get_plies` ordered by ply; frontend extension sites match live insights.js.
