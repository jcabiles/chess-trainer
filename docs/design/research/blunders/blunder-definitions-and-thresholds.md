# Blunder definitions & thresholds

What formally counts as a blunder / mistake / inaccuracy, across the three
axes the industry actually uses, and where this repo's own `analysis.classify()`
sits relative to convention.

## The three axes

1. **Raw centipawn loss (cp-loss)** — `eval(best) − eval(played)`. Oldest and
   simplest; position-insensitive (a 300 cp drop from +800 to +500 counts the
   same as 0 → −300).
2. **Win-probability drop** — convert cp → win% via a logistic fit on real
   game outcomes, classify on the *drop in win%*. This is what **lichess**
   uses. It automatically discounts eval swings inside already-decided
   positions ([lichess accuracy page](https://lichess.org/page/accuracy)).
3. **Expected-points drop, rating-conditioned** — what **chess.com** uses:
   an "expected points" model (1.00 = certain win, 0.50 = even) whose mapping
   from engine eval to expected points **depends on the player's rating** —
   the same eval means different winning chances at 800 vs 2500
   ([chess.com Help Center](https://support.chess.com/en/articles/8572705-how-are-moves-classified-what-is-a-blunder-or-brilliant-etc)).

The industry trajectory is clearly away from raw cp-loss toward outcome-based
axes, and chess.com has gone one step further by making the axis itself
rating-conditional — a directly relevant precedent for rating-targeted bots.

## Lichess (exact, from source)

Win% model (server-side `WinPercent`, client `winningChances`), regression fit
on real lichess game data, benchmarked on games among ~2300-rated players
([lichess accuracy page](https://lichess.org/page/accuracy),
[lila PR #11148](https://github.com/lichess-org/lila/pull/11148)):

```
Win% = 50 + 50 * (2 / (1 + exp(-0.00368208 * centipawns)) - 1)
```

Judgement thresholds on the **winning-chances delta** (0..1 scale), from
[`modules/tree/src/main/Advice.scala`](https://github.com/lichess-org/lila/blob/master/modules/tree/src/main/Advice.scala):

| Winning-chance drop | Label |
|---|---|
| ≥ 0.30 | Blunder |
| ≥ 0.20 | Mistake |
| ≥ 0.10 | Inaccuracy |

(Confirmed in [lila issue #4705](https://github.com/lichess-org/lila/issues/4705),
which introduced win-chance-based judgements to replace raw cp thresholds.)

Move accuracy (separate from judgements) is an exponential fit on the win%
drop: `Accuracy% ≈ 103.1668 · exp(−0.04354 · winDiff) − 3.1669` (+1
uncertainty bonus in source), clamped to [0, 100]
([AccuracyPercent.scala](https://github.com/lichess-org/lila/blob/master/modules/analyse/src/main/AccuracyPercent.scala)).

**Mate transitions get special handling** (`MateAdvice` in the same
Advice.scala): sequences are classified as *MateCreated* ("checkmate is now
unavoidable"), *MateLost* ("lost forced checkmate sequence"), or *MateDelayed*
("not the best checkmate sequence"), with judgement severity depending on how
bad the position already was before the transition (a "mate created" from an
already-lost < −999 cp position is only an Inaccuracy; from a healthy position
it's a Blunder).

## Chess.com (official support article)

Classification V2, "expected points" lost per move
([chess.com Help Center](https://support.chess.com/en/articles/8572705-how-are-moves-classified-what-is-a-blunder-or-brilliant-etc)):

| Expected points lost | Label |
|---|---|
| 0.00 | Best |
| 0.00–0.02 | Excellent |
| 0.02–0.05 | Good |
| 0.05–0.10 | Inaccuracy |
| 0.10–0.20 | Mistake |
| 0.20–1.00 | Blunder |

Note the scale difference: chess.com's expected points run 0–1 where lichess
winning chances also run 0–1, but chess.com's blunder floor (0.20) is *lower*
than lichess's (0.30) — chess.com labels more moves "blunder", **and** its
eval→expected-points mapping shifts with the player's rating. Special labels
(Brilliant = sound sacrifice, Great, Miss, Missed Win) use rules beyond
expected points.

## Research-grade definitions

- **Chabris & Hearst (2003)**, *Cognitive Science* — the reference academic
  operationalization: a **candidate blunder** = move evaluated ≥ **1.5 pawns**
  worse than the engine's best (Fritz 5, 10-ply exhaustive); a **true
  blunder** additionally must plausibly change the game outcome — errors were
  *excluded* if the erring side still retained a ≥ 3.0-pawn advantage
  afterwards. The 1.5-pawn cut was chosen because computer-chess research
  (Hartmann 1989) treats a 1.5-pawn edge as theoretically winning
  ([PDF](https://www.chabris.com/Chabris2003.pdf), pp. 641–642).
  The "true blunder" refinement is the academic ancestor of the
  win-probability axis: a raw eval drop that doesn't change the probable
  result isn't really a blunder.
- Community/blog analyses use ad-hoc cp cuts: ≥ 150 cp
  ([patzersreview](https://patzersreview.blogspot.com/2020/05/estimating-playing-strength.html)),
  > 200 cp ([kwojcicki](https://kwojcicki.github.io/blog/CHESS-BLUNDERS)),
  ≥ 300 cp ([chessanalysis.co](https://chessanalysis.co/research/blunder-curve-blunders-by-rating-level)).
  There is **no single canonical cp threshold** — anything in 150–300 cp is
  defensible; what matters is stating the definition.

## Where this repo sits (`app/analysis.py`, read-only reference)

The repo deliberately runs **both axes** (design note in `analysis.py`,
"Refuter resolution #10"):

**Play-mode `classify()`** — raw cp-loss buckets:
best ≤ 10 < good ≤ 50 < inaccuracy ≤ 100 < mistake ≤ 250 < blunder.

**Review-pipeline `leak_severity()`** — win-prob-drop axis using the *exact
lichess constant* (`win_prob_from_cp` = `1/(1+exp(-0.00368208·cp))`, i.e.
lichess Win%/100): mistake ≥ 0.10 WP drop, blunder ≥ 0.20 WP drop.

How they compare to convention (computed from the shared formula):

| Move | cp axis (`classify`) | WP drop | lichess label | repo `leak_severity` |
|---|---|---|---|---|
| 0 → −100 | inaccuracy | 0.091 | (good) | none |
| 0 → −250 | mistake (boundary) | 0.215 | mistake | blunder |
| 0 → −377 | blunder | 0.300 | blunder | blunder |
| +300 → +50 | mistake→blunder boundary | 0.205 | mistake | blunder |
| +800 → +500 | blunder | 0.087 | *good* | none |

Three takeaways:

1. **`leak_severity` is exactly one notch stricter than lichess** — its
   blunder floor (0.20) equals lichess's *mistake* floor, its mistake floor
   (0.10) equals lichess's *inaccuracy* floor. Intentional: tuned for the
   ~800–1100 audience where a 10% WP swing is practically decisive (comment
   in `analysis.py`). It coincides with chess.com's blunder floor of 0.20 —
   the repo's review labels are closer to chess.com's convention than
   lichess's.
2. **The cp-loss `classify()` over-flags in decided positions** (+800 → +500
   is a "blunder" by cp but doesn't change the result — lichess calls it
   good; Chabris & Hearst would exclude it as not a "true blunder") and is
   roughly one notch *lenient* near equality (a 250 cp drop from equal is
   already a 21.5% WP swing). Fine for its purpose (opening-prep feedback),
   but bots and review logic should classify on the WP axis.
3. **Mate handling**: the repo maps mate to the cp axis as
   `sign·(MATE_CP − N)` so lost/allowed mates land in the blunder bucket via
   the same formula; lichess instead uses a dedicated MateCreated/Lost/Delayed
   sequence classifier with position-conditional severity. Same spirit,
   different mechanism.

## Blunder vs game-ending move

A move that *delivers* checkmate or a draw is not an error even though the
naive eval-delta math can look degenerate (terminal positions have no engine
eval). This repo labels game-ending moves `checkmate`/`draw` rather than
running them through the quality buckets (PR #55; `app/main.py` checks
`board.is_checkmate()` before classification). Lichess similarly never judges
the mating move itself — its MateAdvice logic only fires on transitions
*into/out of forced-mate evals*, not on the terminal move
([Advice.scala](https://github.com/lichess-org/lila/blob/master/modules/tree/src/main/Advice.scala)).
Distinct concept from a blunder that *allows* mate (which the mate-to-cp
mapping correctly buckets as a blunder).

## Implications for bots

- Define bot-blunder severity on the **win-probability axis** (the repo
  already has `win_prob_from_cp` matching lichess exactly); pick the size of
  the induced WP drop, not a raw cp amount, so a "blunder" means the same
  thing in sharp and quiet positions.
- Chess.com's rating-conditioned expected-points model is precedent for making
  the *threshold itself* rating-dependent — at 800, a 15% WP drop is
  routine noise; at 1800 it's a genuine blunder. See
  `../rating-calibration/` for rating math and
  `../human-play-modeling/` for quantitative per-rating error distributions.
