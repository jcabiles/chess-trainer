# Research scope — Openings

Opening-theory research notes. Existing content: `opening-traps.md` (trap
inventory for the traps trainer, engine-verification mandate inside).
Extended 2026-07-16 for roadmap Chapter 3 slice B1 (bots epic): bots need
opening *variety* and rating-plausible opening choice.

## What belongs in this folder

- Existing: **opening traps** (trap inventory, bait/refutation structure,
  verification mandate) — see `opening-traps.md`.
- **Opening books for bots** — polyglot format, building weighted books,
  sampling strategies for game-to-game variety (temperature, top-k),
  exit-depth control.
- **Rating-banded opening behavior** — what openings humans actually play at
  each rating (lichess explorer rating filters as a data source), how early
  low-rated players leave theory, punishable-but-common lines.
- **Persona repertoire bias** — expressing a persona's style through its
  book (gambiteer vs system player), overlap with the user's own repertoire
  (this repo bundles lichess openings TSVs + `data/repertoire.json` — bots
  that play INTO the user's prepared lines have training value).
- **Common openings + branching lines, sub-1600 focus (catalog)** — the
  openings and their main branches most played by beginners and sub-1600
  players, with rating-banded popularity evidence (lichess explorer rating
  filters). Priority coverage, most-common first — NOT comprehensive:
  - White: **1.d4** systems (London, Queen's Gambit main branches) and
    **1.e4** (Italian, Ruy, Scotch, common gambits);
  - Black vs 1.d4: **…d5** (QGD/Slav basics) and **…d6/Indian** setups;
  - Black vs 1.e4: **…e5** (open games), **…e6** (French), **…d6** (Pirc/
    Philidor), **…c5 Sicilian** (the sub-1600-common branches);
  - per line: main branching points, how sub-1600 players typically deviate,
    and which branches a bot book should weight.

## Not here

Engine strength mechanics → `../engine-adaptation/`. Error behavior →
`../human-play-modeling/`. Persona design beyond the book →
`../bot-personas/`.

## Protocol for research agents (enrich, don't dump)

1. Read every existing note in this folder BEFORE writing (`opening-traps.md`
   included — enrich it rather than duplicating trap content).
2. New findings that extend an existing note's concept → edit that note in
   place (weave into its structure, keep its voice, add citations).
3. Only a genuinely unaligned concept gets a NEW note (kebab-case name).
4. Every claim carries a source; anything unverified is flagged ⚠ like
   `opening-traps.md` does — never ship wrong facts silently.
