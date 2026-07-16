# Tickets — B1: Chess-bots research spike

Spec: [`../specs/chess-bots-research.md`](../specs/chess-bots-research.md).
No production code anywhere in this slice. R0 → R1/R2/R3 (parallel) → R4 →
R5 → R6.

## R0 — Branch + commit scaffolding
Create `feat/bots-research` off up-to-date main; commit the currently
uncommitted docs (roadmap Chapter 3, contracts/bot-play.md, this spec +
tickets, the six SCOPE.md files, the opening-traps.md relocation).
- **Owns:** git state
- **Done:** `git status` clean on the feature branch; nothing left on main.

## R1 — Engine probe: build, run, capture
Standalone script(s) under `docs/ai-dlc/research/probes/`: sample ~10
positions from `data/games.db` via sqlite3 (≥4 threat-facing; leaks table
motifs and/or python-chess attack checks — **no `app.*` imports**) + ~8
curated standard FENs; run local Stockfish at ~5 weakened configs (Skill
Level {3,10}, UCI_Elo {1350,1700}, node-cap; 2 = required minimum if time
bites); record chosen move, cpLoss vs full-strength reference, match-best;
emit aggregate table + per-position verdicts (DB-derived FENs NOT in
committed output — index/phase/motif references instead). Include lc0/Maia
detection; absent → emit install-commands block for the synthesis doc.
- **Owns:** `docs/ai-dlc/research/probes/`
- **Done:** committed probe output (table + verdicts) regenerable by
  re-running the script; privacy rule respected; `pytest`/`ruff` untouched.

## R2 — Research wave A: engines + ratings (2 agents, parallel)
Deep-research agents for `engine-adaptation/` and `rating-calibration/`,
each briefed with its SCOPE.md verbatim + the enrichment protocol (read
folder first; enrich in place; new kebab-case notes only for unaligned
concepts; cite everything; ⚠ unverified claims). One agent = one folder.
- **Owns:** `docs/design/research/engine-adaptation/`, `…/rating-calibration/`
- **Done:** each folder has ≥1 substantive cited note beyond SCOPE.md;
  protocol spot-check passes.

## R3 — Research wave B: human behavior + product (4 agents, parallel)
Same protocol for `blunders/`, `human-play-modeling/`, `openings/`
(sub-1600 catalog + bot books; must ENRICH beside `opening-traps.md`, never
duplicate its content), and `bot-personas/`.
- **Owns:** those four folders (one agent each; disjoint)
- **Done:** same per-folder criteria as R2; openings catalog covers the
  user-specified lines (White d4/e4; Black d5/d6, e5/e6, c5) most-common-first.

## R4 — Synthesis + architecture decision
Author `docs/ai-dlc/research/chess-bots.md`: five sections (engine strategy
incl. process-isolation + Mac feasibility · error modeling · opening
variety · think-time · personas), each linking into the enriched notes;
probe results embedded; **ONE recommended architecture** with rejected
alternatives; lc0/Maia install commands as one runnable block (if needed).
- **Owns:** `docs/ai-dlc/research/chess-bots.md`
- **Done:** every Verify-by item 1–2 satisfied; every claim traces to a
  note or probe output. Depends on R1+R2+R3.

## R5 — Dual verification (Codex + Claude refuter)
Codex (gpt-5.6-sol, review-only) + Claude refuter independently attack the
synthesis: claims trace to notes/probe, citations spot-checked, ⚠ flags
where thin. Findings + resolutions appended to the synthesis as a
**Verification log** section; fixes folded.
- **Owns:** synthesis doc (verification log section)
- **Done:** log present; all findings resolved or explicitly accepted.

## R6 — User gate + close-out
Present the recommended architecture + the FEN-commit privacy question
(default: user FENs stay uncommitted; user may override). On approval:
mark B1 `[x]` in the roadmap, run `pytest`/`ruff` (no-regression proof),
commit, push, open PR.
- **Owns:** roadmap checkbox, git close-out
- **Done:** user approved; PR open; B2 unblocked.

## Notes
- R2/R3 agent count (6 total) respects one-folder-one-owner; waves may run
  concurrently with R1 (disjoint files).
- Appetite guard: if over budget, cut probe configs → opening depth →
  personas breadth (never the five sections or the decision).
