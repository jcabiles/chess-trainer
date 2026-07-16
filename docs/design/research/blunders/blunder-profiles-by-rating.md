# Blunder profiles by rating band

Which blunder *types* dominate at which ratings, how often, and in which game
phases. Frequency numbers are **[data analysis]** (large-scale engine
analyses of online games, not peer-reviewed unless noted); type-dominance
claims are mostly **[coaching folklore]** and labeled as such.

## Frequency curves

- **chessanalysis.co "Blunder Curve"** — 160,000+ lichess Rapid games,
  Stockfish 17, blunder = ≥300 cp loss
  ([article](https://chessanalysis.co/research/blunder-curve-blunders-by-rating-level)
  ⚠ numbers below extracted via search excerpts; site blocked direct fetch):
  - Share of games containing ≥1 blunder barely moves across the amateur
    spectrum: **75.6% → 72.8%**. Improvement is not "stop blundering" — it's
    blundering *later*, in *safer* positions, and *less catastrophically*.
  - Average move of the **first** blunder: **move 16 at 400–600** rating vs
    **move 30 at 1500–1700**.
- **kwojcicki** — ~2,500 lichess games, blunder = >200 cp: blunder count
  **drops steeply with rating while "mistakes" (100–300 cp) stay roughly
  flat** across bands — improvement is mostly the elimination of
  catastrophes, not of medium errors
  ([blog](https://kwojcicki.github.io/blog/CHESS-BLUNDERS)).
- **patzersreview** — ~5,000 lichess classical games, blunder = ≥150 cp:
  sub-1500 players sit in the high-blunder-rate zones; strong players around
  10–20% of moves ⚠ (rate definition loose in source). Regression:
  `rating ≈ 1655 − 0.20·ACPL − 0.45·ratingDiff + 8.55·moves − 22·blunders`
  — each blunder ≈ −22 rating points, each survived move ≈ +8; single-game
  estimates ±400 Elo, so **per-game blunder counts are extremely noisy** —
  band-level averages only
  ([blog](https://patzersreview.blogspot.com/2020/05/estimating-playing-strength.html)).
- **Grandmaster baseline** [peer-reviewed]: 23 GMs (2530–2790), true blunders
  (≥1.5 pawns, outcome-changing) per 1000 moves: **5.02 classical, 6.85
  rapid, 7.63 blindfold-rapid**; mean magnitude ~2.7–3.2 pawns (Chabris &
  Hearst 2003, [PDF](https://www.chabris.com/Chabris2003.pdf), Table 1).
  Even the world elite blunders — roughly once per 4–5 slow games.
- Correlation caveat: rating↔ACPL correlation is real but **weak** at the
  per-game level ([kwojcicki](https://kwojcicki.github.io/blog/CHESS-BLUNDERS),
  [Medium ACPL–Elo analysis](https://medium.com/@enzo.leon/data-science-and-chess-centipawn-loss-elo-correlation-e06089efd8b8)).
  A bot tuned to a band should reproduce the *distribution*, not a fixed
  per-game quota. Quantitative distributions → `../human-play-modeling/`.

"Masters blunder three times per game, amateurs three times per move"
(attributed to Kasparov) — folklore, but directionally matched by the data
([quoted at patzersreview](https://patzersreview.blogspot.com/2020/05/estimating-playing-strength.html)).

## Dominant blunder types per band — [coaching folklore unless noted]

Consistent picture across coaching sources
([TheChessWorld: 11 most common mistakes by rating](https://thechessworld.com/articles/general-information/most-common-chess-mistakes-by-rating-explained-with-fixes/),
[chess.com: stuck below 1000](https://www.chess.com/blog/Benson_Gaterell/the-5-biggest-mistakes-that-keep-chess-players-stuck-below-1000),
[Heisman's Novice Nook corpus](https://www.danheisman.com/articles-by-subject.html)) —
⚠ no large-scale study labeling blunder *types* per band was found; this is
converging expert opinion:

| Band | Dominant blunder types | Mechanism (see blunder-causes.md) |
|---|---|---|
| < 1000 | One-move piece drops: not noticing own piece is attacked; not taking free material; mate-in-one allowed/missed; gross counting errors on exchanges | Hope chess (no safety scan at all); apperception — opponent's last move not processed |
| 1000–1400 | Simple tactics missed (forks, pins, skewers) — both walked into and not exploited; counting errors on defended pieces; premature attacks; king left in center | Hope chess (partial safety scan); Heisman's "counting" |
| 1200–1600 | **Missed opponent threat while executing own plan** — spots own 2–3-move tactics but loses to the opponent's counter; unsound "hope" sacrifices; weakening pawn pushes in front of own king | Einstellung / plan fixation becomes the *signature* failure once one-move drops fade |
| 1600–2000 | Deeper tactical oversights (zwischenzug, defensive resource at end of line); positional/structural errors; endgame technique | Retained-image errors; defensive-resource blindness |
| 2000+ | Rare outcome-changing errors, concentrated in time trouble and irrational/complex positions; endgame precision | Time pressure; complexity (see `../human-play-modeling/`) |

The **transition around 1200–1600** is the key fact for this app's audience:
the blunder type shifts from "didn't look at all" to "looked, but only inside
my own plan" — exactly the causal blunder the bots epic needs.

## Game-phase distribution

From the chessanalysis.co dataset
([article](https://chessanalysis.co/research/blunder-curve-blunders-by-rating-level)
⚠ via search excerpts):

- **Opening blunders collapse with rating**: blunder rate in the first 15
  moves drops dramatically as rating rises (opening study does its job);
  opening accuracy improves ~64% across the rating spectrum.
- **The endgame blind spot persists**: endgame accuracy improves only ~15%
  across the same spectrum; even ~1700 players blunder on **~40% of endgame
  moves**. Endgames are the least-improved phase at every amateur band.
- Middlegame is where absolute blunder *counts* concentrate at club level
  (most moves are middlegame moves, and positions are at maximum complexity);
  ACPL is typically lower in openings (theory) and highest in unclear
  middlegames ([lichess forum discussion](https://lichess.org/forum/general-chess-discussion/whats-a-decent-average-centipawn-loss) ⚠ anecdotal).

Repo note: `analysis.game_phase()` (material-count heuristic:
opening/middlegame/endgame) gives the app a compatible phase axis for both
profiling users and conditioning bot blunders.

## Time-control interaction

- The rapid-vs-bullet quality gap **widens with rating**: at low ratings the
  difference in move quality between Rapid and Bullet is negligible
  (beginners can't convert extra time into better moves); by 1500–1700 the
  gap is ~31 cp of ACPL
  ([chessenginelab / jk_182 analysis](https://chessenginelab.substack.com/p/evaluation-time-score)).
  Implication: a low-rated bot should NOT play better when "given more time";
  a higher-rated bot should.
- Low-clock blunder spike (blunders up, inaccuracies down) and the low-time
  alarm bump: see `./blunder-causes.md` §6.

## Bot-relevant summary

1. Per-band target rates must come from a stated definition (≥300 cp or
   ≥0.3 WP drop) — see `./blunder-definitions-and-thresholds.md`.
2. Rating ↑ should shift **when** (later first blunder), **where** (out of
   the opening, never out of the endgame), and **how big** (smaller WP
   drops), more than the raw per-game count.
3. Blunder *type* mix per band per the table above; triggering recipes in
   `./bot-blunder-triggers.md`; quantitative move-level models in
   `../human-play-modeling/`.
