# Attention capture, tunnel vision, and motif-specific blindness

The cognitive-science evidence for *causal* errors — why a human misses your
threat while pursuing their own plan — plus which tactical motifs are missed
most at each level. This is the folder's core support for the epic's headline
requirement (a ~1100 bot that blunders *because* it's attacking). Blunder
taxonomy/causality as applied labels → `../blunders/`.

## Einstellung: the lab-verified mechanism of plan fixation

The strongest experimental evidence that "own-plan salience" causes blindness
is the chess Einstellung work of Bilalić, McLeod & Gobet
(["Why good thoughts block better ones"](https://www.researchgate.net/publication/222561910_Why_good_thoughts_block_better_ones_The_mechanism_of_the_pernicious_Einstellung_effect),
Cognition 2008; eye-movement follow-up in
[PLOS ONE 2013](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0075796)):

- Setup: positions containing a *familiar* winning idea (e.g. a known smothered-
  mate pattern) and a less familiar but *better/faster* solution.
- Experts who spotted the familiar idea **reported** searching for something
  better, but **eye tracking showed their gaze kept returning to squares
  relevant to the familiar solution** — attention stayed captured by the
  first idea even during claimed open search
  ([PLOS ONE 2013](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0075796);
  [summary](https://journals.sagepub.com/doi/abs/10.1177/0963721410363571)).
- The first idea directs attention *toward* confirming information and *away*
  from inconsistent information, unconsciously
  ([Bilalić/McLeod/Gobet 2010 overview](https://journals.sagepub.com/doi/abs/10.1177/0963721410363571)).

Implication for the error model: blindness is not uniform noise — it is
**directional**, pointed away from whatever contradicts the currently active
plan. A bot mid-attack should have *specifically reduced* probability of
noticing defensive resources and opponent counter-threats, which is exactly
the epic's causal-blunder requirement. ⚠ Einstellung experiments quantify the
effect in expert problem-solving, not per-rating-band blunder frequencies in
real games; the *strength* of the fixation dial per band must be calibrated,
not looked up.

## "Hope chess": the dominant sub-1400 failure mode

Dan Heisman's term (from the Novice Nook column): **Hope Chess is making a
move without checking whether you can meet every opponent reply that is a
check, capture, or threat**
([Heisman's definitions page](https://www.danheisman.com/definitions.html)).
The contrast is "Real Chess": for each candidate, anticipate all forcing
replies and reject candidates whose refutation can't be met. Heisman's
coaching claim is that failing to do this systematically caps players below
~intermediate level. ⚠ Instructional/coaching evidence, not a dataset study —
but it operationalizes beautifully: a hope-chess bot evaluates its own
candidate moves *without* the opponent's best forcing reply (shallow or
null-move search on replies), which produces exactly the class of "didn't
check your capture" blunders. Converges with the Maia finding that whether a
human blunders is predictable from the position (71.7% accuracy,
[KDD 2020](https://arxiv.org/abs/2006.01855)) — threat visibility is a
learnable positional feature.

## Invisible moves: geometric blindness classes

Neiman & Afek's *Invisible Chess Moves* (New in Chess, 2011) catalogs move
classes players systematically overlook, with psychological/geometric
explanations ([book](https://www.amazon.com/Invisible-Chess-Moves-Discover-Overlooking/dp/9056913689)):

- **Backward moves** — especially backward piece retreats that attack;
  players are "hard-wired to go forward"
  ([House of Staunton overview](https://www.houseofstaunton.com/chess-blog/a-complete-guide-to-chess-blindness-in-2024/)). ⚠ book + coaching consensus, not dataset-quantified.
- **Quiet moves** amid forcing sequences (no check/capture/immediate threat).
- Horizontal rook moves, moves along the board edge, and moves by
  recently-moved pieces are also cited classes. ⚠ same caveat.

## Which motifs are missed most, by rating

The best quantitative proxy: the [lichess puzzle
database](https://database.lichess.org/#puzzles) (millions of puzzles,
Glicko-2-rated by real solve attempts — each attempt is a rated "game" between
player and puzzle, so **theme difficulty is measured against real humans**).
Community analysis of theme-vs-puzzle-rating distributions
([Nik-Hairie's analysis of 3.08M puzzles](https://github.com/Nik-Hairie/Lichess-Puzzle-Database-Analysis)):

- **Fork** puzzles peak in frequency around **800–900** puzzle rating;
  **skewer** ≈ 900 — the entry-level motifs.
- **Deflection** and **X-ray** peak ≈ **1400**; **trapped piece** ≈ **1600**.
- ⚠ community analysis, not peer-reviewed; also note this measures where
  themed puzzles *land* on the difficulty scale (solve success), which is a
  proxy for — not a direct measurement of — in-game miss rates per band.
- Quiet-move and underpromotion themes sit among the hardest ⚠ (directionally
  consistent with the invisible-moves classes above, but no verified numbers
  found in the surveyed sources).

Rating-band reading (proxy-level, for persona design): a ~900 bot may miss
even simple knight forks; a ~1400 bot reliably sees forks/pins/skewers but
misses deflections, X-rays, and defensive-overload ideas; trapped-piece and
quiet-move blindness persists to ~1600+. Cross-check against the in-game
blunder taxonomy in `../blunders/` before hard-coding.

## Difficulty beats skill even here

Two dataset findings that keep motif blindness honest:

- **Skill-anomalous positions**: some common positions are blundered *more* by
  higher-rated players ([Anderson et al., KDD 2016](https://arxiv.org/abs/1606.04956)) —
  plausibly familiar-pattern overconfidence (Einstellung in the wild ⚠ — the
  paper doesn't attribute a mechanism).
- Maia predicts the *exact* blunder a human plays >25% of the time on
  queen-hanging howlers ([CSSLab blog](http://csslab.cs.toronto.edu/blog/2020/08/24/maia_chess_kdd/))
  — human blunders are systematic and position-determined, so motif-conditioned
  (not uniform) error injection is the empirically correct design.

## Design hooks (derived)

1. **Plan-fixation gate**: while the bot has an active attacking plan, damp
   the salience of opponent forcing replies that don't interact with the
   plan's target squares (Einstellung-consistent directional blindness).
2. **Hope-chess mode** (sub-~1300 personas): evaluate own candidates with the
   opponent's best forcing reply partially hidden (e.g. probability of
   registering each check/capture/threat scaled by rating and by motif class).
3. **Motif-class miss table**: per-band base miss probabilities ordered
   fork/skewer < pin < discovered attack < deflection/X-ray < trapped piece /
   quiet refutations, calibrated against `../blunders/` and
   `../rating-calibration/`. ⚠ ordering partially proxy-based (see above).
4. Backward-moving and quiet refutations get an extra visibility penalty at
   all bands (invisible-moves classes).

## Cross-references

- Blunder taxonomy & causal labels → `../blunders/`
- Persona-level style dials (aggression = stronger plan fixation) →
  `../bot-personas/`
- Quantitative error budgets these gates must sum to →
  `error-rates-by-rating.md`
