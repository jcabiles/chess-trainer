# Training + Portfolio Roadmap — updated 2026-07-12

Two chapters, one queue: **Chapter 1 (training features)** runs first; **Chapter 2
(recruiter/portfolio polish)** starts only when every Chapter-1 slice is checked.
Slices are worked strictly one at a time via `/ai-dlc` — resume from the first
unchecked box. Idea pool for anything not promoted here: [`../backlog.md`](../backlog.md).

## North-star outcomes

- **N1 · Chess improvement** — Outcome: blunders/game and foreseeable-blunder rate
  (profiler metrics, already computed) | Baseline: snapshot profiler numbers when
  Chapter-1 slice 1 starts (150 games in DB today) → Target: visible downtrend over
  the next 50 imported games. Chapter-1 items rank by this.
- **N2 · Portfolio credibility (analytics-first)** — Outcome (proxy, qualitative):
  a hiring manager for an **analytics/AE role** (top priority) or AI-native DS role
  can, within a 5–10 minute skim, find and read each Chapter-2 artifact ≤2 clicks
  from the README, and each artifact survives an interview walkthrough (metric,
  dataset, method, what it caught). No quantitative baseline exists — flagged
  honestly as a proxy outcome. This north-star check is external/qualitative by
  nature; the runnable proxies live at the slice level (slices 7–9 each carry a
  concrete reproducible pass/fail).

## NOW (high confidence · ready to hand to /ai-dlc · proposed ICE order, user approves)

### Chapter 1 — training (serves N1)

