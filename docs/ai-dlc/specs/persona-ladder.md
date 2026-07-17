# Delta spec — B4: Persona ladder (play-vs-bot)

**Goal (one line):** replace the single fixed bot with a **picker over 4 named
personas (UCI_Elo 1350–2000)**, each with a one-line character description and
mild opening variety via **seeded candidate-sampling**, so sparring has graded
difficulty and repeat games diverge — **no DB schema change, no new strength
model** (UCI_Elo only).

Slice: **B4** of [`../roadmap/training-and-portfolio.md`](../roadmap/training-and-portfolio.md)
Chapter 3 (N3 · P1+P2). Depends on B2 + B3 (shipped). Contracts:
[`../contracts/persona-ladder.md`](../contracts/persona-ladder.md). Requirements
confirmed at Gate 1 (2026-07-16): **intermediate 1350–2000 via UCI_Elo** ·
**candidate-sampling variety** (no curated books). Spec dual-reviewed (refuter +
Codex Sol); all HIGH/MED findings folded (see "Review folds" at end).

## Decisions (Gate 1 + review folds)

- **Ladder: 4 personas, UCI_Elo 1350–2000.** Proposed set (adjustable in
  `data/personas.json`):
  | id | name | UCI_Elo | style | temperature (cp) | one-line description |
  |----|------|---------|-------|------------------|----------------------|
  | `casey` | Casey | 1350 | solid | 80 | "Casual club player — steady, but misses tactics." |
  | `morgan` | Morgan | 1550 | tactical | 130 | "Improving — punishes loose play and hangs onto material." |
  | `alex` | Alex | 1800 | aggressive | 200 | "Strong club player — sharp, presses for the attack." |
  | `vera` | Vera | 2000 | positional | 100 | "Expert — grinds small edges in long games." |
  **`casey` is the default persona and its Elo is exactly 1350** → a request
  without `personaId` reproduces B3 behavior bit-for-bit.
- **Style is temperature-only in B4** (honest — deep behavioral style is B5).
  **Contempt is NOT used** (removed from Stockfish 2021; `configure()`-ing it
  crashes engine start + watchdog restart — Codex). Style maps only to the
  sampling **temperature** above.
- **Variety: seeded candidate-sampling.** In the **opening phase only**
  (`ply < OPENING_PLIES = 8`), when a `personaId` is supplied the bot requests
  `k = SAMPLE_K = 5` candidates and plays a **weighted-random** pick; after the
  opening (or for a legacy no-persona request) it plays the best move (`k=1`,
  candidate 0 — identical to B3).
- **Resign is OUT of B4 → deferred to B5** (needs a response union + a net-new
  client outcome branch + stateless gating; it belongs with B5's behavioral
  model). B4 bots play to mate/stalemate or the user resigns (B2 already has
  user resign).
- **Persona switch = engine respawn** with the persona's UCI_Elo, applied
  **atomically inside the single engine lock** (see `candidates(fen,k,elo)`).
- **Persona metadata carriers** (no schema change): selected-persona **pref** in
  `prefs.js`; saved-game persona **id** rides `headers_json`
  (`{"rated": bool, "personaId": str, "personaElo": int}`) — but the server
  **resolves `personaElo` + the PGN name from the catalog by `personaId`**, never
  trusting client-sent Elo/label (Codex).

## Sampling contract (normative)

- **Scores are mover-POV.** `candidates()` returns `scoreCp` **White-POV**; the
  route converts: `mover_cp = white_cp if board.turn == WHITE else -white_cp`
  (reuse the established mover-sign rule). Sampling + any threshold consume
  **mover-POV** scores only. (Refuter/Codex HIGH — a raw-White-POV softmax makes
  a Black bot prefer its worst moves.)
- **Mate is signed, never `None`.** `bot_engine.candidates()` maps a mate score
  to a large signed **White-POV** cp `±MATE_CP` (`MATE_CP = 100000`, sign =
  mate-for-White positive) instead of `None`, so mover-POV conversion preserves
  "winning mate" vs "getting mated." (Both HIGH.) Existing `/api/bot/move` play
  path is unaffected (it plays candidate 0, ignores the score).
- **`weighted_choice(scores, temperature, seed) -> int`** (pure): stable softmax
  `w_i = exp((s_i - max(s)) / temperature)` over **mover-POV** `scores`;
  `temperature` in **centipawns**, `temperature > 0` (floor 1); returns a sampled
  index via a `random.Random(seed)` draw over the normalized weights. `scores`
  are plain numbers (mate already mapped to ±MATE_CP upstream). If fewer than
  `SAMPLE_K` candidates are returned, sample over what exists; if exactly one,
  return 0.
