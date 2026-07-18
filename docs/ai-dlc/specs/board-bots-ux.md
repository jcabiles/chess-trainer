# Delta spec — board/panel rebalance + bot rail + persona renames (board-bots-ux)

Status: REFUTED + REVISED (Claude refuter fail→fixed; Codex gpt-5.6-sol 12 findings
folded). Winner mockup: **V2** (side action column + push rail), selected
2026-07-18 after two divergence rounds. Mockup ref: scratchpad
`mockups/mockup-v2.html` (throwaway; not committed).

**Sequencing note:** the working tree currently carries UNCOMMITTED
`feat/bot-difficulty-roster` work (6-persona catalog: adds diego/robin @1350 +
`mistakeRate`). This spec is written against that 6-persona reality. Build order
vs that branch = Gate-2 decision.

## Design commitment (Gate 1, confirmed)

- Purpose: local Stockfish training app; play surface shows position + eval at a
  glance. Bots are becoming a central feature.
- Aesthetic: keep current **Nocturne** (existing tokens, light + dark, dark
  primary, subtle motion, WCAG 2.2 AA). Anchor: Chess.com analysis view — board
  dominant, panel slim.
- Fixes: panel too wide; board too small; controls crowded → spread out, grouped.
- Scope: play surface + shell; other tabs inherit shell, keep internals.
- Breakpoints: 1440 primary, 375 mobile.
- Anti-goals: no re-theming, no raw hex, no new fonts/CDN.

## Winning layout (V2)

