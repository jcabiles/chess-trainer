# Spec — Blunder Drill correct-answer feedback

**Goal (one line):** a correct answer in the Blunder Drill pauses on a
persistent "Correct!" message with a next-up teaser and waits for the Next
button, instead of flashing green for 900 ms and auto-advancing.

Contracts: `docs/ai-dlc/contracts/trainer-correct-feedback.md`.
Follow-up to the Blunder Trainer epic (`specs/blunder-trainer.md`).

## Behavior delta

On `verdict === 'solved' | 'solved_alt'` in `handleVerdict()`
(`static/trainer.js`):

1. Board still plays + highlights your move (unchanged).
2. Feedback (good/green, persistent):
   - solved: `Correct! — {attempted_san} is the engine's move.{offNote}`
   - solved_alt: `Correct! — {attempted_san} holds the position (best was
     {best_san}).{offNote}` (keep today's `|| '?'` fallback when best_san
     is absent — trainer.js:410; only the wording changes)
3. Note line (`setNote`) teases what's next:
   - more puzzles remain: `Next: {bucketLabel(nextPuzzle.bucket)}`
   - last puzzle: `Last one — Next shows your session summary.`
4. New phase **`'solved'`**: Next button shown; NO auto-advance timer on
   this path. `onNextClick` guard widens to
   `phase !== 'revealed' && phase !== 'solved'` → return.
5. **Hide the Reveal button** (`trainer-reveal`) on entering `'solved'`
   (refuter MED: the pause is now indefinite, and Reveal there is a
   silent no-op that looks live); re-show it in `loadPuzzle()`. Mirror
   the `showNextButton` toggle idiom.
6. Update the FSM header comment: `'advancing'` now applies only to the
   vanished-puzzle skip (404) path, which keeps its timed auto-advance.

## Unchanged (explicit)

- Wrong-answer flow (retry-once → reveal), manual Reveal, outcome
  accounting (`finishPuzzle` already runs before the pause; still exactly
  once, last resolution wins), bucket-complete flush, server API and
  schemas, `ADVANCE_DELAY_MS` (still used by the 404-skip path),
  checkToken semantics (success path now has NO timer to guard, which only
  removes a race), Return-mid-pause exit (exitTrainer already
  invalidates + flushes; a pending 'solved' outcome is already recorded).

## Out of scope

Coaching tips / focus guidance, Insights pointers, backend narration on
solved, keyboard shortcut for Next, any change to `app/` or tests.

## Constraints

- `static/trainer.js` is the only JS file touched; no new files expected
  (reuse existing `trainer-feedback`, `trainer-note`, `trainer-next`
  widgets — likely zero markup/CSS change; if any style is needed it goes
  in `trainer.css`, tokens-only, AA contrast).
- Frontend module keeps injected-api discipline (no app.js import).
- No mutating trainer endpoints added to the feedback path.

## Verify-by

`.venv/bin/python -m pytest -q` green (no backend change → suite must stay
green untouched). Playwright real-mouse on live :8001 server:
1. Solve a puzzle correctly → "Correct!" + teaser persist indefinitely;
   Next button visible, Reveal button hidden; no auto-advance.
2. Click Next → next puzzle loads (feedback/note/Next reset).
3. Miss once, solve on retry → same Correct! pause (retry path shares
   handleVerdict).
4. Solve the LAST puzzle → teaser says summary; Next → session summary.
5. Return mid-"Correct!"-pause → play game restored, movelist tints back,
   no console errors; bucket outcomes flushed once.
6. Wrong-answer flow regression: fail twice → reveal + narration + Next
   still work.
