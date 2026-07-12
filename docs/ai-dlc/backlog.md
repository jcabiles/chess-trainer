# UX / Feature Backlog

Ranked list of future improvements not built yet. Seeded from the 2026 UX research
synthesis (`contracts/specs` for the UX modernization) — the items deprioritized for the
single-user local tool — plus ideas surfaced while building the overhaul + move list.

Impact = value to the user · Effort = build + verify cost. Ordered by rough impact/effort.

> **Now spec'd:** the **Insights / Analytics Dashboard** (openings / mistakes / endgames)
> is designed in `specs/insights-dashboard.md` (+ `research/` + `tickets/`). It absorbs
> item #13 (surface time-trouble from `%clk`) and keeps item #12 (Blunder Trainer → spaced
> repetition) as an explicit out-of-scope Phase 4. Item #3 (eval graph) is adjacent.

| # | Item | What it is | Impact | Effort | Notes / why deferred |
|---|------|-----------|--------|--------|----------------------|
| 1 | ~~**Light / system theme**~~ | **SHIPPED** — theme.js + #theme-toggle (system→light→dark cycle, prefs-persisted, pre-paint script, AA-verified light tokens). Landed with the Nocturne reskin (PR #41); backlog entry was stale. | — | — | Done. |
| 2 | **Command palette (Cmd/Ctrl-K)** | Fuzzy launcher: load FEN, flip, switch mode/tab, jump to a trap/line. | M | M | Big perceived-pro upgrade for a power user; additive module + a registry of the existing actions. |
| 3 | **Eval graph** | A line chart of the eval across the whole game (click a point → jump). | M | M | **Unblocked for saved games:** game review now stores per-ply evals (`game_plies`), so a graph over a reviewed game is a small frontend add. Live-play games still need eval history captured. |
| 4 | **Move-list extras** | Variation tree (branches), eval-per-move sparkline/number, NAG glyphs. | M | H | Variation tree means replacing the flat `moves[]` with a tree model — touches persist/restore + the whole move pipeline. Big. |
| 5 | **Per-move quality on loaded/restored games** | Compute quality for history that wasn't played live this session. | L | M | **Largely delivered for saved games** by game review (per-ply quality computed + cached). Still open for live/FEN-loaded sessions that aren't imported as a game. |
| 6 | **Opening-explorer revival** | Bring back / rework the candidate-openings list (was de-emphasized by traps). | L | M | Decide repurpose vs remove first (earlier `propose-ideas` discussion). |
| 7 | **Deep assistive-tech a11y** | Screen-reader board + full keyboard board navigation (ARIA grid/treegrid, `aria-live` move announcements). | L (solo user) | H | The accessible chess board alone is a sub-project. Cheap a11y (contrast, color+label, keyboard shortcuts, `<dialog>`, reduced-motion) is already done. |
| 8 | **Vendor CDN libs offline** | Download chessground / chessops / Lucide into `static/vendor/` and switch imports to local paths. | L | L | Currently loads from `esm.sh` / jsdelivr (needs internet once). `TODO(vendor)` marker in `index.html`. |
| 9 | **Motion polish** | View-Transitions API for tab/mode switches; eval-bar ease tuning. | L | M | Motion tokens + `prefers-reduced-motion` are in place; this is the next tier of polish. |
| 10 | **P3 wide-gamut accents** | Richer accent colors on P3 displays via `@media (color-gamut: p3)`. | L | L | Pure enhancement; sRGB fallback already correct. |
| 11 | **Harden `askPromotion`** | Replace the `cloneNode` listener-reset with explicit teardown on the same node. | L | L | Not currently reachable (the `<dialog>` is modal, so no concurrent promotion), but the clone-then-detach pattern could orphan a pending Promise if that ever changes. |
| 12 | ~~**Blunder Trainer**~~ | **SHIPPED** — see `specs/blunder-trainer.md` (Leitner SR over motif buckets, Train section in Review tab). | — | — | Done. |
| 13 | **Game-review polish** | Self-hang (not missed-threat) narration; surface time-trouble from `%clk`; auto-fetch games from lichess/chess.com APIs. | M | M | Captured-but-unused: `game_plies.clock_centis` holds clock data; self-hang blunders currently lean on the best-move suggestion; import is manual only. |

| 14 | ~~**Book-badge race on rapid move-after-reset**~~ | **FIXED** (already) — PR #44's unconditional `analysisToken++` after every committed move covers the book path; the stale reset-refresh render is token-dropped. Closed 2026-07-12 during roadmap triage. | — | — | Was: pre-existing, found during blunder-trainer verification. |

> **Promoted 2026-07-12:** items #1 (light theme), #2 (command palette), #3 (eval
> graph), #13's `%clk`/auto-fetch parts, and #14 moved to the durable roadmap —
> see `roadmap/training-and-portfolio.md`. This file stays the un-promoted idea pool.

## How to pick up an item
Run `/ai-dlc <item>` to turn one into requirements → spec → tickets, same as the overhaul.
