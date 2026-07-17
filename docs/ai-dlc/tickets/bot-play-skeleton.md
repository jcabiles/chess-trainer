# Tickets — B2: Bot-play walking skeleton

Spec: [`../specs/bot-play-skeleton.md`](../specs/bot-play-skeleton.md).
Branch: `feat/bot-play-skeleton` off up-to-date main.
Review log: spec dual-reviewed pre-tickets (refuter: fail→fixed — localStorage
single-slot collision, missing restore() branch, redo-stack misdescription,
camelCase; Codex gpt-5.6-sol — analysis-panel play-gating, double-submit,
stale-after-resign, candidates seam, restore-turn check, engine-down UX,
draw-rule precision, testability gaps. All folded into the spec.)

Wave plan (disjoint owners per wave):
**W1:** T1 ∥ T3 ∥ T4 → **W2:** T2 ∥ T5 → **W3:** T6 → T7 → T8.

## T1 — `app/bot_engine.py` + unit tests (W1)
Isolated engine wrapper per spec: lifecycle contract (import-safe, lazy,
one lock, timeout→watchdog restart with FULL option re-application, clean
shutdown), `candidates(fen, k=1)`, `detect_maia()`.
- **Owns:** `app/bot_engine.py`, `tests/test_bot_engine.py`
- **Done:** `pytest tests/test_bot_engine.py -q` green with no binary
  (fake process seam); covers lock serialization, timeout→restart→options
  reapplied, lazy-start failure, shutdown, isolation assertion.

## T2 — Bot routes in `app/main.py` + API tests (W2, after T1)
`POST /api/bot/move` (validation ladder: parse → is_valid → non-terminal;
camelCase response; 503 when bot engine down) + `GET /api/bot/status`;
`get_bot_engine` dependency; lifespan shutdown hook.
- **Owns:** `app/main.py` (bot section only), `tests/test_bot_api.py`
- **Done:** `pytest tests/test_bot_api.py -q` green via dependency
  override; all spec Verify-by-1 route cases present.

## T3 — `static/app.js` seams (W1) — HOTSPOT, single owner
Persistence contract: `mode:'bot-play'` persist branch (embeds `priorPlay`
snapshot) + explicit `restore()` branch with restore-time turn check;
`PRACTICE_MODES` entry; undo/redo button+keyboard gating; **widen the
analysis eval mode-gates (refresh trigger ~1176, response-write staleness
~512, mode gate ~477) to accept `bot-play`** so live eval works in bot
games with the same staleness discipline (Gate-1 decision — panel stays
usable, user toggles); api-hub exposures botplay.js needs (snapshot/
restore-play seam, board control, persist, refresh-analysis trigger).
- **Owns:** `static/app.js`
- **Done:** existing suite + manual smoke: play session survives
  enter/exit; refresh with a bot-play entry restores bot-play (not plain
  play); no regression to trainers' snapshot/restore; analysis refreshes
  in bot-play and a superseded-position eval never writes.

## T4 — "Play vs Bot" UI section (W1)
Collapsible section per spec: persona line (fuzzy label), color pick,
Start, Resign, Retry (hidden default), status/result line, Maia-ready
indicator, Start-disabled state. Look/feel = analysis-mode panel template.
- **Owns:** `static/index.html`, `static/style.css`
- **Done:** section renders in both themes; controls present with ids/
  classes agreed in the ticket brief (T5 consumes them).

## T5 — `static/botplay.js` (W2, after T3+T4)
Mode module per spec: registration, start flow (single-flight), user-move
path (chessops legality/promotion, history append+truncate, rollback on
failure), auto-reply (think-timer + fetch, full staleness set incl. resign
+ terminal + timer-callback re-check), engine-down Retry, game-end
detection (mate/stalemate/insufficient/resign), **trigger an analysis
refresh after the user move and after the bot reply lands (via T3's
api-hub refresh trigger)**, exit-restore handoff.
- **Owns:** `static/botplay.js`
- **Done:** full game playable as White and Black against the live server;
  all spec client behaviors demonstrable.

## T6 — Browser verification pass (W3, after all)
Execute spec Verify-by-3 checklist (Playwright MCP, trusted mouse; real
engine): both colors to a real end; refresh-while-bot-thinking; exit-after-
refresh restores prior play; resign-vs-in-flight race; double-submit;
undo/analysis gating. Fix what it finds (small fixes in-place; anything
structural goes back to the owning ticket).
- **Owns:** verification evidence (screenshots/notes); temporary fixes
  coordinated with file owners
- **Done:** every Verify-by-3 item observed passing in the browser;
  `pytest -q` + `ruff check app tests` green.

## T7 — Dual review of the diff (W3, after T6)
Refuter + Codex (gpt-5.6-sol) review the full branch diff (maker≠checker):
contract regressions, staleness gaps, persistence-schema validation,
lifecycle gaps. Fold findings; re-run T6 items touched by fixes.
- **Owns:** review findings; fixes routed to owners
- **Done:** both reviews resolved or explicitly accepted; suite green.

## T8 — Close-out (W3, after T7)
User exercises the pass/fail in their browser → mark B2 `[x]` in the
roadmap; final `pytest`/`ruff`; commit; push; PR.
- **Owns:** roadmap checkbox, git close-out
- **Done:** PR open; B3/B6 unblocked.

## Notes
- T3 is the sequencing keystone: botplay.js (T5) compiles against T3's
  api-hub surface — T3's brief must pin that surface explicitly.
- Live-reload hazard: the user's uvicorn --reload may be running — workers
  never switch branches mid-work; all work happens on the feature branch
  checked out once at start.
- Appetite guard (2–3 days): cut order if over — Maia indicator polish →
  Retry UX (minimal alert acceptable) → collapsible-section polish. Never
  cut: staleness set, persistence contract, isolation tests, analysis-gate
  staleness (widened gates must keep the drop-late-eval guarantee).
