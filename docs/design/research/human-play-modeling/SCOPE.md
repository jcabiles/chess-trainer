# Research scope — Human play modeling (how real players think and err)

Behavioral science of rating-conditioned human chess: what mistakes players
actually make at each level and how to reproduce them computationally. Seeded
for roadmap Chapter 3 slice B1 (bots epic); the core requirement it serves:
**bot blunders must be CAUSAL** (e.g. a ~1100 misses your threat because it's
orchestrating its own attack), never uniformly random.

## What belongs in this folder

- **Error taxonomies by rating** — tactical oversights, attack tunnel-vision /
  plan fixation, missed defensive resources, back-rank & horizon effects,
  "hope chess"; which error *types* dominate at which rating bands; evidence
  from lichess/chess.com datasets and the Maia papers (McIlroy-Young et al.).
  Blunder-specific taxonomy/causality lives in `../blunders/` — this folder
  carries the broader choice/cognition models; cross-link, don't duplicate.
- **Phase-specific play by rating** — how sub-1600 players handle endgames
  and phase transitions (characteristic endgame misplays a believable bot
  must reproduce).
- **Measuring humanness** — move-matching accuracy vs human games (Maia's
  metric), statistical realism tests; feeds B5's pass/fail design.
- **Quantitative error distributions** — blunder rate / average centipawn
  loss per rating band, cpLoss distribution shapes, how error rate varies by
  game phase and position sharpness.
- **Motif-specific blindness** — which tactical motifs (forks, pins,
  discovered attacks, backward-moving pieces) humans at each level miss most.
- **Human time allocation** — when humans think long (criticality,
  complexity, surprise), think-time distributions by rating; feeds the bot
  think-time *simulation* design in `../bot-personas/`.
- **Computational human-error models** — rating-scaled softmax/temperature
  over move values, targeted error injection conditioned on position features
  (own-plan salience, threat visibility), Maia's move-prediction approach as
  a model of human choice, seedable/deterministic implementations.

## Not here

Engine mechanics for *executing* a strength level → `../engine-adaptation/`.
Persona/style parameter design → `../bot-personas/`.

## Protocol for research agents (enrich, don't dump)

1. Read every existing note in this folder BEFORE writing.
2. New findings that extend an existing note's concept → edit that note in
   place (weave into its structure, keep its voice, add citations).
3. Only a genuinely unaligned concept gets a NEW note (kebab-case name).
4. Every claim carries a source; anything unverified is flagged ⚠ —
   never ship wrong facts silently.
