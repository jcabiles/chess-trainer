# Delta spec — Maia move variety (policy sampling)

**Goal (one line):** Ming Ling stops playing the identical game every time —
her move is a seeded sample from Maia's policy distribution (the literal
frequency with which humans of her band play each move) instead of the argmax.

Roadmap: Chapter 4 slice 2 (M2) of `../roadmap/training-and-portfolio.md`.
Builds directly on the merged skeleton (PR #69); contracts unchanged from
`../contracts/maia-skeleton.md`. Appetite: 1–2 days.

## Design

- **Sample the raw policy** (`p` fractions already captured, temperature-
  corrected to 1.0 at spawn — the skeleton did this deliberately). Maia's
  policy IS the empirical human move distribution for the band, so sampling
  it at temperature 1 is the most defensible variety mechanism: no invented
  dial, no persona-cp-temperature misuse (those temperatures are centipawn
  units for SF score softmax — NOT applicable to probabilities).
- **Howler floor:** candidate set = moves with prior ≥ `MAIA_MIN_PRIOR`
  (0.02) OR the argmax (always included); renormalize; seeded draw. Keeps
  the rare-junk tail (0.01% moves) out while preserving real human spread
  (e.g. startpos e4 0.655 / d4 0.223 / c4 0.028).
- **Determinism contract preserved:** draw seeded by `hash((seed, ply))` —
  the exact idiom the SF opening sampling uses — so the same request
  (fen/seed/ply) replays identically, different seeds diverge.

## Files / interfaces to touch

1. **`app/maia_engine.py`** — new PURE function (engine-free, mirrors
   `personas.weighted_choice`'s testability):
   `pick_from_priors(priors: List[dict], seed) -> Optional[str]` —
   returns a uci or None when `priors` is empty. Constant
   `MAIA_MIN_PRIOR = 0.02`. Uses `random.Random(seed)` cumulative draw
   over the floored+renormalized set (argmax weight ≥ everything, so the
   set is never empty when priors exist).
2. **`app/main.py`** — casey Maia branch only: after `top_move()` returns,
   `sampled = pick_from_priors(result["priors"], hash((req.seed or 0, req.ply)))`;
   use it when it is non-None AND legal in the board (defensive — priors come
   from lc0's legal-move lines, but a fake/parser edge must not 500);
   otherwise keep `result["uci"]` (argmax, already legality-guaranteed by
   the engine module). SAN rendered from the board as today.
3. **`tests/test_maia_engine.py`** — pure tests: same seed → same pick;
   ≥2 distinct picks across 10 seeds on the startpos fixture distribution;
   sub-floor moves never picked (seed sweep); argmax always eligible even
   when everything else is sub-floor; empty priors → None.
4. **`tests/test_bot_api.py`** — FakeMaia gains a realistic priors list;
   route tests: same request replays the same move; two seeds that produce
   different picks return different moves; a FakeMaia emitting an
   ILLEGAL-move prior falls back to its (legal) argmax uci, 200 not 500.

## Review folds (dual review 2026-07-18 — binding amendments)

- **Failure-soft sampler (Codex HIGH):** `pick_from_priors` validates every
  entry — entries with missing/non-numeric/non-finite/non-positive `p` are
  dropped; duplicate uci entries are DEDUPED keeping the highest-p one
  (never double-weighted); if no positive mass remains → return None. It can
  never raise on garbage input.
- **Route restructure (refuter HIGH):** the casey branch resolves
  `chosen_uci` FIRST — `sampled` if it is non-None, parses as UCI
  (`Move.from_uci` inside a try), and is legal in the board; else
  `maia_result["uci"]` — and only THEN builds move/SAN/push/response from
  `chosen_uci` alone. The SAN/UCI/FEN triple can never mix argmax and
  sampled moves. Any sampling-path failure yields the legal argmax with
  `engine:"maia"`, never a 500 and never an SF fallback.
- **Floor semantics named honestly (Codex MED):** 0.02 is a hard howler
  CUTOFF, not a probability floor — it sharpens low-entropy positions
  (0.95 + tail → argmax certainty) and barely touches high-entropy ones.
  Accepted: forced positions SHOULD be near-deterministic; the claim is
  "human distribution above the junk line", not "raw empirical policy".
- **Tie-break pinned (refuter LOW):** argmax = `priors[0]` after
  `parse_movestats`'s DESCENDING STABLE sort (equal p keeps parse order) —
  determinism depends on that stability; do not replace the sort or route
  through a set/dict.
- **Test additions (both):** all-zero mass → None; duplicate uci dedupe;
  non-finite/negative p dropped; 0.02 boundary (exactly-at-floor is IN);
  sampled-malformed-uci → argmax at route level; priors argmax ≠
  result["uci"] consistency; plus a 2000-draw frequency sweep asserting
  renormalized expected frequencies within broad tolerance and ZERO picks
  of excluded moves (possibility-only 10-seed checks stay as smoke).
- **Seeding confirmed sound (both):** `hash((int, int))` is unaffected by
  PYTHONHASHSEED (int hashes unsalted) — matches the bot_blunder idiom;
  saved games persist movesUci, not seeds, so cross-version hash drift
  cannot corrupt anything persisted.

## Out of scope

Opening books (explicit B4/roadmap no-go — sampling only); any change to the
SF persona pipeline or its `weighted_choice`; other personas; per-persona
sampling sharpness dials (a ladder-switch concern once more personas ride
Maia); UI changes (indicator already ships).

## Constraints

Same as the skeleton: suite green with no binaries; server stateless
(determinism only from request fields); `pick_from_priors` pure/engine-free;
no schema change; Conventional Commits on this feature branch.

## Verify-by

1. `.venv/bin/python -m pytest -q` green; `.venv/bin/ruff check app tests`.
2. Pure-test evidence: 10-seed sweep on the captured startpos distribution
   yields ≥2 distinct moves (expect e4/d4 dominant), sub-floor never chosen.
3. Live (real lc0): POST /api/bot/move for casey at a fixed fen with seeds
   1..10 → ≥2 distinct `moveUci`, all with `engine:"maia"`; same seed twice
   → identical move.
