# Tickets — Maia engine walking skeleton

Spec: `../specs/maia-skeleton.md` · Contracts: `../contracts/maia-skeleton.md`
Branch: `feat/maia-skeleton`. Sequential unless noted; owned files listed
(one file = one owner per wave).

- [ ] **T1 — lc0 engine module (the Maia wrapper).** New `app/maia_engine.py`:
      MaiaEngine per spec — lazy spawn with pinned options
      (VerboseMoveStats/Threads=1/MinibatchSize=1/PolicyTemperature=1.0),
      single lock, STREAMING `engine.analysis()` prior capture in executor,
      2.0s own hard timeout (`MAIA_ENGINE_HARD_TIMEOUT`), generation-bound
      watchdog `(engine, pid)` + conditional clear, idempotent close,
      `MaiaUnavailable` failure envelope (legal move or raise — nothing
      else), `get_maia_engine()` singleton, per-persona net map
      (`casey → maia-1400`), pure `maia_ready_for(persona_id)` readiness
      check. Docstring documents single-worker assumption.
      Owned: app/maia_engine.py.
      Done: importable with no lc0 on PATH; unit-instantiable without spawn.
- [ ] **T2 — engine-module tests.** New `tests/test_maia_engine.py`:
      VerboseMoveStats parser on captured fixture text (engine-free);
      failure-envelope tests (timeout/garbage/illegal → MaiaUnavailable);
      watchdog concurrency (timeout+next request, restart+net swap,
      close+in-flight); live-lc0 tests behind skipif (spawn, top_move
      legality, bestmove == max same-run prior).
      Owned: tests/test_maia_engine.py.
      Done: `pytest tests/test_maia_engine.py` green with AND without lc0.
- [ ] **T3 — route wiring + status.** app/main.py: Maia-first branch for
      casey in the persona path (try top_move → `engine:"maia"`, except
      MaiaUnavailable → fall through to the ENTIRE existing block);
      `from app.maia_engine import get_maia_engine` bare-name import;
      `BotMoveResponse.engine: Literal["maia","stockfish"]="stockfish"`;
      `BotStatusResponse.maia["personas"] = {"casey": maia_ready_for(...)}`;
      lifespan shutdown closes maia engine (own try/except).
      Owned: app/main.py.
      Done: TestClient — casey+FakeMaia returns engine:"maia"; FakeMaia
      raising → SF fake serves with engine:"stockfish"; Nina untouched.
- [ ] **T4 — API test hardening.** Shared autouse Maia-unavailable fixture
      (tests/conftest.py) so ALL existing bot-route tests pin the SF path on
      any machine; update the two exact-shape assertions
      (test_bot_api.py:80, :238); add casey-Maia opt-in tests per spec item 5.
      Owned: tests/conftest.py, tests/test_bot_api.py (assertion updates in
      test_bot_causal_api/mistake/personas only if their exact-shape checks
      break — expect none beyond documented two).
      Done: full suite green; grep confirms no bot-route test depends on
      installed lc0.
- [ ] **T5 — client indicator.** static/botplay.js: store `engine` from
      /api/bot/move responses; subtle "Maia" / "engine fallback" text on the
      selected-bot card/rail Maia line for Maia-wired personas (driven by
      status `maia.personas`); tokens-only CSS if any styling.
      Owned: static/botplay.js (+ static/style.css only if needed).
      Done: browser — indicator shows Maia for Ming Ling, flips on fallback,
      absent for other bots.
- [ ] **T6 — end-to-end verify + docs.** Run the spec's Verify-by 1–4 (pytest,
      ruff, live game vs Ming Ling incl. kill-lc0 fallback, no orphan lc0 on
      shutdown); README setup note for lc0/Maia (brew line + weights dir);
      roadmap slice checkbox flipped ONLY when all four pass.
      Owned: README.md, docs/ai-dlc/roadmap/training-and-portfolio.md.
      Done: evidence pasted in PR body; Conventional Commits; PR opened.

Parallelizable: T1+T2 by one owner (same seam), T5 independent after T3.
Everything else sequential T1→T3→T4→T6.
