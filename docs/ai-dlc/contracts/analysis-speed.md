# Contracts — live analysis latency (analysis-speed)

Read-only scout of the move→eval pipeline, for the "faster Stockfish analysis display"
feature. Mapped 2026-07-11 by contract-mapper.

## 1. Request path: move → eval + quality label

- **Frontend trigger:** `onUserMove(orig, dest)` — `static/app.js:447`. Guards at
  `app.js:449-454` skip trap/setup modes. Computes `doAnalyze = shouldAnalyzeMove(moverColor)`
  (`app.js:483`, `77-80`). Single call:
  `postJSON('/api/move', { fen: fenBefore, move: uci, useBook: true, analyze: doAnalyze })` — `app.js:490`.
- Undo/redo/move-list nav re-analyze via `refreshAnalysis()` (`app.js:384-443`):
  cursor > 0 → same `/api/move` (`app.js:414-418`); cursor 0 → `/api/analyze` (`app.js:408-410`).
- **Backend:** `POST /api/move` — `app/main.py:381-466`. Response `MoveResponse`
  (`app/models.py:177-211`) with `analysis: Analysis | None` (`models.py:46-116`:
  evalCp, mate, evalWhitePov, bestMoveSan/Uci, pvSan[], quality, secondLine, retroBest, retroSecond).
- **Frontend consumption:** `applyMoveResponse(data)` — `app.js:577-580` → `renderBookMovePanel`
  or `renderAnalysisPanel` (`static/panel.js:269-333`). **Single JSON consumed atomically;
  no partial/incremental paint.**

## 2. Engine call parameters

| Constant | Value | Location |
|---|---|---|
| `ENGINE_THREADS` | 2 | `app/engine.py:51` |
| `ENGINE_HASH_MB` | 128 | `engine.py:54` |
| `DEFAULT_DEPTH` | 18 | `engine.py:57` |
| `INTERACTIVE_SOFT_TIME_S` | 3.0 (env `ENGINE_SOFT_TIME`) | `engine.py:64` |
| `ENGINE_HARD_TIMEOUT_S` | 8.0 (env `ENGINE_HARD_TIMEOUT`) | `engine.py:69` |
| `BACKGROUND_DEPTH` | 10 (env `REVIEW_BG_DEPTH`) | `app/review.py:85` |

- UCI options set once at start: `engine.configure({"Threads": 2, "Hash": 128})` — `engine.py:201`.
  No global MultiPV/Skill; `multipv` passed per-call (`engine.py:335`).
- Interactive `/api/move`: `Limit(depth=18, time=3.0)`, multipv=2 —
  `analyze_interactive_multi` (`engine.py:441-477`), called `main.py:440-441`.
- `/api/analyze`, `/api/load`: same limit, multipv=1 — `engine.analyze` (`engine.py:506-570`),
  called `main.py:356`, `main.py:370`.
- Background review: `Limit(depth=10)` depth-only, no time cap — `analyze_multi`
  (`engine.py:377-412`), called `review.py:313` (multipv=2) + `review.py:461` (threat probe).
- Hard watchdog 8.0s wraps every call (`_run_analyse`, `engine.py:349-351`); breach poisons
  engine (`_poison`, `engine.py:251-288`).

## 3. Engine calls per user move (latency budget)

| Path | Engine calls | Limit each | multipv | Notes |
|---|---|---|---|---|
| `/api/move` normal analyzed move | **2 sequential** (before, after) | depth=18, soft 3.0s | 2 | `main.py:440-441` |
| `/api/move` book move | 0 | — | — | EPD-set lookup `app/book.py:207-223`, checked before engine `main.py:412` |
| `/api/move` analyze=false | 0 | — | — | `main.py:427-433` |
| `/api/analyze` / cursor-0 refresh | 1 | depth=18, soft 3.0s | 1 | `main.py:356` |
| Review per ply (cache miss) | 1 (+1 threat probe on mistake) | depth=10, no cap | 2 / 1 | `review.py:313`, `461` |

Worst case: 2 × 3.0s soft cap = ~6s per move before watchdogs. No engine "reply move" step
exists (play-both-colors app).

## 4. Serialization / lock contention

- All engine access behind one `asyncio.Lock` (`engine.py:170`, acquired `engine.py:323`).
- The two `/api/move` calls acquire/release separately — a background review chunk can
  interleave BETWEEN before-call and after-call, adding one ~50-200ms depth-10 call.
