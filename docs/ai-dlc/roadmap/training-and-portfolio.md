# Training + Portfolio Roadmap — updated 2026-07-18

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
- **N4 · App-as-product analytics** — Outcome: honest product-metrics story
  (single-subject engagement time series + pre/post causal feature studies)
  served by a best-practice local-first data platform (events → contracts →
  DuckDB/dbt marts → Dagster) with zero practitioner red flags | Baseline:
  no telemetry, no warehouse (2026-07-18) → Target: ≥12 KPI-traced events
  flowing through contract-validated ELT into tested dbt marts on a green
  scheduled DAG; ≥1 pre-registered experiment reaching its stopping rule +
  ≥1 quasi-experimental study, both reproducible one-command from the
  warehouse; every mart segmentable by user_type. Added 2026-07-18;
  deliberately reverses the 2026-07-12 no-dbt no-go.
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
- [x] **2. Eval graph** — problem: no game-level shape of a reviewed game; can't
      spot the collapse point at a glance (backlog #3) · outcome-link: N1 ·
      pass/fail: open a reviewed game → line chart of per-ply eval renders from
      stored `game_plies` evals (no new engine work); click a point → board jumps
      to that ply; works on an un-analyzed game (empty state) · appetite: days ·
      no-gos: no live-play eval history capture (saved games only); no new
      endpoints if existing review payload suffices · contracts:
      `contracts/game-review-coaching.md` · ICE 4·4·3=48 ·
      **CLOSED 2026-07-18 — browser-verified:** `#review-eval-graph` renders an
      18-point eval line from stored per-ply evals; a trusted click on a graph
      point jumps the board to that ply (landed on Qg5). PR #49.
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
      slice 3), regardless of ICE tie** · ICE 3·4·4=48 · **STATUS 2026-07-18:**
      the `_time_trouble` card + `clock_centis` pipeline are BUILT (confirmed via
      the B7 clocks contract scan); currently 0 of 7,551 stored plies have clock
      data (all `source='import'`), so the card correctly shows its honest empty
      state. The POPULATED path unlocks once clocked games arrive — your live fetch
      (slice 3) or saved bot games (B7 now emits `%clk`). Empty-state = done;
      populated = data-gated on you.
