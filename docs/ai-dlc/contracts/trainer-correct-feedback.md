# Contracts — Blunder Drill correct-answer feedback

Area: `static/trainer.js` solved/solved_alt path (+ possibly `app/main.py`
`/api/trainer/check` if coaching content is added server-side).

Mapped directly by the main session (module authored this session, contracts
fresh); no contract-mapper sub-agent spawned.

## Current behavior (the complaint's root cause)

Solved and solved_alt verdicts DO render feedback (`setFeedback(..., 'good')`,
`trainer.js:404-417`) — but phase goes to `'advancing'` and
`scheduleAdvance()` auto-advances after **`ADVANCE_DELAY_MS = 900`**. The
success message is on screen under a second; the failed/reveal path by
contrast parks in phase `'revealed'` with an explicit **Next** button. The
asymmetry is why success reads as "no feedback."

## Invisible contracts a fix must respect

1. **Phase machine** (`trainer.js` header): `moving → checking →
   advancing|revealed → summary`. `'advancing'` = timed auto-next;
   `'revealed'` = waits for Next click (`onNextClick` guards
   `phase !== 'revealed'`). Any "pause on correct" must either reuse
   `'revealed'`-style gating or extend the Next guard — otherwise the Next
   button is dead on the new pause state.
2. **checkToken staleness**: every async continuation (check reply, advance
   timer) is guarded by `token !== checkToken`. Return-mid-pause must keep
   invalidating; new timers/buttons must not bypass it.
3. **Outcome accounting**: `finishPuzzle(verdict)` already runs before the
   pause — one final outcome per puzzle, last resolution wins. Feedback
   changes must not add a second `finishPuzzle` call or alter outcomes.
4. **Server /check response** (`app/main.py:1125-1142`): `narration` is
   populated **only on `failed`** (both online and offline paths). Solved
   responses carry `verdict, attempted_san, best_san, cp_delta-ish fields`
   but NO coaching text. Any "why it works" content on success needs either
   a backend change or client-side composition from existing payload
   (bucket, severity, best_san, session progress).
5. **Reveal path reuses the same widgets** (`trainer-feedback`,
   `trainer-narration`, `trainer-next`): new success content must reset
   cleanly in `loadPuzzle()` (which clears feedback/narration/Next).
6. **CSS tokens-only** (profile invariant): any new styling in
   `trainer.css` uses design tokens, no raw hex; AA contrast;
   `:focus-visible` if new interactive controls.
7. **Stats side door**: `refreshTrainSection()` re-fetches the idempotent
   GET preview — safe to call anytime; `POST /session/start` and
   `/bucket-complete` are mutating — feedback work must not add calls to
   them.

## Integration points

- `static/trainer.js` — sole owner of drill UI (handleVerdict, revealCurrent,
  scheduleAdvance, onNextClick, loadPuzzle).
- `static/index.html` — drill bar markup (`trainer-feedback`,
  `trainer-narration`, `trainer-next`, `trainer-note`).
- `static/trainer.css` — drill bar styles.
- `app/main.py` + `app/models.py` — only if success narration is added
  server-side (TrainerCheckResponse schema).
- Tests: `tests/test_api.py` trainer cases (ScriptedEngine) if response
  shape changes; no backend change → no test change.
