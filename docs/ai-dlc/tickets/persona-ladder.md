# Tickets — B4: Persona ladder

Spec: [`../specs/persona-ladder.md`](../specs/persona-ladder.md).
Branch: `feat/persona-ladder` off up-to-date main.
Wave plan (disjoint owners): **W1:** T1 ∥ T2 ∥ T3 ∥ T4 → **W2:** T5 (needs
T1+T2) → **W3:** T6 (needs T5+T3+T4) → **W4:** T7 verify → T8 review → T9
close-out. (Resign deferred to B5 per review fold.)

## T1 — `app/personas.py` catalog + `weighted_choice` + tests (W1)
New **pure** module. In-memory default = the 4-persona ladder (hardcoded, **no
import-time file I/O**). `init(path=None)` loads `data/personas.json` (env
`PERSONAS_FILE`); missing/invalid or failing validation (unique ids,
casey/default present, Elo∈[1320,3000], finite temp>0) → keep defaults + one
warning, never raise. API: `all()`, `get(id)`, `default_id()="casey"`,
`Persona{id,name,elo,style,description,temperature}`. Pure
**`weighted_choice(scores, temperature, seed) -> int`**: stable softmax
`exp((s-max)/temp)` over **mover-POV** scores, `temp>0` (floor 1), seeded
`random.Random`; `<k`/single-candidate safe; scores are plain numbers (mate
already ±MATE_CP upstream). Ship `data/personas.json` (the 4 personas). Wire
`personas.init()` is T5's concern (lifespan) — T1 exposes it only.
- **Owns:** `app/personas.py`, `data/personas.json`, `tests/test_personas.py`
- **Done:** `pytest tests/test_personas.py -q` green — default when file absent
  (no I/O at import); env-override load; bad file keeps defaults; unknown id →
  None; default elo == 1350; `weighted_choice` deterministic under fixed seed,
  hotter temp → flatter, `<SAMPLE_K`/single handled, mover-POV + ±MATE_CP sort.

## T2 — `app/bot_engine.py` per-persona strength, atomic (W1)
UCI_Elo → instance state `self._elo` (default 1350); `start()` applies
`self._elo` (survives watchdog restart). **`candidates(fen, k, elo=None)`**: under
the single `self._lock`, if `elo is not None and elo != self._elo` set + restart,
then start + search — strength switch and search in ONE lock acquisition (atomic;
no interleave contamination). Map a mate score to signed **White-POV** `±MATE_CP`
(100000) instead of `None`. `elo=None` ⇒ no change (legacy path).
- **Owns:** `app/bot_engine.py`, `tests/test_bot_engine_strength.py` (new; fake
  SimpleEngine seam)
- **Done:** strength switches only on change, atomically under the lock; after a
  restart `start()` re-applies `self._elo` (not hardcoded 1350); mate → ±MATE_CP
  not None; existing bot tests green.

## T3 — `static/app.js` descriptor fields (W1) — HOTSPOT, single owner
`botGame` gains `personaId` + `seed`; carry them through **all three** sites —
persist (`~:182-191`), restore (`~:280-290`), `botSetGame` (`~:431-440`) —
mirroring the B3 `startedAt/saved/rated` pattern.
- **Owns:** `static/app.js`
- **Done:** suite green; a persisted bot game round-trips personaId/seed across
  refresh (all three sites); no B2/B3 regression.

## T4 — persona picker UI (W1)
`static/index.html`: `<select id="bot-persona">` in `#botplay-body` next to the
color radiogroup, locked mid-game/busy (same guard as color). `static/style.css`:
token-only, both themes.
- **Owns:** `static/index.html`, `static/style.css`
- **Done:** picker renders with stable id `bot-persona` for T6; disabled while a
  game is live; both themes.

## T5 — `app/main.py` persona-aware routes + tests (W2, after T1+T2) — HOTSPOT
`personas.init()` in `lifespan` (after `book.init`). `/api/bot/status` lists
personas + `defaultPersonaId`. `/api/bot/move`: optional `personaId=None`,
`ply=0`, `seed=None`. **Legacy (`personaId is None`)**: `candidates(fen,k=1)`
(elo unchanged=1350), candidate 0, existing response — B3-identical. **Persona**:
`personas.get` (unknown → 400); opening (`ply<OPENING_PLIES`)
`candidates(fen,k=SAMPLE_K,elo=persona.elo)` → mover-POV convert →
`weighted_choice(...,hash((seed or 0,ply)))` → play idx; else best. `/api/bot/
save`: optional `personaId`; **server resolves** personaElo + PGN name from
catalog (ignore client Elo/label); present → `headers_json={"rated",personaId,
personaElo}`; absent → `{"rated":bool}` exactly; unknown → 400.
- **Owns:** `app/main.py`, `tests/test_bot_personas_api.py` (new)
- **Done:** `pytest -q` green — status lists personas; **bare `{fen}` is
  B3-identical (explicit regression test)**; personaId threads elo, opening
  samples vs late best; a **Black bot samples best-for-Black** (mirrored-POV
  test); unknown personaId → 400; save writes server-resolved persona keys +
  ignores client Elo + B3 casual/rated shape intact.

## T6 — `static/botplay.js` persona wiring (W3, after T5+T3+T4)
Populate picker from status; persist selection via `prefs.js` (`botPersona`,
default `defaultPersonaId`); read at `startGame` → descriptor `personaId` + minted
per-game `seed`. Each move POST sends `personaId/ply/seed`. `saveGame` snapshot +
POST send `personaId` only. No resign handling (B5).
- **Owns:** `static/botplay.js`
- **Done:** manual/browser: picker persists across reload; persona threads into
  moves; no B2/B3 regression (busy/replyToken/save triggers intact).

## T7 — Browser verification (W4)
Spec Verify-by-3: picker lists 4 personas + persists across reload; a measured
diversity probe (10 games vs one persona, user repeats first move) reports the
first-4-ply spread (target ≥6, measured evidence); higher persona beats lower in
a quick offline probe; saved `headers_json` carries personaId + catalog
personaElo. `pytest`/`ruff` green.
- **Owns:** verification evidence
- **Done:** every Verify-by-3 item observed.

## T8 — Dual review of the diff (W4, after T7)
Refuter + Codex (gpt-5.6-sol): mover-POV sign correctness, atomic strength switch
+ restart survival, mate handling, B3 legacy parity, save server-resolution, no
schema drift, no B2/B3 regression. Fold findings; re-verify.
- **Done:** both resolved/accepted; suite green.

## T9 — Close-out (W4, after T8)
User pass/fail → mark B4 `[x]` + confirm B8 follows B4 in the roadmap;
`pytest`/`ruff`; commit; push; PR.
- **Done:** PR open; B8 next.

## Notes
- Live-reload hazard: one feature branch, never switch mid-work under the user's
  uvicorn --reload.
- Appetite guard (3–4 days): if over, cut order — sampling temperature nuance →
  extra personas (ship 3, add the 4th later). Never cut: bare-`{fen}` B3 parity,
  mover-POV sign, atomic strength+restart survival, picker persistence.
