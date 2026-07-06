# Tickets — app.js full split

Spec: `docs/ai-dlc/specs/appjs-split.md` · Contracts:
`docs/ai-dlc/contracts/appjs-split.md`. Three PRs; tickets sequential within a
PR. **No parallelization** — every ticket touches `static/app.js` (hotspot,
single-owner).

**Build-time amendment (approved plan):** T1 ships as its own **PR-0**
(parallel Opus worker, worktree); PR-A = T2-T4. T1 ∥ T2 is the only
parallel pair — everything else strictly sequential.

## PR-0 — cache header (parallel worker)

- [x] **T1 — no-store on /static.** Add `@app.middleware("http")` in
  `app/main.py` setting `Cache-Control: no-store` on responses for paths
  starting `/static` (StaticFiles has no headers kwarg; middleware also covers
  304s). Write new API test asserting the header on `/static/app.js`.
  Optional same-PR commit: retire `?v=` strings in `static/index.html`.
  Owned: `app/main.py`, `tests/` (new test), `static/index.html`.
  **Done when:** `.venv/bin/python -m pytest -q` passes incl. new test;
  `curl -sI localhost:8001/static/app.js | grep -i cache-control` shows
  no-store.
  *Pre-req:* install ruff into .venv (configured in pyproject, missing) —
  try in-session (`pip install ruff`; pypi.org is sandbox-allowlisted), fall
  back to asking user to run it in their terminal.
  *Note:* `no-store` only governs future fetches — browsers holding
  pre-header cached copies serve stale once more. One manual hard refresh
  (Cmd+Shift+R) needed after PR-A merges; don't mistake it for a regression
  during Phase-1 verification.

- [x] **T2 — widen injected api (expose-only).** Extend the `api` object in
  app.js: `syncBoard`, `postJSON`, `refreshAnalysis`, `persist`, `setMode`,
  `setStatus`, `snapshotPlay`, `restorePlay` (MUST default missing
  `moveQuality`/`moveRetro` → `[]`, `cursor` → 0), `ensurePlay`,
  `registerModeHandlers(mode, {onMove, exit})`, `isPromotion`,
  `askPromotion`, `positionFromFen`, `positionAt`, `fenOf`,
  `lastMoveSquares`. Rewire `ground.events.after` dispatcher + `ensurePlay`
  to use registered handlers — **hub registers ALL FOUR mode handler sets
  itself in T2** (play/setup AND trap-practice→`onTrapMove`,
  rep-practice→`onRepMove`, still hub-resident until T3/T5/T7 move their
  registrations into the modules); missing registration → console.error +
  status, never silent fall-through. Internal hub calls stay direct — zero
  behavior change. Owned: `static/app.js`.
  **Done when:** app boots; play mode: move → analysis + quality label; all
  existing panels work; **sanity drag in trap-practice AND rep-practice
  still validates/snap-backs** (proves all four registrations); no console
  errors.

- [x] **T3 — extract setup.js.** Move setup functions per contracts
  "Extraction inventory" (function names, NOT line ranges — hub play controls
  are interleaved in that span and stay). Move init()'s setup DOM wiring
  (:2100-2109) **plus the board-level brush listeners at :2053-2054**
  (`mousedown`/`touchstart` → `onBoardPointerDown`, capture-phase) into
  `initSetup(api)`. `brush` moves; `playSnapshot` stays hub-owned, accessed
  via `getPlaySnapshot`/`setPlaySnapshot` seam. Owned: `static/app.js`,
  `static/setup.js` (new).
  **Done when:** Playwright (real mouse): enter setup → stamp/erase → set
  side → Begin Game (valid + invalid) → Cancel restores game; refresh
  mid-setup persists; **refresh mid-setup → Cancel → make a move** (no
  crash); cross-cutting guards (movelist tints + retro panel after return;
  play move analyzes).

- [x] **T4 — PR-A docs + ship.** ARCHITECTURE.md codemap row for `setup.js`;
  branch per commit policy (fetch/status first); PR.
  **Done when:** PR open, full pytest green, diff reviewed, no debug
  artifacts.

## PR-B (Phase 2) — repertoire.js

- [x] **T5 — extract repertoire.js.** Move rep functions per inventory
  (**excluding `ensurePlay`** — stays hub); move rep DOM wiring
  (:2143-2147) into `initRepertoire(api)`; owns `rep`, `repTree`,
  `repSnapshot`, `repEngineToken`; registers `rep-practice` handlers.
  Owned: `static/app.js`, `static/repertoire.js` (new).
  **Done when:** Playwright: browse tree → Jump (undo steps back through
  line) → Practice: correct move, wrong-move snap-back, reveal, take-back,
  restart, engine handoff after prep, **promotion during practice if line
  allows** → Return restores snapshot; cross-cutting guards pass.

- [x] **T6 — PR-B docs + ship.** ARCHITECTURE.md row; PR.
  **Done when:** same bar as T4.

## PR-C (Phase 3) — traps.js (riskiest, last)

- [x] **T7 — extract traps.js.** Move trap functions per inventory; move
  traps DOM wiring (:2111-2138) into `initTraps(api)`; owns `trap`,
  `trapsData`, `studyEvalToken` (whole — never split watch/practice),
  `trapsCheckToken`, `trapChipDismissedFen`, `studySnapshot`; registers
  `trap-watch`/`trap-practice` handlers; hub's `refreshOpeningThenTraps`
  calls the module's chip refresh via api/registration. May import
  `panel.js` directly (feature → leaf). Owned: `static/app.js`,
  `static/traps.js` (new).
  **Done when:** Playwright: browse + filter; chip appears / sticky-dismiss
  per FEN / drill; watch stepper + variation picker; practice: auto-victim
  reply, snap-back, reveal, refutation; Return restores snapshot;
  cross-cutting guards pass; no stale-eval flicker stepping fast
  (token guard intact).

- [x] **T8 — PR-C docs + ship + closeout.** ARCHITECTURE.md row; confirm hub
  ≈900-1,000 lines; **refresh `docs/ai-dlc/profile.md` hotspots** (its
  app.js/review.js line refs — e.g. "tab array ~:1999" — are stale after the
  split); PR; mark audit Item 1 done.
  **Done when:** same bar as T4; `wc -l static/app.js` reported in PR body.

## Dependencies

T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 (strictly sequential; each phase's
Playwright pass gates the next). User runs
`uvicorn app.main:app --reload --port 8001` for each verification pass
(sandbox blocks bind).
