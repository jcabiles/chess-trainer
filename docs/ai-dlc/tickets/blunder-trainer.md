# Tickets — Blunder Trainer

Spec: `docs/ai-dlc/specs/blunder-trainer.md` · Contracts:
`docs/ai-dlc/contracts/blunder-trainer.md`. Suggested shipping: **2 PRs**
(backend, then frontend) — backend is independently testable and reviewable.
B1-B4 sequential; F1-F3 sequential after B-PR merges. `app/main.py` and
`static/app.js` are hotspots — single-owner per ticket.

## PR-1 — backend (schema + pure SR + routes)

- [x] **B1 — `analysis.cp_loss` refactor.** Extract pure
  `cp_loss(before_white_cp, after_white_cp, mover_is_white)` from
  `classify()`; classify delegates. Zero behavior change. New tests: sign
  correctness both colors, mate-clamped inputs.
  Owned: `app/analysis.py`, `tests/test_analysis.py`.
  **Done when:** full pytest green (existing classify tests untouched).

- [x] **B2 — schema + storage functions.** `trainer_attempts` (cascade on
  games) + `trainer_boxes` tables in `_SCHEMA_DDL`, `_SCHEMA_VERSION` bump;
  `record_trainer_attempt`, `get_trainer_boxes`, `upsert_trainer_box`,
  `get_attempt_stats` (live-leak join for per-bucket; labeled all-time may
  include orphans; empty-state safe). sqlite3 stays storage-only.
  Owned: `app/storage.py`, `tests/test_storage*` (new cases).
  **Done when:** pytest green incl. natural-key survival across simulated
  re-analysis (delete+reinsert leaks, attempts still join), cascade on
  game delete, zero-games stats.

- [x] **B3 — `app/trainer.py` pure SR module.** Leitner intervals
  (1/2/4/7/14d), due computation, min-sample guard (≥2 served else carry
  over), rotation via cursor_key with vanished-key recovery, box reset on
  empty motif pool, session assembly (≥1 slot per due bucket reserved, then
  hardest-first fill, cap 10, ≤3/bucket), qualification gate
  (`my_color IS NOT NULL AND analysis_status='done'`,
  severity mistake|blunder).
  Owned: `app/trainer.py` (new), `tests/test_trainer.py` (new).
  **Done when:** pure suite green with no Stockfish; rotation test proves
  no identical position twice within a bucket cycle.

- [x] **B4 — routes + ship PR-1.** `GET /api/trainer/session`,
  `POST /api/trainer/check` (server-side FEN rebuild; two-call
  before/after at DEFAULT_DEPTH inside one interactive-yield try/finally;
  verdict via `cp_loss`; narrator text on failed; offline sentinel
  check_depth=0), `GET /api/trainer/stats`. Schemas in models.py;
  literal-before-`{id}` ordering; `Depends(get_engine)`.
  Owned: `app/main.py`, `app/models.py`, `tests/test_api.py` (new cases via
  ScriptedEngine: solved / solved_alt / failed / 503).
  **Done when:** full pytest + ruff green → refuter on diff → PR-1.

## PR-2 — frontend (Train section + drill mode)

- [x] **F1 — hub edits (single-owner app.js ticket).** Add
  `blunder-practice` to `PRACTICE_MODES` and `persist()`'s transient
  early-return list; import + `initTrainer(api)` in init; any markup hooks.
  Owned: `static/app.js`, `static/index.html` (Train section + drill bar).
  **Done when:** app boots unchanged; play/trainers regression drags pass.

- [x] **F2 — `static/trainer.js` module.** Train section render (due
  buckets, box levels, Start), drill flow (serve → board at fen_before,
  your-color orientation → move via registered `onMove` → /check → feedback
  with narration + threat highlight → retry-once → reveal → next → session
  summary), `registerModeHandlers('blunder-practice', {onMove, exit})`,
  snapshot/restore via `api.hub.snapshotPlay`/`restorePlay`, exit restores
  play. Styles tokens-only (trainer.css or review.css section).
  Owned: `static/trainer.js` (new), `static/trainer.css` (new).
  **Done when:** Playwright (real mouse): full drill loop incl. wrong→retry→
  reveal, correct→next, Return restores movelist tints; reload mid-drill
  lands in play (transient); cross-cutting guards pass.

- [x] **F3 — docs + ship PR-2.** ARCHITECTURE.md codemap row (`trainer.js`)
  + backend row (`trainer.py` in app/ table); tickets ticked; refuter on
  diff → PR-2; update memory.
  **Done when:** same bar as prior epics; audit trail complete.

## Dependencies

B1 → B2 → B3 → B4 (PR-1) → F1 → F2 → F3 (PR-2). No parallel lanes — backend
tickets chain on shared seams; frontend waits for merged API.