- [x] **5. Command palette** — problem: power-user navigation (load FEN, switch
      tab/mode, jump to trap/line) takes many clicks (backlog #2) · outcome-link:
      N1 (weak — friction) + N2 (perceived polish); flagged: weakest N1 link in
      Chapter 1, kept by explicit user pick · pass/fail: Cmd/Ctrl-K opens
      palette; fuzzy-matches ≥ these actions: switch tab, flip, load FEN, open
      trap, open repertoire line; keyboard-only operable; `:focus-visible` +
      AA contrast hold · appetite: days · no-gos: no new backend endpoints;
      registry built from existing `api.actions` · contracts:
      `contracts/appjs-split.md` · ICE 3·4·3=36 ·
      **CLOSED 2026-07-18 — browser-verified:** Cmd/Ctrl-K opens `#cmdk`
      (12 commands: tab nav, flip, undo/redo, load FEN, traps, repertoire);
      typing "trap" fuzzy-filters to the trap catalog; Enter runs + closes;
      keyboard-operable. PR #52.
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

- [x] **7. KPI tree + metric dictionary** — problem: repo shows no
      business-analysis framing; HMs for analytics roles screen for goal→metric
      decomposition (2026 hiring research) · outcome-link: N2 · pass/fail:
      `docs/analytics/kpi-tree.md` exists: "improve my chess" decomposed into
      driver metrics (blunder rate, foreseeable-blunder rate, opening adherence,
      endgame conversion, accuracy/Elo…), each with definition, computation
      source (module/table), and an honest caveat; linked from README ≤2 clicks;
      reviewed by fresh-context reviewer for BA rigor · appetite: days (writing)
      · no-gos: no new app code; no invented metrics the app doesn't compute ·
      contracts: none (doc-only) ·
      **CLOSED 2026-07-18 (PR #53 + refresh):** re-audited every metric's
      computation source against real code (AST-scanned all cited symbols +
      schema columns exist); corrected 7 drifted citations (endgame-conversion
      rule = win-prob ≥0.8 sustained ≥4 plies, accuracy `-3.17` sign, exact
      `file::function` + `table.column` refs). README links it in 1 click.
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
> **Phase A (inside the 2-week appetite): B1 → B2 → B3 → B4 → B8 → B6**
> (research, skeleton, N1 save-loop, persona-ladder, personal-ELO, takebacks —
> a complete playable core). **Status 2026-07-18: PHASE A COMPLETE + B5 SHIPPED —
> B1, B2, B3, B4, B8, B6, B5 all done. Only B7 (clocks) remains in the whole
> chapter. B5 (the causal-blunder model, the marquee "realistic bots" feature)
> was built on a user re-up; B7 is the last slice.** **B4 pulled into Phase A + resequenced ahead of B8
> 2026-07-16 (user call):** a personal-ELO trend is only meaningful against a
> rated LADDER of opponents, so the persona ladder ships first; B8 then tracks
> results across the ladder. **Phase B (B5, B7, ~5–8 days) exceeds the stated
> appetite and starts only on an explicit user re-up** after Phase A proves the
> loop is fun. (B5 = the causal human-like blunder model + behavioral style,
> which B4 deliberately defers.) Contracts: `../contracts/bot-play.md` (headline: bot move generation
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
- [x] **B3. Bot games auto-save into the review pipeline** — problem: N3's
      core loop — sparring games must feed the profiler like imported games do
      · outcome-link: N3+N1 · scope: on game end, render a well-formed PGN
      (White/Black = persona vs user, Result; `%clk` comments once B7 lands)
      → existing `_import_pgn_batch` with `source='bot'` + explicit
      `my_color_override`; auto-analysis triggers as on import; profiler/
      insights/blunder-trainer pick the game up with zero changes ·
      **Shipped 2026-07-16** — added a **Rated/Casual** toggle (casual saves
      only on a real ending; rated always saves, quitting = a loss) with
      rated-ness in `headers_json` (`{"rated": bool}`, kept off `source` so B4
      personas + B8's rated query don't collide); browser-verified end-to-end
      (finish/casual-abandon/rated-abandon/refresh-dedup) ·
      pass/fail: finish a bot game in the browser → it appears in the Game
      Library, auto-analyzes, is correctly color-tagged (SQL:
      `source='bot'` row present; profiler game count increments) ·
      appetite: 1–2 days · no-gos: **no DB schema change** (source/
      headers_json/name fields only — anything more forces a spec first);
      never commit game data · depends on B2 · ICE 5·5·4=100 (cheapest
      N1-link in the chapter)
- [x] **B4. Persona ladder + opening variety** — problem: P1 (varied
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
      mode) · Phase A · ICE 4·3·3=36 · **Shipped 2026-07-16 (PR pending):**
      Gate-1 narrowed to **4 personas UCI_Elo 1350–2000** (no sub-1320 Skill
      rung) + **candidate-sampling** variety (no curated books); style =
      temperature only (Contempt removed from SF; deep behavioral style → B5);
      resign deferred to B5. Correctness locks (dual review): White→mover-POV
      score flip, atomic strength-switch+search under one lock (survives
      watchdog restart), mate→±MATE_CP, bare-`{fen}` B3-parity, save
      server-resolves persona Elo. Variety measured: 5 distinct first moves /
      12 seeds. Personas ride `headers_json` (personaId+personaElo) for B8.
- [x] **B5. Human-like blunder + style model** — problem: P2's core — the
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
      ICE kept honest) · **Shipped 2026-07-18 (PR pending):** Gate-1 scoped to
      the **signature plan-fixation mechanism (A) + low-band drop**, deferring
      C (calculation-decay). Pure engine-free `app/bot_blunder.py`: detect the
      opponent's threat (incl. a mate-in-1 scan) → if it's OFF the bot's plan
      attention-set + severity/persona/seed gates fire, drop threat-neutralizing
      candidates so the bot plays its best remaining plan move (input-side, never
      random). Research-calibrated per-persona dials (blunderRate/threatDistance),
      bigger threats damped (severity_damp) so mate/queen rarely missed;
      deterministic per seed; **never leaks into the user's analysis**. Validated:
      unit tests + a ladder-monotonicity harness (Casey 81% → Vera 19% miss) +
      live server proof (Casey ignores an off-plan hanging knight, Vera defends,
      legacy=full-strength). Refuter PASS. **Tuning note:** Casey's hanging-queen
      miss ~33% (MISS_REF=350 dial) may read blundery — tune `data/personas.json`
      after playtesting. Coach narration of the "why" deferred (internal only).
- [x] **B6. Takeback control** — problem: P3 — punishing a mis-click/stupid
      blunder with a lost game kills training value; user wants it policed,
      not free · outcome-link: N3 · scope: per-match setting **never / up to
      3 per game / anytime** (persisted pref, default "up to 3"); bot-mode-
      local undo semantics (a takeback rewinds the full move pair; global
      undo() stays play-mode-only); takeback count shown · pass/fail: in the
      browser each policy enforces correctly (4th takeback blocked under
      "up to 3"; counter resets on new game; "never" hides/disables the
      control) · appetite: 1 day · no-gos: no server-side enforcement
      (client-owned history is the existing trust model) · depends on B2 ·
      ICE 4·5·5=100 · **Shipped 2026-07-17 (PR pending):** entirely
      client-side. New bot-mode-local `botTakeback()` hub method (truncate the
      last pair, botGame↔state lockstep, bump moveToken/analysisToken, full
      ground.set re-render); Gate-1 added **rated→casual flip on first takeback**
      (reuses the `rated` flag → excluded from the B8 bot-ELO, no schema change)
      + idle-only (no mid-think cancellation). Refuter caught a real HIGH in
      browser verify (button never appeared during live play — missing
      `reflectControls()` on the bot-reply handback) + a note-accuracy LOW
      (persisted `ratedFlipped` flag) — both fixed + re-reviewed PASS.
      **Phase A COMPLETE.**
- [x] **B9. Difficulty roster (aggressive-1350 + sloppy sub-ELO)** — problem:
      the ladder had one 1350 (Casey) and no way below Stockfish's UCI_Elo 1320
      floor; wanted a sharper attacker and a believable ~1100–1250 beginner ·
      outcome-link: N3 (a fuller, more human sparring roster) · scope: two new
      1350-band personas — **Diego** (aggressive attacker, weak on defense —
      PURE DATA reusing the B5 causal-blunder gate: high temperature + low
      `threatDistance` 0.10 + high `blunderRate` 0.85) and **Robin** (sloppy,
      via a NEW post-opening "mistake tier": with prob `mistakeRate=0.5` play a
      candidate 50–250cp worse than best — `analysis` inaccuracy/mistake bands —
      keeping `blunderRate` low so it drifts but rarely hangs; effective
      ~1100–1250) · **Shipped 2026-07-18 (PR pending):** new pure engine-free
      `bot_blunder.should_mistake/pick_mistake` (int-salted `hash((seed,ply,1))`
      determinism, mover-POV, `MATE_GUARD` on the bot_engine scoreCp axis,
      bounded so the tier NEVER plays a >250cp blunder-magnitude move); new
      `mistakeRate` persona dial; wired into the `/api/bot/move` persona
      post-opening branch AFTER the blunder gate, single `candidates()` call
      (`assert MISTAKE_K==CAND_K==SAMPLE_K`). Zero frontend change (picker is
      data-driven). Refuter (pre-build) folded 6 findings incl. an unbounded-
      fallback HIGH + a str-hash determinism MED + a monotonicity-test landmine;
      diff refuter (SHIP) folded 2 LOWs (dead fallback removed, ladder blind-spot
      closed). Real-engine verify: Robin plays genuine in-band mistakes; B3/B4
      parity + no analysis-engine leak preserved. Spec/contracts/tickets:
      `../specs/bot-difficulty-roster.md`. · depends on B4 + B5.
- [x] **B7. Clocks + time controls** — problem: real-game realism —
      confirmed at gate: clock enforced for BOTH sides, flag = loss · outcome-
      link: N3 (and feeds the existing time-trouble insights) · scope:
      time-control menu (untimed default · 5+2 · 10+0 · 10+5), live
      dual clocks in bot mode, flag ends the game with the correct result;
      saved PGNs embed `%clk` so `clock_centis` analytics light up ·
      depends on B2 (and B3 for the saved-PGN check) · Phase B · ICE 4·4·3=48
      · **Shipped 2026-07-18 (PR pending):** entirely client-side (server stays
      stateless). KEY FINDING: the time-trouble analytics consumer was ALREADY
      built + shipped (`insights._time_trouble`, `game_plies.clock_centis`
      column, the insights UI card) — starved of data because no bot PGN emitted
      `%clk`. So B7 = (a) client clocks + (b) EMIT `%clk`; NO schema change, NO
      new consumer. Presets Gate-1: **5+2/10+0/10+5**; reload PAUSES clocks
      (away-time not charged, accepted-by-design); takeback RESTORES clocks by
      ply-parity (even=White). Server writes `%clk` (H:MM:SS.s, matches the
      `pgn.py` reader regex) from a client-sent pre-increment `moveTimes[]` in
      the existing replay loop; flag-loss = plain `0-1`/`1-0` (no Termination
      header, no 4th result, no `rating.py` change). Refuter: spec PASS (5 folds:
      tick-reset atomicity, reload-refund accepted, takeback parity, pre-
      increment %clk, casual clock correctness); diff PASS + 1 LOW folded
      (`_format_clk` negative clamp). Codex infra-DOWN → refuter-only fail-open.
      962 tests + live browser verify (5+2 clock ticks the side-to-move live
      05:00→04:59, correct data-active). Spec: `../specs/bot-clocks.md`.
      **⟹ chess-bots epic (Chapter 3) COMPLETE — all of B1–B9 shipped.**
- [x] **B8. Personal ELO estimate** — problem: P4 — no strength trend across
      sparring games · outcome-link: N3 · scope: running rating updated per
      bot-game result vs the persona's rating (standard Elo K-factor update;
      relationship to `accuracy.py`'s per-game est-Elo documented in the
      spec); shown in the bot hub + simple history; **derived read-model over
      stored bot games (recompute-from-history), no new tables** ·
      pass/fail: unit tests on the update math; browser: a win vs a
      1200-rated persona moves the estimate by the expected amount; reload →
      recomputed value equals displayed value · appetite: 1–2 days · no-gos:
      no schema change; bot games only (imported human games keep using
      accuracy.py's per-game estimate) · depends on B3 + **B4 (shipped)** — the
      persona ladder now supplies per-opponent ratings via `headers_json`
      (`personaId`/`personaElo`), so the Elo update runs against a real range of
      opponents · ICE 3·4·4=48 · **Shipped 2026-07-17 (PR pending):** Gate-1
      scoped to **bot-ELO + chess.com anchor only** (no move-quality est-Elo —
      it overlaps chess.com + is uncalibrated); seed 1350, K=32; pure
      `app/rating.py` read-model + `GET /api/rating` (recompute-from-history, no
      persisted Elo, no schema change); rated bot games only (casual excluded),
      pre-B4 rows lacking `personaElo` skipped. Dual-reviewed (refuter PASS ×2;
      Codex spec-stage folded 6, diff-stage infra-blocked). Browser-verified:
      a rated loss vs Alex(1800) moved 1350→1348 live, persisted across reload,
      casual games ignored, chess.com anchor persists.

### Chapter 4 — realistic bots on Maia (serves N3 → N1; added 2026-07-18)

> Discovery interview 2026-07-18 (confirmed at gate): **outcome** — bots feel
> indistinguishable-from-human sparring partners at honest ratings 800–2000,
> measured two ways per slice: (a) user playtest sign-off, (b) an automated
> **trace audit** (bot move-match % against its Maia band; no engine-signature
> moves like instant mate-spotting or 0-loss grinding). **Problems:** P5 —
> weakened-SF bots still show engine texture at every level (B5/B9 mitigate but
> don't remove it; B1 evidence: Maia beats weakened SF at human-move prediction
> by 10–19 pts); P6 — no beginner opponents: roster floors at 1350 (UCI_Elo
> floor ~1320), user wants 800–1400 with 2–3 style-varied bots per rung.
> **Confirmed shape:** lc0/Maia = move source for every persona ≤1900
> (band-matched net; Mandeep 2000 stays SF); the shipped causal-blunder +
> mistake layers stay ON TOP of Maia; variety via Python-side seeded sampling
> of Maia's policy priors (installed lc0 0.32.1 has NO temperature option —
> verified 2026-07-18; MultiPV + VerboseMoveStats expose P values → reuse the
> `personas.weighted_choice` idiom); sub-1100 = maia-1100 + the existing
> error-injection tiers, ratings labeled as calibrated estimates; roster = full
> grid, 2–3 styles per rung at 800/1000/1200/1400 (~10–12 new personas).
> **Appetite: ~2 weeks (full chapter).** Honest math (refuter-corrected
> 2026-07-18): six slices sum to 11–17 working days — exceeds the appetite at
> the high end; M5/M6 drop to a re-up if calibration eats the budget.
> **Install prerequisite DONE 2026-07-18:** lc0 0.32.1 (brew, Metal backend) +
> all nine maia-1100…1900 nets in `~/maia_weights/`; `detect_maia()` reports
> ready. Research base: `../../design/research/engine-adaptation/maia-lc0.md` +
> `../research/chess-bots.md`. Contracts: `../contracts/bot-play.md` (+ the
> B2–B9 wiring notes in specs). Dependency-gated order M1→M6; **user owns
> final order + promotions**.

- [x] **M1. Maia engine walking skeleton** — DONE 2026-07-18 (browser-verified:
      Ming Ling on live Maia — 1.e4 e5 2.Nf3 d6 3.Nc3 Nf6 4.d4 Nc6; kill-lc0
      mid-game → same-request SF fallback + indicator flip + auto-respawn next
      move; 992 tests engine-free; no orphan lc0 on shutdown) — problem: P5 —
      no lc0 move path
      exists (`detect_maia()` is detection-only) · outcome-link: N3 ·
      scope: new `app/maia_engine.py` mirroring the `bot_engine.py` idiom
      (own subprocess, own asyncio.Lock, lazy start, watchdog restart,
      import-safe when lc0/weights absent); loads one net, `go nodes 1`,
      returns candidates + policy priors (VerboseMoveStats/MultiPV parse);
      band selection = weights-swap restart or per-band process (spec
      decides, cite second-engine-process-patterns research); wire ONE
      existing persona (Ming Ling 1350 → maia-1400) through `/api/bot/move`
      behind a fallback: lc0 missing/dead → current weakened-SF path
      unchanged; spec must state the single-process assumptions explicitly
      (asyncio.Lock guards ONE uvicorn worker — document the single-worker
      deployment constraint; blocking lc0 I/O + restarts run in the executor
      so the event loop never stalls, mirroring bot_engine) · pass/fail:
      full browser game vs Maia-backed Ming Ling;
      pytest green with no lc0 binary (fake seam, mirrors `get_engine`);
      kill lc0 mid-game → next move still arrives via SF fallback ·
      appetite: 2–3 days · no-gos: no change to user-analysis engine.py;
      other personas untouched; no schema change
- [x] **M2. Human variety via policy sampling** — DONE 2026-07-18 (live: 12
      seeds at startpos → e4×6/d4×5/e3×1 matching maia-1400 human
      frequencies; same seed replays identically; 1003 tests incl. 2000-draw
      frequency sweep + failure-soft degenerate cases) — problem: Maia is
      deterministic at argmax — same position, same move, every game (B1
      evidence; official lichess Maia bots bolt on books for this) ·
      outcome-link: N3 · scope: seeded sampling over Maia's policy prior
      (reuse `weighted_choice` softmax; per-persona temperature reinterpreted
      as policy-sampling sharpness; floor/cap so sampling never picks a
      <~2%-prior howler move by accident) · pass/fail: same position,
      different seeds → ≥2 distinct sensible moves across 10 seeds;
      same seed → identical move (determinism per seed preserved for
      replay); unit tests engine-free · appetite: 1–2 days · no-gos: no
      opening-book files (sampling-only, per B4 decision)
- [ ] **M3. Realism trace-audit harness** — problem: "realistic" needs a
      repeatable number BEFORE the big switch, or regressions are invisible
      (the outcome's instrument) · outcome-link: N3 measurement · scope:
      offline runnable script (`docs/ai-dlc/verify/` idiom) that replays a
      persona over a test-position set + saved bot games and reports:
      move-match % vs its Maia band net, blunder/mistake frequency vs the
      persona's dials, engine-signature flags (instant mates found, 0-cp-loss
      streaks); baseline run against the CURRENT weakened-SF personas
      committed as the before-picture · **anti-contamination design (Codex
      2026-07-18): the harness ships TWO position sets — an open dev set
      (tuning allowed) and a SEALED eval set (never used for tuning; used
      only for slice acceptance and, later, as Chapter-5's frozen experiment
      instrument) — and the instrument is versioned so any later change is
      visible** · pass/fail: harness runs offline in one command; produces
      per-persona report; baseline numbers committed; dev/eval split
      documented + eval set hash-pinned · appetite: 1–2 days · no-gos: no
      live-server dependency; engine calls only through the existing
      bot/maia engine modules; eval-set positions never enter any tuning
      loop
      · **build status 2026-07-19: harness + tests + spec SHIPPED**
      (`tools/realism_audit.py` — shared `select_persona_move`, independent
      depth-14 loss oracle, Wilson CIs, sf-only/current modes; 19 engine-free
      tests on synthetic ECO-disjoint fixtures; verified offline against real
      weak-SF bot + strong-SF oracle). REMAINING before checkbox: run
      `tools/fetch_lichess_sample.py` against one lichess month (network) to
      populate `data/realism/`, then commit `docs/analytics/realism-baseline.md`
      with real eval-set numbers + eval hash.
- [ ] **M4. Switch the ladder to band-matched Maia** — problem: P5 across
      the whole existing roster · outcome-link: N3 · scope: personas ≤1900
      get `maiaBand` (Ming Ling/Nina/Amanda 1350-band → 1300/1400 nets,
      Diana 1550 → 1500/1600, Melvin 1800 → 1800; Mandeep stays SF —
      explicit non-goal); causal-blunder gate + mistake tier re-wired to run
      over Maia candidates (gate-first wiring preserved: only widen k when
      the gate fires); dial recalibration per persona (Maia already carries
      human error — blunderRate/mistakeRate likely DROP; tune via M3
      harness + playtest) · **acceptance metric fixed (Codex 2026-07-18):
      once Maia IS the move source, "move-match vs the Maia net" is circular
      — acceptance instead uses the SEALED eval set scored against HELD-OUT
      REAL HUMAN games of the band (a lichess rating-band sample the bots
      never trained or tuned on): human-move-match ≥ weakened-SF baseline
      +8 pts, blunder frequency within the band's human profile, zero
      engine-signature flags; tuning happens only on the dev set** ·
      pass/fail: sealed-eval report per switched persona as above; user
      playtests ≥1 game per switched persona and signs off each; full pytest
      green engine-free · appetite: 3–4 days · no-gos: persona ids stable
      (localStorage/PGN/ELO keys); rating.py untouched; legacy bare-{fen}
      branch stays SF; no tuning against the sealed set
- [ ] **M5. Sub-1100 calibration (the 800/1000 rungs)** — problem: P6 —
      Maia floors at 1100 and plays above its label; honest 800/1000 needs
      dragging DOWN · outcome-link: N3 · scope: error-injection tiers
      (mistakeRate/blunderRate on top of maia-1100) tuned per rung via an
      auto-calibration match harness (candidate persona vs SF UCI_Elo ladder
      anchors, score → effective-Elo estimate; cite
      rating-calibration/honest-bot-rating-assignment.md); displayed ratings
      labeled "est." in the rail; two probe personas (one 800, one 1000)
      prove the method · pass/fail: each probe persona's measured effective
      Elo within ±150 of its label over ≥30 harness games; playtest: a
      beginner-level game feels sloppy-human, not random · appetite: 2–3
      days · limitation named in the report (Codex 2026-07-18): SF-anchor
      matches measure strength vs engine texture, not humanness — pair the
      Elo estimate (with its confidence interval) with a maia-1100
      blunder-profile comparison, and label both as estimates · no-gos: no
      maia2/PyTorch in-process dependency (explicit interview decision); no
      new engine binaries
- [ ] **M6. Full beginner-to-club roster (the grid)** — problem: P6 roster
      breadth — 2–3 style-varied bots per rung at 800/1000/1200/1400 ·
      outcome-link: N3 · scope: ~10–12 new personas as PURE DATA
      (data/personas.json: band + dials + name + description; picker/rail
      are data-driven — B9 proved zero-frontend-change), reusing M5's
      calibration for sub-1100 rungs; distinct styles within a rung =
      temperature + threatDistance/mistakeRate contrasts (B9's Diego-vs-Robin
      pattern); avatars: user generates images (standing task), id-keyed
      files into gitignored `data/avatars/`; rail UX check — ~18 cards needs
      grouping-by-rung or scroll affordance (small CSS-only tweak allowed) ·
      pass/fail: every new persona appears in rail + picker with correct
      rating; M3 audit per persona in-band; ladder-monotonicity tests updated
      (group-max invariant, B9 lesson) and green; user picks + plays ≥3 new
      bots and signs off the roster feels varied · appetite: 3–4 days
      (Codex: this is a roster release + calibration campaign, not pure
      data — may ship in two waves: 1200/1400 rungs first, sub-1100 wave
      second) · no-gos: no schema change; persona ids never reuse existing
      six

### Chapter 5 — analytics-engineering platform (serves N4 + N2; added 2026-07-18)

> Discovery + dual ideation 2026-07-18 (user interview → 5 seed directions →
> refuter round 1 + extension round + two cited research dossiers:
> `../research/analytics-portfolio/telemetry-contracts-pipeline.md`,
> `../research/analytics-portfolio/simulation-experiments-validity.md`).
> **DELIBERATELY REVERSES the 2026-07-12 "no dbt/warehouse toolchain" no-go**
> (role requirements changed: SQL depth, dbt, DAG orchestration, and
> data→insight→business-value analysis are now the target signals).
> **New north-star N4 · App-as-product analytics** — Outcome: the app has an
> honest product-metrics story (engagement as single-subject time series,
> feature effectiveness as pre/post causal studies) served by a best-practice
> local-first data platform a practitioner AE reviewer finds zero red flags
> in | Baseline: no product telemetry, no warehouse, analytics = hand-rolled
> Python in app/insights.py → Target: every slice's pass/fail below.
> **Standing requirements:** (1) every data model carries a `user_type`
> segmentation dimension ∈ {real, bot, synthetic} so all downstream marts can
> aggregate or split honestly (user-mandated); (2) after every research
> session agents write dossiers under `../research/analytics-portfolio/`
> (feeds the eventual Obsidian "Analytics Engineer Playbook" wiki — see
> Standing user tasks); (3) n=1 limitations always named in the artifact, not
> hidden. **Budget: ≤$50/mo; current design needs ~$5/mo (Cloudflare R2 for
> the lichess calibration slice) — everything else local DuckDB.**
> **Queue: starts after Chapter 4 (Maia bots) — user decision. Appetite:
> eight slices sum to 17–22 working days (post-review split of the two fat
> slices); the effectiveness study additionally needs ~2–3 months of
> calendar time for post-intervention data to accumulate, so it runs gated
> in the background of the queue, not as a blocking step.** Key
> anti-red-flag decisions (research-backed): batch cursor ELT NOT CDC (SQLite
> has no change log; events immutable); Dagster software-defined assets NOT
> Airflow (both reviewers independently: Airflow = resume-driven overkill at
> one-user scale — the written justification is itself the signal); no
> SELECT-* staging, declared grain, tested PKs, dbt contracts `enforced` on
> marts, breaking changes via model versions.

- [ ] **P1. Product KPI tree + event tracking plan** (the foundation — defines
      what the app emits) — problem: the app has no product-level metrics; the
      shipped Chapter-2 KPI tree measures the USER's chess, not the app as a
      product · outcome-link: N4 · scope: extend `docs/analytics/kpi-tree.md`
      (build on, never duplicate) with the app-as-product layer: north-star =
      engagement time series (sessions/wk, plies analyzed/wk, features
      touched/session) + feature-effectiveness pre/post metrics; then a
      **tracking plan**: ~12–20 events max, Object-Action past-tense names
      (`Game Started`, `Move Played`, `Drill Completed`), envelope spec
      (event_id UUID, occurred_at + received_at, session_id, schema_version,
      app_version), every event traced to a KPI it serves (orphan events
      rejected); **activity counters are not KPIs by themselves (Codex
      2026-07-18) — each engagement counter must state the outcome it proxies
      and how it links to the N1 improvement metrics (e.g. plies-analyzed/wk
      → blunder-rate trend), with known failure modes noted (features
      touched/session rises when navigation confuses)** · pass/fail: doc
      review — each event maps to a metric, each metric to the north-star
      WITH its counter→outcome link stated; explicit "n=1, single-subject"
      framing section; no SaaS-costume metrics (DAU/retention cohorts
      banned) · appetite: 1–2 days · no-gos: no code yet; no new repo
- [ ] **P2a. Event spine + data contracts** (app emits validated events) —
      problem: no instrumentation exists · outcome-link: N4 · scope: app
      emits P1's events to an append-only local log (JSONL or SQLite events
      table), validated at emit time against per-event **JSON Schemas
      versioned in-repo** (SchemaVer, a mini registry = the data contract);
      CI contract tests; `user_type` stamped at the source · pass/fail:
      events flow during a real session; emit-time validation rejects a
      malformed event in a pytest; contract CI fails on an incompatible
      schema edit · appetite: 2 days · no-gos: no cloud services; app
      behavior never blocks on telemetry (fire-and-forget, app works with
      logging off)
