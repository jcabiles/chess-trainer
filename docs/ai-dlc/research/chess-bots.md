# Chess bots — research synthesis & architecture decision (B1)

**Question:** how do we build bot opponents at labeled ELO levels whose
mistakes are *causal* (a ~1100 bot misses your threat because it's busy
orchestrating its own attack) — never chess.com-style random inexplicable
drops?

**Method:** six deep-research agents enriched the knowledge base under
[`docs/design/research/`](../../design/research/) (one folder each,
enrich-in-place, every claim cited, ⚠ = unverified); plus a runnable local
engine probe ([`probes/`](probes/results.md)). This doc carries the
argument; the notes carry the depth. Slice B1 of
[`../roadmap/training-and-portfolio.md`](../roadmap/training-and-portfolio.md)
Chapter 3; contracts in [`../contracts/bot-play.md`](../contracts/bot-play.md).
Dual-reviewed (Codex gpt-5.6-sol + Claude refuter) — findings and
resolutions in the [Verification log](#verification-log).

---

## 1. Engine strategy (incl. process isolation + Mac feasibility)

**Evidence** ([engine-adaptation/](../../design/research/engine-adaptation/)):

- **Stockfish's weakening knobs set error *rate*, not error *shape*.**
  `Skill Level` picks at depth `1+level` among the top-4 MultiPV root moves
  with RNG noise (source-verified). `UCI_Elo` is just a remap onto
  fractional Skill Level with a **hard floor of 1320**, calibrated against
  an *engine* pool — not a human ladder
  ([stockfish-weakening.md](../../design/research/engine-adaptation/stockfish-weakening.md);
  ⚠ the two notes record different calibration-anchor details — Stash at
  120s+1s/CCRL-Blitz vs goldfish1.13 at 60+0.6 per SF PR #2225
  ([engine-elo-vs-human-elo.md](../../design/research/rating-calibration/engine-elo-vs-human-elo.md)) —
  both are engine-pool anchors, which is all the conclusion needs).
- **Maia is the only off-the-shelf human-error model.** Rating-banded lc0
  policy nets (1100–1900) trained to predict the *human* move: 46–53%
  move-match vs 33–41% for weakened Stockfish
  ([maia-lc0.md](../../design/research/engine-adaptation/maia-lc0.md));
  when a human hangs their queen, Maia predicts that exact howler >25% of
  the time
  ([computational-error-models.md](../../design/research/human-play-modeling/computational-error-models.md)).
- **Mac feasibility: trivial.** `brew install lc0` (native ARM, CPU backend),
  nine ~1.3 MB weight files, fully offline, one policy forward-pass per move —
  far under a 1–2 s budget (⚠ latency pending the one-line local benchmark;
  install block in §7).
- **Per-call option toggling on the shared analysis engine is a trap.**
  Mechanically possible, but: `engine.restart()` re-applies only
  Threads/Hash (bot options silently lost after a watchdog restart), skill
  play forces MultiPV≥4 onto the shared process, and the warm transposition
  table from analysis would plausibly feed the bot's shallow search,
  making it stronger than its label (⚠ mechanism-level inference, no
  external measurement — but the probe's warm-TT confound in §6 is a live
  demonstration of the same mechanism)
  ([second-engine-process-patterns.md](../../design/research/engine-adaptation/second-engine-process-patterns.md)).
- Multiple engine subprocesses in one asyncio program is the normal,
  supported python-chess pattern; a bot engine is resource-tiny (1 thread,
  16 MB hash / nodes=1 lc0). Contempt no longer exists in NNUE-era SF —
  out of the design space.

**Recommendation:** a **separate, isolated bot-engine process** behind a new
`BotEngine` wrapper — never the shared analysis Stockfish. The wrapper makes
"Stockfish weakened" vs "lc0+Maia" a *config swap*, not an architecture fork.

## 2. Human-error modeling (the causal-blunder requirement)

**Evidence** ([human-play-modeling/](../../design/research/human-play-modeling/),
[blunders/](../../design/research/blunders/)):

- **Position difficulty dominates skill as a blunder predictor** (0.73 vs
  0.55 accuracy; tablebase ground truth, 24.6M instances — Anderson et al.
  KDD 2016). Uniform rating-scaled randomness inverts the empirically
  correct causal structure — this is the scientific core of the user's
  "never random drops" requirement
  ([error-rates-by-rating.md](../../design/research/human-play-modeling/error-rates-by-rating.md)).
- **Plan fixation is lab-verified** (Einstellung eye-tracking): attention
  stays captured by the player's own idea even while they believe they're
  checking alternatives. Consequence: blunders must be implemented
  **input-side** — restrict what the bot *attends to*, then let it play the
  best move it can see — never output-side dice rolls
  ([attention-and-motif-blindness.md](../../design/research/human-play-modeling/attention-and-motif-blindness.md),
  [blunder-causes.md](../../design/research/blunders/blunder-causes.md)).
- **The 1200–1600 band — this app's audience — is exactly the
  missed-threat-while-executing-own-plan band** (⚠ band-type mapping is
  converging coaching evidence, not peer-reviewed)
  ([blunder-profiles-by-rating.md](../../design/research/blunders/blunder-profiles-by-rating.md)).
- **A candidate analytic model exists:** Regan–Haworth assigns each engine
  candidate a probability via `y = exp(−(δ/s)^c)` with two rating-indexed
  dials — a *seedable probability distribution* over MultiPV candidates
  (⚠ the exact link function and eval-damping transform still need
  re-derivation from the papers before implementation)
  ([computational-error-models.md](../../design/research/human-play-modeling/computational-error-models.md)).
- **Blunder severity should live on the win-prob axis** — the repo's
  `win_prob_from_cp` already exactly matches lichess's model
  ([blunder-definitions-and-thresholds.md](../../design/research/blunders/blunder-definitions-and-thresholds.md)).
- A production-adjacent pattern exists for plausibility: a stronger
  second pass rejects implausible candidates ("Move Curator", Chessiverse —
  ⚠ self-reported)
  ([engaging-vs-annoying-bots.md](../../design/research/bot-personas/engaging-vs-annoying-bots.md)).

**Recommendation:** layered error model — **Maia policy as the human prior**
(it learns threat-blindness implicitly), with a thin deterministic
persona layer on top (Regan–Haworth-style selection + input-side blindness
gates keyed to own-plan salience vs threat visibility). Trigger recipes in
[bot-blunder-triggers.md](../../design/research/blunders/bot-blunder-triggers.md).
B5 implements and validates; pass/fail design in
[humanness-metrics.md](../../design/research/human-play-modeling/humanness-metrics.md).

## 3. Opening variety

**Evidence** ([openings/](../../design/research/openings/)): python-chess
ships weighted-book sampling natively; a hand-curated JSON tree (same schema
family as `data/repertoire.json`) is the recommended format at this catalog
size (build-time judgment, not a researched fact — polyglot remains viable);
**sub-1600 players leave book early — design range ~move 4–8** (⚠
anecdotal/forum-sourced, corroborated by the Two-Knights stat; per-band
exit depths to be tuned in B4, the evidence doesn't support precise
1200-vs-1500 numbers); the
[sub-1600 catalog](../../design/research/openings/sub-1600-opening-catalog.md)
covers 12 opening families (White d4/e4; Black d5/d6, e5/e6, c5) with branch
points and bot-book weights. Lichess-Explorer popularity numbers are
⚠-pending (API blocked in sandbox; exact re-run queries inline in
[rating-banded-opening-behavior.md](../../design/research/openings/rating-banded-opening-behavior.md)).

**Recommendation:** weighted JSON opening books per persona; temperature +
top-k sampling for game-to-game variety; rating-tuned exit depth within the
~4–8 design range; **sparring-bot books derived from the user's own
`repertoire.json` opponent-side branches** (bots that play into prepared
lines = direct training value).

## 4. Think-time realism

**Evidence:** human move-times are heavy-tailed, middlegame-peaked; long
thinks *accompany* errors rather than prevent them (Sigman et al., 2.8M
games — [time-allocation.md](../../design/research/human-play-modeling/time-allocation.md));
bot convention: fast-in-book, slow-on-deviation/complexity
([ladder-and-think-time-ux.md](../../design/research/bot-personas/ladder-and-think-time-ux.md)).
The repo already computes the needed criticality signals (eval swing,
multipv gap) via `analyze_multi`/dual-best-move.

**Recommendation:** simulated delay = base(persona) + variance, weighted by
criticality signals the app already has. Pure UX layer, client-paced,
engine never actually waits. (NEXT-tier slice; B1 confirms signals exist.)

## 5. Persona design

**Evidence** ([bot-personas/](../../design/research/bot-personas/)): the
chess.com complaint is **narrative inconsistency, not difficulty** — players
reject mistakes that don't read as *that persona's kind of mistake*; two
independent 20-year-apart precedents (Chessmaster, Fritz/HIARCS) converge on
**an ELO axis × 3–6 named style dials, presented as one-line narrative
descriptions** ([persona-parameterization.md](../../design/research/bot-personas/persona-parameterization.md));
chess.com bots never resign — an evidenced, unaddressed complaint and a
cheap differentiator ([bot-match-conventions.md](../../design/research/bot-personas/bot-match-conventions.md)).
Ladder rung spacing: open question (no source answers "what ELO gap feels
distinct") — fold into B4's monotonic-ladder probe.

**Recommendation:** persona = **rating band × style profile**, where style
biases the error model (attacker: own-plan salience ↑, threat visibility ↓),
the opening book, and trade affinity (⚠ trade affinity is an inferred
extension — no directly sourced precedent) — surfaced to the user as a
one-line character description, not sliders. Bots resign clearly lost
positions.

## 6. Probe results (local evidence)

Full output: [probes/results.md](probes/results.md) (regenerable;
20 positions — 11 from games.db referenced by index/phase/motif only per the
privacy rule, 9 curated; 5 configs; Stockfish 18).

**Methodology correction (from review):** the first probe run reused ONE
engine process across all configs; the node-cap config ran last on a warm
transposition table over the same positions and looked essentially
full-strength (avg cpLoss 3, 75% match-best). Codex review caught the
confound; the probe now spawns a fresh engine per config. Cold-TT numbers:

| Config | avg cpLoss | %match-best | blunders>200 | verdict |
|---|---|---|---|---|
| Skill Level 3 | 45 | 35% | 1/20 | human-like |
| Skill Level 10 | 22 | 50% | 0/20 | human-like |
| UCI_Elo 1350 | 51 | 35% | 2/20 | human-like |
| UCI_Elo 1700 | 42 | 55% | 2/20 | human-like |
| Nodes cap 500 | 16 | 55% | 0/20 | borderline (heuristic flickers run-to-run) |

Findings: (a) **node caps do weaken SF18 with a cold TT**, but remain the
weakest weakener here and carry no ELO semantics (hardware/version
dependent) — a coarse knob, not a calibrated one; (b) on threat-facing
positions the effective weakeners' errors are *consistent with* missing a
real threat while playing an otherwise purposeful move — cpLoss-inferred;
the probe cannot read engine intent, and its human-vs-random verdict is a
threshold heuristic, not a humanness test; (c) UCI_Elo 1350 averaged ~51
cpLoss — low relative to real sub-1600 human ACPL (~120–150 middlegame),
consistent with the inflated-label evidence (§1).

**Reconciling (b) with §1's "causeless mechanism":** both hold. Per-move,
weakened SF output *looks* plausible (top-4 shallow candidates are rarely
absurd). But the mechanism conditions errors only on score gaps and RNG —
not on the difficulty/threat features that drive human error (Anderson) —
so error *placement* should not track human error placement (⚠
mechanism-level argument; the 20-position probe neither confirms nor
refutes it at scale). Maia/the causal layer fix *placement*, not per-move
plausibility.

## 7. The recommended architecture

> **One isolated bot-engine process behind a `BotEngine` seam; Maia (lc0)
> as the human move prior with weakened Stockfish as the no-install
> fallback; a thin deterministic persona/causality layer on top; weighted
> JSON opening books; Maia-band-anchored fuzzy rating labels.**

Concretely:

1. **`BotEngine` wrapper, own process** (1 thread, tiny hash / nodes=1
   lc0) — never touches the analysis engine, its lock, options, or warm TT.
   **Seam contract:** it must expose *candidates with scores/probabilities*
   (SF: MultiPV-k; lc0: policy priors via verbose move stats), not a bare
   bestmove — the persona layer (item 4) consumes candidates.
   **Lifecycle contract (mirrors `app/engine.py` discipline):** import-safe
   when the binary is absent; one asyncio.Lock; hard timeout + watchdog +
   restart with *full* option re-application (the shared engine's restart()
   only re-applies Threads/Hash — the bot wrapper must not repeat that
   gap); clean shutdown. Band/persona switch = engine respawn with new
   options/weights (processes are tiny; respawn is cheap and beats
   in-place reconfiguration races).
   It does **not** wrap `review.note_interactive_start/end` — that
   mechanism exists to yield the *shared* engine lock, which the bot
   process doesn't contend for; CPU contention at 1 thread/nodes=1 is
   negligible (revisit only if observed).
2. **Move source A (preferred): lc0 + Maia weights**, band-matched to the
   bot's label. Variety: ⚠ nodes=1 policy argmax is deterministic and
   current lc0 temperature-option support is unverified — game-to-game
   variety comes from the opening book plus persona-layer sampling over
   the candidate distribution (which works for both sources).
3. **Move source B (fallback, zero install): weakened Stockfish** —
   UCI_Elo/Skill in the isolated process. Same wrapper API; the
   walking-skeleton (B2) ships on B alone.
4. **Persona/causality layer (B5):** style-conditioned, seedable selection
   over the source's candidates — Regan–Haworth-style curve (⚠ exact
   parameters to be re-derived in B5) + input-side blindness gates
   (own-plan salience vs threat visibility) + a plausibility check —
   producing the *right kind* of mistake for the band (§2).
   **State contract:** plan-salience needs recent-move context and a
   per-game seed; the server stays stateless, so the client sends what the
   layer needs with each bot-move request (it already owns full history —
   `contracts/bot-play.md`). Exact request shape is a B5 spec decision.
5. **Openings:** weighted JSON books, temperature sampling, rating-tuned
   exit depth, persona bias, repertoire-derived sparring books (§3).
6. **Ratings:** anchor rungs to Maia bands as the *human-style* anchor, but
   display **fuzzy labels** ("plays like ~1200"), not precise Elo — Maia
   plays above its training band and no published human-Elo measurement
   per model exists (⚠); validate ladder monotonicity in B4; Glicko-2 with
   visible RD for the user's estimate (B8), kept separate from
   accuracy.py's per-game readout
   ([honest-bot-rating-assignment.md](../../design/research/rating-calibration/honest-bot-rating-assignment.md),
   [rating-systems-math.md](../../design/research/rating-calibration/rating-systems-math.md)).

**Rejected alternatives:**

- **Shared-engine option toggling** — restart() option loss, MultiPV
  pollution, warm-TT strength distortion (⚠ inferred, demonstrated in
  miniature by the probe confound), serialization coupling (§1). Highest-
  risk path touching the app's most load-bearing invariant.
- **Weakened Stockfish as the *permanent* error model** — its error
  mechanism is causeless (uniform noise over shallow score-ranked
  candidates, no human causal conditioning); it can't produce the
  right-mistake-for-the-right-reason behavior the epic requires (§2).
  Kept as fallback/skeleton source; the analytic notes say a SF-only
  stack *can approximate* Maia if Maia is skipped — viable plan B, at the
  cost of hand-building and validating what Maia already learned.
- **Hand-built error model without Maia** — not provably worse, but
  strictly more B5 work with no validated humanness baseline; Maia gives
  a measured 46–53% human prior out of the box, and the hand-built
  analytic layer is still needed *on top* for persona/causality either
  way. Rejected on effort/risk, not on impossibility.
- **LLM move selection** — global no-go (roadmap).

### Install commands (user-run; Claude's sandbox blocks network installs)

```sh
# lc0 (Leela Chess Zero) engine — native Apple Silicon
brew install lc0

# Maia human-like weights (per-Elo networks, 1100..1900)
mkdir -p ~/maia_weights && cd ~/maia_weights
for elo in 1100 1300 1500 1700 1900; do
  curl -L -o maia-${elo}.pb.gz \
    https://github.com/CSSLab/maia-chess/raw/master/maia_weights/maia-${elo}.pb.gz
done

# Smoke test (nodes=1 → pure policy, most human-like)
lc0 --weights="$HOME/maia_weights/maia-1500.pb.gz"
```

⚠ Confirm weight URLs at install time; the CSSLab/maia-chess repo is
canonical. If lc0 is skipped, B2+ run on fallback source B — nothing blocks.

## What this means for the roadmap

- **B2 (walking skeleton):** isolated `BotEngine` + fallback source B + one
  bot, one full game. No Maia dependency. B2's spec must settle, from the
  contracts file: (a) the **default-bot label** — source B cannot honestly
  claim "1200" (UCI_Elo floor 1320, engine-anchored), so the skeleton bot
  ships with a fuzzy label pending Maia; (b) the **lifecycle/failure
  contract** from §7.1; (c) **stale-response protection** for the bot's
  reply (capture-before-await + token check — undo/new-game/mode-exit
  races); (d) terminal/illegal-position request boundaries; (e) takeback
  semantics + survive-refresh persistence (client-owned history).
- **B4/B5:** personas/books and the causality layer per §2/§3/§5; B5's
  pass/fail uses [humanness-metrics.md](../../design/research/human-play-modeling/humanness-metrics.md);
  B5 re-derives the Regan–Haworth parameters before implementing.
- **B8:** Glicko-2 + RD per §7.6.
- Open questions carried forward: ladder rung spacing (→ B4 probe),
  lc0 latency benchmark + temperature-option check (→ at install),
  Explorer popularity verification (→ queries inline in the openings notes).

## Verification log

R5 dual review, 2026-07-16. Both reviewers read the synthesis, the six
research folders, the probe script + output, the spec, and the contracts.

**Claude refuter — verdict: pass.** Deterministic checks: `pytest -q` 757
passed; `ruff check app tests` clean; privacy grep confirmed exactly 9 FEN
strings in committed files, all curated, zero from games.db. Three minor
findings, all folded: (1) the >25%-howler claim was cited to the wrong note
and over-broadened ("hung pieces" → "hangs their queen"; now cited to
computational-error-models.md); (2) the UCI_Elo calibration sentence
conflated two notes' differing anchor details (now stated with the
discrepancy ⚠-flagged); (3) the warm-TT distortion mechanism was stated as
fact where the source note flags it ⚠ inference (flag restored).

