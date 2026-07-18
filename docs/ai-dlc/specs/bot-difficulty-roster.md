# Spec — Bot roster expansion: aggressive-1350 + sloppy sub-ELO

Slice of Chapter 3 (play vs bots, N3). Roadmap "NEXT: Bot roster expansion"
(gated on B4 — shipped). Contracts: [`../contracts/bot-difficulty-roster.md`](../contracts/bot-difficulty-roster.md).
Builds on B4 (personas) + B5 (`app/bot_blunder.py` causal gate).

## Goal (one line)
Add two new 1350-band personas: (1) an **aggressive attacker weak on defense**
(pure-data, reuses the B5 gate) and (2) a **"sloppy" 1350** that makes frequent
small MISTAKES via a NEW inaccuracy-injection tier, faking ~1100–1250 strength.

## Decisions (from Gate-1)
- **#1 aggressive** = data-only. No attack-seeking code; "aggression" = high
  temperature (varied/sharp) + low `threatDistance` (misses defensive threats even
  when far off its attacking plan) + high `blunderRate`. Raw strength stays
  UCI_Elo 1350.
- **#2 sloppy** = frequent inaccuracies, rare blunders. New `mistakeRate` dial +
  a post-opening tier that (with prob `mistakeRate`) plays a candidate ~50–250cp
  worse than best. Keep `blunderRate` LOW so it rarely hangs pieces outright.
  Effective strength ~1100–1250 (ballpark — no hard ELO assertion).

## Proposed personas (values tunable at Gate-2)
Existing ladder unchanged: Casey 1350 · Morgan 1550 · Alex 1800 · Vera 2000.
Two additions (both `elo=1350`, the UCI_Elo floor is 1320 so 1350 is legal):

| id | name | elo | style | temp | blunderRate | threatDistance | mistakeRate |
|----|------|-----|-------|------|-------------|----------------|-------------|
| `diego` | Diego | 1350 | attacking | 190 | 0.85 | 0.10 | 0.0 |
| `robin` | Robin | 1350 | sloppy | 100 | 0.18 | 0.30 | 0.50 |

- **Diego** — "Attacking club player — hunts your king, soft on defense." High temp
  = sharp/varied play; lowest `threatDistance` on the ladder = ignores defensive
  threats that sit off his attack plan; high `blunderRate` (≈ Casey).
- **Robin** — "Beginner — drifts and leaks small mistakes." Low `blunderRate`
  (rarely hangs a piece), high `mistakeRate` (frequent 50–250cp drift).

## Files / interfaces to touch
- `app/bot_blunder.py` (pure, engine-free): add the mistake tier —
  - `should_mistake(persona, phase, ply, seed) -> bool` — fires iff
    `persona.mistakeRate > 0` and seeded
    `Random(hash((seed, ply, MISTAKE_SALT))).random() < mistakeRate * phase_gate(phase)`.
    **`MISTAKE_SALT` is an INT constant (e.g. `1`), NOT a str** — Python randomizes
    str/bytes hashing per process (PEP 456), which would make Robin's moves diverge
    across a server restart; an all-int tuple hashes stably (ints hash to themselves),
    matching the existing blunder draw `hash((seed, ply))`. The int salt still
    decorrelates the two draws (different tuple). `phase_gate` = 0 opening (guard;
    opening is handled by the softmax branch anyway), full otherwise.
  - `pick_mistake(cands, board, seed, ply) -> idx` — compute mover-POV `scoreCp`
    per candidate (flip by `board.turn`), compute its OWN per-candidate delta
    `loss_i = mover_cp[0] - mover_cp[i]` (do NOT call `analysis.cp_loss`, whose
    signature is single-position before/after — only the bucket THRESHOLDS are
    reused). Keep candidates whose `loss_i ∈ [MISTAKE_LO=50, MISTAKE_HI=250]`, pick
    one seeded (`Random(hash((seed, ply, MISTAKE_SALT)))`), tie-broken by lowest
    index. **Empty-band fallback (bounded):** the candidate with the smallest loss
    that is still `> MISTAKE_LO` AND `<= MISTAKE_HI`; if NONE fall in `(MISTAKE_LO,
    MISTAKE_HI]` → return `0` (best). **Never** return a loss `> MISTAKE_HI` — an
    unbounded fallback would let Robin play a blunder-magnitude (800cp+) move in a
    losing position, contradicting its low-blunder design and breaking the
    review-bucket consistency claim. **Skip the whole tier when `cands[0]` is a
    forced mate** (`abs(cands[0]["scoreCp"]) >= MATE_GUARD`) → return `0`.
    `MATE_GUARD` is a LOCAL `bot_blunder` int constant pinned to the `bot_engine`
    scoreCp mate axis (candidates use `bot_engine.MATE_CP=100000`); set e.g.
    `MATE_GUARD = 50_000` (well above any real eval, below the ±100000 sentinel) —
    **NOT** `analysis.MATE_CP=10000` and **NOT** `bot_blunder.MATE_SEVERITY` (severity
    axis). Also guard `len(cands) < 2` → return `0`. Deterministic.
