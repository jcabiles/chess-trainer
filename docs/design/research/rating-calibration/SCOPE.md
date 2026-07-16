# Research scope — Rating calibration (assigning honest ELOs)

How to give each bot a rating that MEANS what it says — and how to update
the user's own estimate from results. Seeded for roadmap Chapter 3 slice B1;
also feeds slice B8 (personal ELO estimate).

## What belongs in this folder

- **Rating-system fundamentals** — Elo math (expected score, K-factor
  choices), Glicko/Glicko-2 differences, provisional-rating handling; what
  B8's per-game update needs.
- **Engine-ELO vs human-ELO** — the core problem: Stockfish's
  `UCI_Elo`/`UCI_LimitStrength` is calibrated against engine pools at
  specific time controls and hardware, NOT against human ladders; `Skill
  Level` has no ELO semantics at all; node-limited strength varies by
  hardware. Document the known evidence on how far off these are and in
  which direction.
- **Mitigations** — the least-problematic assignment path: Maia's rating
  bands as human-anchored ground truth; published SF-setting↔human-ELO
  equivalence attempts; calibration matches (bot vs bot / bot vs
  known-strength opponents); anchoring to lichess/chess.com bot ratings in
  the wild; accepting a labeled ladder ("feels like ~1200") vs claiming
  precision. How other apps label bot strength honestly.
- **Validating a bot's claimed rating** — cheap local procedures: does the
  ladder order correctly (B4's monotonic probe), does play-vs-user data
  confirm the label over time (ties into B8's estimate).
- **Existing repo context** — `app/accuracy.py` already maps per-game
  accuracy → an est.-Elo heuristic (see
  `docs/ai-dlc/contracts/game-accuracy-elo.md`); how bot-game ratings and
  that per-game estimate should relate without contradicting each other.

## Not here

Making the engine PLAY at a level → `../engine-adaptation/`. Why humans
blunder → `../blunders/`, `../human-play-modeling/`.

## Protocol for research agents (enrich, don't dump)

1. Read every existing note in this folder BEFORE writing.
2. New findings that extend an existing note's concept → edit that note in
   place (weave into its structure, keep its voice, add citations).
3. Only a genuinely unaligned concept gets a NEW note (kebab-case name).
4. Every claim carries a source; anything unverified is flagged ⚠ —
   never ship wrong facts silently.
