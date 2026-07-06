# Architecture

A local, single-user chess training app. One FastAPI process drives one
Stockfish subprocess through python-chess; the frontend is a single-page app of
native ES modules with no build step. SQLite is used by the game-review feature
only — everything else is stateless per request. This document covers what
rarely changes: the module map, the invariants, and where work starts. Setup
and features live in the README; per-feature design history in `docs/ai-dlc/`.

## Bird's-eye view: one move

`POST /api/move` is the hot path. The server re-validates the move with
python-chess (the client's chessops check is UX, not authority), then takes one
of three exits:

```
POST /api/move ──► legality check (python-chess)
                     ├─ book move?      → reply from opening book, no engine
                     ├─ analyze=false?  → legal/SAN only, no engine
                     └─ engine path     → two depth-pinned analyses
                                          (position before + after, multipv=2)
                                          → cp-loss → quality label
```

Both analyses run at the same fixed depth so the centipawn loss between them is
comparable. `multipv=2` yields the "second-best" line at no extra cost. Move
history lives client-side as a UCI list; undo/redo is a client replay, not
server state.

## Codemap

### `app/` — backend

| Module | Role |
|---|---|
| `main.py` | FastAPI routes, startup lifespan, `get_engine` dependency, static serving |
| `engine.py` | The single Stockfish process: lifecycle, locking, timeouts, recovery |
| `analysis.py` | Pure: eval normalization (White-POV cp) + move-quality classification |
| `models.py` | Pydantic request/response schemas; no logic |
| `openings.py` | Opening-name detection from bundled lichess TSVs |
| `book.py` | Opening-book fast path: known positions answered without the engine |
| `traps.py` | Opening-traps catalog backend (`data/traps.json`) |
| `repertoire.py` | Prepared-lines backend: per-color move-prefix tree (`data/repertoire.json`) |
| `pgn.py` | Pure: PGN parsing into an import model |
| `storage.py` | SQLite layer — the only module that opens the database |
| `review.py` | Game-review conductor: background per-ply engine analysis, leak detection |
| `motifs.py` | Pure: tactical motif detection (python-chess only) |
| `coaching.py` | Template-based leak narration; pure logic, no LLM anywhere |
| `profile.py` | Cross-game tendency profile; engine-free, read-only queries via storage |
| `insights.py` | Insights read-models (openings/mistakes/endgames); engine-free, via storage |
| `accuracy.py` | Pure: per-side accuracy % and Elo estimate from stored evals |
| `endgame.py` | Pure: endgame classification by material signature |

### `static/` — frontend (native ESM, no bundler)

| Module | Role |
|---|---|
| `app.js` | Hub: board wiring (chessground/chessops from pinned CDNs), state, tab routing |
| `panel.js` | Analysis panel rendering |
| `review.js` | Game library, replay, profile dashboard, foresight cards |
| `insights.js` | Insights tab dashboard |
| `movelist.js` | Clickable notation history |
| `feedback.js` | Move-feedback toasts |
| `shortcuts.js` | Keyboard bindings |
| `theme.js` | Light/dark/system toggle (self-initializing) |
| `prefs.js` | localStorage helpers — leaf module, no imports |
| `format.js` | Shared display formatters — leaf module |

Feature modules receive everything through an `api` object injected by
`app.js` at init and never import `app.js` back. Dependencies point one way:
hub → feature → leaf.

Other directories: `data/` bundled opening/trap/repertoire data plus gitignored
user games; `tests/` unit + API suites; `scripts/` dev-server manager and batch
utilities; `docs/ai-dlc/` per-feature specs, contract maps, and review records.

## Invariants

Things the code relies on that you cannot see from any single file:

- **One engine, one lock.** Exactly one Stockfish subprocess for the app's
  lifetime; every access is serialized behind a single `asyncio.Lock`
  (`SimpleEngine` is not thread-safe). `app.engine` is imported only by
  `main.py` (plus an exception type in `review.py`). At most one analysis is
  ever in flight.
- **Pure core stays pure.** `analysis`, `motifs`, `pgn`, `accuracy`,
  `endgame`, and `models` import no engine, no database, no framework. They
  are the unit-testable heart of the app. `coaching` is pure logic too — it
  imports only storage's `LeakRecord` type, never the database. `profile` and
  `insights` are engine-free read-models: deterministic logic over read-only
  storage queries.
- **`sqlite3` appears in `storage.py` only.** Every other module goes through
  it.
- **All evals are White-POV before anything else happens.**
  `analysis.pov_score_to_white_cp` is the single normalization point; stored
  evals are already normalized at write time. No other module re-derives the
  mover-sign rule.
- **Stateless except review.** Play and the trainers keep no server state —
  move history is client-side. Game review is the one exception (SQLite).
- **Interactive play preempts background work.** The review job funnels
  through the same engine lock and yields to `/api/move` via
  `review.note_interactive_start/end`.
- **localStorage keys are a compatibility contract.** `chess-training:session:v1`
  and `chess-training:ui:v1` are frozen strings; renaming them silently wipes
  users' saved sessions and preferences.

## Engine lifecycle and failure model

Importing `app.engine` never launches anything; a missing binary raises a
catchable `EngineUnavailable`, and engine routes return 503 while the rest of
the app keeps working. Each search has a soft time cap (stop at target depth
or `ENGINE_SOFT_TIME`, whichever is first) and a hard asyncio watchdog
(`ENGINE_HARD_TIMEOUT`). If a call times out or the process wedges, the wrapper
poisons the engine: kill the subprocess first (by its captured pid), null the
handle, clean up off-thread — so a hung Stockfish can never hold the lock or
wedge the server. The next request (or the restart endpoint) relaunches it.

Startup follows the same degrade-gracefully rule: engine, opening data, traps,
repertoire, book, storage, and the games drop-folder each initialize inside
guards; a missing binary or malformed data file logs a warning instead of
preventing boot.

## Testing seams

The full suite runs with no Stockfish installed. Two seams make that work:
`CHESS_SKIP_ENGINE_AUTOSTART` (set by an autouse fixture) keeps the FastAPI
lifespan from spawning a real engine, and `ScriptedEngine`
(`tests/engine_fakes.py`) is a drop-in with the same async surface, installed
per-test via `app.dependency_overrides[get_engine]` and scriptable per
position. Pure-logic suites like `tests/test_analysis.py` need no seam at all.

## Where work starts

- **New API route** — `app/main.py` for the route, `app/models.py` for its
  schemas; follow the shared `Analysis`-shape idiom used by every endpoint.
- **Move-quality change** — `analysis.classify` and its thresholds; covered by
  `tests/test_analysis.py`.
- **New trainer tab** — markup in `static/index.html`, a new injected-`api`
  module mirroring `review.js`, wired in `app.js`; backend module mirroring
  `traps.py` with a `data/*.json` file.
- **New review motif** — detection rule in `app/motifs.py` (pure; see
  `tests/test_motifs.py`), invoked from the leak scan in `review.analyze_game`.

## Design history

Each feature's spec, contract map, adversarial-review findings, and ticket
breakdown live in `docs/ai-dlc/`; the earliest features predate that convention
and live in `docs/design/` (some code comments still cite that tree).
Constraints that AI coding agents must obey when working here are in
`CLAUDE.md`.
