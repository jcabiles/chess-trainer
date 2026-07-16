# Stockfish weakening mechanics

How Stockfish plays below full strength: `Skill Level`, `UCI_LimitStrength`/
`UCI_Elo`, and raw search caps (nodes/depth/movetime). Verified against
Stockfish master source (fetched 2026-07-16). See
`second-engine-process-patterns.md` for how these interact with this repo's
single shared engine; see `../human-play-modeling/` for what *human* errors
look like (the contrast is the point of this note).

## Skill Level — the exact mechanism

`Skill Level` is a spin option 0–20; 20 = disabled. The whole feature lives in
a small `Skill` struct plus three hooks in the search
([search.h](https://github.com/official-stockfish/Stockfish/blob/master/src/search.h),
[search.cpp](https://github.com/official-stockfish/Stockfish/blob/master/src/search.cpp)):

```cpp
struct Skill {
    constexpr static int LowestElo  = 1320;
    constexpr static int HighestElo = 3190;

    Skill(int skill_level, int uci_elo) {
        if (uci_elo) {
            double e = double(uci_elo - LowestElo) / (HighestElo - LowestElo);
            level = std::clamp((((37.2473 * e - 40.8525) * e + 22.2943) * e - 0.311438), 0.0, 19.0);
        } else
            level = double(skill_level);
    }
    bool enabled() const { return level < 20.0; }
    bool time_to_pick(Depth depth) const { return depth == 1 + int(level); }
    ...
};
```

Three hooks in the iterative-deepening loop:

1. **MultiPV is silently forced to ≥ 4** when skill is enabled:
   `multiPV = std::max(multiPV, usize(4));` — the engine searches (at least)
   its top four candidate moves fully.
2. **The move is picked at a shallow depth.** `time_to_pick(depth)` fires when
   the root depth equals `1 + int(level)` — Skill 0 picks its move from a
   **depth-1** search, Skill 10 from depth 11. Search may continue deeper for
   time-management purposes, but the choice is frozen from the shallow
   iteration (if search stops before that depth, `pick_best` runs at the end
   over whatever scores exist).
3. **`pick_best` = weighted random choice among the top-`multiPV` moves.**
   With RootMoves sorted by score descending:

   ```cpp
   double weakness = 120 - 2 * level;
   int delta = std::min(topScore - minScore, int(PawnValue));
   // for each of the multiPV candidates:
   int push = int(weakness * int(topScore - rootMoves[i].score)
                  + delta * (rng.rand<unsigned>() % int(weakness))) / 128;
   // move with highest (score + push) is chosen
   ```

   Two terms: a deterministic one that boosts a move *proportionally to how
   much worse it is than the top move* (flattening the score gaps — more so at
   lower levels, since `weakness` grows as level falls), plus a uniformly
   random term of up to roughly `delta * weakness / 128` ≈ **~0.9 pawns of
   pure noise at Skill 0** (delta capped at PawnValue). The picked move is then `std::swap`ped to
   `rootMoves[0]` before `bestmove` is emitted.

Sources: [search.h (master)](https://github.com/official-stockfish/Stockfish/blob/master/src/search.h),
[search.cpp (master)](https://github.com/official-stockfish/Stockfish/blob/master/src/search.cpp),
["Simplify Skill implementation" commit ef4822a](https://github.com/official-stockfish/Stockfish/commit/ef4822aa8d5945d490acca674eb1db8c3c38e9d5).

### Why low levels feel "random, not human"

The mechanism explains the widely reported feel directly:

- Errors are **uniform noise injected at move-choice time**, not systematic
  misjudgments. There is no concept of an overlooked tactic, a missed hanging
  piece, or time pressure — a blunder is just the RNG term outweighing a score
  gap among the top 4 root moves.
- The candidate set is only the **top-4 MultiPV moves of a real (if shallow)
  search**, so even Skill 0 rarely plays the kind of 5th-rank lunacy or
  one-move piece hangs low-rated humans play — but the shallow pick depth means
  it also fails to *punish* opponent blunders it "can't see" at depth 1–3.
  The combination reads as passive, aimless shuffling punctuated by unmotivated
  errors. ⚠ interpretive framing (mechanism-derived); user reports agree:
  [lichess: "Why is Stockfish Level 5 blunder pieces like this?"](https://lichess.org/forum/general-chess-discussion/why-is-stockfish-level-5-blunder-pieces-like-this),
  [TalkChess: "Stockfish strength level"](https://talkchess.com/forum3/viewtopic.php?t=64963).
- Every error is **causeless** — this is precisely the property the bots epic's
  "causal, never random blunders" requirement rejects. Skill Level can set the
  error *rate*, never the error *shape* (that's `../human-play-modeling/`
  territory).

## UCI_LimitStrength / UCI_Elo — what the Elo actually means

`UCI_LimitStrength=true` + `UCI_Elo=N` does **nothing but map N onto the same
fractional Skill Level** via the cubic in the constructor above (range
1320–3190 → level 0.0–19.0). There is no separate time/nodes throttling in the
current implementation — it is Skill Level with finer granularity.

Calibration ([commit a08b8d4 "Update UCI_Elo parameterization"](https://github.com/official-stockfish/Stockfish/commit/a08b8d4)):

- Derived from **~140k games between Stockfish at skill levels 0–19 and the
  Stash engine**, fitted with a 3rd-degree polynomial.
- Calibrated **at time control 120s+1s**, anchored (±100 Elo) to **CCRL Blitz**
  (formerly "CCRL 40/4") — an *engine-pool* rating list.
- Range widened at that time from 1350–2850 to **1320–3190**.
- History: the original implementation ([PR #2225](https://github.com/official-stockfish/Stockfish/pull/2225),
  [PR #393](https://github.com/official-stockfish/Stockfish/pull/393)) used a
  60s+0.6s anchor; recalibrations happen across releases
  ([issue #3101](https://github.com/official-stockfish/Stockfish/issues/3101)).

### Trustworthiness at 1300–1700 (the app's target band)

- **1320 is the hard floor** — you cannot request weaker via UCI_Elo. The band
  the app most needs (≈1000–1500 human-online-rating opponents) starts *below*
  or *at* the floor.
- CCRL Blitz Elo is **not FIDE, not lichess, not chess.com** rating. These
  pools are offset from each other by hundreds of points and non-linearly;
  a "1400 UCI_Elo" Stockfish does not reliably play like a 1400 lichess human.
  ⚠ No rigorous published mapping from UCI_Elo to online human ratings found;
  treat any equivalence as folklore.
- Calibration holds at 120s+1s. At this app's cadence (fast per-move budgets,
  no clock) effective strength shifts; the shift is unquantified. ⚠
- Because UCI_Elo is *only* fractional Skill Level, **all the "random, not
  human" criticisms above apply unchanged** at every Elo setting.

## Raw search caps (nodes / depth / movetime)

Capping the search directly (e.g. `go depth 3`, `go nodes 500`) weakens play
without the Skill randomizer: the engine plays the *best move of a bad search*.
Deterministic, and errors are "horizon" mistakes (can't see past depth N) —
closer to a caricature of weak play than Skill noise, but still not human
(no piece-blindness, perfect tactics within horizon, and fully repeatable).

**Lichess's production recipe combines both.** Its AI levels 1–8 run
Fairy-Stockfish with a skill level *and* a depth cap per level — current
mapping: level 1 = skill −9/depth 5 … level 7 = skill 15/depth 13, level 8 =
full strength/depth 22; an older fishnet used skills [0,3,6,10,14,16,18,20],
depths [1,1,2,3,5,8,13,22], movetimes 50–1000ms
([TalkChess: Stockfish Level Settings on LiChess](https://talkchess.com/viewtopic.php?t=80123),
[TalkChess: What is "Stockfish Level 8" on Lichess?](https://talkchess.com/viewtopic.php?t=77727)).
Notable: **Fairy-Stockfish extends Skill Level to −20…+20** — that's how
lichess gets below official Stockfish's floor for beginner levels; vanilla
Stockfish stops at 0/1320
([TalkChess](https://talkchess.com/viewtopic.php?t=80123)). ⚠ Elo-per-node/depth
scaling curves exist in fishtest/TalkChess lore but no authoritative
citation gathered; don't design against specific numbers.

Interaction gotcha: with Skill enabled, the pick depth is `1 + int(level)` —
if a nodes/time cap stops the search *before* that depth, the pick happens
from even shallower data. Caps and Skill compose, but not linearly.

## Contempt — no longer exists

The `Contempt` UCI option was **removed in June 2021** ([commit ed436a3](https://github.com/official-stockfish/Stockfish/commit/ed436a36bade82422753f8be9c16d790232e9c91));
the team "tried quite hard to implement a working Contempt feature for NNUE
but nothing really worked." It survives only in the archived `SF_Classical`
tag. Modern Stockfish offers no draw-avoidance/style knob — irrelevant to
this epic on current binaries.

## Bottom line for the bots epic

`Skill Level`/`UCI_Elo` give a cheap, zero-install strength dial with a real
(engine-pool) calibration — but the error model is uniform randomness among
4 shallow-searched candidates, the floor is 1320 CCRL, and the Elo scale's
mapping to human online ratings is unverified. Usable as a *strength
substrate*; unusable, alone, as a *human-likeness* mechanism.