- [ ] **P2b. dbt warehouse + SQL-parity port** (tested marts over the events
      + games) — problem: analytics logic lives as 951 lines of hand-rolled
      Python (app/insights.py) with no SQL story · outcome-link: N4 · scope:
      new `warehouse/` dbt project (DuckDB): cursor-based incremental ELT
      from the event log + a read-only games.db extract → staging (1:1
      sources, explicit columns, no joins) → intermediate → marts with
      declared grain (`fct_games`, `fct_moves`, `fct_drill_attempts`) and
      **`user_type` dimension on every mart**; dbt contracts `enforced` on
      marts; the SQL-depth proof: port 3–4 insights.py aggregations (win
      rates, time-trouble, endgame conversion) into marts with a
      **golden-file test asserting dbt output == Python output pinned to a
      tagged snapshot of the game set** (parity = correctness evidence, not
      a live coupling — the dbt layer is labeled a point-in-time portfolio
      artifact, NOT a second source of truth, so the two implementations
      never have to co-evolve) · pass/fail: `dbt build` green from zero
      twice (idempotent); pinned golden-file parity test passes · appetite:
      2–3 days · no-gos: no cloud services; app runtime never depends on the
      warehouse; pure modules stay engine-free
- [ ] **P3. Dagster orchestration of the real jobs** — problem: DAG/
      orchestration skill unproven; the app already has a real multi-stage
      flow with real failure modes (import → background engine analysis →
      now dbt refresh) · outcome-link: N4 · scope: Dagster OSS
      software-defined assets wrapping event-log extract, games.db extract,
      dbt models (dagster-dbt), freshness/row-count checks; retries + alerts
      on the engine-analysis dependency; GitHub Actions CI runs `dbt build`
      + contract tests on PRs; README section justifying Dagster-not-Airflow
      at this scale (the justification IS the signal); **spec must draw the
      production boundary explicitly (Codex 2026-07-18): the app's own
      import/background-analysis stays app-owned — Dagster assets observe
      and consume (extract, transform, check freshness), they do not
      re-trigger app-runtime work; every asset idempotent with stated
      ownership/handoff semantics so retries can't duplicate work; all five
      tools (duckdb, dbt-core, dbt-duckdb, dagster, dagster-dbt)
      version-pinned with a one-paragraph upgrade policy** · pass/fail: one
      command materializes the full asset graph; a killed engine mid-run
      shows a failed asset + successful retry without duplicate rows; CI red
      on a broken model · appetite: 2 days · no-gos: no always-on daemon
      requirement; no Airflow; Dagster never writes to app-owned state
