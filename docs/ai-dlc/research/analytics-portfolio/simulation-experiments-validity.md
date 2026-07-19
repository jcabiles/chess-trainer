# Simulation-Based Experimentation: Scientific Validity Dossier

Research dossier for the analytics-engineer portfolio's EXPERIMENTATION story: running
bot populations (Stockfish personas + Maia nets) on this app as synthetic users, analyzed
like a product experiment — without the circularity of "we made the bot stronger and it
got stronger." Compiled 2026-07-18. ⚠ marks claims not verified against a primary source.

---

## 1. How others validly use simulation / self-play / synthetic populations

### 1a. Computer-chess evaluation practice (the gold standard for game-sample inference)

- **Fishtest / SPRT.** Stockfish evaluates every patch on a distributed volunteer farm
  playing hundreds of thousands of base-vs-patch games. The Sequential Probability Ratio
  Test (SPRT) frames each patch as H0 "gain ≤ elo0" vs H1 "gain ≥ elo1" with α = β = 0.05,
  updating a log-likelihood ratio per game batch and stopping when a bound is crossed.
  Standard bounds: STC [0, 2.0] Elo, LTC [0, 1.0] Elo. This is a *pre-registered,
  sequential, two-sided-risk* hypothesis test — the strongest existing precedent that
  engine-vs-engine games can support rigorous causal claims about a code change.
  Sources: [Fishtest FAQ](https://github.com/official-stockfish/fishtest/wiki/Fishtest-faq),
  [Stockfish docs — Creating my first test](https://official-stockfish.github.io/docs/fishtest-wiki/Creating-my-first-test.html),
  [DeepWiki fishtest overview](https://deepwiki.com/official-stockfish/fishtest).
- **Elo estimation needs shockingly many games.** Community experience: even ~16,000 games
  is often insufficient to resolve a small Elo difference beyond the error bar
  ([TalkChess thread](https://talkchess.com/forum3/viewtopic.php?t=58067)). Practical CI
  methods: percentile bootstrap over game results (resample with replacement, 1000
  replicates, take 2.5/97.5 percentiles), or likelihood-based intervals as in Rémi
  Coulom's [Bayesian Elo](https://www.remi-coulom.fr/Bayesian-Elo/). A hobbyist but
  well-written walkthrough of SPRT for a home engine:
  [dogeystamp — Elo and rigorous SPRT testing](https://www.dogeystamp.com/chess3/).
- Round-robin tournaments + a rating model (BayesElo/Ordo) are the standard for placing
  N engines on one scale; SPRT is the standard for a single treatment-vs-control question. ⚠
  (widely known practice; specific tooling comparison not verified here).

### 1b. Agent-based modeling (ABM) validity

- The ABM literature has an explicit calibration/validation discipline: calibrate
  parameters to empirical data, then validate model *outputs* against held-out real-world
  benchmarks (RMSE/R², posterior predictive checks), with sensitivity analysis and
  explicit identifiability reporting. Key sources:
  [Windrum, Fagiolo & Moneta — Empirical Validation of Agent-Based Models (JASSS)](https://jasss.soc.surrey.ac.uk/10/2/8.html),
  [Hierarchical ABM Validation Framework (ACM TOMACS)](https://dl.acm.org/doi/10.1145/3769857),
  [ABM calibration with ML surrogates](https://www.sciencedirect.com/science/article/abs/pii/S0165188918301088),
  [calibration verification for stochastic ABMs](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11630602/).
- Best-practice highlights: start minimal and add parameters only if data supports
  identifiability; validate calibration *separately* from overall model validation
  (using one to check the other conceals errors).

### 1c. RL evaluation pitfalls (what NOT to do)

- [Henderson et al., "Deep RL that Matters"](https://arxiv.org/abs/1709.06560): seed
  variance alone produces "improvements"; point estimates without significance testing
  are close to meaningless; seed selection is a multiple-comparisons trap.
- [Agarwal et al., "Statistical Precipice" (NeurIPS 2021)](https://proceedings.neurips.cc/paper_files/paper/2021/file/f514cec81cb148559cf475e7426eed5e-Paper.pdf)
  and Google's [RLiable](https://research.google/blog/rliable-towards-reliable-evaluation-reporting-in-reinforcement-learning/):
  report stratified-bootstrap CIs on aggregate metrics (IQM rather than mean/median),
  keep evaluation protocols constant within comparisons.

### 1d. Bot populations simulating product/user experiments (direct precedent)

- [AgentA/B (arXiv 2504.09723, CHI 2026)](https://arxiv.org/abs/2504.09723): LLM agents
  as synthetic users running between-subjects A/B tests on live Amazon pages (1,000
  agents, 500/condition); results aligned *directionally* with a parallel human A/B test.
  Explicitly framed as a **complement, not replacement** for human testing — agents were
  measurably more goal-directed than real users (fewer actions per task).
- [SimGym — traffic-grounded browser agents for offline A/B testing](https://arxiv.org/pdf/2602.01443)
  and [context-aware agent simulation for recommender evaluation](https://arxiv.org/pdf/2604.09549):
  the emerging pattern is *grounding agent personas in real behavioral data* and
  validating agent behavior against logged human interactions before trusting the
  simulated experiment.

**Bottom line for this app:** the portfolio story has strong, citable precedent —
fishtest-style SPRT for engine-level questions, ABM calibration/validation discipline for
"do my bots behave like real players," RLiable-style bootstrap CIs for reporting, and
AgentA/B as the direct "synthetic users for product experiments" precedent (including its
honest limitation framing). Steal the fishtest H0/H1/α/β structure verbatim for any
bot-vs-bot comparison, and the ABM rule *validate the simulator against real data before
using it to test anything*.

---

## 2. Honest experiment designs when you control the agents

The circularity trap: if treatment = "change agent policy" and outcome = "metric computed
from that same agent's play," you've measured your own dial. Designs that stay honest:

- **Separate the treatment from the measuring instrument.** Treatment should be a
  *product/engine feature* (e.g., matched-limit eval preset, opening-book policy, a
  matchmaking rule), and the outcome a **pre-registered metric measured by an instrument
  the treatment cannot touch**: an external Elo anchor (fixed reference engines never
  modified during the experiment — this is exactly fishtest's base-build role,
  [Fishtest FAQ](https://github.com/official-stockfish/fishtest/wiki/Fishtest-faq)), or a
  human-likeness audit scored against a frozen Maia policy (move-matching accuracy is
  Maia's published metric: ~46–52%+ vs human moves,
  [Maia KDD 2020](https://www.cs.toronto.edu/~ashton/pubs/maia-kdd2020.pdf),
  [Maia-2 NeurIPS 2024](https://arxiv.org/pdf/2409.20553)).
- **Randomize at the game level, do a power analysis first.** Games (or game pairs with
  color swap ⚠ — standard engine-testing practice, unverified citation) are the unit of
  randomization. Power analysis against the expected Elo/effect size tells you the game
  budget before you run; the TalkChess experience (16k games ≠ enough for small deltas,
  [source](https://talkchess.com/forum3/viewtopic.php?t=58067)) is the cautionary anchor.
  SPRT lets you stop early with controlled error rates instead of fixing N.
- **A/A tests + sample-ratio-mismatch (SRM) checks validate the harness.** Run the
  identical bot config as both arms; any "significant" difference exposes harness bugs.
  SRM (observed allocation deviating from configured, chi-square test) is "one of the
  most egregious data-quality issues" — experiments with SRM show ~2x the rate of
  spuriously significant metrics
  ([Microsoft Research](https://www.microsoft.com/en-us/research/articles/diagnosing-sample-ratio-mismatch-in-a-b-testing/),
  [DoorDash](https://careersatdoordash.com/blog/addressing-the-challenges-of-sample-ratio-mismatch-in-a-b-testing/),
  [Convert SRM guide](https://www.convert.com/blog/a-b-testing/sample-ratio-mismatch-srm-guide/)).
- **Pre-register to avoid HARKing.** Commit hypothesis, metric, bounds, and stopping
  rule to the repo (a markdown pre-registration file with a commit hash) *before* running.
  Fishtest's fixed SPRT bounds are effectively institutionalized pre-registration.
  Guard against seed-shopping/multiple comparisons
  ([Deep RL that Matters](https://arxiv.org/abs/1709.06560)).
- **Claims that can NEVER be made from synthetic data** (label them as such in the
  portfolio): anything about *human* preference, engagement, retention, learning, or
  satisfaction; external generalization of effect *sizes* (AgentA/B only claimed
  directional alignment, [arXiv 2504.09723](https://arxiv.org/abs/2504.09723)); anything
  about behaviors the agent model wasn't validated to reproduce. Synthetic experiments
  can validly claim: the harness works, the pipeline is unbiased, effects on
  *mechanically defined* outcomes (Elo vs frozen anchor, Maia-agreement, move-time
  distributions) under the simulated population.

**Bottom line for this app:** design = pick a real product feature as treatment
(e.g., speed-preset policy, opening-book depth, adaptive-difficulty rule), pre-register
metric + SPRT bounds in-repo, randomize at game level with color-balanced pairs, measure
against frozen instruments (reference engine anchor + frozen Maia for human-likeness),
and *lead* the writeup with the A/A + SRM harness validation — that's the section that
convinces a practitioner reviewer. Include an explicit "claims we cannot make" box.

---

## 3. "Bots improve over time" — legitimate, non-circular framings

Injecting strength and reporting improvement is circular. Legitimate mechanisms shift the
research question from "did the bot get better" to "does *policy X* achieve *outcome Y*":

- **Adaptive difficulty / matchmaking as the treatment.** Dynamic Difficulty Adjustment
  (DDA) is a real, studied product mechanism: players report adaptive opponents as more
  enjoyable, and DDA is tied to flow/retention in the games-industry literature
  ([DDA exergame comparative study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8204235/),
  [Ghost Recon Breakpoint player-modeling/retention paper](https://www.researchgate.net/publication/398421162),
  [imitation-learning-based personalized DDA](https://arxiv.org/pdf/2408.06818)).
  Honest question: "does Elo-gap-targeted matchmaking keep a simulated learner in the
  40–60% score band better than static pairing?" — the outcome (score-band occupancy,
  rating-convergence speed) is defined independently of the knob.
- **Rating systems as instruments.** TrueSkill models skill as a distribution with
  uncertainty, converging faster than Elo for new players
  ([skill-based matchmaking overview](https://grokipedia.com/page/Skill-based_matchmaking) ⚠
  tertiary source; original: Herbrich et al., TrueSkill, NeurIPS 2006 ⚠ not fetched).
  Glicko-2 gives per-rating uncertainty and is preferable to Elo at small game counts ⚠
  (claim surfaced in an arXiv survey via search, not independently verified). A "which
  matchmaking policy?" experiment can be run as a **bandit** — multi-armed bandits are
  used for DDA in practice ([MAB-driven DDA in VR rehab](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9228873/)).
- **Simulated learners with a *fixed, disclosed* learning curve.** Model synthetic users
  as agents whose strength follows a disclosed trajectory (e.g., Maia-1100 → Maia-1500
  schedule, or Stockfish skill-level ramps calibrated to real rating-progression curves
  from Lichess data). The learning curve is *scenery*, not the treatment: the experiment
  tests whether a feature (trainer, matchmaking, difficulty policy) changes a downstream
  metric *given* that population. This mirrors ABM practice: calibrate the population to
  empirical data, then experiment on top
  ([JASSS validation paper](https://jasss.soc.surrey.ac.uk/10/2/8.html)).
- **Population-based training (PBT)** is a legitimate mechanism for *producing* a
  diverse bot population (Jaderberg et al. 2017 ⚠ not fetched) but is an
  agent-construction tool, not an experiment design — using it *and* judging its output
  with your own metric re-opens the circularity. Keep PBT (if used) on the
  population-generation side, judged by frozen instruments.

**Bottom line for this app:** never make "bot strength" both the knob and the metric.
Frame the flagship experiment as **matchmaking/difficulty-policy A/B on a calibrated
synthetic learner population** — e.g., Leitner-style adaptive opponent selection vs
static ladder, outcome = time-to-rating-convergence and score-band occupancy, instruments
= Glicko-2/TrueSkill ratings vs frozen anchors. That is a real product-experiment shape a
DS interviewer will recognize.

---

## 4. One real user's longitudinal improvement (n = 1)

- **Interrupted time series (ITS)** is the respected quasi-experimental design here:
  baseline phase → intervention (e.g., "started using the blunder trainer on date D") →
  test for level/slope change, **adjusting for autocorrelation** (serially dependent
  observations inflate Type I error badly if ignored)
  ([single-subject intervention analysis, arXiv](https://arxiv.org/pdf/1403.4309),
  [Bayesian time-series models for single-case designs, tutorial](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8246830/)).
- **Single-case experimental design (SCED)** standards (What Works Clearinghouse):
  credibility comes from within-phase stability, and level/slope differences between
  phases — ideally with reversal or multiple-baseline structure, which a chess-training
  history usually can't provide, so claims stay associational
  ([ITSSIM single-case analysis](https://www.researchgate.net/publication/328084151),
  [ITS with brief single-subject data](https://www.researchgate.net/publication/15084749)).
- Honest claims at n=1: "rating/accuracy improved, and the improvement's timing is
  consistent with intervention X" (with autocorrelation-adjusted ITS + CIs) — **not**
  "the app caused the improvement," and never generalization to other users. Confounds to
  disclose: opponent-pool drift, rating-system dynamics, time-varying play volume,
  regression to the mean after a bad streak. ⚠ (standard threats-to-validity reasoning;
  no single citation.)
- Useful hook: this repo already computes per-game accuracy/est-Elo (`app/accuracy.py`)
  and cross-game leak profiles (`app/profile.py`) — those are the n=1 outcome series.

**Bottom line for this app:** present the owner's own data as a **case study, explicitly
labeled quasi-experimental**: an autocorrelation-adjusted ITS on rating/accuracy around
dated feature-adoption events, with a threats-to-validity table. Pairing an honest n=1
case study with the pre-registered synthetic experiment is itself the portfolio's
credibility signal.

---

## 5. Lichess open database logistics

- **Sizes (verified 2026-07-18 from [database.lichess.org](https://database.lichess.org/)):**
  recent standard-rated monthly dumps are ~1.5–1.6 GB `.pgn.zst` with ~5.6–5.9M games/month
  (June 2026: 1.51 GB / 5.61M games). Note: this is far below the ~20 GB/month figure
  quoted in older forum threads — recent months appear smaller ⚠ (possibly a partial
  listing or format change; sanity-check the actual download). All standard-rated games
  ever total ~2+ TB compressed; PGN decompresses ~5x+
  ([Lichess forum](https://lichess.org/forum/general-chess-discussion/how-to-download-big-databases-of-lichess)).
  Dumps include Elo and (since ~2017) `%clk` clock comments and partial `%eval`
  annotations ⚠ (widely known; not re-verified on the page). A separate evaluations
  dump has ~395M Stockfish-evaluated positions (JSON).
- **Budget reality ($20–50/mo):**
  - **Local DuckDB + parquet** is free and comfortably handles a few months of headers +
    moves on a laptop — the default choice.
  - **BigQuery free tier**: 1 TB queries + 10 GB active storage/month, no credit card
    ([sandbox docs](https://docs.cloud.google.com/bigquery/docs/sandbox),
    [Hoffa](https://medium.com/google-cloud/try-google-bigquery-today-535e854e52c9)) —
    fine for a curated aggregate layer, tight for raw PGN-scale data.
  - **MotherDuck**: free tier with 10 GB storage + limited compute; the old $25 Lite plan
    was removed and Business is $250/mo (2026 pricing change) — so it fits only as a
    free-tier demo, not a $20–50 workhorse
    ([MotherDuck pricing](https://motherduck.com/product/pricing/),
    [pricing-change writeup](https://tasrieit.com/blog/motherduck-pricing-change-2026)).
  - **Cloudflare R2**: $0.015/GB-mo, zero egress, 10 GB free — ~$1.50/mo per 100 GB of
    parquet; ideal cheap remote store DuckDB can query over HTTP
    ([R2 pricing](https://developers.cloudflare.com/r2/pricing/)).
  - Realistic stack under budget: download 1–3 months → transform to parquet locally →
    park on R2 → query with local DuckDB (and optionally mirror a small mart to
    BigQuery/MotherDuck free tier for the "cloud warehouse" checkbox). Total: <$5/mo.
- **Subset strategies:** one recent month; filter to a rating band (e.g., 1400–1800 blitz)
  matching the app's persona range; sample players (not games) to keep longitudinal
  per-player series intact ⚠ (methodological recommendation, not a cited practice).
- **Prior art to emulate/differentiate:**
  [sodascience/lichess_db](https://github.com/sodascience/lichess_db) — game headers to
  parquet at scale; [Aix DuckDB extension + Aix-format Lichess DB (7B+ games)](https://thomasd.be/2026/02/01/aix-storing-querying-chess-games.html)
  — SQL over moves/positions/clocks; [duckdb-chess PGN extension](https://github.com/dotneB/duckdb-chess).
  Maia itself is the flagship analysis built on these dumps
  ([Maia KDD 2020](https://www.cs.toronto.edu/~ashton/pubs/maia-kdd2020.pdf)).
  Differentiator for this portfolio: nobody in that list runs *pre-registered synthetic
  experiments calibrated against* the dump — they build storage/query layers or models.

**Bottom line for this app:** use one recent month (~1.5 GB zst) filtered to the app's
persona rating band; local DuckDB + parquet on R2 keeps the whole thing under $5/mo. The
dump's role in the experiment story is as the **calibration/validation target** (do bot
move-times, blunder rates, and rating trajectories match real players of that band?) —
which is exactly what makes the synthetic experiment defensible per §1b.

---

## Master source list

Fishtest wiki/FAQ · Stockfish docs · DeepWiki fishtest · TalkChess Elo threads ·
Bayesian Elo (Coulom) · dogeystamp SPRT · JASSS ABM validation · ACM TOMACS ABM framework ·
ScienceDirect ABM calibration ·  PMC calibration-verification · Deep RL that Matters ·
Statistical Precipice / RLiable · AgentA/B (arXiv 2504.09723) · SimGym · Maia KDD 2020 /
Maia-2 NeurIPS 2024 / maiachess.com · MSR + DoorDash + Convert SRM · DDA studies (PMC,
ResearchGate, arXiv 2408.06818) · MAB-DDA (PMC) · single-case ITS papers (arXiv 1403.4309,
PMC 8246830, ResearchGate) · database.lichess.org · lichess forums · sodascience/lichess_db ·
Aix blog · duckdb-chess · BigQuery sandbox docs · MotherDuck pricing · Cloudflare R2 pricing.
