# Why blunders happen — causal mechanisms

The evidence base for each mechanism, explicitly labeled **[peer-reviewed]**,
**[data analysis]** (large-scale but not peer-reviewed), or **[coaching
folklore]** (widely taught, evidentially thin). The bots epic's core realism
requirement — blunders must be CAUSAL (bot misses your threat while executing
its own plan), never random — maps directly onto the first two mechanisms.

## 1. Plan fixation / attack tunnel-vision (the Einstellung effect) — [peer-reviewed]

The strongest experimental result in chess-error psychology. Bilalić, McLeod
& Gobet gave players positions containing a *familiar* winning idea (e.g. a
smothered-mate pattern) and a less familiar but objectively better solution.
Even masters who insisted they were searching for something better kept
failing to find it — and **eye-tracking showed why: the first idea that comes
to mind directs attention toward squares consistent with it and away from
inconsistent information**. Players *reported* looking for alternatives while
their gaze stayed locked on squares belonging to the familiar plan.

- Bilalić, McLeod & Gobet (2008), "Why good thoughts block better ones: the
  mechanism of the pernicious Einstellung (set) effect", *Cognition*
  ([ResearchGate](https://www.researchgate.net/publication/222561910_Why_good_thoughts_block_better_ones_The_mechanism_of_the_pernicious_Einstellung_effect))
- Bilalić, McLeod & Gobet (2010), "The Mechanism of the Einstellung (Set)
  Effect", *Current Directions in Psychological Science*
  ([SAGE](https://journals.sagepub.com/doi/abs/10.1177/0963721410363571))
- Bilalić et al. (2008), "Inflexibility of experts — reality or myth?",
  *Cognitive Psychology* — quantifies it: the effect costs experts roughly
  three standard deviations of problem-solving performance (i.e. an
  Einstellung-afflicted master performs about like a much weaker player on
  that position) ([PubMed](https://pubmed.ncbi.nlm.nih.gov/17418112/))
- Replication + boundary conditions with eye movements: Sheridan & Reingold
  (2013), *PLOS ONE*
  ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC3790829/))

**Bot translation:** this IS the causal-blunder mechanism. A bot with an
active plan should generate/weight candidate moves and *threat checks* only
in the attention set induced by its plan; opponent threats outside that set
are the ones it misses. The blindness is attentional (input-side), not a
calculation die-roll (output-side). See `../human-play-modeling/` for
computational implementations.

## 2. Apperception failure — misencoding the position — [peer-reviewed]

Saariluoma (1992), "Error in chess: the apperception-restructuring view",
*Psychological Research*: five protocol-analysis experiments (tactical,
endgame, strategic positions) showed chess errors are **only partially
explained by working-memory overload** — the WM load of the actual solution
paths was usually small. Instead, players fail because *apperception* (the
mechanism controlling what information is taken in) either (a) never
constructs the right problem space at all, or (b) misses one crucial
task-relevant cue, after which the player loses "belief in the idea",
restructures, and becomes even *less* likely to find the solution
([Springer](https://link.springer.com/article/10.1007/BF01359219),
[PubMed](https://pubmed.ncbi.nlm.nih.gov/1603886/)).

**Bot translation:** a realistic blunder is a wrong *representation* (a
defender not registered, a long-diagonal attacker not encoded), not a wrong
*calculation over a correct representation*. One missing cue is enough.

## 3. Retained-image / stale-board errors — [book-level psychology]

Krogius (1976, *Psychology in Chess*) enumerated and estimated likelihoods of
errors of commission/omission during forward calculation: e.g. forgetting
during a long line that a piece has been captured or has left a square, so a
"ghost" piece still guards or blocks in the player's mental image (cited and
discussed in Chabris & Hearst 2003, p. 645,
[PDF](https://www.chabris.com/Chabris2003.pdf)). Not a controlled experiment,
but written by a GM-psychologist from game evidence. Related: blindfold-play
studies show strong players' representations are abstract "lines of force",
not pictures — functionally significant squares are represented much better
than insignificant ones (Saariluoma & Kalakoski 1998, *Memory*,
[PubMed](https://pubmed.ncbi.nlm.nih.gov/9640433/)).

**Bot translation:** in deep lines, errors should concentrate on *changed*
squares (a piece that moved away two plies ago still "defends" in the bot's
model) — a natural way to make miscalculated-own-tactic blunders causal.

## 4. Missed opponent threat vs miscalculated own tactic — the two families

A useful top-level split (this repo's profiler already separates
`missed_threat` from other leak categories):

- **Errors of omission** — the opponent's *new* threat after their last move
  never enters the candidate/check set. Mechanisms 1–2 above produce these.
  "Hope chess" (below) is the habitual version.
- **Errors of commission** — the player *did* calculate their own idea but
  the line was unsound (retained image, missed zwischenzug, missed defensive
  resource at the end of the line). Mechanism 3 produces these.

Chabris & Hearst's data can't separate the two (engine-only), and no
large-scale study quantifying the omission/commission ratio per rating band
was found ⚠ — treat any such split as folklore-calibrated. Coaching
consensus is that omission dominates at low ratings ("didn't see it" vastly
outnumbers "calculated it wrong"), e.g.
[TheChessWorld](https://thechessworld.com/articles/general-information/most-common-chess-mistakes-by-rating-explained-with-fixes/).

## 5. "Hope chess" — skipping the safety check — [coaching, well-defined]

Dan Heisman's term: **making a move without verifying you can safely meet
every forcing reply** (checks, captures, threats) — you "hope" the opponent
doesn't have one. Heisman's Novice Nook columns (aimed at 1000–1400) treat
this as *the* defining habit separating sub-1600 play, alongside "counting"
errors (misjudging exchange sequences)
([danheisman.com articles](https://www.danheisman.com/articles-by-subject.html),
[chess.com forum summary](https://www.chess.com/forum/view/general/do-you-know-what-hope-chess-is),
[Novice Nook archive](https://chesscafe.com/columns/novice-nook/)).
This repo's profiler measures a `hope_chess_rate` = fraction of analysed
games with a `missed_threat` leak (`app/profile.py`).

The classical antidote is **Blumenfeld's rule** (via Kotov, *Think Like a
Grandmaster*): after finishing your calculation, look at the position afresh
"through the eyes of a patzer" — am I leaving mate in one? a hanging piece? —
before moving
([Exeter Chess Club](https://exeterchessclub.org.uk/content/blumenfelds-rule),
[chess.com blog](https://www.chess.com/blog/WGMTijana/blumenfelds-rule-the-key-to-avoiding-blunders)).
The rule exists *because* deep calculation displaces the shallow safety scan —
i.e. the blunder-after-thinking-hard phenomenon is old, known, and causal.

**Bot translation:** hope chess = the bot's threat-scan step runs with
probability p < 1 (or scans only forcing replies to *its own* plan);
Blumenfeld failure = the deeper the bot "thought" about its own plan this
move, the lower the chance the shallow one-ply safety scan runs.

## 6. Time pressure & speed — [peer-reviewed + data analysis]

- **Chabris & Hearst (2003)** [peer-reviewed]: same 23 GMs, engine-scored.
  True blunders per 1000 moves: **5.02 classical vs 6.85 rapid (+36.5%) vs
  7.63 blindfold-rapid**; average blunder magnitude 2.66 vs 3.15 vs 3.08
  pawns. Rapid vs blindfold not significant — **removing sight of the board
  barely matters; removing thinking time matters a lot**. Under flagrant
  criteria (≥3 pawns) fast conditions produced *more than twice* the big
  blunders of classical ([PDF](https://www.chabris.com/Chabris2003.pdf),
  Table 1, pp. 642–643).
- **jk_182 lichess blog** [data analysis]: as clock runs low, *inaccuracies
  decrease, mistakes stay flat, only blunders increase* — under pressure
  players don't get uniformly sloppier, they occasionally fall off a cliff
  ([lichess blog](https://lichess.org/@/jk_182/blog/how-does-the-clock-impact-the-rate-of-mistakes/JSazQplM)).
  Effects on game *results* only become large under ~10 seconds remaining
  ([companion post](https://lichess.org/@/jk_182/blog/how-the-evaluation-and-clock-impact-results-of-blitz-games/I2kRp2sk)).
- **Antiochian, 68M lichess games** [data analysis]: blunder-rate curves show
  a bump exactly at the low-time alarm (20s in 3+0, 40s in 5+0, 60s in 10+0)
  — an anxiety/attention trigger, not just raw time scarcity
  ([GitHub](https://github.com/Antiochian/chess-blunders)).
- Contrast: Calderwood, Klein & Crandall (1988) found little *subjectively
  judged* quality difference between fast and slow play for masters — the
  engine-scored studies superseded this
  ([discussion in Chabris & Hearst](https://www.chabris.com/Chabris2003.pdf), p. 638).

**Bot translation:** time pressure should raise the probability of the
*catastrophic* miss specifically (not scale all noise uniformly), with a
discrete jump near a "panic" trigger.

## 7. Pattern-specific blindness (back rank, retreats, defensive resources) — [coaching folklore] ⚠

Widely taught, but no controlled studies specific to these patterns were
found:

- **Back-rank blindness** — the mating pattern arrives on a square the
  player's attention never visits because no piece of theirs is "doing
  anything" there. Consistent with (but not proven by) the Einstellung
  attention findings. ⚠ folklore as a *distinct* mechanism; plausibly just
  mechanism 1+2 in a specific geometry.
- **Retreating-move blindness** — backward/retreating moves (especially
  knight retreats) are held to be the hardest to consider, for oneself *and*
  as opponent resources. ⚠ No direct experimental evidence found; treat as
  folklore. (Lichess puzzle-theme difficulty data could test this but no
  published analysis was found —
  [themes list](https://lichess.org/training/themes).)
- **Defensive-resource blindness** — at the end of a calculated line, the
  opponent's *quiet* defensive move is missed because calculation is
  attack-generated (forcing moves first). Consistent with Saariluoma's
  missing-cue account; no dedicated study found ⚠.

**Bot translation:** safe to implement these as *position-class triggers*
(they're empirically common in human games even if the mechanism labels are
folklore) — e.g. a bot may under-weight opponent retreating moves and quiet
defenses when generating the opponent-reply set inside its own calculation.

## 8. Fatigue — [thin] ⚠

Plausible and often asserted (long games, late rounds), but no solid
chess-specific quantitative source was located in this pass ⚠. Do not build
bot behavior on it; time pressure (mechanism 6) covers the practical need.

## Cross-links

- Quantitative/computational error models (Maia's rating-conditioned move
  prediction and blunder prediction, choice models, error-vs-complexity
  curves): `../human-play-modeling/`
- How a bot *executes* at reduced strength without these causal mechanisms:
  `../engine-adaptation/`
- Which mechanism dominates at which rating: `./blunder-profiles-by-rating.md`
- How to fire these on purpose: `./bot-blunder-triggers.md`
