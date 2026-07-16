# Bot-match conventions — takebacks, hints, resign, rematch

Conventions for the "meta" interactions around a bot game, as distinct from
move-generation quality. Sourced against chess.com's shipped conventions
(the market leader this epic's user is directly comparing against) plus the
one directly-relevant complaint thread on resignation.

## Takebacks: uncontroversial, expected, already normalized

- [Chess.com forum: "How do you takeback vs
  bots?"](https://www.chess.com/forum/view/general/how-do-you-takeback-vs-bots)
  — mechanically trivial ("use the back arrow... 'previous move'") and,
  notably, **raised with zero pushback or debate** in the thread — no one
  questions whether takebacks against a bot are legitimate. Chess.com
  surfaces a numeric allowance ("3 takebacks") in at least some contexts per
  the OP's own framing.
- [Chess.com Help Center: "What is good etiquette on
  Chess.com?"](https://support.chess.com/en/articles/8614346-what-is-good-etiquette-on-chess-com)
  — general etiquette guidance exists for *human* opponents (e.g., stalling
  in lost positions is "considered rude"), but this norm is explicitly
  human-to-human; it doesn't apply to bot play, reinforcing that bot games
  are treated as a lower-stakes, practice-oriented context where takebacks
  are simply a tool, not an etiquette violation.
- **Design takeaway**: takebacks against bots should be liberal/unlimited by
  default (or a generous cap framed as a training aid, matching chess.com's
  "3 takebacks" pattern) — there is no evidence of user expectation that bot
  takebacks should be scarce or gated. Confidence: high — this is a settled,
  uncontroversial convention across the one platform checked, with no
  counter-evidence found.

## Hints: present but not deeply documented

Search did not surface a dedicated discussion thread specifically about hint
*design* (only passing mentions that "hint" and "resign" exist as available
options during bot play, per general chess.com forum search results).
⚠ Confidence: low/no data — this bullet from the SCOPE.md is under-evidenced
by this research pass. No community complaint or praise was found about hint
quality or availability specifically for bot games. Recommend treating hints
as a solved/non-controversial UI feature (show best move or a nudge on
request) rather than a design-research priority — nothing in the evidence
suggests this is a differentiator players care about, in contrast to
resignation behavior (below), which is an actively cited complaint.

## Resign behavior: the clearest, most actionable finding in this note

- [Chess.com forum: "Why chess.com bots never
  resign?"](https://www.chess.com/forum/view/general/why-chess-com-bots-never-resign)
  — direct, named complaint: *"We still don't have a chess bot that would
  respectfully resign in a lost position"* — framed by the OP as a surprising
  gap given the platform's broader AI investment. A responder (EmTat) explains
  the likely mechanical reason (bots don't have a competitive "want to win"
  driving resignation) but explicitly endorses the feature request: *"it
  would be cool if chess.com had a bot who could resign, propose a draw &
  stuff."**
- As of this thread (2025), confirmed status: chess.com bots do **not**
  resign in lost positions and do **not** offer draws in objectively drawn
  endgames (the cited example is R vs. R). This is presented as current,
  unaddressed behavior on the market leader — i.e., **shipping bots that
  resign/offer draws appropriately is a real, evidenced differentiation
  opportunity**, not a solved problem being copied from elsewhere.
- Cross-reference `engaging-vs-annoying-bots.md`'s rubber-banding section:
  a bot that plays on in a completely lost, technique-only position is the
  *inverse* problem from the "programmed to blunder" complaint but shares the
  same root cause — the bot's behavior doesn't track a *plausible persona*
  (a human player, win or lose, eventually resigns dead positions; a bot
  grinding out a lost R-vs-R endgame indefinitely reads as machine-like in
  the same way an inexplicable blunder does).
- **Design recommendation**: implement resignation as a threshold-based
  check on engine eval (e.g., resign when eval has been beyond some cp
  threshold in the bot's disfavor for N consecutive moves, mirroring how a
  human accepts a clearly lost position rather than an instant single-move
  trigger — avoids resigning on a momentary tactical dip that later
  recovers). Offer a draw when the position is a known dead-drawn endgame
  pattern. ⚠ the specific threshold/consecutive-move mechanism is this
  note's proposal, not sourced from any implementation — no source found
  documents exact resignation-trigger logic used by any shipped bot.
  Persona could plausibly modulate this too (a "fighter" persona plays on
  longer before resigning than a "practical" one) — this specific idea is
  speculative and not evidenced by any source, flagged accordingly.

## Rematch flows: low-friction, optional, no strong convention found

- [Chess.com Help
  Center](https://support.chess.com/en/articles/8614346-what-is-good-etiquette-on-chess-com)
  confirms (for human play, extendable by inference to bot play): *"There's
  no rule that says you must accept a rematch request... accepting one is
  entirely optional."* For bot play specifically, there's no "acceptance"
  friction at all since the bot has no agency — the meaningful design
  question is just UI: how many clicks to start another game against the
  same persona/rating. No source found suggests this is a point of user
  friction or complaint. Confidence: low evidentiary depth, but also low
  apparent risk — treat as a solved, low-priority UI concern (one-click
  rematch against the same bot) rather than a research-worthy design
  question.

## Load-bearing takeaways for design

1. **Takebacks: be generous, this is settled and uncontroversial.**
   Confidence: high.
2. **Resignation/draw-offer behavior is the single clearest, most actionable
   gap this whole research pass found relative to the market leader** —
   chess.com bots demonstrably don't do this as of 2025, players have
   explicitly asked for it, and it directly reinforces persona believability
   (a bot that fights on forever in a dead position is exactly the kind of
   "doesn't feel like someone" complaint this epic exists to fix, just at the
   opposite end of the game from the blunder complaint). Confidence: high on
   the gap existing; medium on the specific threshold-based implementation
   proposed (that mechanism is this note's synthesis, not sourced).
3. **Hints and rematch flows are not evidenced as differentiators** — treat
   as standard, low-research-priority UI features unless local user feedback
   says otherwise. Confidence: low data either way, but no counter-signal
   found either.