- [x] **1. Book-badge race fix** — problem: move played while a reset position's
      analysis is in flight gets its Book badge overwritten by the stale eval render
      (backlog #14) · outcome-link: N1 (trust in labels) · **CLOSED 2026-07-12 as
      already-fixed**: commit `2dec2cb` (PR #44) added an unconditional
      `analysisToken++` after every committed move in `onUserMove` — book moves
      included — so the stale reset-refresh render is token-dropped
      (app.js:410/419/432 guards). Backlog #14 predates that fix; verified via
      `git log -L` on the block + reading the guards. No code change needed.
- [ ] **2. Eval graph** — problem: no game-level shape of a reviewed game; can't
      spot the collapse point at a glance (backlog #3) · outcome-link: N1 ·
      pass/fail: open a reviewed game → line chart of per-ply eval renders from
      stored `game_plies` evals (no new engine work); click a point → board jumps
      to that ply; works on an un-analyzed game (empty state) · appetite: days ·
      no-gos: no live-play eval history capture (saved games only); no new
      endpoints if existing review payload suffices · contracts:
      `contracts/game-review-coaching.md` · ICE 4·4·3=48
- [ ] **3. Auto-fetch games** — problem: manual PGN import is friction; 0 of 7,551
      stored plies have clock data because pasted PGNs lack `%clk` — blocks
      time-trouble analytics (verified 2026-07-12) · outcome-link: N1 (more games,
      richer data); feeds N2 later (real ELT ingestion story) · pass/fail: enter a
      lichess and/or chess.com username → new games land in `data/games.db` with
      clock data populated (`SUM(clock_centis IS NOT NULL) > 0`), idempotent
      re-fetch (no duplicates), auto-analysis triggers as with manual import ·
      appetite: days · no-gos: no OAuth (public APIs only); no background polling
      daemon (fetch on demand); never commit fetched game data · contracts:
      `contracts/auto-analyze.md`, `contracts/game-review-coaching.md`; external
      APIs are greenfield — /ai-dlc maps them · ICE 4·4·3=48
- [x] **4. Time-trouble insights** — problem: user blunders under clock pressure
      but nothing surfaces it; clock columns were empty until slice 3
      (backlog #13 part) · outcome-link: N1 · **CLOSED 2026-07-12 as
      already-built + chain-tested**: the card (insights.js `renderTimeTrouble`)
      and clock-bucket analytics (`insights._time_trouble`: <10s…>2m buckets,
      min-sample guard, honest unclocked-games note) shipped with Insights
      Phase 2 and were dark only for lack of clock data. Slice 3 supplies the
      data; a new integration test (`test_fetch_api.py::TestFetchLightsUpTimeTrouble`)
      proves the full fetch → %clk → clock_centis → time-trouble chain exits
      the empty state. Live population happens on the user's first real fetch.
- [ ] **5. Command palette** — problem: power-user navigation (load FEN, switch
      tab/mode, jump to trap/line) takes many clicks (backlog #2) · outcome-link:
      N1 (weak — friction) + N2 (perceived polish); flagged: weakest N1 link in
      Chapter 1, kept by explicit user pick · pass/fail: Cmd/Ctrl-K opens
      palette; fuzzy-matches ≥ these actions: switch tab, flip, load FEN, open
      trap, open repertoire line; keyboard-only operable; `:focus-visible` +
      AA contrast hold · appetite: days · no-gos: no new backend endpoints;
      registry built from existing `api.actions` · contracts:
      `contracts/appjs-split.md` · ICE 3·4·3=36
- [x] **6. Light theme** — problem: dark-only; OS-light users get mismatch
      (backlog #1) · outcome-link: N1 (weak) + N2 (visual range) · **CLOSED
      2026-07-12 as already-shipped**: `static/theme.js` + `#theme-toggle`
      header button already implement the full system→light→dark cycle with
      prefs persistence, a pre-paint inline script, live OS-scheme tracking,
      and complete `html[data-theme="light"]` token overrides documented as
      AA-verified per pair (style.css:95-135). Backlog #1 predates the
      Nocturne reskin (PR #41). Every pass/fail criterion already met in
      shipped code; no work needed.

### Chapter 2 — portfolio (serves N2; starts after Chapter 1 is fully checked)

- [ ] **7. KPI tree + metric dictionary** — problem: repo shows no
      business-analysis framing; HMs for analytics roles screen for goal→metric
      decomposition (2026 hiring research) · outcome-link: N2 · pass/fail:
      `docs/analytics/kpi-tree.md` exists: "improve my chess" decomposed into
      driver metrics (blunder rate, foreseeable-blunder rate, opening adherence,
      endgame conversion, accuracy/Elo…), each with definition, computation
      source (module/table), and an honest caveat; linked from README ≤2 clicks;
      reviewed by fresh-context reviewer for BA rigor · appetite: days (writing)
      · no-gos: no new app code; no invented metrics the app doesn't compute ·
      contracts: none (doc-only)
- [ ] **8. "State of my chess" analysis report** — problem: no artifact proves
      data→insight→recommendation skill — the core analytics screen · outcome-link:
      N2 · pass/fail: `docs/analytics/state-of-my-chess.md`: written analysis over
      the real games DB — ≥5 findings, each traceable to a stated query/number
      (queries included in an appendix), segmented (opening/phase/color), ending
      in ranked recommendations; uses slice-7 metric definitions; README-linked;
      fresh-context reviewer confirms every number reproduces · appetite: days ·
      no-gos: no notebooks as the deliverable; no auto-generation; personal data
      stays aggregated (no full game dumps committed) · contracts: read-only over
      `app/profile.py` / `app/insights.py` seams
- [ ] **9. LLM eval harness for AI commentary** — problem: the one LLM feature has
      zero quality evidence; eval design is the #1 AI-native hiring signal ·
      outcome-link: N2 · pass/fail: golden set of ≥10 reviewed games checked in
      (facts payloads + cached commentary); deterministic grounding checks run in
      pytest offline (every concrete claim consistent with engine facts — no API
      needed); LLM-as-judge scoring script + ≥30 human-rated samples with
      judge-vs-human agreement reported; `docs/analytics/EVALS.md` publishes
      method + results tables + failure modes + "where I don't trust the judge";
      README-linked; full pytest suite still passes offline · appetite: ~week ·
      no-gos: judge runs are on-demand scripts, not CI-blocking; API spend
      ceiling ~$5/run; no prompt rewrites in this slice (measure first) ·
      contracts: `contracts/narrative-review.md`

## NEXT (validated problems · not yet spec'd)

- **Self-hang narration gap** — evidence: self-hang blunders currently narrated
  via best-move suggestion, not "you hung the piece" (backlog #13 part) ·
  candidate slices: motif/narration extension in review pipeline · open
  questions: detectable purely via SEE/motifs? overlap with existing
  hanging-piece motif? · serves N1.
- **Live/FEN-session move quality** — evidence: quality labels exist only for
  live-evaluated or imported-game moves; a restored/FEN-loaded session shows
  none (backlog #5 remainder) · candidate slices: on-demand "analyze this line"
  action reusing review pipeline · open questions: worth engine cost vs
  importing as a game? · serves N1.
- **Opening-explorer decision** — evidence: candidate-openings list de-emphasized
  since traps shipped (backlog #6) · this is a decide-then-maybe-build: repurpose
  vs remove · open questions: does Insights opening view already cover it? ·
  serves N1 (declutter) — user decides direction before any slice.

## LATER (bets · no dates)

- **Bet: Coach chat** — problem: answering "which openings do I blunder most in?"
  requires clicking through Insights; a NL analytics interface (agent + tool-use
  over SQLite) is also the strongest AE×AI-native fusion artifact · segment: N2
  both role tracks (+N1 convenience) · confidence: med · assumptions to test:
  cost/question acceptable (~cents); text-to-SQL guardrails (read-only connection,
  table allowlist) sufficient; judge from slice 9 reusable for answer-quality
  evals · review-by: after slice 9 lands (explicit user decision: evals first,
  then agent) — promote via user approval only.
- **Bet: Training-effectiveness write-up** — problem: no evidence the blunder
  trainer changes the blunder rate; a small honest causal analysis (interrupted
  time series over profiler history) shows classical-DS judgment · segment: N2
  (AI-native/DS track; user rated less important) · confidence: low-med ·
  assumptions to test: enough post-trainer games for any signal (small-n);
  trainer-usage timestamps queryable · review-by: revisit once ≥30 games
  post-trainer-adoption exist.

## Out of scope / no-gos (global)

- **No dbt/warehouse toolchain** (user decision 2026-07-12 — analytics story told
  through analysis artifacts, not tooling).
- **No hosted/cloud demo; app stays local-first.** No notebooks-as-deliverable;
  no auto-generated reports.
- **No OAuth anywhere** (API keys only — Anthropic ToS).
- Repo invariants hold for every slice: pure modules stay engine-free; one
  engine process behind the lock; no DB schema change unless the slice's spec
  says so; LLM never enters the deterministic review path; tokens-only CSS,
  AA contrast; never commit `data/games.db` / `data/games/`; Conventional
  Commits, feature branches only.
- Low-tier backlog stays in `backlog.md` (vendor offline, motion polish, P3
  gamut, deep a11y, variation tree, askPromotion) — not promoted.

## Standing user task (not a slice)

- [ ] Real-key smoke test of AI commentary: `export ANTHROPIC_API_KEY=…`,
      restart, Generate commentary once on a reviewed game (README setup §5).

## Process notes

- Contract mapping: existing `docs/ai-dlc/contracts/*.md` (17 files) already
  cover every brownfield area this roadmap touches; referenced per-slice above
  instead of re-mapping. Only greenfield area: lichess/chess.com fetch APIs
  (slice 3) — mapped during that slice's /ai-dlc run.
- Ordering is ICE-scored (data thin); scores shown per slice. **The user owns
  the final order and every Later→Next→Now promotion.**
- Hand-off per slice: `{problem, outcome-link, pass/fail, appetite, no-gos}` →
  `/ai-dlc`. Verify a pass/fail actually passes before checking a box.
