# Contracts — Maia engine walking skeleton (scanned 2026-07-18)

Read-only contract scan for wiring an lc0/Maia move source into bot play.
Supplements `bot-play.md` (B2-era). File:line cites verified against main @ PR #68.

## 1. BotEngine lifecycle idiom to mirror (`app/bot_engine.py`)

- Isolation is THE load-bearing decision (docstring 1–9): own subprocess, own
  lock, own options — never shares state with `app.engine`. A third process
  (lc0) must keep three-way isolation.
- Import safety: module import, class construction, and `detect_maia()`
  (132–149) never launch a process. Lazy `start()` on first search (189–232).
- One `asyncio.Lock` (176, 319): strength/net switch + search happen atomically
  inside ONE acquisition (308–324).
- Blocking UCI runs in `run_in_executor`, shielded, `asyncio.wait_for` vs
  `BOT_HARD_TIMEOUT_S` (88–91, 333–349).
- Watchdog `_poison` (254–291): SIGKILL by captured pid, null handle first,
  fire-and-forget close; `restart()` idempotent, callable under the lock.
- `close()` idempotent/never-raises (234–250); lifespan calls it at
  `app/main.py:187–194` — a separate Maia process handle MUST be reached from
  that shutdown path or it leaks.
- `candidates()` (369–421): returns `[{"uci","san","scoreCp"}]`, **scoreCp is
  White-POV**, mate → signed ±MATE_CP=100000 (82, 423–444). Mover-POV
  conversion happens downstream (`app/main.py:755–758`). Accepts
  `elo: Optional[int] = None`.
- Instance config state (`self._elo`, 177–180) re-applied on watchdog respawn —
  "never silently drop a config option" (19–23). Maia analog: `self._net_path`.

## 2. `POST /api/bot/move` decision tree (`app/main.py`)

- Route 656–657, `Depends(get_bot_engine)`; tests override via
  `app.dependency_overrides[get_bot_engine]` (tests/test_bot_api.py:58,67) —
  the single choke point keeping the suite engine-free.
- Validation rungs 670–694 (400s) run before any engine call.
- Persona resolution 696–710; legacy bare-{fen} branch calls
  `bot.candidates(req.fen, k=1)` with NO elo kwarg.
- Blunder gate runs FIRST, engine-free (712–736); gate fires ⇒
  `candidates(k=CAND_K, elo=persona.elo)` (740) + `pick_survivor`.
- `CAND_K == SAMPLE_K == MISTAKE_K == 5` asserted (590–603); `cands` reuse
  pattern across branches (750–781) assumes one k=5 call is valid everywhere.
- Mistake tier 764–776 trades down within a 50–250cp band — REQUIRES real
  centipawn `scoreCp`, never policy priors.
- Error mapping: single `except BotEngineUnavailable` → 503 (782–791); empty
  cands → 503 (793–801). Any Maia failure must be caught by the same handler
  or handled internally before it escapes.
- `BotMoveResponse` (626–631): `moveUci, moveSan, fen` — no engine-source
  field today (additive change if wanted).
- NO `note_interactive_start/end` in bot routes — that contract belongs to the
  analysis engine only (506/522, 1850/1863).

## 3. `GET /api/bot/status` + client (`static/botplay.js`)

- `BotStatusResponse` already carries `maia: {"lc0": bool, "weights": [...]}`
  (634–648, populated at 827 via `detect_maia()`).
- botplay.js has the shape in its offline fallback (632–654) but renders
  nothing from `data.maia` today — extending contents is safe if the top-level
  shape is preserved.
- Picker/rail is persona-id driven, engine-agnostic (505–538, 642).

## 4. Lifespan

- Bot engine: lazy start only, shutdown close at main.py:187–194 (own
  try/except). No Maia env gate exists; only precedent is
  `CHESS_SKIP_ENGINE_AUTOSTART` (analysis engine, 131).

## 5. Test seams

- `FakeBot.candidates(self, fen, k=1)` (test_bot_api.py:22–52) — omits `elo`
  kwarg (pre-existing gap; only exercised on legacy branch). A Maia fake must
  accept the REAL signature (`fen, k=1, elo=None`).
- test_bot_engine.py tests the real class, gated on binary presence — a Maia
  analog test file mirrors that (skip without lc0).

## Landmines

1. **POV inversion** — Maia `scoreCp` must be White-POV or absent-by-design;
   raw policy priors in the scoreCp slot corrupt sampling + mistake band.
2. **`elo=` kwarg** — any candidates() the persona branch can reach must
   accept it.
3. **k=5 reuse** — Maia at `go nodes 1` may not produce 5 well-differentiated
   ranked moves; don't route Maia through the CAND_K path in the skeleton.
4. **Exception unification** — lc0 failure must never escape as a new type to
   main.py's single except; cleanest = fallback handled before it escapes.
5. **Shutdown leak** — a Maia process outside BotEngine.close()'s reach leaks
   on server stop unless lifespan closes it explicitly.
6. **Double weakening** — Maia already encodes human error; running the B5
   blunder gate / mistake tier ON TOP of a Maia move double-applies weakness.
   Skeleton decision needed: casey-via-Maia bypasses gate/mistake/sampling
   entirely (deferred to the ladder-switch slice).
7. **Detection purity** — `/api/bot/status` stays side-effect-free; readiness
   reporting must never launch/probe a live lc0.