- `app/personas.py`: add `mistakeRate: float = 0.0` to the `Persona` dataclass;
  `_parse_persona` reads it with default `0.0` (so old JSON + the 4 existing personas
  stay B4-identical); `_validate` bounds `mistakeRate ∈ [0, 1]`. Add `diego` + `robin`
  to `_DEFAULT_PERSONAS`.
- `data/personas.json`: mirror — add `diego` + `robin` (MUST match `_DEFAULT_PERSONAS`).
- `app/main.py`: in the persona branch post-opening `else` (`main.py:756-760`), add a
  mistake sub-branch BEFORE the plain best-move fallback:
  `if persona.mistakeRate and bot_blunder.should_mistake(...): cands = cands or
  await bot.candidates(fen, k=MISTAKE_K, elo); idx = bot_blunder.pick_mistake(...)`.
  `MISTAKE_K = 5`; add `assert MISTAKE_K == CAND_K == SAMPLE_K` (module level) so the
  `cands = cands or …` reuse of a gate-fetched list stays sound — if `CAND_K` is ever
  widened without matching `MISTAKE_K`, the reused list would be a different width
  with no test catching it. `pick_mistake` additionally tolerates a short list
  (`len(cands) < 2 → 0`). Reuse any `cands` the blunder gate already fetched (single
  `candidates()` call). The blunder gate still runs FIRST and short-circuits — a Robin
  move can blunder (rarely) OR mistake, never both in one ply.

## Out of scope
- No attack-seeking / king-safety heuristic for Diego (data-only, per Gate-1).
- No new UI — the persona picker is already data-driven (`botplay.js` unchanged).
- No hard ELO-calibration test (1100–1250 is a ballpark, not an assertion).
- No DB/schema change; no clocks (B7); no change to Casey/Morgan/Alex/Vera behavior.
- No sub-1320 `elo` value — sub-ELO comes only from the mistake tier.

## Constraints (invariants)
- Pure/engine-free: `bot_blunder.py`, `personas.py`, `analysis.py` gain NO engine/IO;
  full `pytest` passes with no Stockfish binary.
- All RNG via `hash((seed, ply, ...))` — never bare `random`. Mistake draw salted
  `"mistake"` to decorrelate from the blunder draw.
- Bot engine isolation — mistake tier routes ONLY through `bot.candidates()`
  (isolated process/lock); NEVER `app.engine`. User's eval stays full-strength.
- Legacy `personaId=None` branch B3 byte-identical; existing 4 personas keep B4
  late-ply k=1+best parity (`mistakeRate=0` → mistake sub-branch never taken).
- Single `candidates()` call per move (reuse `cands`).
- Mover-POV flip before any `scoreCp` comparison; normalize the two MATE_CP axes
  (skip mistake when best is a forced mate).
- `data/personas.json` ↔ `_DEFAULT_PERSONAS` stay in sync. Persona id/name unique.
- Ladder monotonicity: the current `test_personas.py` asserts (a) strictly-decreasing
  blunderRate and (b) GLOBAL blunderRate uniqueness — BOTH break the moment three
  personas share elo=1350 (Diego=Casey=0.85 kills uniqueness; Robin=0.18 at 1350
  undercuts Morgan=0.65 at 1550, so min-per-group is non-monotone). Rewrite the
  assertion PRECISELY (do NOT weaken to non-strict/per-pair): **group by elo; the
  MAX blunderRate per elo group must be NON-INCREASING across strictly-increasing elo
  groups** (verified to hold: 1350→0.85, 1550→0.65, 1800→0.40, 2000→0.20), and scope
  the uniqueness check to WITHIN an elo group only (equal-elo personas may repeat a
  rate across groups but the max-per-group must strictly step down). Min-per-group is
  NOT monotone and must not be asserted.

## Verify-by (end-to-end)
1. `pytest -q` + `ruff check app tests` green — new mistake-tier tests
   (`should_mistake` seeded/never-opening; `pick_mistake` picks an in-band 50–250cp
   candidate, skips forced-mate, deterministic same-seed-twice); persona tests (new
   dials + 6-persona ladder loads, old-JSON-without-mistakeRate still loads, equal-elo
   monotonicity holds); B3/B4 parity tests still green.
2. Live (Playwright on :8002): picker shows 6 personas incl. Diego + Robin; play
   Robin post-opening → observe it playing sub-optimal-but-legal moves (planted
   position: it drifts ~50–250cp off best on gated plies, deterministic per seed);
   same seed replays identically; Diego ignores an off-plan defensive threat while
   pushing its attack; **user's eval bar / Analysis unaffected** (full strength — no
   leak). Clean up test bot games from the DB.
3. A finished Robin game auto-analyzes (B3 pipeline) and the review coach labels its
   drifted moves as inaccuracies/mistakes (consistent bands).
