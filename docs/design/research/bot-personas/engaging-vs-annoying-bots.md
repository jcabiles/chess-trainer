# What makes bots engaging vs. annoying — the evidence

This note collects community evidence on the specific complaint that motivates
this epic — chess.com bots making random, inexplicable blunders — and
contrasts it with what players praise about Maia, Chessiverse, HIARCS, and
Chessmaster. The goal: extract *specific, citable* failure and success modes,
not vibes.

## The core complaint: blunders that don't fit the story the bot is telling

Chess.com forum threads converge on the same shape of complaint, independent
of which bot or rating band is discussed: **a bot plays consistently at one
level, then drops a piece or blunders a mate-in-1 for no discernible reason,
and the inconsistency — not the loss itself — is what breaks trust.**

- ["At What Point Do The Chess.com Bots Stop Making Egregious
  Blunders?"](https://www.chess.com/forum/view/game-analysis/at-what-point-do-the-chess-com-bots-stop-making-egregious-blunders)
  — an 800-rated player beats the 1600-rated "Pablo" bot and describes its
  `19. Ng7+?` (a pointless knight sac into a trap) as "entirely pointless" /
  "senseless": *"I as an 800 shouldn't be able to say 'wow, that move the 1600
  just played... was terrible.'"* The complaint isn't that the bot lost — it's
  that a human 1600 would never produce that specific move; it doesn't read
  as a *plausible* mistake for the stated strength.
- ["Why do the bots make weird blunders at
  times"](https://www.chess.com/forum/view/general/why-do-the-bots-make-weird-blunders-at-times)
  — user SpacePodz on the "Isabel" bot: it "usually just makes little
  inaccuracies" but occasionally sacs a queen for a rook with no setup. A
  chess.com moderator (moneywaves) gives the quiet part out loud: **"They are
  programmed to blunder, that's why they 'have' elo."** i.e. confirmation from
  a platform representative that blunder-injection, not weakened search
  alone, is the rating-shaping mechanism — and it's the visible seam players
  are reacting to. SpacePodz's own framing: the swing made the win feel like
  luck, not skill — *"a win doesn't feel earned."*
- ["Bad chess bots (no offense they're kinda stupid at this
  game)"](https://www.chess.com/forum/view/site-feedback/bad-chess-bots-no-offense-theyre-kinda-stupid-at-this-game)
  — a 400-rated player claims to beat 1300-rated bots easily; another example:
  a "2200 Komodo18" bot fails to recapture a piece, drops a pawn, then
  blunders a rook, and post-game analysis shows it actually played that
  stretch at ≈1550 strength. Pattern named directly by a poster: bots "play
  fine in the beginning and then make stupid blunders" in the middlegame —
  i.e. the blunder timing itself looks non-random to players (clusters
  mid-game) even when the mechanism is nominally randomized.
- ["Why are bots always easier to play against than people with the same
  ELO?"](https://www.chess.com/forum/view/general/why-are-bots-always-easier-to-play-against-than-people-with-the-same-elo)
  and ["What real ELO would you assign to the chess.com
  bots?"](https://www.chess.com/forum/view/general/what-real-elo-would-you-assign-to-the-chess-com-bots)
  — recurring theme that the *labeled* rating and the *felt* strength diverge;
  players self-report bots in the 1400-1600 band "feel like 80% of their
  rating," and sub-1400 bots "feel like 50%." ⚠ these are informal
  self-reports on a forum, not a controlled study — treat as directional
  community sentiment, not a calibration curve. (Formal calibration approaches
  live in `../rating-calibration/`.)

**Synthesis — the failure mode is specific, not vague "bots are bad":**
players don't mind bots losing or making mistakes. They mind mistakes that
(a) don't match the *character* of play the bot has shown all game, (b) look
engineered ("programmed to blunder... every so many moves" per one poster) and
(c) are described post-hoc as "random" — meaning **the player cannot construct
a story for why a plausible-strength player would make that move here.** This
directly motivates the persona/error-model requirement: a believable mistake
should be legible as *this persona's kind of mistake* (see
`persona-parameterization.md`), not a context-free RNG event. It's also a
knock against the historically simplest weakening lever — see
`../engine-adaptation/stockfish-weakening.md` for what plain `Skill Level` /
node caps actually do (uniform random-ish move degradation), which is
structurally the same shape of complaint players are describing.

## Resignation behavior: a live, cited complaint (not resolved)

- ["Why chess.com bots never
  resign?"](https://www.chess.com/forum/view/general/why-chess-com-bots-never-resign)
  — OP: *"We still don't have a chess bot that would respectfully resign in a
  lost position"* despite it being, in their view, a trivial feature relative
  to the platform's other AI capabilities. A respondent (EmTat) explains the
  mechanical reason — bots don't have a "want to win," so there's no drive to
  resign — but concedes the player desire: *"it would be cool if chess.com had
  a bot who could resign, propose a draw & stuff."* As of the thread's
  discussion (2025), chess.com bots do **not** resign lost positions or offer
  draws in dead-drawn endgames (e.g., R vs R). Confidence: high that this is
  current community sentiment; see `bot-match-conventions.md` for the design
  recommendation this feeds.

## What Maia gets right (and where even Maia draws skepticism)

- [Lichess: "Introducing Maia, a human-like neural network chess
  engine"](https://lichess.org/@/lichess/blog/introducing-maia-a-human-like-neural-network-chess-engine/X9PUixUA)
  — Maia is trained (not hand-weakened) directly on human game data, nine
  models targeting rating milestones 1100-1900, one net per band. Reported
  headline stat: Maia predicts a human's actual next move up to **53%** of the
  time vs. ~43% for Leela and ~38% for Stockfish (matched for comparable
  strength) — i.e., it is measurably closer to *how* humans err, not just
  *how often*. Cross-reference: `../engine-adaptation/maia-lc0.md` owns the
  mechanics of this; this note only owns the reception evidence.
- [Lichess forum: "Maia Chess: A human-like neural network chess
  engine"](https://lichess.org/forum/general-chess-discussion/maia-chess-a-human-like-neural-network-chess-engine)
  — a representative positive reaction: asked whether Maia plays like a
  human, a poster answers *"for the overwhelming part, yes it does and that's
  absolutely amazing!"*
- Same thread, the critical counter-thread: posters note Maia's opening play
  can be *too* theory-accurate for its band — *"the bots know WAY too much
  theory for their rating"* — citing the Leningrad Dutch, where Maia
  reportedly follows main theoretical lines that real players at that rating
  wouldn't know. This is a concrete, named failure mode distinct from the
  chess.com blunder complaint: **overqualified opening knowledge breaks the
  illusion just as much as underqualified middlegame play does.** Feeds
  `persona-parameterization.md`'s opening-bias section and cross-refs
  `../openings/bot-opening-books.md`. ⚠ single-thread anecdote, not
  quantified — flagged, not verified against actual Maia opening-book stats.
- Also noted in the same discussion: Maia's endgame technique reads as
  unusually precise relative to its human-like middlegame — "quite precise in
  the endgame, though her play is quite human in the middle game" — a
  reminder that human-likeness needs to hold across *all three phases*, not
  just the middlegame where most training signal concentrates.

## What Chessiverse (a 2025-era competitor explicitly copying the
Chessmaster idea) does differently — and names its own design philosophy

Chessiverse is the closest modern analogue to what this epic is building —
persona-labeled bots at scale, explicitly marketed against the "bots feel
fake" complaint.

- [Chessiverse: "How We Build Human-Like Chess
  Bots"](https://chessiverse.com/blog/how-we-build-human-like-chess-bots) —
  names the exact same failure mode chess.com players complain about, and
  proposes a concrete architectural fix: a **"Move Curator"** — a second,
  *stronger* engine pass that reviews the weak persona-engine's candidate move
  and rejects it if it's "unnatural" (their examples: "a reckless king walk or
  an inexplicable piece sacrifice"). Their claim: *"even our weakest bots lose
  in believable ways."* This is the most direct, actionable counter-pattern to
  the "programmed to blunder" complaint above — instead of injecting random
  noise into move selection, filter the *output* of a weakened engine through
  a plausibility check. ⚠ this is Chessiverse's own marketing description of
  their system, not independently verified or benchmarked — treat the
  *design pattern* as credible (it's architecturally sound and directly
  answers the cited complaint) but the specific claim of universal success
  ("even our weakest bots") as unverified marketing copy.
- States explicitly: *"Creating believable weaknesses is harder than creating
  strength"* and that natural mistakes should look like "missing tactical
  patterns or poor endgame judgment — not random piece drops." This is the
  clearest single-sentence design thesis found in this research pass and
  should anchor the error-model work in `persona-parameterization.md`.
- Opening approach offers two modes: curated human-game repertoires per
  rating band, or statistical sampling matching real opening-choice
  frequencies at a rating (their example: French Defense 15%, Sicilian 30% at
  some band). Cross-refs `../openings/bot-opening-books.md` for format/
  sampling mechanics — this note only owns the *why* (matches the "too much
  theory" complaint above).
- Scale claim: 1000+ bots live, roadmap to 30,000-40,000, spanning Elo
  0-3300. ⚠ scale claims unverified beyond their own blog; not load-bearing
  for our design (we don't need thousands of bots), noted only as an
  ambition-scale data point.
- [Chessiverse review on chess.com
  blog](https://www.chess.com/blog/vitualis/chessiverse-review-amazing-600-human-like-chess-ai-bots)
  — third-party (player-authored) review, generally positive tone toward the
  human-like feel and the think-time pacing (see
  `ladder-and-think-time-ux.md`) — corroborates the "feels human" claim from
  outside Chessiverse's own marketing, though it is still a single enthusiast
  review, not a systematic survey. ⚠ flagged as one player's account.

## Chessmaster: the gold-standard reference, sourced

- [Chess.com forum: "Reinventing the wheel: Chessmaster type personalities on
  Chess.com"](https://www.chess.com/forum/view/chess-equipment/reinventing-the-wheel-chessmaster-type-personalities-on-chess-com)
  — the thread that prompted this epic's framing exists organically in the
  community: players already reach for "Chessmaster" and "Kasparov Chess"
  (Game Boy Advance) as the reference point for "personality level systems"
  unprompted, i.e. Chessmaster's reputation as the genre benchmark is a live
  community touchstone, not just a design team's nostalgia. Same thread
  surfaces a modern comparable: **HIARCS** offers 3 style dimensions
  (aggressive / active / solid) crossed with 5 opening-book modes (off / wild
  / surprise / dynamic / tournament) = 15 combinable opponent configurations
  — a smaller, shipped precedent for crossing a style axis with a book-style
  axis. Directly relevant to the persona x opening-bias design in
  `persona-parameterization.md`.
- The actual slider mechanics Chessmaster exposed are documented in
  `persona-parameterization.md` (this note stays scoped to reception/
  reputation evidence; the knob list is parameterization content).
- [Chessmaster 7000 Computer Personality Guide,
  Neoseeker](https://www.neoseeker.com/chess7000/faqs/67064-chessmaster-personality.html)
  / mirrored on
  [GameFAQs](https://gamefaqs.gamespot.com/pc/193200-chessmaster-7000/faqs/26260)
  — worth noting for *presentation* design, not just mechanics: Chessmaster's
  shipped personalities were **narrative characters**, not raw slider readouts
  — e.g. "Cole" (rating 1214) is described in-universe as believing "the
  secret to chess is opening up cramped positions and letting the energy of
  the pieces fly, which usually leaves his king vulnerable to attack"; "Raina"
  (rated 52) "overvalues the queen and will try to set up defensive positions
  to protect her." **The lesson for UX, not just engine design: Chessmaster
  sold personality through a one-line prose description of a tendency, not a
  slider readout** — the sliders were implementation, the narrative was the
  product surface. This favors surfacing personas to end users as short
  behavioral descriptions ("attacks the king even when it's not safe to")
  rather than exposed parameter values.

## Rubber-banding: a cautionary adjacent pattern (NOT recommended here)

- [Game Wisdom: "Explaining 'Rubber-Banding AI' in Game
  Design"](https://game-wisdom.com/critical/rubber-banding-ai-game-design) —
  general game-AI design literature on dynamically weakening/strengthening an
  opponent based on how the player is doing. Core finding: players resent it
  when detected — *"the game is helping you without your consent"* — because
  skilled play stops being rewarded and the player loses trust in the
  outcome. The one broadly-accepted exception is *environmental* difficulty
  adaptation (their example: Left 4 Dead's AI Director varying spawns/items)
  because the adjustment reads as world behavior, not as the opponent itself
  being secretly nerfed mid-game.
- **Direct relevance**: this is close kin to the "programmed to blunder"
  complaint above — a bot that quietly injects a blunder to keep a game
  competitive is functionally rubber-banding the *opponent's own play*, which
  is the least-forgiven form per this literature (it directly cheapens a
  player's win, per SpacePodz's "doesn't feel earned" comment above).
  **Recommendation for this epic: persona/difficulty should be set once
  per-game (or per bot selection), not dynamically adjusted mid-game based on
  how the human is doing.** Static-per-game weakening (via a fixed
  persona+ELO config) reads as honest; live-adjusted weakening reads as
  condescending. ⚠ this is an inference bridging general game-AI literature
  to chess specifically — no chess-specific source makes this exact claim,
  flagged as reasoned extrapolation, not a cited fact.

## Load-bearing takeaways for design

1. **The complaint is about narrative consistency, not difficulty.** A
   bot's mistakes must be legible as *that persona's* mistake type — the
   error model must be persona-conditioned (`persona-parameterization.md`),
   not a flat random-blunder-injection layer bolted onto any style.
   Confidence: high — directly and repeatedly cited across independent forum
   threads.
2. **A plausibility filter on candidate moves (Chessiverse's "Move Curator"
   pattern) is the most concrete architectural answer found to the exact
   complaint driving this epic.** Confidence: medium — sound design pattern,
   directly answers the cited complaint, but only self-reported by
   Chessiverse, not independently benchmarked.
3. **Resignation/draw-offer behavior is a live, unaddressed complaint on the
   market leader.** Shipping bots that resign lost positions is a
   differentiator, not table stakes yet. Confidence: high on the complaint
   existing; see `bot-match-conventions.md` for the recommendation.
4. **Opening theory depth needs a rating-band ceiling, or "too smart in the
   book" becomes its own immersion break** (Maia Dutch example). Confidence:
   medium (single-thread anecdote) — but consistent with the general
   principle in finding #1.
5. **Do not dynamically rubber-band mid-game.** Set difficulty/persona once
   per game. Confidence: medium (extrapolated from general game-AI
   literature + one direct textual echo in the chess.com complaints).
