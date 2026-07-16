# Measuring humanness: move-matching and statistical realism

How the literature quantifies "plays like a human of rating R" — the metrics a
later slice's pass/fail design should adopt. The reference standard is Maia's
move-matching protocol; secondary tests check distributional realism.

## Maia's move-matching accuracy protocol (the reference standard)

From [McIlroy-Young et al., KDD 2020](https://arxiv.org/abs/2006.01855) and the
[CSSLab blog](http://csslab.cs.toronto.edu/blog/2020/08/24/maia_chess_kdd/):

**Test-set construction** (the details are load-bearing — they remove
confounds):
- Nine rating bins of 100 points (1100–1900); a game qualifies only if *both*
  players are in the bin.
- 10,000 games per bin → ~500,000 test positions per bin.
- **Excluded**: Bullet/HyperBullet games entirely; the first 10 ply (memorized
  opening moves); any move played with <30 seconds left for the rest of the
  game (time-scramble noise).
- Metric: top-1 accuracy — did the model's argmax equal the move the human
  actually played?

**Results to benchmark against:**

| Predictor | Accuracy on matched band |
|---|---|
| Maia (trained on that band) | 50.8% (1100) → 52.9% (1900) |
| Leela (various strengths) | ~46% peak, not band-specific |
| Stockfish (depth-limited) | 33–41%, rises with band |

- Every Maia model's accuracy curve is **unimodal, peaking at its trained
  band** — the paper's operationalization of "capturing a skill level" rather
  than being generically strong or weak
  ([paper](https://arxiv.org/abs/2006.01855)).
- Accuracy rises with move quality, but Maia still matches outright howlers:
  >25% exact-match on queen-hanging blunders
  ([blog](http://csslab.cs.toronto.edu/blog/2020/08/24/maia_chess_kdd/)).
  A humanness suite should report accuracy **stratified by cpLoss of the
  human's move** — matching only good moves means the error model is wrong.
- Ceiling context: fine-tuning on an individual raises accuracy to ~58%
  ([KDD 2022](https://arxiv.org/abs/2008.10086)), so ~52–55% is a realistic
  population-level ceiling; a template/softmax bot will land lower — the pass
  bar should be "closer to Maia than to Stockfish," not "equal to Maia."

**Blunder prediction as a companion metric**: same KDD 2020 paper trains a
classifier predicting *whether* the human's next move will be a blunder
(win-prob drop ≥10pp): 71.7% accuracy (residual CNN) vs 63.0% (random forest
on hand features) ([paper](https://arxiv.org/abs/2006.01855)).

## Maia-2's coherence metrics (skill must vary smoothly)

[Maia-2 (NeurIPS 2024)](https://arxiv.org/abs/2409.20553) adds tests that a
*family* of bots at different ratings should jointly pass:

- **Monotonicity**: fraction of positions where P(correct move) increases
  monotonically as the skill input increases — Maia-2 27% vs Maia-1's 1%
  (independent per-band models disagree incoherently).
- **Transitional positions**: smooth progression from a characteristic
  low-skill move to the correct move as skill rises — 22% vs 17%.

For a bot ladder (1100 bot, 1300 bot, …): a stronger bot should not miss
tactics the weaker bot finds. Worth adopting as a cheap invariant test.

## Statistical realism tests beyond move-matching

- **Error-distribution realism**: compare the bot's per-game ACPL, blunder
  rate, and cpLoss histogram against human baselines for the band (see
  `error-rates-by-rating.md`); errors should also concentrate in
  high-blunder-potential positions as humans' do
  ([Anderson et al.](https://arxiv.org/abs/1606.04956)) — a bot that blunders
  in *quiet* positions fails even with the right aggregate rate.
- **Think-time realism**: human move-time distributions are long-tailed and
  phase-dependent ([Sigman et al. 2010](https://pmc.ncbi.nlm.nih.gov/articles/PMC2965049/));
  clock traces alone carry enough signal to predict a player's rating
  ([CNN-LSTM rating estimation, 2024](https://arxiv.org/html/2409.11506v1)) —
  so simulated think times are *testable*: a rating model fed the bot's clock
  trace should estimate ≈ the bot's target rating. See `time-allocation.md`.
- **Stylometry as a discriminator**: models can identify individual players
  from ~100 games at 98% among 400 candidates — even from their mistakes alone
  ([KDD 2022](https://arxiv.org/abs/2008.10086)). The inverse is a strong
  adversarial test: can a classifier distinguish bot games from human games of
  the band? ⚠ No published bot-vs-human discriminator benchmark exists for
  this; it would have to be built.
- ⚠ Human Turing-test judgments (e.g. "did a human play this?") appear in the
  Maia project's follow-on work but no standardized protocol/numbers were
  found in the sources surveyed; treat panel testing as supplementary.

## Practical pass/fail sketch for this app (derived, not from literature)

1. Move-matching vs held-out lichess games of the target band (replicate the
   Maia filters: no bullet, skip 10 ply, skip <30s moves); require the bot's
   accuracy curve to peak at its target band (unimodality), not its absolute
   value to hit Maia's.
2. cpLoss histogram + blunder-rate within tolerance of band baselines,
   stratified by game phase and by blunder potential.
3. Monotonicity across the bot ladder on a fixed tactical test suite.
4. Deterministic replay: same seed ⇒ identical game (implementation invariant,
   not a literature metric).

## Cross-references

- Error distributions to match → `error-rates-by-rating.md`
- Think-time distributions to match → `time-allocation.md`
- Rating calibration (is the bot actually ~1100?) → `../rating-calibration/`
