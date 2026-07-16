# Triggering the right blunder for a target rating

Practical synthesis: given a target rating band and the current position,
what conditions should make a bot blunder, and *which* blunder. Grounded in
`./blunder-causes.md` (mechanisms + evidence) and
`./blunder-profiles-by-rating.md` (band mix). Computational machinery
(rating-conditioned move models, error-vs-complexity curves) lives in
`../human-play-modeling/`; strength execution in `../engine-adaptation/`.

## Design principle: blunders are input-side, not output-side

The peer-reviewed picture (Einstellung eye-tracking, Saariluoma's
apperception work — see `./blunder-causes.md` §1–2) says human blunders are
failures of **attention and representation** (what the player looks at /
encodes), not random noise added to a correct evaluation. So:

- ❌ Anti-pattern: "roll a die; if blunder, play a bad move" (random,
  uncausal — what the bots epic explicitly forbids).
- ✅ Pattern: **restrict or corrupt the bot's view of the position**, then let
  it play the *best move it can see*. The blunder is then automatically
  causal — the bot missed your threat *because* its attention was on its own
  plan — and automatically narratable by the coach ("the bot was pushing its
  kingside attack and never checked your d-file battery").

## Trigger conditions by mechanism

### A. Plan-fixation miss (Einstellung) — signature type for 1200–1600

**When to fire:** the bot has an active plan (an attack, a pawn break, a
maneuver — detectable as consecutive moves improving the same region /
increasing engine-eval of its own idea), AND the opponent's last 1–2 moves
created a *new* threat whose key squares are **disjoint from the plan's
attention set** (e.g. opposite wing, back rank, long diagonal into the bot's
camp).

**How:** evaluate opponent replies only within the plan-consistent attention
set (squares touched by the bot's recent moves + its target region); threats
outside it are invisible this move. Evidence that attention locks to
plan-consistent squares even during deliberate "search for something better":
[Bilalić et al. 2008](https://www.researchgate.net/publication/222561910_Why_good_thoughts_block_better_ones_The_mechanism_of_the_pernicious_Einstellung_effect),
[Sheridan & Reingold 2013](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0075796).

**Rating scaling:** probability of the miss decreases with rating; the
required "distance" between threat and plan region shrinks (a 1900 bot only
misses genuinely hidden threats; an 1100 bot misses anything off-plan).

### B. Hope-chess miss (no safety scan) — dominant below ~1200

**When to fire:** any move where the bot's intended move is not forced, and
the opponent has an immediate forcing reply (check, capture, or one-move
threat) that punishes it.

**How:** skip the "can I safely meet every forcing reply?" verification with
probability p(rating) — Heisman's definition of hope chess verbatim
([danheisman.com](https://www.danheisman.com/articles-by-subject.html)).
Below ~1000 also fire the degenerate version: fail to notice the opponent's
*last* move attacked something (play the previously-intended move anyway) —
the classic one-move piece drop
([TheChessWorld band inventory](https://thechessworld.com/articles/general-information/most-common-chess-mistakes-by-rating-explained-with-fixes/) ⚠ folklore mix).
This is also the natural sparring partner for this app's profiler, which
already measures the user's own `hope_chess_rate` (`app/profile.py`).

### C. Calculation decay (retained image / defensive-resource blindness) — 1400+

**When to fire:** the bot chooses a forcing line ≥4 plies deep.

**How:** inside its lookahead, (a) with small probability keep a moved/
captured piece's *influence* on its old square (Krogius's retained image —
see `./blunder-causes.md` §3), or (b) generate opponent replies at
inner nodes from forcing moves only, so a *quiet* defensive resource or
retreating defense at the line's end goes unseen (⚠ mechanism labels partly
folklore; the resulting error type — "own tactic was unsound" — is well
attested). Produces the miscalculated-own-tactic family rather than the
missed-threat family.

### D. Time-pressure spike — any band, only if the bot simulates a clock

**When to fire:** simulated clock low.

**How:** don't scale all noise up — **raise only the catastrophic-miss
probability** (blunders up, inaccuracies actually down under time pressure:
[jk_182](https://lichess.org/@/jk_182/blog/how-does-the-clock-impact-the-rate-of-mistakes/JSazQplM)),
with a discrete jump at a "panic threshold"
([Antiochian, 68M games](https://github.com/Antiochian/chess-blunders)).
GM-level calibration: rapid ≈ +36.5% true blunders vs classical
([Chabris & Hearst 2003](https://www.chabris.com/Chabris2003.pdf)).

## Position-class gates (works with any mechanism)

- **Phase:** never "cure" the endgame — endgame blunder rates barely improve
  with rating (~1700s err on ~40% of endgame moves,
  [chessanalysis.co](https://chessanalysis.co/research/blunder-curve-blunders-by-rating-level)
  ⚠ via excerpts); opening blunders should nearly vanish above ~1400. Use
  `analysis.game_phase()` as the gate.
- **First-blunder timing:** low bands may blunder from move ~16; higher bands
  should survive to move ~30 on average (same source) — a per-game hazard
  schedule, not a per-move constant.
- **Severity:** classify the induced drop on the win-probability axis
  (`win_prob_from_cp`, identical to lichess's model — see
  `./blunder-definitions-and-thresholds.md`); pick candidate "blunder moves"
  by target WP drop (e.g. 0.20–0.35), so blunders stay proportionate in
  sharp vs quiet positions and never re-blunder an already-lost game into
  absurdity.
- **Back-rank / geometry triggers:** maintain a small library of
  position-class predicates (bot's back rank weak + heavy pieces traded off
  the defense; bot's king ring pawns advanced; opponent battery formed on a
  file the bot's plan ignores) that raise the mechanism-A fire probability.
  ⚠ folklore as mechanism, but empirically common and cheap to detect with
  python-chess.

## Anti-randomness invariant (testable)

Every induced blunder should be able to answer: **(1)** what was the bot
attending to (its plan), **(2)** what did it therefore not see (the threat /
the resource), **(3)** why is that miss plausible at this rating (band table
in `./blunder-profiles-by-rating.md`). If any answer is "no reason — the dice
said so", the design has regressed to random weakening, which is exactly what
`../engine-adaptation/` documents as feeling artificial. This triple is also
the hook for coach narration and for the foresight trainer ("find the threat
the bot is about to miss").
