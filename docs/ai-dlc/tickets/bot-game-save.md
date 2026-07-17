# Tickets — B3: Bot games auto-save into the review pipeline

Spec: [`../specs/bot-game-save.md`](../specs/bot-game-save.md).
Branch: `feat/bot-game-save` off up-to-date main.
Wave plan (disjoint owners): **W1:** T1 ∥ T3 ∥ T4 → **W2:** T2 (needs
T1's route contract) ∥ nothing else → **W3:** T5 verify → T6 review → T7
close-out. (T2 client save-triggers depends on T1's route; T3/T4 are
independent.)

## T1 — `/api/bot/save` route + PGN builder + tests (W1)
New `POST /api/bot/save` in `app/main.py`: build a python-chess PGN from
`{movesUci, userColor, personaLabel, result, startedAt, rated}` (headers per
spec: persona vs "You" by color, Result, Date, Event="Bot game <startedAt>"),
`source='bot'`, `headers_json=json.dumps({"rated": rated})`. Extend
`_import_pgn_batch` with optional `headers_json: str | None = None` (thread
into the `fields` dict slot at main.py:822; existing callers unaffected).
Call `_import_pgn_batch(pgn, userColor, engine, source='bot',
headers_json=headers_json)`. Empty moves → 400; `result='*'` → 400. Plus
`GameSummary.source` exposure (`app/models.py` + `_game_summary`).
- **Owns:** `app/main.py` (bot-save section + `_import_pgn_batch` param +
  `_game_summary` line), `app/models.py`, `tests/test_bot_save.py`
- **Done:** `pytest tests/test_bot_save.py -q` green (fake engine):
  source='bot' rows, headers_json rated true/false, my_color by color, names,
  1-ply persists, stable-startedAt dedup, distinct-startedAt two rows,
  empty→400, '*'→400, GameSummary carries source, import/fetch still
  headers_json=None.

## T2 — `static/botplay.js` rated state + save triggers (W2, after T1)
Read the Rated toggle at game start → `rated` on descriptor; mint
`startedAt`. `saveGame(snapshot)` — snapshot captured SYNCHRONOUSLY before
teardown; success = ImportResponse `imported+duplicates>=1` (not just
postJSON resolving); `botMarkSaved(startedAt)` identity-guarded. Finished
trigger (casual + rated: real result). Exit/New-game trigger — ordered:
finished-but-unsaved → re-save REAL result; else unfinished+rated → loss;
else discard. ≥1-move guard. Must not fight the B2 busy/replyToken machinery.
- **Owns:** `static/botplay.js`
- **Done:** manual/browser: finished game POSTs once; rated-abandon posts a
  loss; casual-abandon posts nothing; a WON rated game whose finish-POST
  failed re-saves as a WIN (not a loss) on exit; no double-save; stale save
  can't mark a new game.

## T3 — `static/app.js` descriptor round-trip (W1) — HOTSPOT, single owner
`botGame` gains `startedAt` + `saved` + `rated`; persist/restore `bot-play`
branch carries all three; new `botMarkSaved(startedAt)` hub seam
(identity-guarded set + persist); `botSetGame` mirrors the three fields.
- **Owns:** `static/app.js`
- **Done:** existing suite green; a persisted bot game round-trips
  startedAt/saved/rated across refresh; no regression to B2 persistence.

## T4 — Rated toggle UI + "vs Bot" badge (W1)
`static/index.html`: a Rated toggle (default off) + hint in the "Play vs
Bot" section. `static/review.js`: badge when `game.source === 'bot'`.
`static/style.css`: token-only toggle + badge styles, both themes.
- **Owns:** `static/index.html`, `static/review.js`, `static/style.css`
- **Done:** toggle renders (default off) with stable id for T2; a
  source^=bot row shows the badge; imported rows unchanged; both themes.

## T5 — Browser verification (W3, after all)
Spec Verify-by-3: play a bot game to mate/resign → appears in Library with
badge, auto-analyzes to done, correct color; SQL `source='bot'` present +
profiler count increments; abandon → '*' row; refresh-then-exit → no dup.
- **Owns:** verification evidence
- **Done:** every Verify-by-3 item observed; `pytest`/`ruff` green.

## T6 — Dual review of the diff (W3, after T5)
Refuter + Codex (gpt-5.6-sol) on the branch diff: dedup correctness, save-
trigger races, my_color/profiler correctness, no schema drift, no B2
regression. Fold findings; re-verify touched items.
- **Owns:** review findings
- **Done:** both resolved or accepted; suite green.

## T7 — Close-out (W3, after T6)
User exercises pass/fail → mark B3 `[x]` + reorder B8 to follow B3 in the
roadmap; `pytest`/`ruff`; commit; push; PR.
- **Owns:** roadmap, git close-out
- **Done:** PR open; B8 promoted to next; B6 still available.

## Notes
- Live-reload hazard: work only on the feature branch checked out once;
  never switch branches mid-work under the user's uvicorn --reload.
- Appetite guard (1–2 days): cut order if over — badge polish → abandoned-
  game trigger (finished-only is the minimum viable). Never cut: source='bot'
  tagging, stable-hash dedup, my_color correctness.
