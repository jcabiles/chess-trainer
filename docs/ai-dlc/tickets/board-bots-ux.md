# Tickets — board-bots-ux (V2 layout + bot rail + renames)

Spec: `docs/ai-dlc/specs/board-bots-ux.md` (refuted + revised).
Order: T1, T2 parallel → T3 → T4 → T5 → T6 → T7 → T8 (style.css single-owner
per ticket; sequential where shared).

## T1 — Persona display renames (backend, functional)
Rename display names + descriptions/style text for all 6 personas; ids/elos
unchanged. casey→Ming Ling, morgan→Diana, alex→Melvin, vera→Mandeep,
diego→Nina (attacking), robin→Amanda (sloppy).
- Files: `app/personas.py`, `data/personas.json`, `tests/test_personas.py`,
  `tests/test_bot_personas_api.py` (incl. PGN-name assert), stale comment
  mentions in `tests/test_bot_blunder_ladder.py`, `tests/test_bot_causal_api.py`.
- Accept: `pytest -q` green; `/api/bot/status` returns new names; grep finds no
  old display names outside git history/PGN data.
- Done-condition: `.venv/bin/python -m pytest -q` exits 0.

## T2 — Avatar serving + files (backend, functional)
`data/avatars/` gitignored; downscale user's 6 portraits to ≤320px into it
(rename by id per spec mapping: nina.png→diego.png, amanda.png→robin.png etc.);
BASE_DIR-relative StaticFiles mount at `/avatars` only-if-dir-exists,
registered before the root static mount.
- Files: `app/main.py`, `.gitignore`, `data/avatars/*` (untracked).
- Accept: `curl /avatars/casey.png` 200 with server up; app imports cleanly
  with dir renamed away; new test covers dir-absent import safety.
- Done-condition: pytest green incl. new test; `git status` shows no avatar
  files staged.

## T3 — Grid + board sizing + action column (design)
4-track grid closed / 5-track under `main.bot-rail-open`; action column
(Undo/Redo/Flip/Reset/Set up, IDs preserved, BOTH mode-gating mechanisms
verified); `--board-size: min(560px, calc(100dvh - <C>px))` re-derived; 480px
sweep by selector across style.css + trainer.css + both mobile reset blocks;
FEN row sole below-board chrome.
- Files: `static/style.css`, `static/trainer.css`, `static/index.html`
  (structure move of controls).
- Accept: board ≈560px @1440×900; no scroll @700px height; setup/trap/rep/
  trainer bars aligned to board width; all modes still hide the right controls.
- Done-condition: Playwright checks pass on live server; pytest unaffected.

## T4 — Panel rework + botplay relocation (design)
Panel ≈300px; E-style eval+moves card on top; `#botplay-block` moves from
board-col into panel below the card; green Play-vs-Bot pill (avatar thumb)
bottom-right of panel.
- Files: `static/index.html`, `static/style.css`, `static/panel.css`,
  `static/movelist.css` (if move-list styles shift).
- Accept: eval/moves render in card; botplay disclosure works in panel; pill
  visible in all tabs; review/analysis seams (`#analysis-review-col`,
  `#review-bar`) intact.
- Done-condition: Playwright: pill click toggles rail class; all six tabs
  render without layout breakage.

## T5 — Bot rail component + wiring (design + JS)
Rail markup + styles (N cards from `/api/bot/status`, 56px avatar + initials
fallback, name, rating, description blurb); card click syncs `#bot-persona`
select + change event; selection disabled during live bot game with hint;
`[hidden]` override; `botRailVisible` pref; z-index < 9000. Avatar click →
native `<dialog>` lightbox (full photo + name/rating caption; ×/backdrop/Esc
close; avatar files ≤1024px, one file for thumb + lightbox).
- Files: `static/botplay.js` (rail render + wiring), `static/index.html`
  (rail mount), `static/style.css` (rail styles).
- Accept: 6 cards render; click → persona picked → game starts vs it; mid-game
  clicks blocked w/ hint; missing avatar → initials; pref survives reload.
- Done-condition: Playwright script covering all five accepts passes.

## T6 — Mobile treatments (design)
≤820px: action column folds to horizontal row under board; rail becomes
fixed overlay sheet (scrim backdrop, ×/backdrop/Esc close, focus in-out,
reduced-motion guard); pill fixed bottom-right; ≤560px exact-fit math
re-verified.
- Files: `static/style.css` (media blocks), `static/botplay.js` (sheet
  focus/Esc handling).
- Accept: 375×700: board exact-fit unchanged, sheet opens/closes by all three
  paths, focus returns to pill; no horizontal scroll.
- Done-condition: Playwright at 375×700 + 820×900 passes.

## T7 — Theme + a11y pass (design)
Light-theme audit of every new component (tokens only — zero component-level
theme rules); `:focus-visible` on pill, cards, ×, action buttons; AA contrast
check on card text/blurbs both themes; reduced-motion on rail transitions.
- Files: `static/style.css` (tokens consumption fixes only).
- Accept: no raw hex outside token blocks (grep); contrast spot-checks pass;
  keyboard-only walkthrough completes.
- Done-condition: grep clean + design-reviewer a11y items pass.

## T8 — Review + gates (verification)
design-reviewer pass (1440 + 375, rail closed + open, both themes, graded
against spec); full pytest + ruff; hygiene sweep (no debug artifacts,
`.playwright-mcp/` removed); final screenshots for the report.
- Accept: design-reviewer verdict pass; all deterministic gates green.
- Done-condition: report delivered with screenshots; working tree clean of
  artifacts.
