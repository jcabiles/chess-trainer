# Tickets — auto-analyze

Spec: `docs/ai-dlc/specs/auto-analyze.md` · Contracts:
`docs/ai-dlc/contracts/auto-analyze.md` · Branch: `feat/auto-analyze`

DAG: T1 → T2 (same file, sequential). T3 independent of T1/T2 (frontend only)
— parallelizable with T1+T2 as the second lane. T4 last (verification barrier).

## T1 — backend: auto-kick helper + import/retag/color-change triggers
Add `_kick_auto_analysis()` in `app/main.py` with BOTH guards from the spec:
(1) return if `CHESS_SKIP_ENGINE_AUTOSTART` set — gates every trigger, not
just lifespan; (2) return if not `engine.is_running` — no try/except around
`start_analyze_all` (it never raises; without the probe an engine-down kick
cascades all pending games to 'failed'). Call from import_games, retag_color,
per-game color-change route.
- Owned files: `app/main.py`, `tests/test_games_api.py` (HOTSPOT — single
  owner with T2; T3 must not touch these)
- Acceptance: with running fake engine, import/retag/color-change start the
  singleton bulk task; with engine not running, routes return 200 and games
  stay `pending` (never `failed`); new tests monkeypatch the env var off +
  isolate `GAMES_DB`; existing pending-status tests untouched and green.
- Done-condition: `.venv/bin/python -m pytest -q` green, no Stockfish binary
  needed.

## T2 — backend: startup + engine-restart catch-up (depends on T1)
Call `_kick_auto_analysis()` from lifespan (after reset_stuck + drop-folder
import, when pending > 0 — env gate lives inside the helper) and from
`restart_engine` after a successful restart when pending > 0.
- Owned files: `app/main.py`, `tests/test_api.py`,
  `tests/test_games_api.py` (same owner as T1)
- Acceptance: lifespan skips auto-kick under the test env var; restart route
  kicks when pending exists; suite wall-clock stays ~20 s.
- Done-condition: `.venv/bin/python -m pytest -q` green and not slower than
  baseline by more than a few seconds; `ruff check app tests` clean.

## T3 — frontend: remove buttons, add auto-polling (parallel with T1/T2)
In `static/review.js`: restructure `renderBulkControls()` to retag-only
(delete "Bulk analyze" section + `triggerAnalyzeAll` wiring); per-game button:
`done` → "Re-analyze", `failed` → "Retry" (refuter #1 — failed games must
stay recoverable), none for pending/analyzing; generalize
`_analyzeAllInterval` to auto-poll whenever any listed game is
pending/analyzing (start on render and after import success; stop + one
"All games analyzed." toast when none remain); update empty-state copy; prune
unused `review-bulk-progress` CSS class.
- Owned files: `static/review.js` + the CSS file owning
  `review-bulk-progress` (no app.js)
- Acceptance: no Analyze/Analyze-all controls anywhere; list self-refreshes
  during analysis; Re-analyze on done games, Retry on failed games; toast
  fires once.
- Done-condition: exercised in browser (Playwright MCP or manual) against a
  live server: import PGN → chips Pending → Analyzing… → Analyzed, zero
  clicks.

## T4 — verify + docs sweep (barrier: after T1–T3)
Run full verify (pytest, ruff, browser walkthrough per spec Verify-by);
update README's game-review section if it mentions manual Analyze buttons;
confirm no debug artifacts.
- Owned files: `README.md` (docs only)
- Acceptance: spec Verify-by checklist all green.
- Done-condition: evidence pasted in PR description; PR opened from feature
  branch.
