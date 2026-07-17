# Training + Portfolio Roadmap — updated 2026-07-16

> **Progress 2026-07-12 (autonomous run):** every slice was implemented or
> closed in one pass, delivered as stacked PRs **#48→#54** (merge in order;
> each PR's base is the previous branch). Boxes below stay unchecked until
> their full pass/fail — including the browser/live steps only the user can
> run — actually passes. Per-slice status notes inline.

Two chapters, one queue: **Chapter 1 (training features)** runs first; **Chapter 2
(recruiter/portfolio polish)** starts only when every Chapter-1 slice is checked.
Slices are worked strictly one at a time via `/ai-dlc` — resume from the first
unchecked box. Idea pool for anything not promoted here: [`../backlog.md`](../backlog.md).

## North-star outcomes

- **N1 · Chess improvement** — Outcome: blunders/game and foreseeable-blunder rate
  (profiler metrics, already computed) | Baseline: snapshot profiler numbers when
  Chapter-1 slice 1 starts (150 games in DB today) → Target: visible downtrend over
  the next 50 imported games. Chapter-1 items rank by this.
- **N3 · Sparring loop (bots)** — Outcome: regular full games against
  realistic, ELO-graded bots feed the existing review/profiler pipeline so N1's
  blunder metrics trend over *sparring* games, not just imported ones |
  Baseline: 0 bot games exist (feature absent) → Target: bot games/week > 0 and
  appearing analyzed in the Game Library + profiler; a personal ELO estimate
  exists and updates per result (baseline: none). Added 2026-07-16 from the
  bots discovery interview (Chapter 3).
- **N2 · Portfolio credibility (analytics-first)** — Outcome (proxy, qualitative):
  a hiring manager for an **analytics/AE role** (top priority) or AI-native DS role
  can, within a 5–10 minute skim, find and read each Chapter-2 artifact ≤2 clicks
  from the README, and each artifact survives an interview walkthrough (metric,
  dataset, method, what it caught). No quantitative baseline exists — flagged
  honestly as a proxy outcome. This north-star check is external/qualitative by
  nature; the runnable proxies live at the slice level (slices 7–9 each carry a
  concrete reproducible pass/fail).

