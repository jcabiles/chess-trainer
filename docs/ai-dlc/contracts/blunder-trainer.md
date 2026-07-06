# Contract map — Blunder Trainer (re-solve own blunders + spaced repetition)

Read-only scan (contract-mapper, 2026-07-05) ahead of the Blunder Trainer epic
— the deferred third head of the game-review coaching epic.

## Data available to seed puzzles

- **`leaks`** (`app/storage.py:97-117`, `LeakRecord` :126-152): `game_id, ply,
  color, severity('mistake'|'blunder'), category, phase`; `motif_json`
  (OPPONENT-threat motifs from `motifs.detect_motifs()`, `app/review.py:483-499`);
  `threat_motif` single string; `hung_square`, `threat_uci` (opponent's
  punishing reply, null-move probe :456-464), `best_uci`/`best_san` (what user
  should have played, pv[0] :311-319); `lead_in_ply` (**display-only** —
  defaults `ply-1` :410; never authoritative for the puzzle FEN);
  `tags_json`; `win_prob_before/after/drop` (difficulty/priority signal).
- **`game_plies`** (:83-95): `fen_before` per ply = the puzzle's starting FEN
  (join on `leaks.ply`); `is_user_move`, `clock_centis`.
- **`pos_cache`** (:69-81): keyed `(epd_key, depth)` — reusable solution
  validation at the recorded depth; mismatched depth = silent cache miss.
- **`games`**: `my_color, opening, eco, date` for filtering.
- **Read-model precedent:** `profile.py`/`insights.py` issue raw read-only SQL
  via `storage._get_conn()`; **writes** must be new functions in `storage.py`
  (only file importing sqlite3).

## Contracts to honor (ranked)

1. **Leak IDs are UNSTABLE.** `write_leaks()` deletes+reinserts all leaks per
   game on every re-analysis (`app/storage.py:441-482`); AUTOINCREMENT issues
   new ids; retag/color changes reset `analysis_status` → re-analysis
   (:521,571). **SR/attempt state must key on a stable natural key**
   (`(game_id, ply, threat_motif)` or FEN+motif hash), never `leaks.id`.
   New tables referencing `games(id)` should `ON DELETE CASCADE` (pattern
   :84,:99; `delete_game` relies on it :301-309).
2. **Schema-change gate:** `profile.md:32` — no DB change unless a spec says
   so; THIS epic's spec is the authorizing doc. Pattern: bump
   `_SCHEMA_VERSION` (:37), add `CREATE TABLE IF NOT EXISTS` to `_SCHEMA_DDL`
   (:43-118), extend `_run_migrations` (:159-178 — the migration body is a
   never-exercised stub; new-table-only changes ride the IF NOT EXISTS path).
3. **Motif vocabulary closed, duplicated:** `'hanging'|'fork'|'knight_fork'|
   'pin'|'skewer'|'discovered'|'back_rank'` + review's `'mate'|'missed_threat'`
   (`app/motifs.py:247-249`, `app/review.py:507-514`);
   `coaching.name_cluster()` hardcodes the same keys (:317-345). No positional
   similarity index exists — "similar position" = exact category match only.
4. **POV normalization authority:** any eval comparison reuses
   `analysis.pov_score_to_white_cp`/`classify` (pattern `app/main.py:396-402`).
5. **Engine lock + yield:** puzzle-check engine calls must wrap
   `review.note_interactive_start()`/`note_interactive_end()` in try/finally
   (`app/review.py:111-127`; template `app/main.py:384-394`) or background
   analysis and puzzle UI starve each other.
6. **Depth pinning:** leaks computed at `BACKGROUND_DEPTH=10`
   (`app/review.py:85`) vs interactive `DEFAULT_DEPTH=18` (`engine.py:56-57`).
   Re-checking at a different depth can disagree with the stored `best_uci`.
   `leaks` does NOT store its depth; `pos_cache` does.
7. **New client mode housekeeping (hub edits):** add mode to `persist()`'s
   transient early-return list (`static/app.js:126-129`), call
   `registerModeHandlers(mode, {onMove, exit})` (two positional args), AND add
   the mode to `PRACTICE_MODES` (`static/app.js:103`) for the fail-loud guard.
8. **One-directional module contract:** new `static/` module receives injected
   api, never imports app.js; hub services via `api.hub.*`
   (`static/app.js:849-869`), actions via `api.actions.*`; canonical shape =
   `static/setup.js` / `static/traps.js` / `static/repertoire.js`.
9. **Qualification gate:** only leaks from games with
   `my_color IS NOT NULL AND analysis_status='done'` count as "yours"
   (`app/profile.py:43-49`).
10. **Narration reuse:** hint/explanation text via
    `coaching.get_narrator().narrate_leak()` (`app/coaching.py:494-510`) —
    don't invent a second narrator.

## Integration points

- Routes in `app/main.py` only; schemas in `app/models.py`; literal-before-
  `{id}` route ordering. Puzzle-detail endpoint mirrors
  `GET /api/games/{game_id}/review` (:763-829); move-check mirrors
  `POST /api/move` (:330-415) minus book/skip branches; engine via
  `Depends(get_engine)`; testable through `ScriptedEngine` fake seam.
- Frontend: new injected-api module + `initX(api)` in app.js init + index.html
  markup/tab; deep-link precedent `api.actions.openGameAtPly` (insights →
  review at ply).

## Prior locked decisions (from game-review epic)

- Trainer deferred by `specs/game-review-coaching.md:11-12,102`; design notes
  research §4.
- **de la Maza caveat (requirement, not suggestion):** naive SR of the
  identical position teaches board recall, not transfer — resurface the MOTIF
  in varied positions (`research/game-review-coaching.md:83-85`,
  `backlog.md:27`).
- No LLM; `COACH_NARRATOR` seam stays the pluggable narration point.

## Open questions for the requirements interview

1. Puzzle identity / SR durability across re-analysis (natural key choice).
2. "Varied positions" sourcing: own-history same-motif leaks vs synthetic
   perturbation vs external puzzle bank (new dependency).
3. Solved = exact `best_uci` match, or eval-window acceptance (needs engine)?
4. Depth policy for validation (store recorded depth? accept deeper re-check?).
5. SR algorithm + where state lives (new pure module + storage tables?).
6. Frontend placement: new top-level tab vs section inside Review; new
   interactive mode vs review-mode affordance.