- [ ] **P4a. Tournament harness + A/A validation** (prove the measurement
      machine before any experiment) — problem: synthetic-population
      experiments are valid ONLY with fishtest-style discipline, and the
      harness itself must be validated first · outcome-link: N4 + N3 ·
      scope: scheduled bot-vs-bot tournament harness (personas from Chapters
      3–4) writing games to the warehouse as `user_type='bot'`; **wall-clock
      honesty (Codex 2026-07-18): at fast-preset speeds throughput is
      ~50–120 games/hour on one engine — the harness reports projected
      run-time per design, and experiments are scoped to LARGE effects or
      bounded max-N**; A/A validation with teeth (not
      absence-of-significance): repeated A/A batches under the final config
      must show empirical false-positive rate consistent with the declared
      α AND the outcome metric inside a pre-stated equivalence margin;
      sample-ratio (SRM) chi-square check; one permanently-frozen held-out
      persona as instrument-stability baseline · pass/fail: A/A report
      meets the margin + FPR criteria; SRM clean; harness one-command
      re-runnable · appetite: 2–3 days · no-gos: no experiment claims from
      this slice; dials frozen during validation runs
- [ ] **P4b. Lichess calibration + first pre-registered experiment** —
      problem: the flagship walkthrough-able experiment a practitioner
      respects · outcome-link: N4 + N3 · scope: calibration layer: one
      rating-band-filtered lichess monthly dump slice (~1.5GB zst → parquet
      on R2, ~$5/mo) proving the bot population's move/error distributions
      track real players; then ONE experiment: **treatment = a PROSPECTIVE
      product feature (Codex: NOT the already-shipped Maia switch — e.g. a
      new matchmaking/difficulty policy or opening-variety change), dated
      pre-registration committed BEFORE the run (hypothesis, primary metric
      on the M3 SEALED versioned instrument, SPRT bounds + a max-N budget
      sized to harness throughput — "inconclusive at max-N" is a valid,
      publishable outcome)**; write-up includes an explicit "claims we
      cannot make from synthetic data" box (no human engagement/retention
      claims) · pass/fail: calibration report within stated tolerance of
      the lichess band; experiment reaches SPRT stopping rule OR its
      pre-declared max-N with an honest inconclusive verdict; write-up
      survives a refuter posing as a skeptical DS interviewer ·
      appetite: 3–4 days · no-gos: never tune dials and test them in the
      same experiment; no post-hoc metric switches; synthetic data never
      blended unlabeled into real-data artifacts
