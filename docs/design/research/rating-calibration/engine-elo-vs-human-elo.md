# Engine-ELO vs human-ELO — why a Stockfish "1500" is not a human 1500

The core problem for labeling bots honestly. Stockfish exposes strength knobs
(`UCI_Elo`, `UCI_LimitStrength`, `Skill Level`) but **none of them is calibrated
against a human rating ladder**. This note documents what each knob actually
means, what it was calibrated against, and the known direction/size of the error
vs human ratings. The *fix* (Maia bands, calibration matches, fuzzy labels) is in
[honest-bot-rating-assignment.md](honest-bot-rating-assignment.md). Making the
engine *play* weak is out of scope here → `../engine-adaptation/`.

## Stockfish's three strength knobs

### `Skill Level` (0–20) — no Elo semantics at all
Skill Level weakens play by internally enabling MultiPV and, with a probability
that depends on the level, **deliberately picking a weaker move** from the
candidate list. It is a *difficulty dial*, not a rating. There is no documented
Elo number attached to a given Skill Level. [Stockfish UCI & Commands wiki](https://github.com/official-stockfish/Stockfish/wiki/UCI-&-Commands)

### `UCI_LimitStrength` + `UCI_Elo` — an Elo number, but an *engine* Elo
When `UCI_LimitStrength` is `true`, `UCI_Elo` targets a given Elo. Internally
**Stockfish converts `UCI_Elo` to a fractional Skill Level** and uses the same
weaken-the-move mechanism — so `UCI_Elo` is Skill Level wearing a rating label.
[Stockfish UCI & Commands wiki](https://github.com/official-stockfish/Stockfish/wiki/UCI-&-Commands)

**Range:** `UCI_Elo` is a spin with **default 1320, min 1320, max 3190** (these
values are version-dependent — older Stockfish had min ~1350). [UCI_Elo min/max —
Stockfish docs & discussion](https://github.com/official-stockfish/Stockfish/discussions/4434)
There is **no sub-1320 setting** via `UCI_Elo` — a real human 800 cannot be
targeted this way at all (a hard limit for a beginner-facing ladder).

## What `UCI_Elo` was actually calibrated against (the key finding)

From the original implementation PR (vondele, PR #2225), the calibration
conditions were:

> **TC 60+0.6, Hash 64Mb, 8moves_v3.pgn, rated with Ordo, anchored to
> goldfish1.13 (CCRL 40/4 ~2000).**

[Stockfish PR #2225 — UCI_Elo implementation](https://github.com/official-stockfish/Stockfish/pull/2225)

Unpacking every anchor — **and why each one breaks the human meaning:**

- **Opponent pool = other engines (Stockfish self-play at varied strength), not
  humans.** The Elo numbers were fit so that engines at setting *X* score as
  expected *against each other*. An engine ladder and a human ladder are
  different populations; equal Elo across the two does **not** imply equal
  playing strength or equal *style*. This is the root mismatch.
- **Anchor = goldfish 1.13 ≈ 2000 on CCRL 40/4** — CCRL is a *computer* rating
  list. The PR author himself noted "the anchoring to CCRL is a bit weak."
  [PR #2225](https://github.com/official-stockfish/Stockfish/pull/2225)
- **Time control = 60+0.6 for calibration, but the docs also cite 120s+1s** for
  the shipped feature. Either way it is a fixed, engine-testing TC. Change the
  TC or hardware and the effective strength shifts. [Stockfish UCI wiki](https://github.com/official-stockfish/Stockfish/wiki/UCI-&-Commands)
- **Rated with Ordo** — Ordo is an Elo-computation tool over game results; it
  computes a *relative* Elo within the tested pool. It does not tie the scale to
  FIDE, lichess, or chess.com. [PR #2225](https://github.com/official-stockfish/Stockfish/pull/2225)

**Bottom line:** `UCI_Elo` is an *engine-pool Elo* anchored to a *computer*
rating list. It is internally self-consistent (setting 1600 beats setting 1500
as expected) but it is **not** anchored to any human ladder, and the anchor
itself (CCRL) is acknowledged as weak.

## Node-limited strength is hardware- and version-dependent

If instead of `UCI_Elo` you cap **nodes per move** (a common way to make a
reproducible-ish weak engine), the *strength* of a fixed node budget still moves
with Stockfish version and, for time-based limits, with hardware:

- Stockfish at **15k nodes/move is ~800 Elo weaker** than at 300k nodes/move —
  strength is steeply sensitive to the node budget. [TalkChess / MeloniMarco node
  tests](https://www.melonimarco.it/en/2021/03/08/stockfish-and-lc0-test-at-different-number-of-nodes/)
- Community consensus: Stockfish Elo values are **hardware-, version-,
  time-control-, and hash-dependent** and should be treated as **approximate
  anchors, not fixed ground truth.** [TalkChess node-equivalence threads](https://talkchess.com/viewtopic.php?t=83654)
- Practically: a "1500 by node budget" tuned on one machine/version will not be
  1500 on another. **Nodes give reproducible *ordering* on the same box, not a
  portable Elo.**

## The style problem — the deeper reason equal Elo ≠ equal human

Even if a Stockfish setting scored exactly like a human 1500 in a match, it does
not **play** like a human 1500. Weakened Stockfish still calculates cleanly, then
occasionally injects a random-ish weak move; a human 1500 has *systematic*
weaknesses (misjudges pawn structure, misses back-rank ideas, mishandles
specific endgames). This is why move-matching studies find attenuated Stockfish
matches human moves poorly: **only ~35–40%** of the time, vs Maia's ~50%+ (see
[honest-bot-rating-assignment.md](honest-bot-rating-assignment.md) and
`../human-play-modeling/`). [Maia KDD 2020 — CSSLab blog](http://csslab.cs.toronto.edu/blog/2020/08/24/maia_chess_kdd/)
The upshot: a "1500" weakened-SF bot can feel simultaneously *too strong*
(crushing calculation for 40 moves) and *too weak / weird* (one absurd blunder),
which is exactly the complaint pattern users report about chess.com bots
(see [honest-bot-rating-assignment.md](honest-bot-rating-assignment.md)).

## Known error direction and size vs human ratings

Evidence is anecdotal/community-sourced, not a controlled study — **flag as
soft**, but the direction is consistent:

- **Chess.com's own community consensus:** bot ratings are **increasingly
  inflated at higher levels** — beginner/intermediate bots are "quite accurate,"
  but master-level bots play **~200–300 points below** their label; a coach
  quoted "most bots are 100–150 points lower than shown." ⚠ (Community/blog
  consensus, not a study.) [Are Chess.com Bots' Ratings Accurate? — chess.com
  blog](https://www.chess.com/blog/AdviceCabinet/are-chess-com-bots-ratings-accurate);
  [chess.com forum threads](https://www.chess.com/forum/view/general/are-the-bot-characters-elo-ratings-accurate)
- **Low-rated bots feel *too strong in calculation but too blunder-prone* to be
  a coherent human of that rating** — 1000–1200 bots "still hang pieces and
  blunder a lot when an actual 1000 rarely would." ⚠ (Forum consensus.)
  [chess.com forum](https://www.chess.com/forum/view/for-beginners/do-bots-have-an-accurate-rating)

**Net takeaway for us:** treat any Stockfish-setting-derived Elo as accurate to
**no better than ±100–200 points** against a human ladder, with a bias toward
*overstating* strength at the top of the range, and with a *style* mismatch that
no single number captures. This is the evidence base for preferring
human-anchored models (Maia) and honest fuzzy labels, per
[honest-bot-rating-assignment.md](honest-bot-rating-assignment.md).

## Sources

- [Stockfish PR #2225 — UCI_Elo implementation & calibration (primary)](https://github.com/official-stockfish/Stockfish/pull/2225)
- [Stockfish UCI & Commands wiki — Skill Level, UCI_LimitStrength, UCI_Elo](https://github.com/official-stockfish/Stockfish/wiki/UCI-&-Commands)
- [UCI_Elo min/max (1320–3190) — Stockfish discussion #4434](https://github.com/official-stockfish/Stockfish/discussions/4434)
- [Node-budget strength tests — MeloniMarco](https://www.melonimarco.it/en/2021/03/08/stockfish-and-lc0-test-at-different-number-of-nodes/)
- [Node equivalence / hardware dependence — TalkChess](https://talkchess.com/viewtopic.php?t=83654)
- [Maia KDD 2020 — attenuated Stockfish move-match ~35–40% (CSSLab blog)](http://csslab.cs.toronto.edu/blog/2020/08/24/maia_chess_kdd/)
- [Are Chess.com Bots' Ratings Accurate? — chess.com blog (soft, community)](https://www.chess.com/blog/AdviceCabinet/are-chess-com-bots-ratings-accurate)