- **Per-choice seed** = `hash((gameSeed, ply))` (a stable derivation), so each
  ply samples an independent quantile rather than reusing one quantile every
  move (Codex MED). Deterministic under a fixed `gameSeed`.

## Server

### NEW `app/personas.py` (pure, import-safe catalog)
- **In-memory default = the 4-persona ladder above (hardcoded), set at import
  with NO file I/O.** `init(path=None)` loads `data/personas.json` (env
  `PERSONAS_FILE`, default `data/personas.json`); missing/invalid → keep the
  built-in default + one warning (never raise). **Validation before replacing
  defaults:** unique ids, `casey`/default present, Elo in [1320, 3000], finite
  `temperature > 0`; on any failure keep defaults. Called from `lifespan` after
  `book.init`.
- API: `all() -> list[Persona]`, `get(id) -> Persona | None`,
  `default_id() -> str` (`"casey"`), plus the pure helper
  `weighted_choice(scores, temperature, seed)`. `Persona =
  {id, name, elo, style, description, temperature}` (temperature derived from a
  style→temp table if absent). Engine-free, unit-pure.

### `app/bot_engine.py` — per-persona strength, atomic
- UCI_Elo → instance state `self._elo` (default 1350); `start()` applies
  `{..., "UCI_Elo": self._elo}` so a watchdog restart re-applies the CURRENT
  persona's Elo (closes the strength-reset gap).
- **`candidates(fen, k, elo=None)`** does the strength switch **and** the search
  in **one lock acquisition**: under `self._lock`, if `elo is not None and elo !=
  self._elo`, set `self._elo` and restart the process, then `start()` + search.
  This makes strength+search atomic — two interleaved requests for different
  personas can't cross-contaminate (refuter/Codex HIGH). Mate → ±MATE_CP (above).
- No separate public `set_strength` in the request path (folded into
  `candidates`). `elo=None` ⇒ no strength change (legacy/B3 path).

### `app/main.py` — persona-aware routes
- `GET /api/bot/status` → add `personas: [{id,name,elo,style,description}]` +
  `defaultPersonaId`; keep `personaLabel` (= default persona name) for compat.
- `POST /api/bot/move` — **all new fields optional with defaults so a bare
  `{fen}` still validates and behaves EXACTLY like B3:**
  `personaId: str | None = None`, `ply: int = 0`, `seed: int | None = None`.
  - **Legacy branch — `personaId is None`:** `candidates(fen, k=1)` (elo=None ⇒
    stays 1350), play candidate 0, existing response shape. No sampling. (Both
    HIGH — bare `{fen}` must be B3-identical; add a regression test.)
  - **Persona branch:** resolve persona (`personas.get`; **unknown id → 400**).
    `elo = persona.elo`. If `ply < OPENING_PLIES`: `cands =
    candidates(fen, k=SAMPLE_K, elo=elo)`; convert each `scoreCp` to mover-POV;
    `idx = personas.weighted_choice(mover_scores, persona.temperature,
    hash((seed or 0, ply)))`; play `cands[idx]`. Else `candidates(fen, k=1,
    elo=elo)`, play candidate 0. Same `{moveUci,moveSan,fen}` response.
- `POST /api/bot/save` — request gains optional `personaId: str | None`. **Server
  resolves** `personaElo` + PGN name from the catalog by id (ignores any
  client-sent Elo/label). `personaId` present + valid → `headers_json =
  {"rated": bool, "personaId": id, "personaElo": catalogElo}` and PGN name =
  catalog persona name; **absent → `{"rated": bool}` exactly (B3 unchanged)**;
  unknown id → 400. (Codex — no client-trusted rating; exact B3 shape preserved.)

## Client

### `static/index.html` + `static/style.css` — persona picker
A **persona picker** (`<select id="bot-persona">`) in `#botplay-body` next to the
color radiogroup, populated from `/api/bot/status`.personas, options
`name (≈elo) — description`. Locked while busy / mid-game (same guard as color).
Token-only CSS, both themes.

### `static/botplay.js` — persona state + sampling wiring
- Populate the picker from status; **persist the selection** via `prefs.js`
  (`writeUiPref('botPersona', id)` / `readUiPrefs().botPersona`), default =
  `defaultPersonaId`. Read the chosen persona at `startGame()` (like color);
  store `personaId` on the descriptor; mint a per-game `seed`
  (`Math.floor(Math.random()*1e9)`), persisted.
- Each bot-move POST sends `personaId`, `ply` (current half-move index), `seed`.
- `saveGame` snapshot + POST send **`personaId` only** (server resolves Elo/name).
- No resign handling (deferred to B5).

