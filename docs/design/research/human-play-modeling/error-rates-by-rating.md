# Quantitative error distributions by rating and phase

How often, and how badly, humans err at each rating band — and what actually
predicts an error. Feeds the bot error-budget design; blunder *taxonomy and
causality* lives in `../blunders/` (cross-link, don't duplicate).

## The single most load-bearing finding: difficulty dominates skill

Anderson, Kleinberg & Mullainathan, ["Assessing Human Error Against a Benchmark
of Perfection"](https://arxiv.org/abs/1606.04956) (KDD 2016) is the strongest
ground-truth study of human chess error, because it sidesteps engine-eval noise
entirely: it analyzes only positions with ≤6 pieces, where tablebases give the
*game-theoretically perfect* answer. Dataset: ~200M amateur games (FICS) plus
~1M elite tournament games, yielding 24.6M analyzable move instances (FICS) and
880K (GM). A **blunder** is defined game-theoretically: a move that worsens the
minimax value (e.g. throws away a forced win).

Predicting whether a given move will be a blunder, using three feature families
([paper](https://arxiv.org/abs/1606.04956)):

| Feature family | Prediction accuracy |
|---|---|
| Position difficulty alone | **0.73** |
| Player skill (Elo) alone | 0.55 |
| Time remaining alone | 0.53 |
| All combined | 0.75 |

**Position difficulty is a far stronger predictor of error than who is moving
or how much clock they have.** The paper's headline framing: blunder potential
"contributes more to aggregate error rates than 600 Elo rating points."

Their difficulty measure, **blunder potential** β(P) = b(P)/n(P) — the fraction
of legal moves that are blunders (i.e. the error rate of a uniformly random
player). Empirical human blunder rate tracks β(P) through a one-parameter
skill curve: blunder rate ≈ β / (c − (c−1)β), with c ≈ 15 fitted for amateurs
and c ≈ 100 for grandmasters ([paper](https://arxiv.org/abs/1606.04956)).
⚠ Functional form and fitted constants taken from a summary read of the paper;
re-verify exact equation before implementing.

Two more findings from the same paper that matter for a causal error model:

- **Skill-anomalous positions exist**: among frequently-occurring positions,
  some show *higher* blunder rates for higher-rated players — skill does not
  uniformly reduce error ([paper](https://arxiv.org/abs/1606.04956)).
- **Longer think ≠ safer move**: conditioned on the position, moves that took
  the player *more* time show *higher* blunder rates — long thinks signal the
  player is in trouble, not that the output is more reliable (see
  `time-allocation.md`).

Design implication: a believable bot's error probability should be conditioned
primarily on **position features** (how many trap-moves the position offers,
whether the refutation is hard to see) and only secondarily scaled by rating.
Rating-uniform random error — chess.com-bot style — inverts the empirically
correct causal structure.

## Average centipawn loss (ACPL) and blunder rate by rating band

No rigorously published lichess-official table of ACPL-per-band exists; the
best available numbers are community analyses, all flagged accordingly.

- Direction is unambiguous: ACPL falls as rating rises, and blunder frequency
  falls "dramatically" with rating, but the *correlation is weak per-game* —
  ACPL is a noisy strength signal for any single game
  ([Wojcicki blog analysis, ~2,500 lichess games](https://kwojcicki.github.io/blog/CHESS-BLUNDERS)). ⚠ small-sample blog.
- Same analysis: **mistakes** (their def: 100–300 cpLoss) stay *relatively flat*
  across bands, while **blunders** (their def: >200 cpLoss) are what falls with
  rating ([Wojcicki](https://kwojcicki.github.io/blog/CHESS-BLUNDERS)). ⚠ Their
  thresholds overlap and differ from lichess's; treat the flat-mistakes claim
  as a hypothesis, not a fact.
- Community rules of thumb from lichess forums: ~50 ACPL is decent in quiet
  games, ~100 normal in sharp games; ~20 is near-perfect
  ([forum](https://lichess.org/forum/general-chess-discussion/whats-a-decent-average-centipawn-loss)).
  ⚠ anecdotal.
- **Sharpness matters as much as rating**: the same forum consensus — sharp
  games roughly double ACPL vs quiet games at the same rating
  ([forum](https://lichess.org/forum/general-chess-discussion/whats-a-decent-average-centipawn-loss)).
  ⚠ anecdotal, but consistent with the KDD-2016 difficulty-dominates result.

The cleanest large-scale rating-conditioned error data is implicit in the Maia
training corpus (12M lichess games *per* 100-point band, 1100–1900,
[McIlroy-Young et al. KDD 2020](https://arxiv.org/abs/2006.01855)); Maia's
per-band move distributions are effectively the empirical error distribution
(see `computational-error-models.md`).

## Error rate by game phase

Consistent qualitative pattern across sources: **middlegame ACPL is highest**,
opening lowest, endgame in between.

- Rule of thumb from lichess-forum analyses: opening ACPL ≈ ½ of middlegame
  ACPL; endgame ACPL ≈ ¾ of middlegame ACPL
  ([forum](https://lichess.org/forum/general-chess-discussion/analyzing-average-centipawn-loss-by-game-phase)). ⚠ anecdotal.
- One blog's estimated table for lichess blitz — U1600: opening 60–80,
  middlegame 120–150, endgame 90–120; 1600–2000: 40–60 / 80–120 / 60–90
  ([MyChessPlan](https://mychessplan.com/centipawn-loss-vs-accuracy-chess-metrics-explained/)).
  ⚠ blog estimates, methodology unstated — use as a sanity-check band only.
- Mechanism (why opening cpLoss is low): memorized theory, not skill — which is
  why Maia's evaluation *excludes the first 10 ply* as "memorized opening
  moves" ([Maia paper](https://arxiv.org/abs/2006.01855)).
- Endgame caveat: raw endgame ACPL is deflated by decided/dead-drawn games
  where any move is ≈0 loss
  ([forum](https://lichess.org/forum/general-chess-discussion/is-it-normal-to-have-much-worse-acpl-in-the-middlegame)) —
  yet the tablebase study shows sub-6-piece endgames are exactly where amateurs
  throw away *game-theoretic* wins at high rates
  ([Anderson et al.](https://arxiv.org/abs/1606.04956)). cpLoss understates
  endgame error severity: a single endgame blunder flips the *result*, not
  just the eval.
- Time-scramble endgames are their own regime: blunder rate spikes sharply
  under ~10s remaining ([Anderson et al.](https://arxiv.org/abs/1606.04956)),
  and endgame move times collapse to time-pressure-driven, not
  complexity-driven, speeds
  ([Sigman et al. 2010](https://pmc.ncbi.nlm.nih.gov/articles/PMC2965049/)).

**Characteristic sub-1600 endgame misplays a bot should reproduce** (for the
practice-realism goal): failing to convert tablebase-won ≤6-piece positions,
with error probability rising with blunder potential β(P) of the position
([Anderson et al.](https://arxiv.org/abs/1606.04956)). ⚠ A motif-level catalog
of *which* endgame errors (wrong king approach, premature pawn pushes, wrong
rook placement) dominates per band was not found in the literature surveyed —
this is a gap; lichess-database mining could fill it later.

## Sharpness / tension as a position feature

A candidate computable "sharpness" feature: **fragility** — total betweenness
centrality of attacked pieces in the piece-interaction graph. It peaks around
move 15 and marks tipping points in elite games
([Barthelemy, arXiv 2410.02333](https://arxiv.org/html/2410.02333v2)).
⚠ That paper explicitly does *not* link fragility to human error rates or think
time — it's an unvalidated-but-plausible conditioning feature, not evidence.
A simpler, *validated* sharpness proxy is Anderson's β(P) computed from engine
MultiPV output (fraction of legal moves losing ≥ threshold).

## Cross-references

- Blunder causality taxonomy → `../blunders/`
- Which error model to *execute* on the engine → `../engine-adaptation/`
- Mapping error parameters to a target Elo → `../rating-calibration/`