**Codex (gpt-5.6-sol) — findings + resolutions:**
- *Node-cap "dead knob" confounded by warm TT (major)* — *confirmed
  empirically.* Probe re-architected: fresh engine process per config.
  Cold-TT re-run: node-cap avg cpLoss 3→16-22, match-best 75%→55%. §6
  rewritten; conclusion downgraded to "coarse, unanchored knob."
- *Maia-band rating labels overstated (major)* — accepted; §7.6 now
  requires fuzzy display labels + B4 validation, notes Maia plays above
  its band ⚠.
- *Regan–Haworth promoted past its ⚠ (major)* — accepted; ⚠ restored in
  §2/§7.4; B5 must re-derive parameters.
- *nodes=1 sampling determinism / lc0 temperature unverified (major)* —
  accepted; §7.2 reworded: variety via book + persona-layer sampling;
  lc0 temperature check moved to install-time open questions.
- *BotEngine seam doesn't expose candidates the persona layer needs
  (major)* — accepted; §7.1 seam contract now requires candidate
  distributions (MultiPV / policy priors), not bare bestmove.
- *Band-switch lifecycle unspecified (major)* — accepted; §7.1 now
  specifies respawn-per-band + full lifecycle contract.
- *Plan-fixation state vs stateless server (major)* — accepted; §7.4 state
  contract: client supplies history/seed per request; shape settled in B5.
- *§6 "uncorrelated at scale" asserted without measurement (major)* —
  accepted; reconciliation reworded as a ⚠ mechanism-level argument the
  probe neither confirms nor refutes.
- *"Hand-built = worse humanness" unsupported (major)* — accepted;
  rejection reworded to effort/risk grounds; SF-only approximation
  acknowledged as viable plan B.
- *B2 gaps: default-1200 mapping, lifecycle contract, stale-response,
  terminal/illegal boundaries, takeback/persistence (2 major + 3 minor)* —
  accepted; all added to the B2 handoff list.
- *note_interactive wrapping unnecessary for an isolated process (minor)* —
  accepted; §7.1 corrected (it existed to yield the shared lock).
- *Minor precision items* (exit-depth false precision, JSON-vs-polyglot as
  judgment not fact, trade-affinity qualifier, "structurally
  uniform-random" → "causeless mechanism", probe intent-reading wording) —
  all folded into §3/§5/§6/§7.

**Post-fold checks:** probe re-run green (results.md regenerated,
privacy rule re-verified), `pytest -q` + `ruff check app tests` re-run
green after the probe edit.
