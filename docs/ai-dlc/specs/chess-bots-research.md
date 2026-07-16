# Delta spec — B1: Chess-bots research spike

**Goal (one line):** evidence-backed architecture decision for the bots epic
(roadmap Chapter 3), delivered as an enriched research knowledge base + a
synthesis doc + a runnable local engine probe — **no production code**.

Slice: **B1** of `../roadmap/training-and-portfolio.md` Chapter 3 (N3).
Contracts: [`../contracts/bot-play.md`](../contracts/bot-play.md).
Requirements confirmed at Gate 1, 2026-07-17 (picker-off session; user
confirmed in plain text after two taxonomy expansion rounds).

## Deliverable 1 — enriched research knowledge base

Six research agents (deep-research harness: parallel web sweeps + claim
verification), **one agent per folder, folders are disjoint = one owner
each**, working under `docs/design/research/`:

| Folder | Focus (full scope in its `SCOPE.md`) |
|---|---|
| `engine-adaptation/` | SF weakening internals, Maia/lc0, process isolation, Mac feasibility |
| `human-play-modeling/` | rating-conditioned cognition/choice models, endgame-by-rating, humanness metrics |
| `blunders/` | definitions/thresholds, causal mechanisms, ELO-conditioned blunder profiles |
| `rating-calibration/` | honest bot-ELO assignment; engine-ELO vs human-ELO; Elo/Glicko math for B8 |
| `openings/` | bot books/variety + the **sub-1600 common-openings catalog** (d4/e4; d5/d6, e5/e6, c5) |
| `bot-personas/` | engagement design, style→parameter mapping, ladders, think-time UX |

