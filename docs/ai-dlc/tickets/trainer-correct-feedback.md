# Tickets — Blunder Drill correct-answer feedback

Spec: `docs/ai-dlc/specs/trainer-correct-feedback.md` · Contracts:
`docs/ai-dlc/contracts/trainer-correct-feedback.md`. One PR, two tickets,
strictly sequential. Single owner throughout (no parallel lanes — one file).

- [x] **C1 — solved pause in trainer.js.** In `handleVerdict()`: reword
  solved/solved_alt feedback to the "Correct! — …" forms, set the next-up
  teaser via `setNote`, set new phase `'solved'`, `showNextButton(true)`,
  drop `scheduleAdvance` from this path; widen `onNextClick` guard to
  accept `'solved'`; hide `trainer-reveal` on entering `'solved'` and
  re-show in `loadPuzzle()` (refuter MED); keep the `best_san || '?'`
  fallback in the solved_alt wording; update the FSM header comment
  ('advancing' = 404-skip only). No other behavior touched.
  Owned: `static/trainer.js`.
  **Done when:** full pytest green (untouched backend) and Playwright
  passes spec Verify-by items 1-6.

- [x] **C2 — ship.** Diff read (no debug artifacts), refuter on the diff,
  Conventional Commit on a feature branch, PR.
  Owned: git/PR only.
  **Done when:** PR open with verification evidence in the body; tickets
  ticked.
