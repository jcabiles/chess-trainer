# Delta spec — app.js full split (optics-first, phased)

**Goal (one line):** split `static/app.js` (2,162 lines) into `setup.js`,
`repertoire.js`, and `traps.js` over three PRs with **zero user-visible
behavior change**, landing the hub at ≈900-1,000 lines.

Motivation: recruiter-facing optics (audit called app.js the repo's weakest
visual) + maintainability. Contract map: `docs/ai-dlc/contracts/appjs-split.md`.

## Files / interfaces to touch

**Build-time amendment (approved plan):** 1a ships as its own **PR-0**
(`chore/static-no-store`, parallel Opus worker in a worktree) — 4 PRs total.
PR-0 and PR-A are file-disjoint and independent.

| Phase | PR | Files |
|---|---|---|
| 1a | **PR-0** | `app/main.py` — `Cache-Control: no-store` on `/static` via `@app.middleware("http")` (StaticFiles has no headers kwarg; middleware also covers 304s) + **new test** asserting the header (none exists); own commit. Retire `?v=` strings in `static/index.html` (follow-up commit, same PR) |
| 1b | PR-A | `static/app.js` — widen injected api (expose-only); extract `static/setup.js`; `ARCHITECTURE.md` codemap row |
| 2 | PR-B | `static/app.js` → `static/repertoire.js`; ARCHITECTURE.md row |
| 3 | PR-C | `static/app.js` → `static/traps.js`; ARCHITECTURE.md row |

### Widened api surface (Phase 1b, expose-only — internal hub calls stay direct)

Add to `api.actions` (or a new `api.hub` namespace): `syncBoard`, `postJSON`,
`refreshAnalysis`, `persist`, `setMode`, `setStatus`, `snapshotPlay()` /
`restorePlay(snap)` (canonicalizes the 5-field copy: `baseFen, moves,
moveQuality, moveRetro, cursor` — **`restorePlay` MUST default missing
`moveQuality`/`moveRetro` to `[]` and `cursor` to 0**: reload rehydrates a
legacy 3-field snapshot, and a strict reader crashes refresh-mid-setup →
Cancel → next move), `ensurePlay`, `registerModeHandlers(mode, {onMove,
exit})` (two positional args — mode string first, NOT an options object;
passing one object registers under key `undefined` silently) — the
dispatcher/teardown seam — plus the hub position/promotion
helpers trainers call: `isPromotion`, `askPromotion`, `positionFromFen`,
`positionAt`, `fenOf`, `lastMoveSquares` (refuter api-gap findings; never
duplicate these into modules).

**Snapshot seam, precise contract:**
- `snapshotPlay()` **returns** a 5-field snapshot object; trap/rep store their
  own copies (`studySnapshot`, `repSnapshot`) module-side.
- `restorePlay(snap)` applies a snapshot to state (with the `[]`/0 defaults
  above) — used by all trainers' exits.
