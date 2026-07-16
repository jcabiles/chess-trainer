# Honest bot-rating assignment — the least-problematic path

Given that no Stockfish knob gives a human-anchored Elo (see
[engine-elo-vs-human-elo.md](engine-elo-vs-human-elo.md)), how do we put a rating
label on each bot that *means* what it says — or at least fails honestly? This
note ranks the assignment strategies, describes how other apps label bots, and
gives cheap local validation procedures. Feeds slice **B1** (research spike) and
**B4** (monotonic ladder probe).

## The design stance: a labeled ladder, not a precision claim

The single most important decision: **decide up front whether the bot number is
a *claim* ("this bot is 1200 Elo") or a *label* ("plays around 1200 / beginner
tier").** The evidence says a precision claim cannot be honestly backed to better
than ±100–200 points against a human ladder (see engine-elo note). So the
honest framings are:

- **Fuzzy label** — "~1200" or "Beginner (≈1000–1300)". Sets expectations the
  system can actually meet. Cheapest and most defensible.
- **Human-anchored model** — use Maia, whose rating bands *are* derived from
  human play, so a "1500" means "plays like lichess 1500s do." Strongest honesty,
  most infrastructure.
- **Calibration-validated** — assign a number, then verify it locally against
  known-strength references and adjust. Effortful; still ends in a fuzzy band.

These are not exclusive: the recommended path is **Maia for the human-like
tiers + fuzzy labels everywhere + a cheap local validation gate** (below).

## Option A — Maia rating bands as human-anchored ground truth (strongest)

Maia is an AlphaZero-style network **trained to predict the move a human of a
given rating actually played**, not to play optimally. Nine models were trained,
one per 100-point lichess rating bin from **1100 through 1900** (Maia 1100 …
Maia 1900); each training set held **~12M games** from its bin. [Maia KDD 2020 —
CSSLab blog](http://csslab.cs.toronto.edu/blog/2020/08/24/maia_chess_kdd/);
[Maia paper (Toronto)](https://www.cs.toronto.edu/~ashton/pubs/maia-kdd2020.pdf)

Why this is the honest anchor:

- **The band label is defined by human data.** "Maia 1500" is fit on games by
  ~1500-rated lichess players, so its *label* is human-anchored by construction —
  unlike `UCI_Elo`'s engine-pool anchor.
- **It demonstrably plays *like* that rating, not just *at* it.** Each Maia model
  reaches its **peak move-matching accuracy at its own training rating** — the
  defining property that "every version captures a specific human skill level."
  Peak is **>52%** (Maia 1900 predicting 1900s); the *worst* Maia still matches
  **46%** of human moves — higher than the *best* attenuated Stockfish or Leela,
  which top out around **35–40%**. [CSSLab blog](http://csslab.cs.toronto.edu/blog/2020/08/24/maia_chess_kdd/)
- **Maia targets can span 600–2600 on the lichess scale** in the deployed
  lichess bots, though the *published academic* models are the 1100–1900 bins. ⚠
  (The 600–2600 range is from Maia's lichess-bot deployment description, broader
  than the 9 published bins — treat sub-1100 / super-1900 as less rigorously
  band-validated.) [maiachess.com](https://www.maiachess.com/)

**Caveats / costs for us:** Maia needs a neural-net runtime (Leela/lc0-style or
the Maia weights via a supported engine), which is heavier than shelling out to a
Stockfish binary and does **not** fit the current "one Stockfish process" engine
seam (`app/engine.py`). It also only covers the **middle** of the ladder well
(≈1100–1900 with rigor). This is an engine-integration question →
`../engine-adaptation/`; here we only assert Maia is the best *rating anchor*.

## Option B — published SF-setting ↔ human-Elo equivalence attempts (weak)

Various community tables try to map `Skill Level` or node budgets to a human Elo.
They are all derived against **engine pools or one author's own play** and
inherit every problem in the engine-elo note (engine-pool anchor, hardware
dependence, style mismatch). Usable only as a **rough starting guess** for a
band you then validate locally. ⚠ (No authoritative human-anchored table exists;
UCI_Elo's own basis is CCRL/engine, per PR #2225.)

## Option C — calibration matches (bot vs bot / vs known-strength opponents)

Run games between your bots and **reference opponents of known human-anchored
strength** (e.g. Maia bins, or lichess's own bots), compute relative Elo from
results (as Ordo/Elo would). This *transfers* a human anchor onto a
Stockfish-based bot without trusting `UCI_Elo`. Same method Stockfish used
internally (PR #2225), but anchored to a *human-derived* reference instead of
CCRL. Effortful but the most defensible way to put a number on a non-Maia bot.

## Option D — anchor to lichess/chess.com bot ratings "in the wild"

Borrow the labels those platforms already ship — but **discount them**, because:

- **Chess.com bots** use Dragon (an engine) with strength-reducing parameters
  and are widely reported **inflated at higher levels** (~200–300 pts below
  label for masters; a coach's rule of thumb "100–150 lower than shown"), with
  low bots that blunder in un-human ways. [Are Chess.com Bots' Ratings Accurate?](https://www.chess.com/blog/AdviceCabinet/are-chess-com-bots-ratings-accurate);
  [chess.com forums](https://www.chess.com/forum/view/general/are-the-bot-characters-elo-ratings-accurate)
- **Lichess** hosts many bots: **Maia** (human-anchored, best label quality) and
  **Fairy-Stockfish / Stockfish-level bots** (engine-anchored, e.g. Fairy-Stockfish
  carries a lichess *play-derived* Glicko rating ~2502 because it actually *played
  rated games* on the site). [Lichess bots list](https://lichess.org/player/bots)
  Note the important distinction: a lichess bot's displayed rating is often its
  **actual Glicko-2 rating earned by playing humans**, which is a genuinely
  human-anchored number — better than any `UCI_Elo` self-label.

**Takeaway:** the honest anchors, best to worst — (1) a rating *earned by playing
rated games against humans* (lichess bot ratings, Fairy-Stockfish), (2) Maia band
labels (human-trained), (3) calibration matches vs those, (4) discounted
platform bot labels, (5) `UCI_Elo`'s self-label (engine pool — weakest).

## How other apps label honestly (patterns to copy)

- **Lichess** leans on either **real earned Glicko-2 ratings** (bots that played
  humans) or **human-trained Maia bands** — both human-anchored. [Lichess bots](https://lichess.org/player/bots)
- **Chess.com** attaches *named personas* with rating labels and leans on the
  *persona / difficulty* framing, accepting that the number is approximate;
  community and their own blog openly acknowledge the labels drift. [chess.com
  blog](https://www.chess.com/blog/AdviceCabinet/are-chess-com-bots-ratings-accurate)
- **Pattern worth stealing:** present a **tier + fuzzy number** ("Beginner ·
  ~1000") rather than a bare precise Elo, and let the user's *own* results
  (slice B8) refine which bot "feels right" over time.

## Validating a bot's claimed rating — cheap local procedures

These need **no human data** and run on the box we already have:

1. **Monotonic ladder probe (slice B4).** Play each adjacent pair of bots a fixed
   number of games (e.g. bot_N vs bot_N+1, ≥ ~50 games each color-balanced). The
   *only* hard requirement to ship is that **the higher-labeled bot scores > 50%
   against the lower one, monotonically up the ladder.** If the ladder isn't even
   monotonic, the labels are meaningless regardless of absolute accuracy. This is
   cheap, deterministic, and catches the worst failures. (Method mirrors
   Stockfish/Ordo's own relative-Elo validation, PR #2225.)
2. **Relative-Elo spacing check.** From the same round-robin results, compute
   relative Elo (Elo expected-score inversion) and confirm the *gaps* roughly
   match the label gaps (a "1200" and "1400" should show ≈200 pts of separation,
   not 500 or 50). Flags compressed/stretched ladders.
3. **Anchor one rung to a human-derived reference.** Play the ladder against one
   **Maia bin or a lichess bot of known human-earned rating**; that single
   external tie-point converts the internally-consistent ladder into a
   human-anchored one (Option C, minimal form).
4. **Play-vs-user drift (slice B8, over time).** As the user racks up games, the
   user's Glicko-2 estimate (see [rating-systems-math.md](rating-systems-math.md))
   and their win-rate per bot are a *live* calibration signal: if the user is a
   confirmed 1300 but crushes the "1400 bot" 80%, the bot label is too high —
   surface this and optionally auto-adjust the bot's displayed band. This closes
   the loop without ever needing an external human ladder.

**Recommended ship gate:** require **#1 (monotonic)** to pass before shipping any
ladder; treat **#2–#4** as calibration refinements. Present all bot numbers as
**fuzzy bands** until #3 or #4 gives an external anchor.

## Sources

- [Maia KDD 2020 — CSSLab blog (bins, 12M games, peak >52%, worst 46% vs SF 35–40%)](http://csslab.cs.toronto.edu/blog/2020/08/24/maia_chess_kdd/)
- [Maia paper (Toronto, primary PDF)](https://www.cs.toronto.edu/~ashton/pubs/maia-kdd2020.pdf)
- [maiachess.com — Maia targets 600–2600 on lichess scale](https://www.maiachess.com/)
- [Lichess bots list — Maia + Fairy-Stockfish earned ratings](https://lichess.org/player/bots)
- [Are Chess.com Bots' Ratings Accurate? — chess.com blog (inflation, discounts)](https://www.chess.com/blog/AdviceCabinet/are-chess-com-bots-ratings-accurate)
- [Stockfish PR #2225 — relative-Elo/Ordo validation method (reused for probe)](https://github.com/official-stockfish/Stockfish/pull/2225)
