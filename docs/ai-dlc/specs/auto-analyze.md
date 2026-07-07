# Delta spec — auto-analyze

**Goal (one line):** analysis of imported games starts automatically (import,
retag, per-game color change, startup, engine restart) so the manual
Analyze/Analyze-all buttons can be removed; only "Re-analyze" on done games
survives as an escape hatch.

Contracts: `docs/ai-dlc/contracts/auto-analyze.md`. Premise note: eval data is
already persisted (game_plies + pos_cache); this change is automation only.

## Files / interfaces to touch

Backend — `app/main.py` only (plus tests):
- Add a small helper (e.g. `_kick_auto_analysis()`). Guards, in order
  (refuter findings #2/#3 — both mandatory):
  1. **Env gate for ALL triggers:** return immediately when
     `CHESS_SKIP_ENGINE_AUTOSTART` is set. This is what keeps the pytest
     suite (which sets that var) from ever mutating the real `data/games.db`
     via TestClient lifespans that don't override `GAMES_DB`, and keeps the
     existing pending-status assertions in `tests/test_games_api.py`
     (`test_analyze_status_moves_off_pending`,
     `test_analyze_all_returns_pending_count`) race-free.
  2. **Up-front availability probe:** if `engine.is_running` is false,
     attempt the idempotent `engine.start()` (sync, no awaits ⇒ atomic on the
     event loop); on `EngineUnavailable` skip, log, games stay `'pending'`.
     `start_analyze_all` never raises synchronously — a try/except around it
     is dead code, and without this probe an unavailable engine makes
     `analyze_pending` walk the whole queue flipping every pending game to
     `'failed'`. The start() attempt (not a bare is_running check) matters
     because `engine.restart()` poisons the process and leaves lazy start to
     the next analyze — a bare check would make the restart trigger a
     silent no-op with the real engine.
  Then call `review.start_analyze_all(engine, depth=review.BACKGROUND_DEPTH)`
  — reuses the existing singleton task (second call while running is a
  no-op) and the existing no-starve yielding. No changes to `app/review.py`.
  Residual accepted: engine dying mid-run still fails in-flight games; the
  Retry button (below) is the recovery path.
- Call it from:
  1. `import_games` (POST /api/games/import) — after inserts, when the batch
     produced ≥1 game (imported or duplicate-backfilled) with status pending.
     Route gains an engine dependency in an import-safe way (resolve via the
     same `get_engine` seam; must not raise when binary absent).
  2. `retag_color` (POST /api/games/retag-color) — when `updated > 0`.
  3. per-game color update route (the one calling
     `storage.set_my_color` / resetting to pending) — after a successful
     change.
  4. `lifespan` — after `reset_stuck` + drop-folder import, when
     `storage.coverage()["pending"] > 0` (env gate already inside the helper
     keeps the test suite engine-free and fast).
  5. `restart_engine` (POST /api/engine/restart) — after a successful restart,
     when pending > 0.
- `POST /api/games/analyze-all` route: keep (harmless, used as internal seam
  and belt-and-braces), but it is no longer wired to any UI button. Per-game
  `POST /api/games/{id}/analyze` stays — it backs the surviving Re-analyze
  button.

Frontend — `static/review.js` only:
- Remove the "Bulk analyze" section: restructure `renderBulkControls()` to
  emit the retag section only; delete `triggerAnalyzeAll` wiring; prune the
  now-unused `review-bulk-progress` CSS class (refuter #5).
- Per-game action button (refuter #1 — 'failed' must stay recoverable):
  - `done` → "Re-analyze"
  - `failed` → "Retry"
  - `pending` / `analyzing` → no button (automation owns these states).
  Both labels use the existing `triggerAnalysis` path unchanged.
- Auto-polling: whenever the rendered game list contains any game with status
  `pending` or `analyzing`, start the status-polling interval (generalize the
  existing `_analyzeAllInterval` machinery); stop when none remain and show
  the existing "All games analyzed." toast once per run. Import success also
  (re)starts polling.
- Update empty/help copy that says "Import and analyze some games" →
  "Import some games" (analysis is automatic).

## Out of scope

No DB schema change; no depth configuration; no changes to the analysis
pipeline (`app/review.py` internals), insights, profile, or trainer; no
changes to `app/storage.py`.

## Constraints (from profile)

- Engine-free purity: full pytest suite passes with no Stockfish binary; the
  lifespan hook must skip under `CHESS_SKIP_ENGINE_AUTOSTART` and must not
  re-slow the suite (test-suite-speedup regression).
- One Stockfish process behind one asyncio.Lock — reuse `start_analyze_all`
  singleton; never spawn parallel per-game tasks.
- `engine.py` stays import-safe when binary absent; auto-kick is best-effort
  (log-and-continue), never a 5xx on import/retag.
- Frontend: review.js keeps its own fetch layer, never imports app.js;
  tokens-only CSS; :focus-visible preserved on surviving controls.
- Conventional Commits; feature branch; commit only implemented+verified+
  reviewed.

## Verify-by (what /verify-change checks)

1. `.venv/bin/python -m pytest -q` green, wall-clock in the ~20 s ballpark
   (no engine autostart in tests).
2. `.venv/bin/ruff check app tests` clean.
3. New API tests (each must monkeypatch `CHESS_SKIP_ENGINE_AUTOSTART` off AND
   isolate `GAMES_DB` — the helper's env gate means the default fixtures
   never exercise auto-kick): import with running fake engine ⇒ bulk task
   started (spy/flag); import with engine not running ⇒ 200, games stay
   `pending` (never `failed`), no crash; retag ⇒ task started; restart ⇒
   task started when pending. Existing tests
   (`test_analyze_status_moves_off_pending`,
   `test_analyze_all_returns_pending_count`) stay green unchanged — the env
   gate keeps auto-kick off under the default fixtures.
4. Browser (live server + Playwright): import a short PGN → status chip goes
   Pending → Analyzing… → Analyzed with zero clicks; toast fires; no
   "Analyze all" section present; "Re-analyze" visible only on done games.
