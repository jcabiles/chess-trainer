# Tickets — B6: Takeback control

Spec: [`../specs/takeback.md`](../specs/takeback.md).
Branch: `feat/takeback` off up-to-date main.
Wave plan (disjoint owners): **W1:** T1 ∥ T2 → **W2:** T3 (needs T1+T2) →
**W3:** T4 verify → T5 review → T6 close-out. Frontend-only (no server change).

## T1 — `static/app.js` `botTakeback()` + descriptor field (W1) — HOTSPOT
Add `takebacksUsed` (int, default 0) to `botGame` at ALL THREE shape sites
(`botSetGame ~436`, `persist ~183`, `restore ~283`; legacy/restore defaults 0).
New hub method **`botTakeback()`**: if `movesUci.length < 2` → return `null`;
else slice `movesUci` to `len-2`, set cursor, **mirror into
`state.moves`/`state.cursor`** (as `botAppendMove`), `++takebacksUsed`, if
`rated` was true set it false + `flippedToCasual=true`, **bump
`moveToken`+`analysisToken`**, re-render with a full `syncBoard`-style
`ground.set` (position + turnColor + lastMove), `persist()`. Return
`{takebacksUsed, rated, flippedToCasual}`. Expose on the hub.
- **Owns:** `static/app.js`
- **Done:** `node --check` clean; `pytest -q` still green; reasoning trace proves
  lockstep (botGame↔state) after truncation, correct turnColor re-render, tokens
  bumped, field on all 3 sites, `<2` plies → null, legacy default 0.

## T2 — takeback UI elements (W1)
`static/index.html`: `<select id="bot-takeback-policy">` (Never / Up to 3 /
Anytime) in `#botplay-body` near persona/rated; `<button id="botplay-takeback"
hidden>` in `.botplay-controls`; `#botplay-takeback-count` label +
`#botplay-takeback-note` (hidden). `static/style.css`: token-only, both themes.
**Stable ids are contracts for T3.**
- **Owns:** `static/index.html`, `static/style.css`
- **Done:** elements render with exact ids; button + note default `hidden`;
  token CSS both themes; `pytest -q` green (sanity).

## T3 — `static/botplay.js` policy + guard + handler (W2, after T1+T2)
Read/persist `takebackPolicy` via `prefs.js` (allowlist, default "three",
normalize on read); wire the selector locked mid-game (persona-picker idiom).
`canTakeback()` = `!busy && user's turn && !result && movesUci.length>=2 &&
policy allows (three → used<3, never → false, anytime → true)`. `takeback()`
handler → `hub().botTakeback()`, restore user dests, **`hub().refreshAnalysis()`**
(re-eval the rewound position — token bump only drops, doesn't fetch),
`reflectControls()`. `reflectControls()` also sets the button `hidden =
!canTakeback()`, the counter text, and the note `hidden = !(takebacksUsed>0 &&
!rated)` (derived from descriptor → survives refresh). Do not disturb
busy/replyToken/save-triggers/persona.
- **Owns:** `static/botplay.js`
- **Done:** `node --check` clean; `pytest -q` green; reasoning trace covers each
  policy, the rated flip + note, turn detection both colors, no busy wedge.

## T4 — Browser verification (W3)
Spec Verify-by-2 matrix: up-to-3 rewinds a full pair + counter + 4th blocked;
counter resets on new game; never hides the control; anytime unlimited; selector
locked mid-game + persists across reload; **rated game → takeback flips to casual
→ saved `{"rated":false}` → excluded from `/api/rating`**; bot replies still work
after a takeback (no wedge). `pytest`/`ruff`/`node --check` green.
- **Done:** every matrix item observed; test games cleaned from the DB.

## T5 — Dual review of the diff (W3, after T4)
Refuter + Codex (gpt-5.6-sol; diff-stage may infra-fail → refuter-only fail-open):
lockstep/re-render, busy safety, rated-flip → ELO exclusion, shape agreement,
no undo() regression, no server change. Fold findings; re-verify.
- **Done:** resolved/accepted; suite green.

## T6 — Close-out (W3, after T5)
User pass/fail → mark B6 `[x]` (**Phase A complete**) + note Phase B (B5/B7)
needs a user re-up; `pytest`/`ruff`; commit; push; PR.
- **Done:** PR open; Phase A flagged complete.

## Notes
- Live-reload hazard: one feature branch, never switch mid-work under uvicorn --reload.
- Appetite guard (~1 day): if over, cut order — the "no longer rated" note polish →
  the anytime counter. Never cut: lockstep+re-render correctness, !busy guard,
  rated→casual flip (ELO integrity), counter reset on new game.
