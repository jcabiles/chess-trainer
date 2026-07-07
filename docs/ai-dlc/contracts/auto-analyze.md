# Contracts — auto-analyze (kill manual Analyze/Re-Analyze friction)

Scanned 2026-07-07 for intent: "persist eval data ahead of time so Stockfish
never re-analyzes; drop Analyze/Re-Analyze buttons."

## Fact check on the premise

Evals **are already persisted**. Nothing in the Review tab replay hits the
engine live:

- `app/storage.py` — `game_plies.eval_cp_white` etc. stored White-POV at write
  time; `pos_cache` table is an EPD+depth-keyed eval cache.
- `app/review.py:303` — `analyze_game` checks `storage.get_pos_cache(epd_key,
  depth)` before calling the engine; re-analysis of an already-seen position
  at the same depth is a cache hit, not engine work.
- `static/review.js:529` — replay loads `/api/games/{id}/review` (pure SQLite
  read). No live `/api/analyze` calls during replay.

**The real gap is automation, not persistence:** import inserts games as
`analysis_status='pending'` and nothing starts analysis until the user clicks
per-game "Analyze" or "Analyze all pending".

## Contracts / integration points a change must honor

1. **Import route has no engine dependency** (`app/main.py:542`
   `import_games`). Auto-triggering analysis there means adding
   `Depends(get_engine)` — must stay import-safe when the Stockfish binary is
   absent (`EngineUnavailable`), and must not break the engine-free pytest
   suite (fixtures use the `get_engine` fake seam and skip engine autostart).
2. **Single background task discipline** — `review.start_analyze_all` is a
   singleton (sentinel key in `_tasks`; second call is a no-op). Auto-trigger
   should reuse it, never spawn parallel per-game tasks.
3. **No-starve rule** — background analysis yields to interactive `/api/move`
   via `review.note_interactive_start/end`. Reusing `start_analyze_all`
   preserves this for free.
4. **`retag-color` resets matching games to `pending`** (app/main.py:619) and
   relies on "the next bulk-analyze pass" — today that pass is manual. Same
   for per-game color change (`storage.py:525` resets to pending).
5. **Startup** — `storage` resets stale `'analyzing'` → `'pending'`
   (storage.py:353). Drop-folder (`data/games/`) imports also land pending.
   Any "catch-up on boot" hook lives in the FastAPI lifespan — but tests
   memoize/skip lifespan work for speed (test-suite-speedup PR #8); a startup
   auto-analyze must not re-slow the suite or autostart the engine in tests.
6. **Leaks are reissued on every re-analysis** — `leaks.id` unstable by
   design; Blunder Trainer attempts key on stable identity, not leaks.id.
   Auto re-analysis therefore safe for trainer data, but "Re-analyze" on a
   *done* game is the only way to force leak recompute (e.g. after pipeline
   code changes) — removing that button entirely loses the escape hatch.
7. **Frontend one-way rule** — review.js does its own fetch; receives
   injected `api`; never imports from app.js. UI polling pattern for bulk
   progress already exists (`_analyzeAllInterval`, review.js:421).
8. **Depth contract** — background depth is `review.BACKGROUND_DEPTH`;
   pos_cache keyed by (epd, depth). Changing depth later invalidates cache
   hits, not correctness.

## Consumers of analysis_status

- review.js list rendering (status chips, button labels/disable states).
- `/api/profile`, insights read-models count `analysis_status='done'`.
- `coverage()` (tagged/analyzed/pending counts) shown in Review header.