Grid tracks at 1440 — **closed rail (4 tracks):**
`tab-rail | board-col | action-col | panel(≈300px)`
**open rail (5 tracks):** `tab-rail | board-col | action-col | panel | bot-rail(≈300px)`
Rail enters/leaves via a class on `<main>` (e.g. `main.bot-rail-open`), NOT DOM
surgery; `grid-template-columns` gains the 5th track under that class
(coupling #1; Codex #2).

1. **Left tab rail** — unchanged IDs/roles (`#panel-tabs`, `#tab-btn-*`).
2. **Board** — `--board-size: min(560px, calc(100dvh - <C>px))` where `<C>` is
   re-derived from the NEW below-board chrome (FEN row only — see #4/#6); the
   dvh term keeps guarding short viewports (refuter L5). `#board` + `#eval-bar`
   stay on this single source (coupling #6). Open rail: board may shrink ≈40px
   via the grid track math — acceptable, no overlap.
3. **Action column** — NEW narrow vertical stack between board and panel:
   labeled buttons **Undo, Redo, Flip, Reset, Set up** (icon+text, ≥40px,
   uppercase "BOARD" caption). Existing IDs preserved
   (`#undo #redo #flip #reset #setup-toggle`). BOTH mode-gating mechanisms
   preserved: `body.setup-mode`/`.trap-*-mode`/`.rep-mode`/`.trainer-mode`
   class rules (style.css:429-433, 761-772, 1438-1443; trainer.css:165-171)
   AND `body[data-mode] .tab-panel` rules (style.css:593-599) (Codex #7).
   `#setup-toggle` keeps its `[hidden]` override behavior (Codex #8).
4. **FEN row** — slim `input + Load` under the board (`.fen-row`/`#fen-error`
   preserved). This is the ONLY below-board chrome after this change.
5. **Right panel ≈300px** — top: E-style card (eval `+0.30` + `BEST NOW d4`
   chip + best line/depth + MOVES 2-col list). Existing panel seams below.
6. **Play-vs-Bot block relocates** — `#botplay-block` (persona row, color,
   rated, takeback, ELO readout, status, action buttons) MOVES from
   `.board-col` into the panel, below the eval/moves card (refuter H2;
   Codex #5). Its `#bot-persona` select remains (fallback + the value
   `startGame()` reads — see #8). Board-col chrome claim (#4) is now true.
7. **Play-vs-Bot pill** — green pill w/ avatar thumbnail, bottom-right of the
   panel column (mock-C). Toggles the bot rail.
8. **Bot rail** — hidden by default; open = 5th grid track (~300px), pushes,
   never overlays. Header "Bots" + ×. **One card per persona from
   `GET /api/bot/status` (currently 6) — NEVER hardcode count** (refuter H1;
   Codex #1). Card: 56px avatar, name, rating below name, blurb =
   `persona.description`. Selection wiring (Codex #3): clicking a card sets
   `#bot-persona` select value + fires its change handler (so
   `prefs.botPersona`, caption, ELO readout all update through the existing
   path), highlights the card. **During a live bot game the rail is
   visible but selection is disabled** (matches existing picker lock,
   botplay.js:334-360) with a "finish or resign first" hint (Codex #6).
   Root element: explicit `[hidden]{display:none}` override (coupling #8).
   No `role="tabpanel"`. Toggle pill lives outside `.tab-panel`. z-index
   below toasts' 9000; rail is in-flow (grid track) so no collision (§6).
   Visibility persisted as ui-pref `botRailVisible`
   (read-on-init → class toggle → write-on-change, app.js:1475-1484 pattern).
   **Avatar lightbox:** clicking a card's avatar photo (not the card body)
   opens a native `<dialog>` (same top-layer pattern as `#promo-dialog`/cmdk)
   showing the full photo + name/rating caption; closes via ×, backdrop click,
   or Esc. Avatar files ship at ≤1024px — one file serves both the 56px thumb
   (CSS-sized) and the lightbox.

## Mobile (≤820px and ≤560px) — explicit treatment (refuter M3; Codex #4, #9)

- **Action column** does not exist at ≤820px: buttons fold back into a
  horizontal row under the board (current mobile pattern), FEN row below.
- **Bot rail** at ≤820px: NOT a grid track. Full-screen overlay sheet:
  `position:fixed; inset:0`, backdrop `var(--scrim)`, sheet panel from right at
  ~min(320px, 90vw). Close: × button, backdrop click, Esc. Focus moves into
  sheet on open, returns to pill on close (AA). Sits below toasts (z-index
  <9000). Reduced-motion-guarded slide.
- **Pill** at ≤820px: fixed bottom-right, above content, below toasts.
- ≤560px exact-fit board formulas unchanged (overlay rail never affects board
  width); re-verify `calc(100vw - 54px)` / `- 32px` math after any eval-bar/gap/
  padding change (coupling #5).

## Persona renames (functional, /ai-dlc side)

Display **names + descriptions/style text only** — internal ids stay stable
(durable key: localStorage, PGN `personaId`, ELO math; contract §4).
**6 personas** (roster branch reality; refuter H1):

| id     | old    | new       | elo  | style tag |
|--------|--------|-----------|------|-----------|
| casey  | Casey  | Ming Ling | 1350 | kid prodigy |
| diego  | Diego  | Nina      | 1350 | attacking |
| robin  | Robin  | Amanda    | 1350 | sloppy |
| morgan | Morgan | Diana     | 1550 | focused student |
| alex   | Alex   | Melvin    | 1800 | casual crusher |
| vera   | Vera   | Mandeep   | 2000 | calm veteran |

Touch: `app/personas.py` built-ins, `data/personas.json`, tests
(`test_personas.py`, `test_bot_personas_api.py` name asserts incl. the
PGN-name assert), stale name mentions in comments/docstrings of
`test_bot_blunder_ladder.py`, `test_bot_causal_api.py` (Codex follow-up).
Accepted: already-saved games keep old display names (coupling #4);
`BOT_PERSONA_LABEL` refreshes at restart.
**Sweep by content/selector, not by line numbers — they drift** (refuter M4).

## Avatars (functional)

- Files: `data/avatars/<personaId>.png` (user-supplied AI portraits, ≤320px).
  Source: `~/Desktop/chess personas/` — **file↔id mapping** (photos named by
  display name, files keyed by id; casey's photo is still `cholocho.png` on
  Desktop — the Ming Ling rename is display-only): cholocho.png→casey.png,
  diana.png→
  morgan.png, melvin.png→alex.png, mandeep.png→vera.png, nina.png→diego.png,
  amanda.png→robin.png. Gitignore: add `data/avatars/` entry. Personas without
  a file fall back to initials.
- Serving (normative, Codex #12): `AVATARS_DIR = BASE_DIR / "data" / "avatars"`
  following main.py's existing path convention; mount
  `app.mount("/avatars", StaticFiles(directory=...))` ONLY if the dir exists
  (import-safe), registered BEFORE the root static mount so `/avatars` isn't
  shadowed; verify actual mount order in app/main.py:1900-1914 at
  implementation.
- No persona-schema change: URL derived from id; frontend `<img>` +
  `onerror` → initials circle (tokens-only).

## Constraints (invariants + remaining couplings)

- Tokens-only CSS, both themes, AA, `:focus-visible` (2px accent outline) on
  every new control; `--eval-bar-*` theme-invariant.
- **480px sweep by selector, both files**: `.fen-row`, `.setup-bar`,
  `.botplay-block`, `.trap-bar`, `.rep-bar` (style.css) **+ `.trainer-bar`
  (trainer.css:100)**, plus BOTH mobile reset blocks (style.css:1810-1816 AND
  trainer.css:178-181) (coupling #2; Codex #11). New width source: one CSS var
  tied to board width.
- Setup/trap/rep/trainer bars: verify they fit in the new board-col width at
  1440 (they follow board width; refuter check).
- Frontend modules injected-`api` only; no app.js imports. Server stateless
  except review. No DB schema change. Never commit `data/`.

## Out of scope

Other tabs' internals; bot strength/behavior changes (that's the roster
branch); Maia; clocks (B7); committing avatar photos; retroactive PGN renames.

## Verify-by

- `pytest -q` green (renames covered; avatar mount import-safe test — incl.
  dir-absent case). `ruff check app tests` green.
- Browser (Playwright, live server): board ≥560px at 1440×900 closed; no
  board scroll at 700px height; rail open/close + persistence + mid-game lock;
  card click → select syncs → game starts vs chosen persona; avatar fallback
  (missing file → initials); 375px: action row fold, overlay sheet, Esc close.
- `design-reviewer` pass: play surface, 1440 + 375, closed + open rail, both
  themes, graded against this spec.
- No raw hex outside token blocks; no debug artifacts.
