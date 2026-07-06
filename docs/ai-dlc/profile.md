# AI-DLC profile — chess-trainer

stack:        python (FastAPI + python-chess backend; vanilla ES-module frontend, no build step)
artifact_dir: docs/ai-dlc

verify:
  test:  .venv/bin/python -m pytest -q
  lint:  .venv/bin/ruff check app tests
  boot:  uvicorn app.main:app --reload --port 8001 (Claude Code sandbox blocks socket bind —
         verify routes in-process via FastAPI TestClient); UI via Playwright-MCP on a live server

hotspots:
  - app/main.py         # single FastAPI entrypoint — all routes
  - app/models.py       # shared Pydantic schemas
  - static/index.html   # single SPA shell (tab buttons + panels + css links)
  - static/app.js       # hub (~980 ln): state, ground, bus, mode registry, api.hub,
                        # persistence, play controls, review shim, init/tab wiring
  - static/review.js    # duplicate tab array; openGame/goto seams
  - requirements.txt

invariants:
  - Pure modules (analysis, motifs, pgn, coaching, profile, accuracy — and new insights,
    endgame) stay engine-free: full pytest suite passes with no Stockfish binary.
  - Reuse analysis.pov_score_to_white_cp / classify; never re-derive the White-POV
    mover-sign rule.
  - One Stockfish process, all access serialized behind a single asyncio.Lock;
    engine.py stays import-safe when the binary is absent.
  - Server stateless per request except game review (SQLite data/games.db);
    never commit data/games.db or data/games/.
  - Frontend modules receive an injected `api`; never import from app.js.
    Tokens-only CSS (no raw hex), AA contrast, :focus-visible on interactive controls.
  - No DB schema change unless a spec explicitly says so.
  - Commit only implemented + verified + reviewed (Conventional Commits, ≤50-char subject,
    Co-Authored-By trailer). Feature branches only; never push main, never force-push,
    never merge PRs.

auth: none (local single-user app; no external services)

hygiene: no debug artifacts in commits (console.log, window.__dbg, screenshots, .playwright-mcp/)
