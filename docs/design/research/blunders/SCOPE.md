# Research scope — Blunders (the phenomenon itself)

The app's central concept — the profiler, blunder trainer, foresight coach,
and now the bots epic (Chapter 3, B1) all revolve around blunders. This
folder holds what a blunder IS and WHY it happens; durable well beyond bots.

## What belongs in this folder

- **Definitions & thresholds** — blunder vs mistake vs inaccuracy: formal
  cp-loss threshold definitions (lichess/chess.com conventions), win-prob-
  drop definitions, where this repo's own `analysis.classify()` thresholds
  sit relative to industry convention; blunder vs "game-ending move"
  (checkmate/draw — this repo distinguishes them, PR #55).
- **Causal mechanisms** — WHY blunders happen: attack tunnel-vision / plan
  fixation (the bots epic's core realism requirement), missed opponent
  threat vs miscalculated own tactic, defensive-resource blindness,
  retreating-move blindness, back-rank patterns, fatigue/time-pressure,
  "hope chess" (this repo's profiler already measures a hope-chess rate).
- **ELO-conditioned blunder profiles** — which blunder *types* dominate at
  which rating bands and why (e.g. sub-1000: one-move piece drops; 1200-1600:
  missed tactics while executing own plan; higher: positional/endgame errors);
  frequency curves per band; game-phase distribution of blunders by rating.
- **Anything that helps build realistic bots** — how to trigger the RIGHT
  blunder type for a target rating in a given position class; links to the
  computational models in `../human-play-modeling/`.

## Not here

Broader human move-choice/time modeling → `../human-play-modeling/`.
Strength execution → `../engine-adaptation/`. Rating math →
`../rating-calibration/`.

## Protocol for research agents (enrich, don't dump)

1. Read every existing note in this folder BEFORE writing.
2. New findings that extend an existing note's concept → edit that note in
   place (weave into its structure, keep its voice, add citations).
3. Only a genuinely unaligned concept gets a NEW note (kebab-case name).
4. Every claim carries a source; anything unverified is flagged ⚠ —
   never ship wrong facts silently.
