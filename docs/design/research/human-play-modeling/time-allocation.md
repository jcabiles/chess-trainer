# Human time allocation: when players think long

Evidence on how humans spend clock time by phase, rating, and position — the
empirical basis for bot think-time *simulation* (the simulation design itself
lives in `../bot-personas/`).

## The primary dataset study: Sigman et al. 2010

[Sigman, Etchemendy, Slezak & Cecchi, "Response time distributions in rapid
chess" (Frontiers in Neuroscience 2010)](https://pmc.ncbi.nlm.nih.gov/articles/PMC2965049/)
— 2.8M FICS 3+0 games (May 2009–Jan 2010), >200M moves. Findings:

- **Move-time distributions are long-tailed (power-law-like), not normal.** A
  bot sampling think times from a Gaussian is statistically detectable; the
  right shape is heavy-tailed with occasional very long thinks.
- **Phase profile**: fast opening moves, fast endgame moves, longest thinks in
  the **middlegame** — with middlegame RT tails "pronouncedly longer."
- **Autocorrelation**: successive move times are positively correlated within
  a player (thinks cluster — a slow move tends to follow a slow move), while
  widely separated moves anti-correlate (the finite time budget forces later
  speed-up). Striking twist: **black–white move-time correlations exceed
  white–white** — opponents' thinking times synchronize, because both are
  reacting to the same critical moments. A believable bot should think long
  roughly when the *user* just thought long.
- **Complexity drives opening/middlegame thinks, time pressure drives endgame
  speed**: move-type entropy correlates with RT early in the game but weakly
  in the endgame — late-game speed is budget-driven, not ease-driven.
- **Skill and budgeting**: higher-rated players systematically allocate a
  larger share of their budget to the middlegame; and time is worth material —
  in 20–30s-remaining scrambles the fitted trade-off was ≈ "8 seconds is worth
  a rook." ⚠ that figure is specific to 3+0 FICS scrambles; don't generalize
  the constant, only the direction.

## Time and error (the causal link)

From [Anderson et al., KDD 2016](https://arxiv.org/abs/1606.04956) (tablebase
ground truth, see `error-rates-by-rating.md`):

- Blunder rate **rises sharply below ~10 seconds remaining and is flat above**
  — clock matters only near zero; among non-scramble moves, time features
  barely predict error (0.53 accuracy vs 0.73 for difficulty).
- **Longer per-move think correlates with *higher* blunder probability**,
  holding difficulty constant — a long think signals the player is lost/
  uncertain, not that the resulting move is safer. For the bot: long simulated
  thinks should *accompany* its errors and critical decisions, not substitute
  for them. This also matches the training-app UX goal: a bot that tanks
  before its blunder telegraphs "hard position" exactly like a human.

## Clock traces carry rating signal

A CNN-LSTM fed move sequences *plus per-move clock times* predicts player
rating move-by-move on 1.2M lichess games (Apr 2021–Jul 2024), and ablations
confirm the clock times improve the estimate
([Chess Rating Estimation from Moves and Clock Times, 2024](https://arxiv.org/html/2409.11506v1)).
Two consequences: (1) think-time patterns are rating-dependent, so a 1100 bot
and an 1800 bot need *different* time profiles; (2) this gives a ready-made
realism test — see `humanness-metrics.md`. Lichess stores per-move clocks at
0.1s precision in exported PGNs
([lichess feedback](https://lichess.org/forum/lichess-feedback/timestamps-on-moves)),
so band-specific think-time distributions can be fitted directly from the
[open database](https://database.lichess.org/) when parameterizing.

⚠ Gap: no published table of think-time distribution parameters per rating
band was found — fitting from the lichess database (or eyeballing Sigman's
figures) is required work, not a lookup.

## Design-ready summary for bot think-time simulation

Empirically grounded rules (each sourced above):

1. Sample from a **heavy-tailed** distribution, not a normal one.
2. Condition the mean on **game phase** (opening fast, middlegame slow,
   endgame fast) and on **remaining budget**.
3. Add **positive short-range autocorrelation** and coupling to the opponent's
   recent think time.
4. Spike think time on **critical/complex positions** (high blunder potential
   β(P) or eval-gap-narrow MultiPV sets are computable proxies; position
   "fragility" is an unvalidated alternative —
   [arXiv 2410.02333](https://arxiv.org/html/2410.02333v2) ⚠).
5. Let long thinks **precede blunders** sometimes — never make "bot thought
   long" imply "bot plays well."
6. Scale the whole profile by rating band (verifiable via a rating-from-clock
   model).

## Cross-references

- Bot think-time simulation design/parameters → `../bot-personas/`
- Realism testing of simulated clocks → `humanness-metrics.md`
- Time-scramble blunder regime → `error-rates-by-rating.md`
