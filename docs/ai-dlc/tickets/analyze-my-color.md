# Tickets — Skip Opponent Evaluation ("analyze my color")

Spec: `docs/ai-dlc/specs/analyze-my-color.md`. Contracts: `docs/ai-dlc/contracts/analyze-my-color.md`.

**Shared contract (all tickets agree):**
- `static/prefs.js` exports `readUiPrefs()` and `writeUiPref(key, val)` (ui key `chess-training:ui:v1`).
- ui-pref field: `analyzeColor` ∈ `'both' | 'white' | 'black'` (default `'both'`).
- Toggle element id `#analyze-color` with the three values above.
- `panel.js` exports `renderSkippedPanel()`; `app.js` wraps it as `renderSkipped`.
- `MoveRequest.analyze: bool = True`; `/api/move` with `analyze:false` → `{legal, book, analysis:null}`, no engine.

**Orchestration:** T1–T4 touch disjoint files → ran as 4 parallel haiku agents. Then T5 (app.js
integration, sonnet) ∥ T6 (backend test, sonnet). T7 verify last.

| # | Ticket | Owned files | Done-condition | Deps |
|---|--------|-------------|----------------|------|
| T1 | Extract `readUiPrefs`/`writeUiPref` from `movelist.js` into new `static/prefs.js` (export both); update `movelist.js` to import them. | `static/prefs.js` (new), `static/movelist.js` | Collapse toggle (PR #4) still persists; no behavior change. | — |
| T2 | `MoveRequest.analyze: bool = True`; `/api/move` early-returns legal+null analysis (no engine) when `analyze:false`, after the book fast-path. | `app/main.py`, `app/models.py` | `analyze:false` → legal, null analysis, no engine call; omitted → unchanged. | — |
| T3 | `renderSkippedPanel()` in `panel.js` (clears eval/best/pv, `setEvalBar(50)`, "Not evaluated · opponent's move"). | `static/panel.js` | Clears panel + neutral bar + note. | — |
| T4 | `<select id="analyze-color">` (Both/White/Black) in the Analysis panel; tokens-only CSS. No JS. | `static/index.html`, `static/style.css` | Renders; no new raw hex. | — |
| T5 | `app.js` integration: imports; `analyzeColor` + `shouldAnalyzeMove`/`shouldAnalyzeCursor` (cursor 0 EXEMPT); gate `onUserMove` + `refreshAnalysis` (skip inside try after coalesce guard, emit `analysis:end`); wire `#analyze-color`. | `static/app.js` | Both=today; White/Black skips opponent plies (no engine call, neutral); persists. | T1,T2,T3,T4 |
| T6 | Backend test: `/api/move {analyze:false}` → legal, null analysis, engine NOT called (fake call-count); omitted → unchanged. | `tests/test_api.py` | `pytest -q` green incl. new tests. | T2 |
| T7 | Verify end-to-end (browser + pytest + ruff). | — | See spec Verify-by. | T1–T6 |

## Result
Shipped. 455 tests pass; ruff clean. Browser-verified: White-only → Black plies fire 0 engine
calls + "Not evaluated" + neutral eval bar; cursor 0 still shows opening eval; Both unchanged;
toggle persists across reload; 0 console errors. (T5 also fixed an `analysis:end` imbalance so the
"Analyzing…" indicator clears on a skipped position.)
