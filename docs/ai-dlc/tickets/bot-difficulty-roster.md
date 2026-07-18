# Tickets — Bot roster expansion: aggressive-1350 + sloppy sub-ELO

Spec: [`../specs/bot-difficulty-roster.md`](../specs/bot-difficulty-roster.md).
Contracts: [`../contracts/bot-difficulty-roster.md`](../contracts/bot-difficulty-roster.md).
Branch: `feat/bot-difficulty-roster` off up-to-date main.
Waves (disjoint owners): **W1:** T1 ∥ T2 → **W2:** T3 (needs T1+T2) →
**W3:** T4 verify → T5 review → T6 close-out. Refuter-only (Codex infra-down).
All 6 refuter findings already folded into the spec — implement the spec as written.

## T1 — `app/bot_blunder.py` mistake tier + tests (W1) — CORE
New PURE, engine-free, seedable functions (co-located with the B5 gate):
- `MISTAKE_LO=50`, `MISTAKE_HI=250`, `MISTAKE_SALT=1` (INT — never a str, per
  determinism finding), `MATE_GUARD=50_000` (local; pinned to the `bot_engine`
  scoreCp mate axis ±100000, NOT `analysis.MATE_CP`, NOT `MATE_SEVERITY`).
- `should_mistake(persona, phase, ply, seed) -> bool` — `persona.mistakeRate>0` AND
  `Random(hash((seed, ply, MISTAKE_SALT))).random() < mistakeRate * phase_gate(phase)`
  (phase_gate 0 in opening, full otherwise).
- `pick_mistake(cands, board, seed, ply) -> int` — mover-POV flip by `board.turn`;
  own delta `loss_i = mover_cp[0]-mover_cp[i]`; keep `loss_i ∈ [MISTAKE_LO,MISTAKE_HI]`,
  seeded pick (`hash((seed,ply,MISTAKE_SALT))`), tie-break lowest index. **Bounded**
  fallback: smallest loss in `(MISTAKE_LO, MISTAKE_HI]`; else `0`. NEVER return a
  loss `> MISTAKE_HI`. Return `0` when `cands[0]` is a forced mate
  (`abs(scoreCp) >= MATE_GUARD`) or `len(cands) < 2`.
- **Owns:** `app/bot_blunder.py`, `tests/test_bot_mistake.py`
- **Done:** `pytest tests/test_bot_mistake.py -q` green — `should_mistake` seeded,
  never fires in opening, respects `mistakeRate=0`; `pick_mistake` picks an in-band
  50–250cp candidate, **never returns a >250cp (blunder-magnitude) move even when the
  band is empty** (planted losing position: all non-best >250 → returns 0), skips
  forced-mate best, handles a 1-element list, Black-to-move mover-POV correct,
  **deterministic (same seed ⇒ same idx twice, stable across a fresh Python process
  — int-only hash)**. Full `pytest -q` + `ruff` green; no engine import added.

## T2 — persona dials + two new personas + tests (W1)
`app/personas.py`: add `mistakeRate: float = 0.0` to `Persona`; `_parse_persona`
reads it default `0.0` (old JSON + the 4 existing personas stay B4-identical);
`_validate` bounds `mistakeRate ∈ [0,1]`. Add `diego` + `robin` to `_DEFAULT_PERSONAS`
(values from spec table). `data/personas.json`: mirror exactly.
Rewrite the ladder-monotonicity test per spec: **max-blunderRate-per-elo-group
non-increasing across strictly-increasing elo**; uniqueness scoped WITHIN an elo
group (drop the global-uniqueness assertion). Do NOT weaken to non-strict/per-pair.
- **Owns:** `app/personas.py`, `data/personas.json`, `tests/test_personas.py`
- **Done:** `pytest tests/test_personas.py -q` green — 6 personas load; `mistakeRate`
  present with default 0.0 when absent from JSON; old JSON (no `mistakeRate`) still
  loads; `_validate` bounds; `diego`(mistakeRate 0)/`robin`(mistakeRate 0.5) parsed;
  **max-per-elo-group monotonicity holds, equal-elo (three 1350s) accepted**;
  `data/personas.json` == `_DEFAULT_PERSONAS`.

## T3 — `app/main.py` wire the mistake tier, gate-after-blunder (W2, T1+T2) — HOTSPOT
In the persona post-opening `else` (`main.py:756-760`), add a mistake sub-branch
BEFORE the plain best-move fallback: `if persona.mistakeRate and
bot_blunder.should_mistake(persona, phase, req.ply, req.seed or 0):
cands = cands or await bot.candidates(req.fen, k=MISTAKE_K, elo=persona.elo);
idx = bot_blunder.pick_mistake(cands, board, req.seed or 0, req.ply)`; else the
UNCHANGED k=1 best path. Add `MISTAKE_K = 5` + `assert MISTAKE_K == CAND_K == SAMPLE_K`.
Blunder gate still runs FIRST (short-circuits); reuse any gate-fetched `cands` (single
`candidates()` call). Legacy no-persona branch + B4 late-ply parity untouched.
- **Owns:** `app/main.py`, `tests/test_bot_mistake_api.py` (new). May need a one-line
  touch to a B4 parity test ONLY if a `mistakeRate=0` persona trips the new branch
  (it must NOT — first confirm green as-is). Do NOT weaken parity tests.
- **Done:** `pytest -q` green (incl. `test_persona_late_ply_plays_best`) — Robin
  post-opening plays a gated in-band mistake for a planted position; the 4 existing
  personas stay k=1+best (mistake branch unreachable, `mistakeRate=0`); bare `{fen}`
  + no-persona B3-identical; Black-bot mover-POV correct; only ONE `candidates()` call
  per move; no second engine call on the gate-fired-no-survivor reuse path.

## T4 — Browser verification (W3)
Playwright on :8002 (server via dangerouslyDisableSandbox). Picker shows **6**
personas incl. Diego + Robin. Play Robin post-opening → it plays legal
sub-optimal-but-not-hanging moves (drifts ~50–250cp); same seed replays identically.
Play Diego → ignores an off-plan defensive threat while pushing its attack.
**User's eval bar / Analysis stays full-strength (no leak).** A finished Robin game
auto-analyzes (B3) and the coach labels its drift as inaccuracy/mistake. Clean up test
bot games from the DB (`DELETE /api/games/{id}`).
- **Done:** every item observed; test games removed.

## T5 — Refuter review of the diff (W3, after T4)
Fresh-context refuter over the actual diff: `pick_mistake` bound never exceeded (no
blunder-magnitude leak), int-salt determinism across process, single `candidates()`
call, mover-POV correctness, B3/B4 parity, no analysis-engine leak, monotonicity test
not weakened, personas.json↔defaults sync. Fold; re-verify. (Codex if it recovers.)
- **Done:** resolved/accepted; suite green.

## T6 — Close-out (W3, after T5)
User pass/fail → mark the roadmap "Bot roster expansion" slice `[x]`;
`pytest`/`ruff`/`node --check` (no JS change, but confirm); commit; push; PR.
- **Done:** PR open.

## Notes
- No frontend change — the picker is fully data-driven (`botplay.js` unchanged); T4
  only verifies the roster renders.
- Live-reload hazard: one feature branch; don't leave commits unpushed under the
  user's live `--reload` server.
- Appetite (~1–1.5 days): if over, cut order — Diego is pure data (nearly free); the
  mistake tier is the real work. Never cut: the bounded `pick_mistake` fallback (the
  HIGH fix), int-salt determinism, B3/B4 parity, no analysis leak.
