# Contract map — app.js full split (setup.js / repertoire.js / traps.js)

Read-only scan of `static/app.js` (2,162 lines) ahead of the phased extraction.
Verified against source 2026-07-05 (post-PR #23; ARCHITECTURE.md exists).

## Invisible contracts

1. **Move dispatcher routes by mode** — `static/app.js:1971-1978`
   `ground.events.after` hard-routes every board move:
   `trap-practice → onTrapMove`, `rep-practice → onRepMove`, else `onUserMove`.
   `onUserMove` early-returns in trainer modes, so a mis-wired dispatcher makes
   trainer moves **silently do nothing** (no error, no snap-back). Each phase
   that moves a handler must re-wire this explicitly (module registers its
   handler through the api).

2. **Snapshot/restore field parity** — five near-identical blocks copy
   `{baseFen, moves, moveQuality, moveRetro, cursor}`:
   `enterSetup` (~:692), `enterTrap` (~:967), `startRepPractice` (~:1668),
   `enterReview` (~:1878), plus matching restores. Dropping one field (e.g.
   `moveRetro`) shows up only as a stale retrospective panel after a specific
   enter→exit sequence. No test guards this.

3. **Async token guards** — module-level counters drop stale responses:
   - `studyEvalToken` (:64) — shared by trap-watch **and** trap-practice
     (comment at ~:1088 says "shared with study" to cancel across mode
     switches). Moves wholly into traps.js in Phase 3; must not be split.
   - `trapsCheckToken` (:66) — live-chip `/api/traps/check` guard; traps.js.
   - `repEngineToken` (:75) — rep engine replies; self-contained; repertoire.js.
   - `analysisToken` / `analysisInFlight` / `analysisPending` (:78-80) — stay
     in the hub with `refreshAnalysis`.

4. **Cross-trainer teardown** — `ensurePlay` (:1570-1574) calls
   `exitTrap` / `exitRepPractice` / `cancelSetup` depending on mode. After the
   split these live in three different modules: each must register its exit
   with the hub, and `ensurePlay` stays in the hub dispatching to them.
   Also: the live trap chip's "drill" action enters a trap; `repJump` calls
   `ensurePlay` — cross-module entries all route through the api.

5. **Injected-api invariant** — `docs/ai-dlc/profile.md:29`,
   `ARCHITECTURE.md:69-71`: feature modules receive an injected `api` and never
   import app.js. Current surface built at :1994-2018
   (`undo/redo/flip/reset/goto/getState/getGround/closeAnyDialog/enterReview/
   exitReview/openGameAtPly` + `on`/`emit` + `mounts`). Must be **widened**
   (expose-only) before extraction: `syncBoard`, `postJSON`, `refreshAnalysis`,
   `persist`, `setMode`, snapshot/restore helpers, `ensurePlay`, `setStatus`.

6. **Event bus is fire-and-forget** — `on`/`emit` (:100-119) swallows handler
   errors (`try{fn()}catch(_){}`). Fine for notifications
   (`position:change`-style); **cannot** carry awaitable/cancellable flows
   (trap auto-play `setTimeout` loops ~:1235/:1764, rep engine replies).
   Extracted modules need direct function refs via api, not bus messages.

7. **Cache: bare sub-imports are unversioned** — `static/index.html:44-51`
   comment: only direct references get `?v=`; app.js's relative sub-imports
   are bare by design. New modules would be silently cacheable → resolved by
   serving `/static` with `Cache-Control: no-store` (Phase 1), which also
   retires the `?v=` bump ritual.

8. **localStorage keys frozen** — `chess-training:session:v1`,
   `chess-training:ui:v1` (ARCHITECTURE.md:103-105). `persist`/`restore` stay
   in the hub; extracted modules call them via api.

9. **Playwright verification needs trusted mouse** — chessground drags require
   real `page.mouse` events, not synthetic dispatches; app internals are
   module-scoped (memory: chessground-needs-trusted-mouse). Per-phase verify
   scripts must drive real drags; server runs outside the sandbox (user
   launches uvicorn on 8001 — sandbox blocks socket bind).

## Integration points / consumers

- `review.js` calls `api.actions.enterReview/exitReview/openGameAtPly`; it
  re-implements its own `postJSON` — untouched by this work.
- `refreshOpeningThenTraps` (:798-801) chains opening detect → trap chip;
  after Phase 3 the chip refresh is a traps.js function invoked by the hub.
- `movelist.js` / `panel.js` consume `api.actions.goto/getState` — unaffected,
  but regression-check tints/retro panel after trainer exits (contract 2).
- ARCHITECTURE.md codemap (`static/` table) — one new row per extracted module
  per phase; the api contract text (:69-71) is principle-level and stays valid.

## Extraction inventory (function names, NOT line ranges)

**Refuter correction:** app.js interleaves hub code inside the trainer spans —
the span :460-777 contains hub play controls (`renderAnalysis`,
`renderBookMove`, `renderSkipped`, `applyMoveResponse`, `setStatus` :490-533;
`undo`/`redo` :535-553; `goto`/`flip`/`reset` :555-591; `loadFen` :593-632),
and the span :1471-1856 contains `ensurePlay` (:1570-1574) which stays in the
hub. **Extract by function name, never by line range.**

- **setup.js** (~170 lines): `eventSquare`, `onBoardPointerDown`,
  `showSetupUI`, `updatePaletteActive`, `setTool`, `setSide`,
  `showSetupError`, `clearSetupError`, `emptyBoard`, `startPosition`,
  `enterSetup`, `enterSetupUI`, `exitSetupToPlay`, `expandRank`,
  `inferCastling`, `friendlyPosError`, `beginGame`, `cancelSetup`; owns
  `brush` (:63). **Shared:** `playSnapshot` (see contract 10).
- **traps.js** (~657 lines + wiring): `loadTraps`, `renderTraps`,
  `refreshTrapsAvailable` + chip render/dismiss, `buildTrap`, `enterTrap`,
  `populateVariationPicker`, `selectTrapVariation`, `applyTrapModeUI`,
  `toggleTrapMode`, `goToTrapStep`, `renderTrapStep`, `showTrapUI`,
  `exitTrap`, `startPractice`, `advancePractice`, `renderPracticeBoard`,
  `applyPracticeStep`, `setTrapInteractive`, `setTrapFrozen`, `onTrapMove`,
  trap-back/reveal/refutation helpers; owns `trap`, `trapsData`,
  `studyEvalToken`, `trapsCheckToken`, `trapChipDismissedFen`,
  `studySnapshot` (:64-70).
- **repertoire.js** (~380 lines + wiring): `loadRepertoire` (:1485),
  `renderRepertoireTree` (:1497),
  `repJump`, `repChild`, `repScopedChildren`, `repSetNote`, `repSetMove`,
  `repSetFeedback`, `showRepUI`, `repRenderBoard`, `repSetInteractive`,
  `repSetFrozen`, `repPlayApply`, `startRepPractice`, `repRestart`,
  `exitRepPractice`, `repAdvance`, `repEngineReply`, `onRepMove`,
  `revealRepMove`, `repBack`; owns `rep`, `repTree`, `repSnapshot`,
  `repEngineToken` (:72-75). **Excludes** `ensurePlay` (hub).
- **init() DOM wiring moves too** (~44 lines, :2099-2147): setup-toggle /
  begin-game / cancel-setup / palette (:2100-2109), traps filters/chip/bar
  (:2111-2138), rep controls (:2143-2147) — each block moves into its
  module's own `initX(api)`, mirroring `initPanel`/`initMovelist`.
  **Also:** the board-level brush listeners
  (`boardEl.addEventListener('mousedown'/'touchstart', onBoardPointerDown,
  capture)` at :2053-2054) sit OUTSIDE those blocks — they move into
  `initSetup(api)` with `onBoardPointerDown`.
- review shim: ~:1858-1948 (~90 lines) — **stays** in hub.
- hub remainder after full split: **≈900-1,000 lines** (refuter-recomputed).

## Additional contracts (refuter findings)

10. **`playSnapshot` is shared AND persisted** — unlike `studySnapshot`/
    `repSnapshot` (in-memory only), `playSnapshot` round-trips localStorage:
    hub `persist()` serializes it (:141) and `restore()` rehydrates it
    (:177-180), while `enterSetup`/`cancelSetup`/`beginGame` (setup.js)
    read/write it. Hub keeps ownership of the variable; setup.js accesses it
    only through api helpers (`snapshotPlay`/`restorePlay`/getter).

11. **Legacy 3-field snapshot on reload** — `restore()` rebuilds
    `playSnapshot` as `{baseFen, moves, cursor}` only (`moveQuality`/
    `moveRetro` are transient, never persisted). `cancelSetup` defends today
    with `snap.moveQuality || []` (:771-772). Any canonical `restorePlay(snap)`
    helper MUST default `moveQuality`/`moveRetro` to `[]` and `cursor` to 0,
    or refresh-mid-setup → Cancel → next move crashes on
    `state.moveQuality.slice(...)` (:439).

12. **Hub position/promotion helpers used by trainers** — `isPromotion` +
    `askPromotion` (used by `onTrapMove` :1330-1343 and `onRepMove`
    :1803-1808), `positionFromFen`, `positionAt`, `fenOf`, `lastMoveSquares`
    (used throughout the trap/rep ranges). All must be on the widened api —
    never duplicated into modules.

13. **StaticFiles can't set headers** — Starlette `StaticFiles` has no
    headers kwarg (init or file_response). The no-store header needs an
    `@app.middleware("http")` on paths starting `/static` (also covers the
    304 path). No existing test asserts static headers; one must be written.

14. **Reload cannot re-enter trainer modes** (defused hazard) — `persist()`
    early-returns for trap-watch/trap-practice/rep-practice/review
    (:129-132), so `restore()` only ever lands in `play` or `setup`; the
    dispatcher's fail-loud path can't fire from a reload race. Trap-watch and
    review boards also disable dragging, so `events.after` never fires there.

15. **traps.js note rendering may need `panel.js`** — resolve via direct
    feature→leaf import of `panel.js` (allowed: hub → feature → leaf), not an
    api addition. Confirm at Phase 3 implementation.
