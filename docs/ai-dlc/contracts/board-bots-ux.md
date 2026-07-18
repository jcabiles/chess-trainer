# UI Contracts — board/panel rebalance + bot rail (board-bots-ux)

Mapped 2026-07-17 by contract-mapper (read-only) ahead of the layout redesign:
board bigger / panel slimmer (Chess.com anchor), de-crowded controls, new
hidden-by-default right bot rail (avatar + name + rating), persona renames
(Cholocho 1350 / Diana 1550 / Melvin 1800 / Mandeep 2000).

## 1. Layout grid

- `static/style.css:262-270` — `main { grid-template-columns: auto auto minmax(280px, 1fr) }` — exactly **3 columns** (rail | board-col | panel). A 4th region (bot rail) requires extending this line or it overlaps/clips.
- `static/style.css:524-535` — `#panel-tabs` is a **direct child of `<main>`**, not `.panel`. Tab wiring is ID-based, so DOM location can move if IDs survive, but grid math must track wherever the rail sits.
- `static/style.css:276-288` — `.board-col { --board-size: min(480px, calc(100dvh - 240px)) }` — the `240px` is a hand-tuned reservation for chrome below the board. De-crowding controls invalidates it; most load-bearing number for "board bigger".
- `static/style.css:298-316` — `#eval-bar` (min-height) and `#board` (width/height) both consume `--board-size` — one var drives both; new sizing must keep both on one source or they desync.
- `static/style.css:1795-1808` (≤560px) — exact-fit formulas `calc(100vw - 54px)` / `calc(100vw - 32px)` encode 14px eval-bar + 8px gap + 32px padding. Changing any of those silently breaks phone fit (no test covers it).
- `static/style.css:1687-1742` (≤820px) — grid flattens to `1fr`; a new rail needs its own explicit mobile treatment or it disappears/breaks stack order.
- `static/style.css:429-433, 761-772, 1438-1443` — per-mode control hiding via `body[data-mode] #undo/#redo/...` ID selectors (mode set at `app.js:159`). Restructured controls must preserve IDs `#undo #redo #reset #setup-toggle .fen-row #fen-error`.
- **Six `width: 480px` literals** — `style.css:383, 437, 1113, 1383, 1582` + `trainer.css:100` (`.fen-row, .setup-bar, .botplay-block, .trap-bar, .rep-bar`) — hand-matched to current board cap; must move in lockstep with any new board width. Mobile override resets same six at `style.css:1810-1816`.

## 2. Design tokens

- `static/style.css:8-92` — single `:root` token block (surfaces, borders, text, accent, `--q-*` quality ramp, `--space-1..10` 4px scale, radii, shadows, scrim, motion).
- `static/style.css:103-155` — light theme = pure token override (`html[data-theme="light"]`); zero component-level theme rules. New components must consume tokens or they break in one theme.
- `static/index.html:16-28` — pre-paint theme script **duplicates** prefs key `chess-training:ui:v1` + `theme` field by design; hand-synced with prefs.js.
- `static/style.css:58-61, 153-154` — `--eval-bar-black/white` intentionally theme-invariant; do not retint.
- `static/style.css:1751-1759` — second token pocket: `--board-light/--board-dark` checkerboard colors live here, not in the top block.
- `:focus-visible` convention — `outline: 2px solid var(--accent)`, offset 1-2px (negative for inset elements like `#panel-tabs button`). New rail controls must replicate.

## 3. Panel show/hide + geometry

- `static/index.html:84-91` — tabs use `role="tab"`, `data-tab`, `aria-controls="tab-<name>"`; `app.js:1352-1371` keeps a **hand-maintained 6-tab array** that must match buttons 1:1.
- `static/style.css:584` — `[role="tabpanel"]:not(.is-active){display:none}` is the whole tab mechanism. Bot rail must NOT use `role="tabpanel"` or it gets swept into tab hiding.
- `static/style.css:593-599` — special modes hide `.tab-panel` but keep the tab strip. `bot-play` mode is NOT in the list; rail visibility during a bot game needs an explicit decision. Rail toggle must live outside `.tab-panel` to stay reachable in special modes.
- `app.js:1128-1135` — third show/hide pattern: ad-hoc `el.hidden` toggles by ID (`#review-bar`, `#analysis-review-col`).
- `setup.js:38-40` — **only geometry read in the frontend**: `boardEl.getBoundingClientRect()` per pointer event (click→square mapping). Safe under CSS resizes; breaks only if `#board` identity changes.
- No `ResizeObserver`/manual chessground resize anywhere — board sizing is **100% CSS-driven** via `--board-size`; chessground auto-adapts. CSS-only resize is safe, no JS sync needed.

