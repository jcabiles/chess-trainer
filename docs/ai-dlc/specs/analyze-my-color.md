# Delta Spec — Skip Opponent Evaluation ("analyze my color")

Contracts: `docs/ai-dlc/contracts/analyze-my-color.md`. Frontend-led + a tiny `/api/move` assist.

## Problem (why)
Every move (both colors) and every navigation triggers a full `/api/move` (2 depth-pinned engine
analyses). On complex positions that's slow even after the reliability fix. The user plays a known
color and only cares about **their own** moves' quality (blunder-spotting), so the opponent's
analyses are wasted work.

## Goal (one line)
A persisted **Both / White / Black** toggle in the Analysis panel; when a color is selected,
Stockfish evaluates **only that color's moves** — the opponent's moves are skipped and shown as
"not evaluated". `Both` = today's behavior exactly.

## Locked decisions
- **Semantics A (pure skip):** analyze a position **iff it is the result of a move by the selected
  color**. After your move → quality + eval. Opponent moves → skipped when a specific color is set.
  (No eval/best-move hint while you're deciding — accepted.)
- **Cursor 0 is EXEMPT** (refuter [med]): the start position always shows its opening eval via
  `/api/analyze` regardless of `analyzeColor` — it's one cheap call (only on reset / go-to-start),
  it isn't "the opponent's move," and a "not evaluated" empty board reads as broken.
- **Explicit toggle** Both/White/Black, default **Both**, persisted in the existing
  `chess-training:ui:v1` ui-prefs key as `analyzeColor`. Board flip does NOT change it.
- Play mode only. Opt-in: `'both'` reproduces current behavior bit-for-bit.

## In scope

### `static/prefs.js` (NEW — refuter [high] #1)
- `readUiPrefs`/`writeUiPref` currently live **private inside `movelist.js`** (PR #4) — `app.js`
  can't call them. Extract both into a new `static/prefs.js` module (the existing error-safe
  read-merge-write on `chess-training:ui:v1`) and export them. Update `movelist.js` to import from
  `prefs.js` (replace its local copies — no behavior change). `app.js` imports from `prefs.js` too.

### `static/app.js`
- Import `readUiPrefs`/`writeUiPref` from `./prefs.js` + `renderSkippedPanel` from `./panel.js`.
  `analyzeColor = readUiPrefs().analyzeColor || 'both'` module var; helpers:
  - `shouldAnalyzeMove(moverColor)` → `analyzeColor === 'both' || moverColor === analyzeColor`.
  - `shouldAnalyzeCursor(cursor)` → `'both'` ⇒ true; `cursor === 0` ⇒ true (EXEMPT); else
    mover = `positionAt(cursor - 1).pos.turn`, return `mover === analyzeColor`.
- **`onUserMove`** (~376): `moverColor = before.pos.turn`; `doAnalyze = shouldAnalyzeMove(moverColor)`.
  Send `{ fen, move, useBook:true, analyze: doAnalyze }`. `moveQuality[cursor] = data.book ? 'book'
  : (doAnalyze ? (data.analysis?.quality || null) : null)`. Render: `if (doAnalyze)
  applyMoveResponse(data); else renderSkipped();` (NOT `applyMoveResponse(null)` — reads as error).
- **`refreshAnalysis`** (~325): skip-check INSIDE the `try`, AFTER the in-flight coalesce guard
  (refuter [high] #2): `if (!shouldAnalyzeCursor(state.cursor)) { renderSkipped(); setStatus('');
  emit('analysis:end'); return; }` — emit `analysis:end` so the feedback "Analyzing…" indicator
  clears (it listens to start/end); the `finally` resets the coalesce vars.
- **Toggle wiring** in `init()`: set the control to the saved value; on change → set the var,
  `writeUiPref('analyzeColor', value)`, `refreshAnalysis()`.

### `static/panel.js`
- Add+export `renderSkippedPanel()` (mirror `renderBookMovePanel`): `#eval`→`—`, `#best-move`/`#pv`
  →`—`, **`setEvalBar(50)`** (refuter [med] — else stale fill), quality slot → "Not evaluated ·
  opponent's move".

### `static/index.html` + `static/style.css`
- A `<select id="analyze-color">` (Both/White/Black) in the Analysis panel near `#engine-restart-btn`,
  labelled "Evaluate". Tokens-only CSS, `:focus-visible`.

### `app/models.py` + `app/main.py`
- `MoveRequest.analyze: bool = True` (additive). In `/api/move`, after the book fast-path (~303),
  before `note_interactive_start`: `if not req.analyze: return MoveResponse(legal=True,
  fen=fen_after, lastMoveSan=last_move_san, analysis=None)`.

## Out of scope
- Retroactively re-analyzing past plies on toggle change (forward-only; tints stay until revisited).
- setup / trap / rep / review modes; opening + traps checks (engine-free, keep running).
- Auto-following orientation; any change to `:session:v1` game-state shape; an engine opponent.

## Constraints
- `analyzeColor='both'` MUST be byte-for-byte today's behavior (regression-safe default).
- Server stays legality authority → live-play skip uses `/api/move analyze=false`.
- Tokens-only CSS, no raw hex; persist only via `chess-training:ui:v1`.
- Full suite green via the `get_engine` fake; verified in-browser before commit.

## Verify-by
1. **Backend (pytest):** `POST /api/move {analyze:false}` on a legal non-book move → 200,
   `legal:true`, `analysis:null`, engine NOT called (assert via the fake call-count); omitting
   `analyze` → unchanged 2-analysis behavior + quality.
2. **Browser, Both (default):** identical to today.
3. **Browser, White selected:** White move → quality + eval; Black move → "Not evaluated ·
   opponent's move", eval/best/PV cleared, **eval bar neutralized**, no engine call (network:
   `analyze:false` on play, no call on nav); **cursor 0 still shows the opening eval**; persists
   across reload; 0 console errors.
4. `pytest` green; `ruff` clean.
