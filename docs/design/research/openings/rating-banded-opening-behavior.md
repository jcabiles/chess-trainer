# Rating-banded opening behavior

Scope: what openings real humans actually play at sub-1600 ratings, and when
they leave book theory. This is the evidence base that `sub-1600-opening-catalog.md`'s
"suggested bot-book weight" notes lean on, and that `bot-opening-books.md`'s
exit-depth guidance leans on. See both for how this data should be *used*;
this note is the *evidence*.

## Data source: lichess Opening Explorer

The [lichess Opening Explorer](https://lichess.org/opening) exposes a public
JSON API (`explorer.lichess.ovh` / documented under
[lichess.org/api](https://lichess.org/api) → Opening Explorer) that supports:
- `ratings=` — a comma-separated list of rating-bucket floors. Confirmed
  buckets: `0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500` (each bucket
  spans "this value to the next higher group" per the lichess feedback forum
  thread cited below) — i.e. `ratings=1000,1200,1400` pools games played by
  either side rated in `[1000,1200)`, `[1200,1400)`, `[1400,1600)`.
  ⚠ **This app's target band is "sub-1600," so the correct query is
  `ratings=0,1000,1200,1400` to cover everything below 1600, NOT
  `ratings=1000,1200,1400` (which excludes 0-1000 and stops at 1400, not
  1600). Any prior mention of `ratings=1000,1200,1400` elsewhere (e.g. the
  scope brief this note was commissioned under) undercounts the low end —
  use `ratings=0,1000,1200,1400` for sub-1600 popularity queries.**
- `speeds=` — game speed filter (`bullet,blitz,rapid,classical,...`).
- `play=` — a comma-separated UCI move sequence locating the position to
  query (e.g. `play=e2e4,e7e5,g1f3`).
- Response shape (per the API and general opening-explorer conventions):
  `white`/`draws`/`black` game-count totals for the position, plus a `moves[]`
  array of candidate next moves each with `uci`, `san`, and its own
  `white`/`draws`/`black` counts — popularity % for a move = its count / sum
  of all moves' counts at that node.

⚠ **Verification gap, disclosed rather than papered over**: this research
pass could not execute live queries against `explorer.lichess.ovh` — the
sandboxed fetch tool returned HTTP 401 on the raw JSON endpoint (likely a
non-browser-UA block on this environment's fetch proxy), and `curl` to that
host is outside this environment's network allowlist. **No specific
move-popularity percentage in this note or in `sub-1600-opening-catalog.md`
should be treated as a live-verified explorer number** — every percentage
below is sourced from secondary write-ups that themselves cite the explorer,
not from a query this agent ran directly. The exact `play=` query that
*should* be run once explorer access is available is given inline at each
finding below, so the build phase (or a future research pass with network
access) can re-run and confirm/correct these numbers before they drive book
weights. Treat every percentage in this note as ⚠ pending-verification even
where not individually re-flagged.

## Findings

### First-move split (1.e4 vs 1.d4) at sub-1600
No specific first-move percentage split for the 0-1600 band was found via a
secondary source in this pass. ⚠ Needs a direct explorer query:
`ratings=0,1000,1200,1400&play=` (empty play = starting position) once
network access is available. General secondary-source consensus (not
percentage-cited) is that 1.e4 is the more common first move at low ratings
because it leads to faster, more tactical games that beginners gravitate
toward, while 1.d4 systems (London especially) are recommended *to* beginners
by content creators for their low theory burden — these are two different
claims (what beginners naturally play vs what they're told to play) and
shouldn't be conflated. Flagging both as directional, not quantified.

### Fried Liver Attack peaks at 1200-1400
"The Fried Liver peaks at 1200-1400 ELO (74%)" per a secondary aggregator
source (see below) — read as: among games reaching the Fried Liver tabiya,
White's practical results peak in that band, not that 74% of games *are* Fried
Livers. This overlaps `opening-traps.md` A4 (Fried Liver Attack, sound
attacking compensation, not a forced mate) — that note covers the trap/tactics
angle; this note is flagging it only as a rating-popularity data point for
book-weighting. Source: [MyChessPosters — Best white Chess Opening by
Rating](https://mychessposters.com/best-white-chess-opening-by-rating/). ⚠
Secondary source, not explorer-verified directly — re-run
`ratings=1200,1400&play=e2e4,e7e5,g1f3,b8c6,f1c4,g8f6,g1g5` (post-4.Ng5) to
confirm.

### Two Knights 4.Ng5: sub-1600 opponents often misdefend
At ~1000 ELO, only **47.61%** of players find the correct `4...d5` reply to
`4.Ng5` in the Two Knights Defense (Fried Liver tabiya); the majority
(52.39%) play an inferior move that hands White a significant advantage, and
`4.Ng5`'s practical win rate falls from a sub-1600 peak to 54% at 1400-1600
and 51% at 1800+. Source: [MyChessPosters — Two Knights Defense 4.Ng5 Crushes
at 1000 ELO](https://mychessposters.com/two-knights-defense-ng5-1000-elo/).
This is a concrete, citable **rating-dependent correctness curve** (not just
popularity) — directly useful for a bot book: a ~1000-1200 persona playing
White into `4.Ng5` is playing a rating-plausible *and* practically strong
choice; the same line is progressively worse-and-less-plausible as the
target persona rating climbs past 1600. ⚠ Secondary source; treat the exact
percentage as pending-verification, but the *direction* (sub-1600 opponents
frequently misdefend 4.Ng5) is corroborated by the independent "beginners
should learn the Fried Liver defense" advice-genre content found across
multiple search results in this pass.

### Queen's Gambit reaches ~57% for White by 1400-1600
"By 1400-1600, the Queen's Gambit (1.d4 2.c4) overtakes tactical 1.e4 lines
with 57%" per the same MyChessPosters source. Read cautiously: this reads as
a practical-results percentage (White's score), not a play-frequency
percentage, and the source bundles "Queen's Gambit" without distinguishing
Declined/Accepted/Slav. ⚠ Needs disambiguation + explorer re-verification
before use as a book weight; see `sub-1600-opening-catalog.md`'s QGD entry for
the master-level Slav/QGD/QGA split (50/34/12), which is a *different*,
better-sourced statistic (Wikipedia-cited, but for masters, not sub-1600 —
the two numbers answer different questions and neither substitutes for the
other).

### When low-rated players leave book
No peer-reviewed statistical study was found (this pass searched explicitly
for one and came up short — flagging the absence rather than guessing).
Community consensus from lichess/chess.com forum threads, several independent
threads in this pass: players rated below ~1000 "frequently play book
openings but only for 1 to 4 moves," and deviation "will happen within the
first 5-10 moves, if not earlier" for inexperienced players generally.
Sources: [lichess forum — Solid openings requiring less theory for low
ranked](https://lichess.org/forum/general-chess-discussion/solid-openings-requiring-less-theory-for-low-ranked),
[chess.com forum — deviating from opening lines](https://www.chess.com/forum/view/chess-openings/deviating-from-opening-lines).
⚠ Anecdotal/forum-sourced, not a dataset — but directionally consistent
across independent threads, and consistent with the Two Knights 4.Ng5 finding
above (a well-known, heavily-taught trap line is *still* misplayed by >50% of
~1000-rated players at move 4). **Practical implication for
`bot-opening-books.md`'s exit-depth guidance**: a sub-1600-plausible bot book
should treat move 4-8 as the realistic point where book-depth should start
thinning into probabilistic/shallow territory, not stay deep-and-deterministic
through move 12-15 the way a strong-player book would.

### Recommended low-theory openings (advice-genre, not popularity data)
Multiple independent sources converge on a "starter repertoire" advice set for
1200-1500: **London System or Italian Game** (White), **Caro-Kann** (Black vs
1.e4), **Slav or QGD** (Black vs 1.d4) — valued for low theory burden and
consistent resulting structures, not for being what beginners already play.
Source: [CheckmateX — Best Chess Opening Repertoire for 1200-1500
ELO](https://checkmatex.app/blog/best-chess-opening-repertoire-1200-1500-elo).
Treat this as a *different signal* from "what sub-1600 players actually play"
(the explorer-style data above) — advice content shapes what improving players
adopt, but doesn't equal current-population popularity. Both signals are
useful for bot-book design for different reasons: actual-popularity data
makes a bot's *opponent modeling* realistic; advice-genre data is a proxy for
what a *rising* sub-1600 player's book increasingly looks like as they study.

## What this means for book weighting (cross-ref `bot-opening-books.md`)
- Popularity-based weights should ideally come from live explorer queries at
  the `ratings=0,1000,1200,1400` band (not yet executed — see verification
  gap above), not from this note's secondary-sourced percentages.
- Until live-verified, treat every percentage here as a **directional prior**
  suitable for rough weight ordering (e.g. "London/Italian more common than
  Scotch at this band" is safe to act on; "exactly 57%" is not).
- The one quantitatively strongest finding (Two Knights 4.Ng5 sub-1600
  misdefense rate) is still secondary-sourced but is corroborated by
  independent advice-genre consensus and is specific enough to be worth a
  targeted re-verification query before shipping.

## Sources
- [Lichess Opening Explorer](https://lichess.org/opening) and [lichess.org/api](https://lichess.org/api) (Opening Explorer endpoints) — API shape, not independently queried this pass (see verification gap).
- [Lichess feedback forum — Opening explorer API not filtering by rating?](https://lichess.org/forum/lichess-feedback/opening-explorer-api-not-filtering-by-rating) — confirms rating bucket values (0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500).
- [MyChessPosters — Best white Chess Opening by Rating](https://mychessposters.com/best-white-chess-opening-by-rating/) — Fried Liver 1200-1400 peak, Queen's Gambit 57% by 1400-1600. ⚠ secondary source.
- [MyChessPosters — Two Knights Defense 4.Ng5 Crushes at 1000 ELO](https://mychessposters.com/two-knights-defense-ng5-1000-elo/) — 47.61% correct-defense rate at 1000 ELO. ⚠ secondary source.
- [Lichess forum — Solid openings requiring less theory for low ranked](https://lichess.org/forum/general-chess-discussion/solid-openings-requiring-less-theory-for-low-ranked)
- [Chess.com forum — deviating from opening lines](https://www.chess.com/forum/view/chess-openings/deviating-from-opening-lines)
- [CheckmateX — Best Chess Opening Repertoire for 1200-1500 ELO](https://checkmatex.app/blog/best-chess-opening-repertoire-1200-1500-elo)
- [Wikipedia — Queen's Gambit Declined](https://en.wikipedia.org/wiki/Queen's_Gambit_Declined) — master-level Slav/QGD/QGA split (50/34/12), cited for contrast, not as a sub-1600 number.
