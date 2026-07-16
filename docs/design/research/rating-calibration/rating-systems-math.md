# Rating-system math — Elo, Glicko-2, and the per-game update

What a rating system needs to do for us: take **game results** (win/draw/loss)
against opponents of known strength (the bots) and maintain an **estimate of the
user's playing strength** that improves as more games come in. This note covers
the math; the *bot-side* problem (are the bots' ratings honest?) lives in
[engine-elo-vs-human-elo.md](engine-elo-vs-human-elo.md) and
[honest-bot-rating-assignment.md](honest-bot-rating-assignment.md).

Feeds roadmap slice **B8** (personal ELO estimate). See also
`../../../ai-dlc/contracts/game-accuracy-elo.md` for the *existing* per-game
accuracy→Elo heuristic, and [reconciling-with-accuracy-elo.md](reconciling-with-accuracy-elo.md)
for how the two estimates should coexist.

## Elo — the baseline

**Expected score.** Against an opponent rated `R_opp`, a player rated `R` is
expected to score

```
E = 1 / (1 + 10^((R_opp - R) / 400))
```

`E` is a number in [0,1] read as expected fraction of a point (win=1, draw=0.5,
loss=0). The `400` constant means a 400-point gap ≈ 10:1 expected score. [Elo
rating system — Wikipedia](https://en.wikipedia.org/wiki/Elo_rating_system)

**Per-game update.** After a game with actual score `S` (1/0.5/0):

```
R' = R + K * (S - E)
```

`(S - E)` is the surprise: beating a stronger opponent (`S > E`) raises your
rating; losing to a weaker one lowers it. [Elo rating system —
Wikipedia](https://en.wikipedia.org/wiki/Elo_rating_system)

**K-factor** controls how fast the rating moves. FIDE uses **K=40** for new
players (first 30 rated games), **K=20** while rating < 2400, and **K=10** at
2400+. The idea: move fast while the estimate is uncertain, slow down once it
has settled. [FIDE rating rules, via
shatranj.live](https://www.shatranj.live/blogs/fide-rating-system-explained)

**What Elo lacks.** Plain Elo carries a *point estimate only* — no explicit
uncertainty. It cannot distinguish "1400, confirmed over 200 games" from "1400,
first game ever." The K-factor tiers are a crude proxy for uncertainty (games
played), but they don't decay with **inactivity** and don't widen after an
upset. For a single-user app where the user may play in bursts and where each
bot opponent's true rating is itself fuzzy, this matters. ⚠ (Judgment call, not
a cited fact — but it follows directly from the Elo update having no variance
term.)

## Glicko / Glicko-2 — Elo plus an uncertainty term

Glicko (Mark Glickman) extends Elo by tracking, per player, a **rating deviation
(RD)** — the standard deviation of the rating estimate. Low RD = confident
rating; high RD = uncertain. Glicko-2 adds a third quantity, **volatility (σ)**,
capturing how erratically the player's *true* skill has been changing. [Glicko
rating system — Wikipedia](https://en.wikipedia.org/wiki/Glicko_rating_system);
[Glickman, "Example of the Glicko-2 system"
(PDF)](https://glicko.net/glicko/glicko2.pdf)

The three quantities per player: rating mean **μ**, rating deviation **φ** (=RD
on the internal scale), volatility **σ**. After each *rating period* all three
are updated jointly using closed-form Gaussian approximations. [Glickman
Glicko-2 paper (PDF)](https://glicko.net/glicko/glicko2.pdf)

**Why RD matters for us:**
- **Provisional handling is built in.** A high RD *is* the provisional flag —
  no separate "first 30 games" rule needed. Lichess shows a `?` next to a rating
  whenever Glicko-2 RD > 110, and requires RD < 75 to appear on leaderboards.
  [Lichess FAQ](https://lichess.org/faq)
- **Uncertainty shrinks with games and grows with inactivity.** Lichess starts
  new players at **1500 with a wide interval (displayed 1500 ± 1000)**; the
  interval narrows as they play and re-widens over idle time so a returning
  player's rating can move faster. [Lichess FAQ](https://lichess.org/faq)
- **Update size scales with RD automatically** — effectively a self-tuning
  K-factor. A confident (low-RD) rating barely moves on one result; an uncertain
  one moves a lot. This replaces the hand-picked K tiers of Elo. [Glicko —
  Wikipedia](https://en.wikipedia.org/wiki/Glicko_rating_system)

**Both major chess sites use a Glicko variant, not raw Elo:** Lichess uses
Glicko-2, chess.com uses a Glicko-based system. Neither uses FIDE-style fixed-K
Elo for online play. [Lichess FAQ](https://lichess.org/faq); FIDE-vs-online note
per the K-factor search above.

## Glicko-2 rating periods vs. per-game updates — a real gotcha

Glicko-2 is defined over a **rating period** containing *several* games, and
Glickman recommends tuning the period so it holds **10–15 games on average**;
the volatility math is derived under that batching assumption. [Glickman
Glicko-2 paper (PDF)](https://glicko.net/glicko/glicko2.pdf) A single-user app
that wants a *live per-game* estimate has two honest options:

1. **Period = 1 game** (update after every game). Works, and is what many game
   implementations do, but the volatility estimate is noisier than the paper's
   design point. ⚠ (Widely done in practice, e.g. game-server Glicko-2 libraries;
   the noise cost is qualitative, I did not find a quantified error figure.)
2. **Batch a session's games into one rating period.** Closer to the paper's
   intent; the rating only updates at session end. Less "live."

## Recommendation for B8 (single-user, games vs. bots)

**Use Glicko-2, updated once per session (or per game with a widened
volatility), not fixed-K Elo.** Reasoning:

- The user plays in bursts and against opponents whose ratings are *themselves
  uncertain* (see engine-elo note). An explicit RD is exactly the tool for "I'm
  not sure yet" — it lets early estimates swing and later ones stabilize without
  a magic games-played threshold.
- It matches what the user already sees on lichess/chess.com, so the number is
  legible to them.
- It gives a **confidence interval to display** ("~1350 ± 120"), which is far
  more honest than a bare number given the bot-rating uncertainty upstream.

**If a minimal Elo is preferred for a first cut**, use **K=32** (a common online
default) but *widen it (e.g. K=40–60) for the first ~10–20 games* to mimic
provisional behavior, and **flag the estimate as provisional** until enough
games accumulate. This is a poor-man's RD and should be labeled as approximate.
⚠ (K=32 default and the provisional-widening are common engineering practice,
not a single authoritative citation.)

**Non-negotiable regardless of system:** the *input* to any update is
**opponent rating + game result**. If the bot's own rating is off by 150 points
(very plausible — see engine-elo note), the user's estimate inherits that bias.
Track and surface uncertainty; do not present the number as precise.

## Sources

- [Elo rating system — Wikipedia](https://en.wikipedia.org/wiki/Elo_rating_system)
- [Glicko rating system — Wikipedia](https://en.wikipedia.org/wiki/Glicko_rating_system)
- [Glickman, "Example of the Glicko-2 system" (PDF, primary source)](https://glicko.net/glicko/glicko2.pdf)
- [Lichess FAQ — Glicko-2, RD>110 provisional, RD<75 leaderboard, 1500±1000 start](https://lichess.org/faq)
- [FIDE K-factor rules (40/20/10) — shatranj.live](https://www.shatranj.live/blogs/fide-rating-system-explained)
