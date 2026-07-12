# Tickets — analysis-speed

Spec: `specs/analysis-speed.md` · Contracts: `contracts/analysis-speed.md`
Sequential T1→T5 (each builds on the previous); T6 verify + T7 env-report close it out.
One branch, ticket-per-commit.

## T1 — Engine preset table + threads/hash (backend core)
Replace interactive `Limit(depth=18, time=INTERACTIVE_SOFT_TIME_S)` with the preset table
(`fast`=nodes 400k/t 0.5 · `balanced`=nodes 800k/t 0.8 · `deep`=nodes 12M/t 1.4);
`analyze`/`analyze_interactive_multi` take a `speed` preset (default `balanced`), `depth`
param removed from interactive signatures; `ENGINE_THREADS` = env override or
`max(1, (os.cpu_count() or 4) - 2)`; `ENGINE_HASH_MB` 128→256 (+env); warm-TT invariant
comment (no `game=`/`ucinewgame` — refuter-confirmed already warm).
- **Owns:** `app/engine.py`, `tests/test_engine.py`
- **Deliberately rewrite** `TestSoftCapAndMultiPVLimit` (`test_engine.py:203-233`) to the
  new preset→Limit assertions; add cpu_count-None test.
- **Done when:** `pytest tests/test_engine.py -q` passes with no Stockfish binary;
  review's `analyze_multi(depth=10)` path untouched.

## T2 — API plumbing: `speed` field + `depth` in Analysis (depends T1)
`MoveRequest`/`AnalyzeRequest` gain `speed: Literal['fast','balanced','deep'] = 'balanced'`;
`main.py` threads it into the 3 interactive call sites (`main.py:356, 370, 440-441`);
`/api/trainer/check` (`main.py:1321-1328`) adapted, pinned `balanced`; `Analysis` gains
`depth: int | None` populated from the after-position primary info line in
`_build_analysis` (White-POV code untouched).
- **Owns:** `app/main.py`, `app/models.py`, `tests/test_api.py`
- **Done when:** engine-free API tests pass: speed accepted+defaulted, invalid preset →
  422, `depth` present, both `/api/move` calls receive identical limits (matched-limit
  contract), trainer-check regression test green; full `pytest -q` passes.

## T3 — Preset UI: Fast/Balanced/Deep control (depends T2)
Three-state control next to the Evaluate toggle (analyzeColor pattern,
`app.js:1075-1083`); persisted via `prefs.js` `engineSpeed` (default `balanced`); sends
`speed` on `/api/move` + `/api/analyze`; on change: bump `analysisToken` +
`refreshAnalysis()`. Preset-flip-mid-move race accepted (spec §1).
- **Owns:** `static/app.js`, `static/index.html`, CSS file styling the play controls
- **Done when:** browser check — control renders, selection persists across reload,
  changing preset re-evaluates current position; tokens-only CSS, `:focus-visible`,
  AA contrast.

## T4 — Depth caption (depends T2, parallel-safe with T3 if files stay disjoint — they
don't fully (index.html/CSS possible overlap) → run after T3)
Extend the existing inline `pv-depth` caption seam (`panel.js:117-120`, defensive read
`panel.js:315`) to show real reached depth (e.g. `d16`).
- **Owns:** `static/panel.js` (+ CSS token touch if needed)
- **Done when:** eval renders with depth caption on analyzed moves; absent (not stale) on
  book/skipped panels.

## T5 — Docs touch-up (depends T1–T4)
CLAUDE.md "Constraints" line if engine defaults changed materially; note `ENGINE_SOFT_TIME`
retirement from interactive path.
- **Owns:** `CLAUDE.md`
- **Done when:** doc matches shipped behavior.

## T6 — End-to-end verify (depends T1–T4)
Full `pytest -q` (no binary) + live-server Playwright pass per spec Verify-by #3, and
latency evidence (#4): time an analyzed move on each preset — fast/balanced sub-second,
deep ≈2–3 s, all ≪ old 6 s worst case; 2nd-best line + retro block still render.
- **Done when:** evidence captured in PR description.

## T7 — Environment report (no code)
Check installed Stockfish version + build arch (≥17, native ARM); check ruff presence
(pre-existing gap). Report to user; recommend `brew upgrade stockfish` if outdated.
- **Done when:** findings reported in chat/PR.

**Hotspot note:** `app/main.py`, `static/app.js`, `static/index.html` are single-owner
hotspots — T2/T3 must not run concurrently with any other work touching them.