- [ ] **P5. Training-effectiveness study (comparative interrupted time
      series)** — problem: the flagship "insight that drives value" artifact;
      plain pre/post on n=1 has confounds the user explicitly flagged ·
      outcome-link: N4 + N1 · scope: **comparative ITS** per the user's
      quasi-experimental guide: treated series = weekly blunder rate on
      TRAINED motifs (hanging pieces — the blunder trainer's target),
      control series = untrained-motif blunder rate (global confounds hit
      both; only the trainer bends the treated series); segmented regression
      (level + slope change) with Newey-West/autocorrelation correction,
      ≥8–12 points per side; intervention dates from trainer_attempts
      timestamps + git ship history; robustness: placebo intervention dates,
      opponent-strength covariate (per-game bot Elo now recorded),
      bin-width sensitivity; dated pre-registered analysis plan committed
      before running; data via P2 marts (`user_type='real'`) ·
      **data-sufficiency gate (refuter 2026-07-18): DB today has only 15
      trainer_attempts, all on ONE day (2026-07-06), 150 games — nowhere
      near 8–12 weekly points/side. P5 does NOT start until ≥8 weekly bins
      of post-intervention games exist (or the spec re-bases the
      intervention on a later, better-instrumented feature ship — e.g. the
      Chapter-4 Maia switch — with the same gate); if still short at
      Chapter-5 time, P5 demotes to NEXT rather than shipping a
      hollow study (calendar reality: ≥8 weekly bins ≈ 2–3 months of
      post-intervention play — plan around it, don't fake it)** · pass/fail:
      analysis reproducible one-command from the warehouse; write-up states
      assumption + how tested + limitations (the guide's interview rubric);
      pre-registration commit predates the results commit · appetite: 2–3
      days · no-gos: no causal language beyond what the design supports;
      no cherry-picked windows
- [ ] **P6. Synthetic warehouse patterns lab** (clearly-labeled, separate) —
      problem: cohort retention/segment joins/funnel SQL patterns need
      multi-user volume one real user can't produce; highest smells-fake
      risk of the chapter (refuter) — survives only with unmissable labeling
      · outcome-link: N4 (breadth) · scope: generator for ~500 synthetic
      users' game/session histories **calibrated against the P4 lichess
      distributions** (generator code + calibration report public);
      `user_type='synthetic'` end-to-end; dbt patterns the real app can't
      exercise: cohort retention models, funnels, snapshots (SCD-2 on a
      mutable synthetic profile table — the ONE legitimate snapshot use),
      exposures + dbt docs site; README + docs make the synthetic/real split
      unmissable in the first 10 seconds; hard-separated marts (never joined
      into real-data artifacts except through the explicit user_type
      dimension); **honesty split in the calibration report (Codex
      2026-07-18): game-level parameters (move/error/rating distributions)
      tie to lichess-derived sources; product-behavior parameters (sessions,
      funnels, retention, profile changes) CANNOT come from game dumps and
      are declared as stylized assumptions in their own labeled table —
      claiming lichess grounding for those would itself be a red flag** ·
      pass/fail: docs site published; a reviewer-simulating refuter pass
      confirms no real/synthetic ambiguity anywhere; calibration report's
      lichess-derived vs stylized-assumption split is complete (every
      generator parameter appears in exactly one) · appetite: 3 days ·
      no-gos: synthetic rows never counted in any real-metric artifact;
      labeling never below h2 prominence

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

- ~~**No dbt/warehouse toolchain** (user decision 2026-07-12)~~ — **REVERSED
  2026-07-18** (user decision: target roles now require dbt/warehouse/DAG
  skills demonstrated; Chapter 5 is the sanctioned home). Chapter-5 guardrails
  replace it: no pipeline-for-pipeline's-sake, app runtime never depends on
  the warehouse, over-engineering red flags (CDC/quarantine at one-user
  scale, Airflow) stay banned.
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
- [x] If B1 recommends Maia/lc0: install `lc0` + Maia weights — DONE
      2026-07-18 (lc0 0.32.1 via brew + nine maia-1100…1900 nets in
      `~/maia_weights/`; `detect_maia()` verified ready).
- [ ] Chapter 4 / M6: generate ~10–12 new persona avatar images (ChatGPT,
      as before) and drop them id-keyed into `data/avatars/` — ids land in
      the M6 spec.
- [ ] Chapter 5 wrap-up (after ALL slices ship): build the comprehensive
      **Analytics Engineer Playbook wiki** at
      `/Users/johncabiles/Documents/Obsidian/Analytics Engineer Playbook/`
      from the accumulated dossiers in
      `docs/ai-dlc/research/analytics-portfolio/` (foundations, SOPs,
      patterns, best practices), emulating the structure of
      `/Users/johncabiles/Documents/Obsidian/dbt Certification Test Prep/`.
      Process rule until then: every research session ends with a dossier so
      nothing needs re-research.

## Process notes

- Contract mapping: existing `docs/ai-dlc/contracts/*.md` (17 files) already
  cover every brownfield area this roadmap touches; referenced per-slice above
  instead of re-mapping. Only greenfield area: lichess/chess.com fetch APIs
  (slice 3) — mapped during that slice's /ai-dlc run.
- Ordering is ICE-scored (data thin); scores shown per slice. **The user owns
  the final order and every Later→Next→Now promotion.**
- Hand-off per slice: `{problem, outcome-link, pass/fail, appetite, no-gos}` →
  `/ai-dlc`. Verify a pass/fail actually passes before checking a box.