### `static/app.js` — descriptor fields
`botGame` gains `personaId` + `seed`; both round-trip through the **three**
enumeration sites — persist (`~:182-191`), restore (`~:280-290`), and
`botSetGame` (`~:431-440`) — mirroring the B3 `startedAt/saved/rated` pattern.
(Refuter LOW — miss any one site and the field silently drops on refresh.)

## Out of scope
- Skill-Level / sub-1320 personas (Gate 1) · curated per-persona opening books
  (Gate 1) · **Contempt / any style engine-option** (removed from SF) ·
  **resign** (→ B5) · causal/behavioral style + error model (B5) · avatar art
  (Next) · personal ELO math (B8) · clocks (B7) · any DB schema change ·
  Maia/lc0 install.

## Constraints (profile)
- Bot engine stays the **isolated** process (own lock, own options); never
  touches the shared analysis engine → no `note_interactive_start/end`. Strength
  switch is atomic inside its lock.
- Server **stateless except review** — persona threads **per request**; no
  server-side "current persona" state (the engine's `_elo` is a cached
  process-config detail, re-pinned atomically per move, not request session
  state).
- Frontend modules receive the injected `api` hub, never import `app.js`; persona
  pref via `prefs.js`.
- `personas.py` **pure/engine-free**, default set with no import-time file I/O;
  sampling seeded/deterministic, kept out of any classify path.
- No DB schema change (persona metadata rides `headers_json`). Feature branch +
  PR; commit only implemented+verified+reviewed.

## Verify-by
1. `pytest -q` green with no engine binary (fake bot): **`personas.py`** — default
   ladder when file absent (no import I/O); `init()` env-override load;
   validation rejects a bad file (keeps defaults); unknown id → None; default
   elo == 1350. **`weighted_choice`** — deterministic under fixed seed; hotter
   temperature → flatter distribution; `<SAMPLE_K` and single-candidate handled;
   consumes mover-POV scores; mate mapped to ±MATE_CP sorts correctly. **`bot_
   engine`** — `candidates(fen,k,elo)` switches strength only on change + within
   one lock; `start()` re-applies `self._elo` after restart (survives watchdog);
   mate → ±MATE_CP not None. **`/api/bot/move`** — bare `{fen}` is B3-identical
   (elo 1350, k=1, candidate 0, same response — explicit regression test);
   `personaId` threads elo → `candidates(...,elo)`; opening ply samples
   (k=SAMPLE_K, mover-POV, seeded) vs late/legacy best; a **Black** bot samples
   its own best-for-Black moves (mirrored White/Black test proving the sign);
   unknown personaId → 400. **`/api/bot/status`** — lists personas +
   defaultPersonaId. **`/api/bot/save`** — `personaId` → server-resolved
   `{"rated",personaId,personaElo}` (client-sent Elo ignored); absent →
   `{"rated": bool}` exactly (B3 assertions intact); unknown id → 400.
2. `ruff check app tests` green.
3. Browser (Playwright/manual, real engine): the picker lists 4 personas and
   **persists across reload**; a **measured diversity probe** — 10 games vs one
   persona with the user repeating the same first move — yields a spread of
   first-4-ply sequences (report the count; target ≥6, treated as measured
   evidence not a hard flaky gate); a quick offline strength probe shows a higher
   persona scoring the majority vs a lower one; a saved bot game's `headers_json`
   carries `personaId` + the **catalog** `personaElo`.

## Review folds (audit trail)
- HIGH POV sign → mover-POV conversion in the route; helpers take mover scores.
- HIGH resign path/response → **resign removed from B4** (→ B5).
- HIGH atomicity → `candidates(fen,k,elo)` switches+searches in one lock.
- HIGH mate `None` → engine maps mate to signed ±MATE_CP.
- HIGH B3 parity → explicit legacy branch (`personaId is None` ⇒ B3-identical) +
  regression test; all new request fields optional with defaults.
- MED Contempt removed from SF → dropped entirely; style = temperature only.
- MED sampling params undefined → SAMPLE_K=5, temps in cp, stable softmax
  formula, per-`(seed,ply)` seed; variety = measured probe, not a hard gate.
- MED save trusts client Elo → server resolves Elo/name from catalog by id.
- MED seed reuse per ply → per-`(seed,ply)` derivation.
- LOW personas.py init ambiguity → `init(path=None)`, in-memory default, lifespan
  call, validation. LOW app.js 3 enumeration sites noted; typo fixed. LOW
  headers_json exact `{"rated"}` retained for no-persona.
