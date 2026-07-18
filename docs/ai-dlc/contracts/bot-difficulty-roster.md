# Contracts — Bot roster expansion: aggressive-1350 + sloppy-1350 (sub-ELO)

Read-only scan (contract-mapper, 2026-07-17). Evidence `file:line`. Two new
1350-band personas: (1) aggressive attacker, weak on defense; (2) "sloppy" 1350
that makes frequent small MISTAKES (not blunders) to fake ~1100–1250 strength.

## 1. Persona schema + loader (`app/personas.py`)
- `Persona` frozen dataclass: `id,name,elo,style,description,temperature,
  blunderRate,threatDistance` (`personas.py:50-57`).
- `_parse_persona` (`personas.py:106-132`): `temperature` from style, `blunderRate`/
  `threatDistance` from elo when absent. A new entry needs only `id,name,elo,style,
  description` to load — but two personas at the SAME `elo=1350` get IDENTICAL
  elo-derived dials unless set explicitly. So hand-set the dials.
- `_validate` (`personas.py:135-153`): unique ids, `DEFAULT_ID="casey"` present,
  `_ELO_MIN=1320 <= elo <= 3000` (`personas.py:80-81`), temp finite >0, blunderRate/
  threatDistance ∈ [0,1]. **UCI_Elo floor = 1320** — can't go below via elo.
- **Any NEW dial** (e.g. `mistakeRate`) must: optional JSON key + elo/style default in
  `_parse_persona` + bound in `_validate`, else old JSON silently reverts the WHOLE
  ladder to built-in defaults (fail-silent, logger.warning only, `personas.py:176-179`).
- `data/personas.json` MUST mirror `_DEFAULT_PERSONAS` (`personas.py:85-90`) — update
  BOTH or tests (in-memory default) and server (JSON) disagree.

## 2. `/api/bot/move` persona branch (`app/main.py:688-760`)
Gate-first chain: `if gate_fired (blunder) → pick_survivor`; `elif ply<OPENING_PLIES
→ weighted_choice softmax`; `else → best move (k=1)` (B4 parity).
- Mover-POV flip explicit at `main.py:749-752` (opening branch); `pick_survivor` flips
  internally (`bot_blunder.py:383,403`).
- **Insertion seam for the mistake tier**: the post-opening `else` block
  (`main.py:756-760`) — reached only when NOT blundered. Add a new branch gated on
  `persona.mistakeRate`; personas without it fall through to byte-identical B4 best-move.
- **Reuse the single `candidates()` call** (`cands is None` guards, `main.py:743,759`)
  — a second call cold-starts the warm TT. If the blunder gate already fetched
  `CAND_K=5`, reuse it.
- **MultiPV thinning**: `BOT_MOVETIME_S=0.3` shared across `multipv=k` lines
  (`bot_engine.py:86,402`) → higher k = noisier lower-ranked scoreCp. A cp-band pick
  tolerates some imprecision.

## 3. `app/bot_blunder.py` — no mistake concept exists
- Only ONE axis: `Threat.severity_cp` (material at risk), `MIN_MISSABLE=200`,
  `severity_damp=min(1,MISS_REF/sev)` `MISS_REF=350` (`bot_blunder.py:40-45,283-291`).
  That's threat-severity, NOT move cp-loss — different axis.
- `pick_survivor` (`bot_blunder.py:359-408`) = threat-neutralization filter, not a
  cp-loss picker. Not reusable for "give me a move ~X cp worse."
- **The cp-loss band lives in `app/analysis.py`**: `INACCURACY_MAX=100, MISTAKE_MAX=250`
  (`analysis.py:44-47`), `bucket(cp_loss)` (`:81-99`), `cp_loss(...)` (`:102`). Target
  ~50–250cp maps onto the inaccuracy/mistake buckets — reusing keeps the mistake
  consistent with how the review coach later labels the SAME move.

## 4. `bot_engine.candidates(fen,k,elo)` (`bot_engine.py:369-421`)
- Returns `[{uci,san,scoreCp}]` best-first, **White-POV**, mate=±`MATE_CP=100000`
  (≠ `analysis.MATE_CP=10000`). List MAY be shorter than k (no-PV dropped,
  `:406-409`) — a cp-band pick must handle `len(cands)<idx+1` gracefully.
- Isolated process/lock, never `app.engine`.

## 5. Frontend `static/botplay.js` — fully data-driven, NO change needed
- `/api/bot/status` → `populatePersonaPicker` builds `<select>` dynamically, no
  hard-coded count/ids (`botplay.js:310-331,444`). `chosenPersonaId`/`setPersonaName`/
  `personaNameFor` all derive from the catalog.
- `requestBotMove` body ALREADY sends `personaId,seed,ply,recentMoves`
  (`botplay.js:695-715`). Both new personas are server-side selection keyed on
  `personaId` only — no JS edit.

## 6. B8 rating (`app/rating.py`) + `headers_json` — no collision
- `build_rating` reads `headers.personaElo` per saved game (`rating.py:97-104`),
  frozen at save (`main.py:885-887`). Three personas at elo=1350 don't collide —
  Elo math uses only the numeric `personaElo`, never keys by elo-uniqueness.
  Distinct `id`/`name` required (already enforced) so PGNs/review tell them apart.
- No DB schema change; `headers_json` additive.

## Protect-list
1. Legacy `personaId=None` branch B3 byte-identical (`main.py:693-696`).
2. B4 late-ply k=1+best parity for personas not opting into the mistake tier
   (`test_bot_personas_api.py::test_persona_late_ply_plays_best`).
3. Bot engine isolation — mistake tier never touches `app.engine`.
4. All RNG via `hash((seed,ply))`, never bare `random`.
5. Pure modules stay engine-free; full pytest passes with no Stockfish.
6. `_ELO_MIN=1320` floor — sloppy persona stays `elo>=1320`; sub-ELO comes from the
   mistake tier, NOT from elo.
7. `data/personas.json` + `_DEFAULT_PERSONAS` updated together.
8. Persona id/name uniqueness (three 1350s now).
9. Two MATE_CP axes — normalize before any cp-loss/bucket call (a mate candidate's
   ±100000 sentinel blows the buckets).
10. Single `candidates()` call per move — reuse `cands`.
11. Mover-POV flip before comparing any scoreCp magnitudes.
12. `headers_json.personaElo/personaId` frozen per saved game.