- `playSnapshot` (setup's Cancel target) stays a hub variable because
  `persist()`/`restore()` serialize it; setup.js uses `getPlaySnapshot()` /
  `setPlaySnapshot(snapOrNull)` — set on `enterSetup`, read+clear on
  `cancelSetup`, discard (`null`) on `beginGame`.

### Dispatcher + teardown seam

`ground.events.after` keeps routing by `state.mode`, but looks up handlers
registered by modules (`registerModeHandlers`). `ensurePlay` stays in the hub
and calls registered `exit` handlers. Missing registration must fail loudly
(console.error + status message), never silently fall through to `onUserMove`.

### Module ownership after full split

**Extract by function name, never line range** — app.js interleaves hub play
controls (`undo`/`redo`/`goto`/`flip`/`reset`/`loadFen`, `renderAnalysis` etc.,
:490-632) inside the "setup" span, and `ensurePlay` inside the "repertoire"
span. Full function inventory: contracts doc, "Extraction inventory".

- **setup.js** (~170 ln + its init wiring): brush/palette/stamping, castling
  inference, enter/begin/cancel; owns `brush`; shares `playSnapshot` via hub
  seam (above).
- **repertoire.js** (~380 ln + wiring): tree render, jump, rep-practice,
  engine reply; owns `rep`, `repTree`, `repSnapshot`, `repEngineToken`.
  `ensurePlay` stays in the hub.
- **traps.js** (~657 ln + wiring): browse, live chip, watch, practice; owns
  `trap`, `trapsData`, `studyEvalToken` (whole — never split watch/practice),
  `trapsCheckToken`, `trapChipDismissedFen`, `studySnapshot`. May import
  `panel.js` directly (feature → leaf) for note rendering.
- **init() wiring moves too**: each module gets `initX(api)` owning its DOM
  listener block (setup :2100-2109, traps :2111-2138, rep :2143-2147).
- **hub (app.js)**: state, ground, bus, persistence (frozen localStorage keys
  + `playSnapshot`), position helpers, board sync, promotion, server calls +
  analysis tokens, onUserMove, play controls, opening detect, `ensurePlay`,
  review shim, init.

## Out of scope

Review shim stays in app.js; `review.js` / `insights.js` / all CSS untouched;
no behavior, UX, markup, or backend changes beyond the cache header; no TOC
comment (split supersedes it); no new tests framework.

## Constraints (from profile + contracts)

- Injected-api invariant: new modules never import app.js (hub → feature →
  leaf). Bus stays notification-only; imperative flows use direct api refs.
- Snapshot field parity via the canonical `snapshotPlay`/`restorePlay` helpers
  — no module hand-rolls the 5-field copy.
- localStorage keys frozen. Tokens-only CSS untouched.
- Commit policy: implemented + verified + reviewed; Conventional Commits;
  feature branches; fetch/status before branching.

## Verify-by (each phase, per `<profile.verify>`)

1. `.venv/bin/python -m pytest -q` passes (cache-header change has an API
   test touchpoint; frontend phases must not break backend suite).
2. `.venv/bin/ruff check app tests` clean (Phase 1a only touches Python).
3. Live browser via Playwright-MCP (user runs
   `uvicorn app.main:app --reload --port 8001`; real `page.mouse` drags —
   chessground rejects synthetic events):
   - **Phase 1:** enter setup → stamp/erase → set side → Begin Game (valid +
     invalid position) → Cancel restores prior game; refresh mid-setup
     persists; **refresh mid-setup → Cancel → make a move** (3-field legacy
     snapshot crash guard); response header `Cache-Control: no-store` on
     `/static/app.js`.
   - **Phase 2:** browse tree → Jump (undo steps back through line) →
     Practice: correct move, wrong-move snap-back, reveal, take-back, restart,
     engine handoff after prep ends → Return restores play snapshot.
   - **Phase 3:** browse + filter; chip appears/dismisses (sticky per FEN) /
     drill enters trap; watch stepper + variation picker; practice: auto-victim
     reply, snap-back, reveal, refutation; Return restores play snapshot.
   - **Cross-cutting every phase:** after Return-from-trainer, movelist
     quality tints + retrospective panel intact (snapshot parity guard); a
     play-mode move still gets analysis + quality label (dispatcher guard);
     no console errors.

## Refuter findings (folded)

Refuter verdict on draft: REJECT → all findings folded above. Summary:

- **HIGH** line-range extraction would rip hub play controls out (spec now
  mandates function-name inventory; contracts doc corrected).
- **HIGH** `ensurePlay` was inside the repertoire range — stays hub.
- **HIGH** `playSnapshot` shared + persisted — hub-owned, api seam added.
- **HIGH** legacy 3-field snapshot crash — `restorePlay` defaulting mandated;
  Playwright step added.
- **MED** api gaps (`isPromotion`, `askPromotion`, `positionFromFen`,
  `positionAt`, `fenOf`, `lastMoveSquares`) — added to widened api.
- **MED** hub target recomputed ≈900-1,000 (was 1,000-1,100).
- **MED** StaticFiles has no headers kwarg — middleware named; header test
  must be written (none exists).
- **LOW** init()'s ~44 lines of per-mode DOM wiring move with modules.
- **LOW** (defused) reload can't re-enter trainer modes — persist()
  early-returns for them; dispatcher fail-loud unreachable from reload.
- Baseline checks: pytest 549 passed; **ruff not installed in .venv**
  (configured in pyproject) — install before Phase 1a or verify without it.