## 4. Bot personas

- `app/personas.py:39-90` — `Persona` dataclass: `id, name, elo, style, description, temperature, blunderRate, threatDistance`. Ladder: casey/Casey/1350, morgan/Morgan/1550, alex/Alex/1800, vera/Vera/2000. `DEFAULT_ID="casey"` (line 77).
- `data/personas.json` — on-disk mirror; `_validate()` (`personas.py:135-153`) requires `DEFAULT_ID` present or the whole file is rejected.
- `app/main.py:585` — `BOT_PERSONA_LABEL` computed **once at import** from default persona name; rename needs restart to show.
- `app/main.py:876-893` — persona `name` baked verbatim into saved-game PGN white/black fields (`data/games.db`). **Rename does not retroactively update old games** — old games keep "Casey" etc. `id` is the durable key everywhere (localStorage `botPersona`, PGN `personaId`, ELO math via `personaElo` per `app/rating.py:1-33` — rename-safe for ratings).
- `app/main.py:788-806` — `GET /api/bot/status` → `{available, personaLabel, personas[8-field dicts], defaultPersonaId, maia}`; consumed by `botplay.js:310-333` (`populatePersonaPicker`).
- **No avatar field exists anywhere** in the schema (dataclass → JSON → validation → API → frontend). Avatar support = end-to-end addition; scope it up front.
- Frontend: `index.html:124,141-143` (`#botplay-persona`, `#bot-persona` select); `botplay.js:29,274-360` (catalog, picker, caption by `.id`). Styling `style.css:1135-1146, 1191-1231`; no image slot — rail is greenfield UI.
- Tests needing updates on rename: `tests/test_personas.py` (exact ids + `morgan.name=="Morgan"` line 68, elo asserts), `tests/test_bot_personas_api.py` (`personaLabel=="Casey"` line 84, **line 296 `g["black"]=="Alex"`** — name-in-PGN is test-covered/intentional). Persona-adjacent (mechanics only): test_bot_causal_api, test_bot_blunder_ladder, test_bot_engine_strength, test_bot_engine, test_bot_save, test_bot_api.

## 5. localStorage / prefs

- `static/prefs.js:1-16` — single key `chess-training:ui:v1`, flat object, `readUiPrefs()/writeUiPref()`. Known fields: theme, analyzeColor, engineSpeed, analysisMode, analysisPanelCollapsed, evalBarHidden, botPersona, takebackPolicy, chessComRating. Rail visibility belongs here (e.g. `botRailVisible`).
- `app.js:168, 240-342` — separate `chess-training:session:v1` for game/session state. Don't conflate: rail open/closed = UI pref, not session.
- `app.js:1475-1484` — collapse-persistence precedent (`analysisPanelCollapsed`): read-on-init → class toggle → write-on-change. Mirror it.

## 6. Shared-layout couplings

- `static/feedback.css:11-21` — `#toasts { position: fixed; top/right; z-index: 9000 }` — **only z-index in the tree**; toasts anchor top-right where a rail would live. Keep rail below 9000 + avoid horizontal collision.
- `index.html:475-492` — cmdk + promo picker are native `<dialog>` top-layer; always above any rail. Non-issue.
- `style.css:187-230` — header reserves a 68px gutter for the absolute theme toggle; pattern to copy if rail toggle lands in header.
- `style.css:642-647, 1355-1362` — **`[hidden]` gotcha**: `display:flex` elements need explicit `[hidden]{display:none}` override or the attribute no-ops. A "hidden by default" rail with flex/grid root hits this exact trap.
- No other viewport-level absolute/fixed overlays exist.

## Top 10 riskiest couplings

1. 3-column `grid-template-columns` (`style.css:265`) — highest blast radius line.
2. Six `width:480px` literals — miss one → misaligned sub-board bar.
3. `--board-size` 240px chrome reservation — invalidated by de-crowding controls.
4. Persona name baked into saved PGNs (`main.py:876-893`) — rename leaves historical mismatch (irreversible data shape; test-asserted).
5. Mobile exact-fit formula `calc(100vw - 54px)` — silent phone-fit break.
6. `--board-size` single-source for board + eval bar — keep both consumers on one source.
7. `#panel-tabs` outside `.panel` — structural surprise.
8. `[hidden]`-on-flex no-op gotcha — the rail's "hidden by default" will hit it.
9. `body[data-mode]` ID-based control hiding — preserve exact control IDs.
10. No avatar field in persona schema — plan it end-to-end, don't discover mid-build.
