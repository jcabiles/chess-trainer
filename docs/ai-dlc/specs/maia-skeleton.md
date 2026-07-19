# Delta spec — Maia engine walking skeleton

**Goal (one line):** Ming Ling (persona id `casey`) plays real human-trained
Maia moves end-to-end via a new isolated lc0 engine module, with automatic
fallback to the existing weakened-Stockfish path and a subtle engine indicator.

Roadmap: Chapter 4 slice 1 of `../roadmap/training-and-portfolio.md` (serves
N3). Contracts: `../contracts/maia-skeleton.md` (+ `bot-play.md`). Research:
`../../design/research/engine-adaptation/maia-lc0.md`. Appetite: 2–3 days.

## User-confirmed decisions (Gate 1, 2026-07-18)

- **One lc0 process, restart to swap nets** (~1s, only on net change; mirrors
  the watchdog idiom; extends to the full ladder later).
- **Subtle fallback indicator** — no toast; status/response surfaces which
  engine served, rail shows it quietly.
- **Scope confirmed thin**: Maia path for `casey` only; plays Maia's TOP move
  (variety sampling = next slice); policy-prior PARSING included (returned in
  the internal candidate shape, consumed by nobody yet); blunder/mistake gates
  untouched and NOT applied to Maia moves (see Behavior change below).

## Files / interfaces to touch

1. **NEW `app/maia_engine.py`** — `MaiaEngine` class mirroring the
   `bot_engine.py` idiom exactly:
   - Own subprocess (python-chess `SimpleEngine.popen_uci("lc0", ...)` with
     `--weights=<net>`), own single `asyncio.Lock`, lazy start, blocking calls
     in executor + shield + hard timeout (reuse the 5s default, own env
     override `MAIA_ENGINE_HARD_TIMEOUT`), `_poison`/`restart()` watchdog,
     idempotent never-raising `close()`.
   - Import-safe: module import / construction / `is_available()` never launch
     lc0. Availability = `detect_maia()` facts (lc0 on PATH + required net
     file present) — pure, no probing (landmine 7).
   - Instance state `self._net_path`; net switch + search atomic inside one
     lock acquisition (restart-with-new-weights when the requested net ≠
     current — this slice only ever requests maia-1400).
   - `async def top_move(fen: str, net: str) -> {"uci","san","priors":[{uci,p}...]}`
     — `go nodes 1`; move = lc0 bestmove (policy argmax); priors from
     VerboseMoveStats (stored for the next slice; **never mapped into
     scoreCp** — landmine 1).
     **Protocol reality (BOTH reviewers verified against the live binary):
     `SimpleEngine.analyse()` CANNOT capture the priors — python-chess
     `info.update()` lets each `info string` line overwrite the previous, so
     only the final node-summary survives. Implementation MUST use the
     streaming `engine.analysis()` API and consume every info line inside the
     executor, taking bestmove from `wait()`. Engine options set at spawn:
     `VerboseMoveStats=true`, `Threads=1`, `MinibatchSize=1`,
     `PolicyTemperature=1.0` (installed default 1.359 preserves argmax but
     distorts priors for the next slice).** Parse defensively; if prior parse
     fails, still return the bestmove with `priors: []`.
   - **Failure envelope: `top_move()` returns a LEGAL move or raises
     `MaiaUnavailable` — nothing else escapes.** Internal hard timeout is its
     own, LOW: `MAIA_ENGINE_HARD_TIMEOUT` default **2.0s** (nodes=1 inference
     is <100ms; 2s covers cold start + net load) so worst-case
     Maia-timeout-then-SF-fallback stays inside the interactive budget;
     timeout / dead process / malformed or illegal bestmove / parse crash are
     all caught and re-raised as `MaiaUnavailable` (never a raw
     TimeoutError/500 past main.py's handlers).
   - **Watchdog hardening (Codex): do NOT copy `_poison`'s mutable-pid read
     blindly — use generation-bound `(engine, pid)` handles and conditional
     clearing (`if self._engine is engine`) so a stale timeout cleanup can
     never kill/null a newer respawn.** Concurrency cases to cover in tests:
     timeout + immediately-following request; restart + net swap; close with
     in-flight search.
   - Own `MaiaUnavailable` exception; NEVER escapes to main.py (landmine 4) —
     the caller catches it and falls back.
   - Module singleton `get_maia_engine()` (FastAPI-independent accessor).
   - Single-worker assumption + executor isolation documented in the module
     docstring (Codex roadmap finding): the asyncio.Lock guards ONE uvicorn
     worker; multi-worker deployment is out of contract.
2. **`app/main.py`** —
   - Persona branch of `POST /api/bot/move`: BEFORE the blunder gate, if
     `persona.id == "casey"` and Maia is available → `try: maia top_move
     (net=maia-1400); return response with engine="maia" except
     MaiaUnavailable: fall through` to the ENTIRE existing block (gate →
     sampling → mistake → k=1) unchanged. Legacy bare-{fen} branch untouched.
   - `BotMoveResponse` gains `engine: Literal["maia","stockfish"] =
     "stockfish"`. **NOT shape-preserving (both reviewers): Pydantic
     serializes defaulted fields, so tests/test_bot_api.py:80's exact-set
     assertion (`{"moveUci","moveSan","fen"}`) and :238's maia-keys assertion
     MUST be updated as part of this slice** — wire change is additive for
     the CLIENT (confirmed: botplay.js reads only moveUci today), not for
     exact-shape tests.
   - `BotStatusResponse.maia` gains `"personas": {"casey": bool}` —
     **per-persona readiness = lc0 present AND that persona's REQUIRED net
     file present (maia-1400 for casey; "any *.pb.gz exists" is NOT ready —
     Codex)**; top-level `{lc0, weights}` keys preserved; still pure
     detection, no probing.
   - **Import style pinned (test-seam, both reviewers): main.py uses
     `from app.maia_engine import get_maia_engine` (bare name, matching the
     detect_maia precedent) and tests patch
     `monkeypatch.setattr(main, "get_maia_engine", ...)`. Module-attr call
     style is forbidden — it silently no-ops that patch.**
   - Lifespan shutdown: `await get_maia_engine().close()` alongside the
     existing bot-engine close, own try/except (landmine 5).
3. **`static/botplay.js`** — subtle indicator only: store `engine` from the
   last `/api/bot/move` response; the rail's existing Maia status line (or the
   selected-bot card) shows "Maia" vs "engine fallback" for wired personas.
   No new elements beyond one small text node; tokens-only CSS if any.
