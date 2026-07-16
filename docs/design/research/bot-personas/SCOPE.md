# Research scope — Bot personas & experience design

Product/design knowledge for opponents that feel like *someone*, not a
weakened engine. Seeded for roadmap Chapter 3 slice B1 (bots epic).

## What belongs in this folder

- **What makes bots engaging vs annoying** — chess.com bot criticism (the
  random-inexplicable-blunder complaint this epic exists to avoid), Lichess
  bots, **Chessmaster personalities** (the classic gold standard), Fritz
  sparring/handicap modes, Maia-based bots in the wild; evidence on what
  players actually value in practice opponents.
- **Persona parameterization** — mapping ELO + style (aggressive / solid /
  positional / gambiteer …) onto concrete knobs: engine params, error-model
  biases (an attacker over-values its own threats), opening repertoire bias
  (executed via `../openings/` books), trade affinity, king-safety neglect.
- **Difficulty ladder design** — how many rungs, spacing that feels distinct
  (what ELO gap is perceptible), progression/matchmaking conventions;
  honest rating labels per rung → math and mitigations in
  `../rating-calibration/`.
- **Think-time simulation UX** — believable pacing: base delay + variance,
  criticality-weighted pauses (engine signals: eval swing, multipv gap —
  human time-use data lives in `../human-play-modeling/`), tolerable wait
  ceilings, "thinking" indicators.
- **Bot-match conventions** — takebacks, hints, resign behavior (bots that
  resign lost positions vs play on), rematch flows.

## Not here

Strength-execution mechanics → `../engine-adaptation/`. Why humans err →
`../human-play-modeling/`. Book formats/sampling → `../openings/`.

## Protocol for research agents (enrich, don't dump)

1. Read every existing note in this folder BEFORE writing.
2. New findings that extend an existing note's concept → edit that note in
   place (weave into its structure, keep its voice, add citations).
3. Only a genuinely unaligned concept gets a NEW note (kebab-case name).
4. Every claim carries a source; anything unverified is flagged ⚠ —
   never ship wrong facts silently.