**Enrichment protocol (binding for every agent; also stated in each
SCOPE.md):** read every existing note in the target folder first → weave new
findings into existing notes where the concept aligns (edit in place, keep
the note's voice) → create a new kebab-case concept note ONLY for unaligned
concepts → every claim cited → unverified claims flagged ⚠ (the
`openings/opening-traps.md` convention). **No standalone dossiers.**
Cross-folder references allowed; cross-folder EDITS not (one folder = one
owner). Agents receive their SCOPE.md verbatim in the brief.

## Deliverable 2 — synthesis + decision doc

`docs/ai-dlc/research/chess-bots.md` (the roadmap's pass/fail artifact):
- The roadmap's five sections — (a) engine strategy incl. the
  process-isolation question from `contracts/bot-play.md` and Mac install
  feasibility; (b) human-error modeling; (c) opening variety; (d) think-time
  realism; (e) persona design — each a tight synthesis **linking into the
  knowledge-base notes** (the notes carry the depth; the synthesis carries
  the argument).
- Probe results (deliverable 3) embedded or linked.
- **ONE recommended architecture**, with rejected alternatives and why.
- lc0/Maia install commands as one runnable block for the user (sandbox
  blocks Claude from network installs — repo convention: commands in docs,
  not chat).

## Deliverable 3 — runnable local engine probe

Script(s) under `docs/ai-dlc/research/probes/` (research tooling, NOT app
code; standalone python-chess + Stockfish binary — **must not import
`app/`** so production seams stay untouched):
- **Positions (~18):** ~10 sampled from the user's `data/games.db`
  (`game_plies.fen_before` — refuter-verified populated, 7551/7551 rows)
  across phases, of which ≥4 are positions where the side to move faces a
  concrete threat — direct evidence for the causal-blunder question; plus
  ~8 curated standard FENs (opening/middlegame/endgame, tactical + quiet).
  - Threat selection: read `leaks.motif_json`/`threat_motif` **directly via
    sqlite3** (only leak-flagged plies have them — partial coverage is fine)
    and/or a minimal standalone attack/SEE check built on python-chess
    board primitives (`Board.attackers` etc.). **`import app.*` is
    forbidden** — python-chess the library is fine, the repo's `app/motifs`
    is not (keeps production seams untouched).
  - **Privacy (refuter major, resolved):** committing FENs extracted from
    the user's private games is NOT covered by the "aggregated personal
    data" precedent (roadmap Chapter 2 slice 8 blessed aggregates only).
    Default: DB-sampled FEN strings are read at runtime and stay OUT of
    committed probe output — committed results carry aggregate stats plus
    per-position verdicts referenced by index/phase/motif description.
    Curated standard FENs commit freely. The user may explicitly override
    at Gate 2 ("my FENs may be committed") — it is their call, made
    visibly, not smuggled under a precedent.
- **Configs (≥2 required, ~5 proposed):** Skill Level ≈ {3, 10} ·
  `UCI_LimitStrength+UCI_Elo` ≈ {1350, 1700} · a node-cap-only config.
  Exact values may be adjusted during implementation; record whatever ran.
- **Per config × position:** chosen move, cpLoss vs full-strength best
  (reference eval at a fixed decent budget), match-best flag; per config:
  avg cpLoss, %match-best, count of cpLoss>200 ("blunders"), and a short
  qualitative verdict — *does the weakening read as human or random?*
- **lc0/Maia check:** detect binary + weights; if absent, emit the install
  commands into deliverable 2 instead of failing.
- Uses the user's local Stockfish (`STOCKFISH_PATH`/brew path) directly —
  the app server is not involved.

## Process

- Research execution and verification happen at TICKET time (after Gate 2),
  via the deep-research harness (workflow fan-out per category) — this spec
  authorizes that orchestration.
- **Verification pass (ticket stage):** per the user's decision, **Codex
  (gpt-5.6-sol) + Claude refuter dual-review the synthesis doc** — claims
  must trace to notes/probe output; citations spot-checked; ⚠ flags present
  where evidence is thin. (Codex was deliberately NOT used on this spec.)
  **Auditability (refuter fix):** both reviewers' findings AND their
  resolutions are appended to the synthesis doc as a visible
  "Verification log" section — the gate is checkable after the fact.
- **Exit gate:** user reads the synthesis, approves the recommended
  architecture → B1 marked `[x]` in the roadmap → B2 may start.
- **Branch first (refuter fix):** the roadmap/contract/spec/scaffolding
  edits currently sit uncommitted on `main`. Ticket R0 creates
  `feat/bots-research` and commits them BEFORE any research agent runs —
  no agent output lands on `main`.
- **Appetite honesty (refuter fix):** 2–3 days is tight for six research
  folders + probe + synthesis + dual review + user gate. The fan-out
  parallelizes; probe debugging and synthesis are serial. If it runs over,
  cut in this order: probe configs 5→2 (the required minimum), opening
  catalog depth (already most-common-first), bot-personas breadth. The
  five synthesis sections and the architecture decision never get cut.

## Out of scope

- Any production code or `app/`/`static/` change; any engine-invariant
  change (a second engine is a *recommendation output*, not an action).
- No LLM move selection anywhere (global no-go).
- No quantitative blunder-curve validation (B5) and no bot-vs-bot
  rating-gap matches (B4's probe harness).
- Opening catalog is most-common-first for sub-1600, explicitly NOT
  comprehensive.

## Constraints (from profile)

- `pytest` + `ruff` stay green (trivially — no app code changes; run once
  at the end as the no-regression proof).
- Never commit `data/games.db` / `data/games/`; probe respects this.
- Feature-branch + PR workflow; Conventional Commits.

## Verify-by (B1 pass/fail, from the roadmap)

1. `docs/ai-dlc/research/chess-bots.md` exists; five sections, each
   evidence-backed with citations + a recommendation; ends in ONE
   recommended architecture.
2. Probe ran: its output (table + verdicts) is embedded/linked; ≥2 weakened
   settings covered; lc0/Maia feasibility answered (installed-and-tested OR
   install commands documented).
3. Knowledge base enriched: every one of the six folders gained or extended
   notes per its SCOPE.md; spot-check that existing notes were enriched in
   place (e.g. `openings/opening-traps.md` untouched or enriched, not
   duplicated); citations present; ⚠ flags on unverified claims.
4. Dual verification (Codex + refuter) of the synthesis passed with
   findings folded.
5. `pytest -q` and `ruff check app tests` green (no-regression proof).
6. **User approves the architecture direction** — the gate to B2.