## NOW (high confidence · ready to hand to /ai-dlc · proposed ICE order, user approves; Chapter 3 orders by dependency gating — see its header)

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
      `contracts/game-review-coaching.md` · ICE 4·4·3=48 ·
      **STATUS: implemented (PR #49)** — pytest green; remaining pass/fail
      step: user opens a reviewed game in the browser and click-jumps once
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
      APIs are greenfield — /ai-dlc maps them · ICE 4·4·3=48 ·
      **STATUS: implemented (PR #50)** — 10 mock-transport tests green
      (clocks/dedupe/tagging/errors); remaining pass/fail step: one live
      fetch against the user's real account
- [ ] **4. Time-trouble insights** — problem: user blunders under clock pressure
      but nothing surfaces it; clock columns exist and are empty until slice 3
      lands (backlog #13 part) · outcome-link: N1 · pass/fail: with clocked games
      imported, Mistakes tab time-trouble card populates (blunder rate at low
      clock vs otherwise, min-sample guard); empty state remains honest with no
      clock data · appetite: days · no-gos: no per-move clock UI in replay (card
      only, this slice) · contracts: `contracts/insights-endgames.md` (insights
      seams) · **hard-gated: cannot start before slice 3 lands (sort floor = after
      slice 3), regardless of ICE tie** · ICE 3·4·4=48
- [ ] **5. Command palette** — problem: power-user navigation (load FEN, switch
      tab/mode, jump to trap/line) takes many clicks (backlog #2) · outcome-link:
      N1 (weak — friction) + N2 (perceived polish); flagged: weakest N1 link in
      Chapter 1, kept by explicit user pick · pass/fail: Cmd/Ctrl-K opens
      palette; fuzzy-matches ≥ these actions: switch tab, flip, load FEN, open
      trap, open repertoire line; keyboard-only operable; `:focus-visible` +
      AA contrast hold · appetite: days · no-gos: no new backend endpoints;
      registry built from existing `api.actions` · contracts:
      `contracts/appjs-split.md` · ICE 3·4·3=36 ·
      **STATUS: implemented (PR #52)** — remaining pass/fail step: user
      presses Cmd-K once and runs a command in the browser
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
      contracts: none (doc-only) ·
      **STATUS: delivered (PR #53)** — fresh-context verifier code-checked
      every definition; two wording errors found and fixed. Check the box on
      merge
- [ ] **8. "State of my chess" analysis report** — problem: no artifact proves
      data→insight→recommendation skill — the core analytics screen · outcome-link:
      N2 · pass/fail: `docs/analytics/state-of-my-chess.md`: written analysis over
      the real games DB — ≥5 findings, each traceable to a stated query/number
      (queries included in an appendix), segmented (opening/phase/color), ending
      in ranked recommendations; uses slice-7 metric definitions; README-linked;
      fresh-context reviewer confirms every number reproduces · appetite: days ·
      no-gos: no notebooks as the deliverable; no auto-generation; personal data
      stays aggregated (no full game dumps committed) · contracts: read-only over
      `app/profile.py` / `app/insights.py` seams ·
      **STATUS: delivered (PR #53)** — verifier re-ran every appendix query
      (all numbers reproduced); one framing issue (cherry-picked openings)
      found and fixed. Check the box on merge
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
      contracts: `contracts/narrative-review.md` ·
      **STATUS: harness delivered (PR #54)** — golden set (10 real sanitized
      games), grounding checks in CI (11 tests), judge runner + agreement
      machinery ready; remaining pass/fail steps need ANTHROPIC_API_KEY:
      first judge run + human ratings for the agreement table

### Chapter 3 — play vs bots (serves N3 → N1; added 2026-07-16)

> Discovery interview 2026-07-16 (confirmed at gate): **problems** — P1 openings
> never face realistic varied replies (repertoire trainer drills *my* moves
> only); P2 can't practice punishing typical human mistakes at my level
> (profiler: 240× hanging-piece leaks to punish); P3 real games allow no
> takebacks after a stupid blunder; P4 no sense of own strength trend.
> **Appetite: ~2 weeks committed = Phase A only.** Honest math (refuter
> 2026-07-16): all eight slices sum to 15–21 working days (~3–4 weeks).
> **Phase A (inside the 2-week appetite): B1 → B2 → B3 → B6** (~6–9 days:
> research, skeleton, N1 save-loop, takebacks — a complete playable core).
> **Phase B (B4 → B5, B7, B8, ~9–12 days) exceeds the stated appetite and
> starts only on an explicit user re-up** after Phase A proves the loop is
> fun. Contracts: `../contracts/bot-play.md` (headline: bot move generation
> is greenfield; engine strength options are process-global on the one shared
> Stockfish — B1 decides isolation). ICE scores below are reference input
> only — hard dependency gating (B1 first) fully determines executable order
> in this chapter; **user owns final order + promotions**.

- [x] **B1. Research spike: what makes chess bots human-like** — problem:
      P2/P1 realism is a research question, not a build question (user
      requirement: blunders must be *causal* — e.g. a low-ELO bot misses your
      threat because it's busy orchestrating its own attack — never
      chess.com-style random drops) · outcome-link: N3 (whole chapter hangs on
      this) · deliverable: `../research/chess-bots.md` covering, each with
      cited sources + a recommendation: (a) engine strategy — Stockfish
      weakening (Skill Level / UCI_Elo / node caps: known to feel non-human at
      low levels — verify) vs **Maia/lc0** (neural nets trained on human games
      per rating band) vs hybrid, including the process-isolation question
      from `contracts/bot-play.md` and install feasibility on this Mac;
      (b) human-error modeling — literature on rating-conditioned mistake
      types (tunnel vision during own attacks, missed defensive resources,
      horizon effects) and how to reproduce them deterministically;
      (c) opening variety — weighted books vs policy sampling, per-persona
      repertoire bias; (d) think-time realism — feasibility of
      criticality-weighted delays from engine signals (eval swing, multipv
      gap); (e) persona design — how ELO + style (aggressive/solid/…) map to
      concrete engine/model parameters · pass/fail: research doc exists with
      all five sections evidence-backed; includes output of a **runnable local
      probe** (script driving Stockfish at ≥2 weakened settings over test
      positions, plus lc0/Maia install check); ends in a single recommended
      architecture; **user approves the direction before B2 starts** ·
      appetite: 2–3 days · no-gos: no production code; no engine-invariant
      change (that happens only via B2+'s specs) · ICE 5·4·4=80
- [x] **B2. Walking skeleton: play one full game vs one bot** — problem:
      P1/P2 need a live opponent at all before realism matters · outcome-link:
      N3 · scope: new `bot-play` mode (mode-handler registry + PRACTICE_MODES);
      a "get bot move" server call per B1's architecture (interim Stockfish
      weakening acceptable if B1 says so; wrapped in
      `note_interactive_start/end`); one default ~1200 persona; new-game flow
      (pick color), bot auto-replies, game-end detection (mate/stalemate/
      resign button), untimed, session-persistence decision per spec ·
      pass/fail: in the browser, start a bot game as White and as Black; bot
      replies arrive automatically and legally; play to a real end (mate or
      resign); exiting the mode restores the prior play session · appetite:
      2–3 days · no-gos: no personas beyond one, no clocks, no save-to-DB, no
      blunder model (skeleton only) · **hard-gated on B1 user sign-off** ·
      ICE 5·4·3=60
- [ ] **B3. Bot games auto-save into the review pipeline** — problem: N3's
      core loop — sparring games must feed the profiler like imported games do
      · outcome-link: N3+N1 · scope: on game end, render a well-formed PGN
      (White/Black = persona vs user, Result; `%clk` comments once B7 lands)
      → existing `_import_pgn_batch` with `source='bot'` + explicit
      `my_color_override`; auto-analysis triggers as on import; profiler/
      insights/blunder-trainer pick the game up with zero changes ·
      pass/fail: finish a bot game in the browser → it appears in the Game
      Library, auto-analyzes, is correctly color-tagged (SQL:
      `source='bot'` row present; profiler game count increments) ·
      appetite: 1–2 days · no-gos: **no DB schema change** (source/
      headers_json/name fields only — anything more forces a spec first);
      never commit game data · depends on B2 · ICE 5·5·4=100 (cheapest
      N1-link in the chapter)
- [ ] **B4. Persona ladder + opening variety** — problem: P1 (varied
      realistic replies) + P2 (graded difficulty) — one fixed bot trains
      neither · outcome-link: N3 · scope: 4–6 named personas (ELO ~800–2000,
      style params per B1: aggressive/solid/…), persona picker UI (persisted
      pref), per-persona weighted opening books so repeat games diverge ·
      pass/fail: (a) 10 games vs one persona produce ≥6 distinct first-4-ply
      sequences; (b) an offline fast-preset probe harness shows monotonic
      strength ordering across the ladder (higher persona scores majority vs
      lower over N quick games); (c) picker persists across reload ·
      appetite: 3–4 days · no-gos: no avatar art (Next); no blunder-model
      work (B5) · **hard-gated on B1 · depends on B2** (needs the bot-play
      mode) · Phase B · ICE 4·3·3=36
- [ ] **B5. Human-like blunder + style model** — problem: P2's core — the
      user's explicit requirement that low-ELO bots fail *causally* (miss your
      threat while pursuing their own plan), not randomly · outcome-link: N3 ·
      scope: implement B1's recommended error model, style-conditioned per
      persona · pass/fail: (a) offline harness — blunder rate per ELO band
      matches the target curve from B1 within stated tolerance; (b) blunder
      *context* check — ≥ the B1-specified share of injected/emergent errors
      occur in positions where the bot had an active plan or a missable
      opponent threat (measured with the existing motif/threat probes), NOT
      uniformly random; (c) user plays ≥3 games vs a low persona and signs
      off that mistakes read as human · appetite: 3–4 days · no-gos: no LLM
      move selection; model must be deterministic-ish/seedable for tests ·
      **hard-gated on B1 · depends on B4** (style-conditioning needs the
      personas) · Phase B · ICE 5·3·2=30 (highest value, most uncertain —
      ICE kept honest)
- [ ] **B6. Takeback control** — problem: P3 — punishing a mis-click/stupid
      blunder with a lost game kills training value; user wants it policed,
      not free · outcome-link: N3 · scope: per-match setting **never / up to
      3 per game / anytime** (persisted pref, default "up to 3"); bot-mode-
      local undo semantics (a takeback rewinds the full move pair; global
      undo() stays play-mode-only); takeback count shown · pass/fail: in the
      browser each policy enforces correctly (4th takeback blocked under
      "up to 3"; counter resets on new game; "never" hides/disables the
      control) · appetite: 1 day · no-gos: no server-side enforcement
      (client-owned history is the existing trust model) · depends on B2 ·
      ICE 4·5·5=100
- [ ] **B7. Clocks + time controls** — problem: real-game realism —
      confirmed at gate: clock enforced for BOTH sides, flag = loss · outcome-
      link: N3 (and feeds the existing time-trouble insights) · scope:
      time-control menu (untimed default · e.g. 5+0 · 10+0 · 15+10), live
      dual clocks in bot mode, flag ends the game with the correct result;
      saved PGNs embed `%clk` so `clock_centis` analytics light up ·
      pass/fail: in the browser, run the human's clock out → game ends as a
      loss and saves with that result; SQL: bot-game plies have
      `clock_centis IS NOT NULL` · appetite: 2 days · no-gos: no clock in
      ordinary analysis play mode; no bot think-time realism yet (Next) ·
      depends on B2 (and B3 for the saved-PGN check) · Phase B · ICE 4·4·3=48
- [ ] **B8. Personal ELO estimate** — problem: P4 — no strength trend across
      sparring games · outcome-link: N3 · scope: running rating updated per
      bot-game result vs the persona's rating (standard Elo K-factor update;
      relationship to `accuracy.py`'s per-game est-Elo documented in the
      spec); shown in the bot hub + simple history; **derived read-model over
      stored bot games (recompute-from-history), no new tables** ·
      pass/fail: unit tests on the update math; browser: a win vs a
      1200-rated persona moves the estimate by the expected amount; reload →
      recomputed value equals displayed value · appetite: 1–2 days · no-gos:
      no schema change; bot games only (imported human games keep using
      accuracy.py's per-game estimate) · depends on B3+B4 · Phase B ·
      ICE 3·4·4=48

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
- **Realistic bot think-time** (Chapter 3 follow-on) — evidence: user request
  at interview — instant replies feel robotic; bots should "think" longer on
  critical moves/inflection points · candidate slices: criticality-weighted
  delay from engine signals (eval swing between plies, multipv gap), capped
  so waits never annoy · open questions: B1 must confirm which signals
  correlate with human think-time; UX ceiling for acceptable delay · serves
  N3 · gated on B1+B2.
- **Persona avatars** (Chapter 3 follow-on) — evidence: user nice-to-have —
  unique realistic faces per persona · candidate slices: user generates
  images with ChatGPT (user task, outside the app), app displays bundled
  avatar assets in the picker + game header · open questions: none technical
  (static assets) · serves N3 (legibility of the roster) · gated on B4.
- **Bot-vs-human insights segmentation** — evidence: once B3 lands,
  `source='bot'` cleanly splits the games DB; mixing sparring games into
  human-game analytics may skew trends · candidate slices: source filter in
  Insights/profiler views · open questions: default to combined or split? ·
  serves N3+N1 honesty.

## LATER (bets · no dates)

- **Bet: Coach chat** — problem: answering "which openings do I blunder most in?"
  requires clicking through Insights; a NL analytics interface (agent + tool-use
  over SQLite) is also the strongest AE×AI-native fusion artifact · segment: N2
  both role tracks (+N1 convenience) · confidence: med · assumptions to test:
  cost/question acceptable (~cents); text-to-SQL guardrails (read-only connection,
  table allowlist) sufficient; judge from slice 9 reusable for answer-quality
  evals · review-by: after slice 9 lands (explicit user decision: evals first,
  then agent) — promote via user approval only.
- **Bet: Adaptive leak-hunting persona** — problem: generic bots train generic
  skills; the profiler already knows the user's specific leak patterns (240×
  hanging, hope-chess rate) — a persona that deliberately steers toward
  positions testing those leaks would train the exact punish/defend skill N1
  measures · segment: N3+N1 · confidence: low-med · assumptions to test:
  position-steering toward motif classes is feasible with the chosen engine
  architecture (B1 evidence); enough leak data per motif to target · review-by:
  after B5 lands and ≥20 bot games are in the DB.
- **Bet: Bot table-talk / post-game persona commentary** — problem: personas
  feel flat without voice; the narrative-review pipeline (PR #36) already
  turns engine facts into prose · segment: N3 (fun) + N2 (another LLM artifact)
  · confidence: low · assumptions to test: persona-voiced commentary stays
  grounded (reuse slice-9 eval harness); cost per game acceptable · hard
  boundary: **LLM never selects moves** (global no-go) · review-by: after
  Chapter 3 must-haves ship.
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
- **Chapter 3 (bots) additions:** no LLM move selection ever (LLM voice/
  commentary is a Later bet, moves are engine/model only); the one-engine
  invariant changes **only** via a B1-evidenced, spec'd decision (a second
  engine process is a candidate outcome, not a default); takeback/clock
  enforcement stays client-side (no server session state); bot game data
  lives in the gitignored games.db like all game data.

## Standing user task (not a slice)

- [ ] Real-key smoke test of AI commentary: `export ANTHROPIC_API_KEY=…`,
      restart, Generate commentary once on a reviewed game (README setup §5).
- [ ] If B1 recommends Maia/lc0: install `lc0` + Maia weights in your own
      terminal (network installs are sandbox-blocked for Claude) — exact
      commands will land in the B1 research doc.

## Process notes

- Contract mapping: existing `docs/ai-dlc/contracts/*.md` (17 files) already
  cover every brownfield area this roadmap touches; referenced per-slice above
  instead of re-mapping. Only greenfield area: lichess/chess.com fetch APIs
  (slice 3) — mapped during that slice's /ai-dlc run.
- Ordering is ICE-scored (data thin); scores shown per slice. **The user owns
  the final order and every Later→Next→Now promotion.**
- Hand-off per slice: `{problem, outcome-link, pass/fail, appetite, no-gos}` →
  `/ai-dlc`. Verify a pass/fail actually passes before checking a box.
