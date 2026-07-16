# Research scope — Engine adaptation (playing at a target strength)

Systems knowledge for making chess engines play at controlled, human-plausible
strength levels. Seeded for roadmap Chapter 3 slice B1 (bots epic); durable
beyond it.

## What belongs in this folder

- **Stockfish weakening mechanics** — `Skill Level` internals (how it samples
  among MultiPV candidates), `UCI_LimitStrength`/`UCI_Elo` (what ELO the scale
  is calibrated against, known criticisms: passive/random feel at low levels),
  node/depth/movetime caps and their strength effect, contempt.
- **Maia / lc0** — rating-banded human policy networks (maia-1100…1900),
  move-matching accuracy claims, maia2 (unified model), lc0 runtime
  requirements, CPU vs GPU inference speed on Apple Silicon, weights
  distribution, licensing.
- **Process/architecture patterns** — running a second engine beside an
  analysis engine (this repo: ONE Stockfish behind an asyncio.Lock with
  process-global UCI options — see `docs/ai-dlc/contracts/bot-play.md`),
  per-call option toggling vs process isolation, python-chess multi-engine
  management, restart/option-reapplication pitfalls.
- **Mac install feasibility** — brew/lc0, Maia weights download, binary sizes,
  offline operation (this app is local-first).

## Not here

Human error *behavior* (why/how humans blunder) → `../human-play-modeling/`.
Persona/style design → `../bot-personas/`. Opening books → `../openings/`.

## Protocol for research agents (enrich, don't dump)

1. Read every existing note in this folder BEFORE writing.
2. New findings that extend an existing note's concept → edit that note in
   place (weave into its structure, keep its voice, add citations).
3. Only a genuinely unaligned concept gets a NEW note (kebab-case name).
4. Every claim carries a source; anything unverified is flagged ⚠ like
   `../openings/opening-traps.md` does — never ship wrong facts silently.