- No-starve seam: `review.note_interactive_start/end` (`main.py:435/445`,
  `review.py:103, 111-127`); background loop checks counter only BEFORE issuing a new
  call (`review.py:281-286`, `451-453`) — interactive can still queue behind one
  in-flight background call (`review.py:38-45`).

## 5. Frontend display contract

- **No SSE/WebSocket/streaming anywhere** (grep confirmed). Single fetch → `res.json()`
  (`postJSON`, `app.js:371-382`) → synchronous paint.
- `analysisToken` (`app.js:65`) monotonic staleness guard — bumped `app.js:394, 535, 1102, 677`;
  stale fetches dropped `app.js:410, 419, 432`. `moveToken` (`app.js:70`) separately guards
  the history-write path (`app.js:463-465`).
- Eval toggle (`evalEnabled`, `app.js:75`): off → `refreshAnalysis` short-circuits and
  freezes panel (must NOT `renderSkipped()`, `app.js:404-406`); `onUserMove` still
  round-trips for legality with `analyze:false`.
- Book fast-path: client always sends `useBook:true` from play mode; server checks book
  before engine.

## 6. Eval caching

- **No server-side cache on interactive path** — every `/api/move`/`/api/analyze` hits engine fresh.
- `pos_cache` (SQLite) is background-review-only, keyed `(epd_key, depth)`
  (`review.py:301-330`); depth-10 entries can't serve depth-18 requests — no promotion.
- `state.moveRetro[]` (`app.js:54`) is a per-move-index retro-block carry, not a FEN→eval
  cache. Undo→redo re-fetches from engine.

## 7. Config surface for a latency feature

- Env vars: `STOCKFISH_PATH`, `ENGINE_SOFT_TIME`, `ENGINE_HARD_TIMEOUT`, `REVIEW_BG_DEPTH`,
  `CHESS_SKIP_ENGINE_AUTOSTART`, `BOOK_FILE`. **No env/request field for interactive
  depth or multipv** — `DEFAULT_DEPTH=18` is a constant; multipv=2 hardcoded at `main.py:440-441`.
- Natural slider home: `static/prefs.js` (`readUiPrefs`/`writeUiPref`,
  `chess-training:ui:v1`) — the `analyzeColor` precedent (`app.js:72`, `1075-1083`).
  Would need new fields on `MoveRequest`/`AnalyzeRequest` (`models.py:122-148`) threaded
  into `main.py:440-441`.
- Eval toggle is deliberately session-only (`app.js:73-74`); `analyzeColor` is persisted —
  new setting must pick a precedent.

## 8. Other latency contributors

- **Lazy engine restart spike:** after `_poison()` or `/api/engine/restart`
  (`main.py:478-494`), next `/api/move` pays full Stockfish launch inside the lock
  (`engine.py:189-190`, `324-325`).
- Background-loop poll interval 0.05s (`review.py:89`) — governs yielding only.
- Book probe negligible (in-memory set). No CDN calls on the move path.

## Invisible contracts a speed change could break

1. **Matched-limit cpLoss contract** — `classify()`/`cp_loss()` (`app/analysis.py:102-152`)
   assume before/after evals searched to the SAME limit (`analysis.py:105-109`,
   `engine.py:46-47`). Mixed-depth pairs silently corrupt every quality label.
2. `_run_analyse` list-normalization (`engine.py:334-339`) — preserve `infos[0]` assumptions.
3. **White-POV normalization is universal** — any new fast-path returning raw engine scores
   must still route through `pov_score_to_white_cp`/`.white()`.
4. **The lock is the ONLY serialization** — `asyncio.gather` on before/after gains nothing
   (serializes on lock); bypassing the lock corrupts UCI state (`engine.py:16-20`).
5. `note_interactive_start/end` must stay paired in try/finally (`main.py:435-445`) —
   an unpaired increment starves the review loop forever.
6. `analysisToken`/`moveToken` guards are load-bearing (PR #43/#44) — caching/partial
   delivery must still route through them.
7. **Frontend expects ONE atomic JSON** — `renderAnalysisPanel` reads quality/pvSan/
   secondLine/retroBest at once (`panel.js:269-333`); partial delivery needs a new
   response shape + render rework.
8. `useBook` is per-request opt-in — trap practice relies on full analysis in book
   positions (`models.py:134`); don't flip book-skip on server-side by default.
9. `pos_cache` is depth-keyed and background-only — naive reuse serves depth-10 evals
   into the quality pipeline with no error.
10. `Analysis` schema carries **no depth field** (`panel.js:315` reads `a.depth`
    defensively but `_build_analysis` never sets it) — variable-depth features need a
    schema addition for the UI to show/reason about depth.
