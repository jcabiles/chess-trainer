# Difficulty ladder design + think-time simulation UX

Two closely related UX questions bundled here because both are about pacing
and structuring the *experience* of playing a persona bot, distinct from how
the bot's moves are generated (`persona-parameterization.md`) or how its
rating is honestly labeled (`../rating-calibration/`).

## Difficulty ladder: rung count and spacing

Hard numbers on "how many rungs" and "what ELO gap feels distinct" were
**not found directly stated** anywhere in this research pass — this is the
weakest-evidenced section of the three notes in this folder. What was found:

- [Chess.com forum: "Why are bots always easier to play against than people
  with the same
  ELO?"](https://www.chess.com/forum/view/general/why-are-bots-always-easier-to-play-against-than-people-with-the-same-elo)
  and ["What real ELO would you assign to the chess.com
  bots?"](https://www.chess.com/forum/view/general/what-real-elo-would-you-assign-to-the-chess-com-bots)
  — informal community self-reports: bots in the 1400-1600 labeled band "feel
  like about 80% of their rating," sub-1400 bots "feel like 50%." ⚠ these are
  single-forum-post impressions, not a controlled study, and don't answer the
  rung-spacing question directly — they're evidence of label/feel mismatch,
  which is a `../rating-calibration/` concern more than a ladder-spacing one.
  Included here only because it was the closest thing found to a
  perceptibility signal.
- A tangential academic pointer surfaced in search but not deeply verified:
  a study design comparing games at "100% of a player's Elo, 125%, and 75%"
  bands treats a **25% Elo delta** as a meaningful, separately-analyzed
  category. ⚠ this was surfaced via a search-engine summary, not confirmed by
  directly reading the paper — flagged as unverified and not load-bearing;
  do not treat "25%" as an established perceptibility threshold without
  independent verification.
- Chessiverse claims **1000+ discrete bots across 0-3300 Elo**
  ([source](https://chessiverse.com/personaplay)), which — if evenly spread —
  implies rungs far finer than a human could perceive as distinct; this
  strongly suggests their granularity is about matchmaking precision (picking
  a bot close to a target rating), not about each rung being perceptibly
  different from its neighbor. This is a useful reframe: **"how many rungs
  feel distinct" may be the wrong question — the right question is "how fine
  does matchmaking need to be so a player can find *a* bot near their
  level,"** which is a different design goal than "each rung should feel like
  a new experience."
- Maia ships **9 target rating milestones from 1100-1900** (only 3 publicly
  playable on lichess: maia1/1100s, maia5/1500s, maia9/1900s — per
  [lichess.org/team/maia-bots](https://lichess.org/team/maia-bots) and the
  [Maia lichess
  forum](https://lichess.org/forum/general-chess-discussion/question-about-maia-bots)),
  i.e. roughly **100-Elo-wide milestone spacing** across the trained range,
  narrowed to ~400-Elo spacing (1100/1500/1900) in the actually-shipped
  public set. ⚠ Maia's spacing choice is not explained/justified in any
  source found — treat as an existing shipped convention (100-Elo internal
  granularity, ~400-Elo practical/public granularity) rather than as evidence
  that this spacing is optimal.

**Honest gap flag**: no source found directly answers "what ELO gap between
rungs feels perceptibly different to a human player." This should be treated
as an open question for local playtesting (this repo already plans a
calibration probe — see `../rating-calibration/honest-bot-rating-assignment.md`'s
"B4 monotonic ladder probe") rather than something the literature search
resolved. Recommend piggybacking a perceptibility check onto that same probe
rather than running a separate study.

## Think-time simulation: pacing conventions

- [Chessiverse review, chess.com
  blog](https://www.chess.com/blog/vitualis/chessiverse-review-amazing-600-human-like-chess-ai-bots)
  and [Chessiverse's own
  description](https://chessiverse.com/blog/how-we-build-human-like-chess-bots)
  — bots "play openings quickly but will often pause at moves that deviate
  from theory or in tricky positions." This is the single most concrete,
  named pacing convention found: **fast in book, slow when leaving book or
  when the position is sharp** — a binary/graduated pause keyed to
  book-exit and position complexity, not a flat random delay.
- General mechanism description (found via search, exact original source
  unclear — ⚠ low-confidence attribution, treat as a description of a
  common technique pattern rather than a single citable implementation):
  randomized padding on top of a base delay to avoid a mechanical, uniform
  cadence, plus an **"urgency factor"** that increases think time pressure
  cues as material drops, clock time drops, or the position becomes more
  imbalanced. Directionally consistent with (and should defer to for hard
  numbers) the human empirical data already collected in
  `../human-play-modeling/time-allocation.md` — notably the Sigman et al.
  2010 finding that **real think-time distributions are long-tailed/
  power-law-shaped, not Gaussian**, and that **complexity (not just phase)
  drives opening/middlegame think time while endgame speed is budget-driven**.
  A bot using flat base+variance Gaussian jitter is the statistically
  detectable failure mode that note already flags — this note's job is just
  to confirm the product-facing pattern (fast-in-book / slow-on-deviation)
  matches that empirical shape, which it does.
- **Criticality-weighted pausing** (the epic brief's own phrase) has direct
  engine-signal support already available in this repo's stack: eval swing
  between the position before/after a candidate move, and multipv gap
  (the score difference between the engine's best and second-best lines) are
  both already-computed signals per `CLAUDE.md`'s description of
  `analyze_multi(fen, depth, multipv)` and the existing dual-best-move
  feature (per project memory: "Dual best-move" PR #9 — free
  `before.pv[0]` + soft-capped multipv=2). **This means criticality-weighted
  think-time can likely be built on signals the engine already produces for
  other features, without new engine calls** — an implementation-cost note
  worth carrying into planning, though it's an inference from this repo's
  existing architecture, not an external source.

### UX literature on delay/latency perception (adjacent field, not chess-specific)

- [UX Tigers: "Think-Time UX: Design to Support Cognitive
  Latency"](https://www.uxtigers.com/post/think-time-ux) — general HCI
  guidance on system "thinking" delays, applying Nielsen's classic response-
  time thresholds:
  - **0-400ms**: signal that input was received immediately (avoid the
    impression of an unresponsive UI / prevent repeated clicking).
  - **0.4-2s**: show *meaningful* activity, not a generic spinner — "show the
    stages of processing" rather than an indeterminate state.
  - **10s+**: provide a way to do something else while waiting; persistent
    progress indication if the wait is long.
  - Prefer **ETA-with-uncertainty framing** ("usually 3-7 seconds") over
    false-precision countdowns.
  ⚠ this source is general software UX guidance, not chess-specific or
  bot-specific — it's a reasonable adjacent-field anchor for the *tolerable
  ceiling* question, not direct chess-bot evidence. Apply with judgment: a
  chess "thinking" pause is an intentional pacing *feature*, not incidental
  latency to be minimized, so the "reduce delay" framing of most UX-latency
  literature inverts here — the goal is a *believable, tolerable* delay, not
  the shortest one.
- Practical synthesis for this repo: a "thinking" indicator that appears
  within ~400ms of the bot's "turn" starting (matches Nielsen's immediate-
  acknowledgment threshold) prevents the "did my move register?" doubt, while
  the actual move-selection delay should follow the fast-in-book/slow-when-
  critical pattern above rather than a fixed duration — this reconciles the
  general UX-latency literature (acknowledge fast) with the chess-specific
  pacing convention (vary the "thinking" duration meaningfully).

### Tolerable wait ceilings — not directly sourced for chess bots specifically

No source in this pass gives a specific tested maximum tolerable "bot think
time" ceiling for a chess app. ⚠ Recommend treating the general UX literature
threshold (make anything past ~10s interruptible/escapable) as a soft upper
bound, and defer to whatever value the human time-allocation data in
`../human-play-modeling/time-allocation.md` suggests is a plausible *maximum*
observed human think time at the target time control, scaled down for
patience reasons (a human waits for their own thinking; waiting on a bot's
simulated thinking has a lower patience budget). This is this note's
proposal, not a sourced number.

## Load-bearing takeaways for design

1. **Fast-in-book, slow-on-deviation/complexity is the one concretely
   evidenced pacing pattern** (Chessiverse, corroborated by a third-party
   review). Confidence: medium (single vendor + one outside review, not a
   controlled study, but internally consistent and matches the independently
   sourced human time-allocation data).
2. **This repo likely already computes the signals needed for
   criticality-weighted pauses** (eval swing, multipv gap) via existing
   `analyze_multi`/dual-best-move infrastructure — worth flagging to
   planning as a low-marginal-cost feature. Confidence: medium (architectural
   inference from CLAUDE.md + project memory, not independently verified in
   code during this research pass — this folder is docs-only, no code was
   read).
3. **Ladder rung count/spacing has no direct evidentiary answer** — the
   strongest recommendation this research can support is to fold a
   perceptibility check into the already-planned rating-calibration probe
   rather than treat rung spacing as solved. Confidence: low on any specific
   number; medium-high on the recommendation to test locally rather than
   guess.
4. **Acknowledge the bot's "turn" within ~400ms, vary the actual think
   duration meaningfully rather than fixing it** — reconciles general UX
   latency guidance with chess-specific pacing conventions. Confidence:
   medium (general UX principle applied by inference to a chess-specific
   context, not a chess-specific source).