4. **NEW `tests/test_maia_engine.py`** — real-lc0 tests gated
   `pytest.mark.skipif` on `detect_maia()`; unit tests for the
   VerboseMoveStats prior parser run engine-free on captured fixture text.
5. **Test suite (wider than one file — Codex HIGH):** the existing casey
   assertions in tests/test_bot_causal_api.py, test_bot_mistake_api.py,
   test_bot_personas_api.py and test_bot_api.py currently pin casey to the
   SF persona pipeline and would become BINARY-DEPENDENT (pass without lc0,
   diverge on machines with lc0+maia-1400). **Required: a shared
   Maia-unavailable override (conftest fixture, autouse across bot-route test
   files) so every existing test deterministically exercises the SF path on
   any machine**; casey-specific tests then OPT IN to a `FakeMaia`
   (real signature) to prove: casey served by Maia when available
   (`engine:"maia"`); `MaiaUnavailable` AND a fake that times out /returns
   garbage → same-request SF response (`engine:"stockfish"`); non-casey
   personas never touch Maia. Existing
   `dependency_overrides[get_bot_engine]` choke point untouched.

## Accepted degradations (explicit, revisit at the ladder-switch slice)

- **FEN-only inference** (Codex HIGH): Maia's maintainers note move-sequence
  input matters; this skeleton sends FEN only (no move history), accepting
  slightly degraded Maia fidelity + no repetition awareness. Full-line
  transmission (additive `movesUci` request field) is a named item of the
  ladder-switch slice.
- **Engine provenance is ephemeral** (Codex MED): the `engine` field informs
  the live indicator only; it is not persisted in saved games — a
  Maia-then-fallback mixed game saves with persona identity alone. Per-game
  provenance lands with the ladder switch.
- **Determinism contract** (Codex MED): tests pin the prior PARSER on fixture
  text and, in live-lc0 tests, assert bestmove == max parsed prior of the
  SAME run + legality. No cross-backend golden move (Metal vs CPU float
  variance would break it).
- **SF stays mandatory**: Start remains gated on Stockfish availability —
  fallback is part of this slice's contract; Maia-only operation is out of
  scope.

## Behavior change (accepted, documented)

While Maia serves casey, the B5 causal-blunder gate, mistake tier, and opening
sampling DO NOT run for casey (Maia-1400's own human-trained error profile
stands in). Ming Ling's feel changes this slice; recalibration of the
gate-on-Maia interaction is explicitly the ladder-switch slice's job
(landmine 6). All other personas: byte-identical behavior.

## Out of scope

Variety/policy sampling (next slice); any other persona on Maia; blunder-gate
interaction with Maia candidates; realism audit harness; roster changes;
schema changes; changes to `app/engine.py` (user-analysis engine) or
`app/bot_engine.py` internals (only composed alongside, never modified except
none-at-all — if a shared helper is tempting, copy, don't couple).

## Constraints (profile invariants)

Pure modules stay engine-free (maia_engine is an engine module; no pure module
imports it); full pytest green with NO lc0 AND NO stockfish binary; three-way
process isolation (analysis SF / bot SF / lc0 — separate locks, zero shared
state); server stateless per request (no hidden position cache; determinism
from request fields); `/api/bot/status` stays side-effect-free; tokens-only
CSS, AA, :focus-visible for any UI text; Conventional Commits, feature branch,
no push to main.

## Verify-by (end-to-end)

1. `.venv/bin/python -m pytest -q` green (suite must not require lc0 OR
   stockfish; baseline 970 passed). Automated coverage MUST include: the
   timeout→MaiaUnavailable rewrap (a FakeMaia that hangs/raises
   TimeoutError resolves to a same-request SF move, not a 500/503), the
   parser fixture tests, and the watchdog concurrency cases.
2. `.venv/bin/ruff check app tests` clean.
3. Live server: start bot game vs Ming Ling → moves arrive; response
   `engine:"maia"`; rail shows the subtle Maia indicator; `kill <lc0 pid>`
   mid-game → next move still arrives with `engine:"stockfish"` and indicator
   flips; a different persona (Nina) plays via SF exactly as before.
4. Server stop leaves no orphan lc0 process (`pgrep lc0` empty).
