# KPI tree & metric dictionary

The goal "get better at chess" is not measurable, so nothing can manage it.
This document decomposes it into a north-star metric and a driver tree, then
defines every metric the app computes — definition, computation source, and
the caveat that keeps it honest. The [State of my chess](state-of-my-chess.md)
report reads these definitions; the Insights tab renders most of them.

Everything below is computed deterministically by the app (Stockfish +
python-chess; no LLM in any metric). Nothing in this document is aspirational:
each metric names the module and table it comes from.

## The tree

```
Play stronger games (north star: blunder rate ↓)
│
├── Fewer tactical collapses
│   ├── Blunder rate            (leaks/severity='blunder' per user move)
│   ├── Foreseeable-blunder %   (was the threat visible ≥2 plies early?)
│   └── Hope-chess rate         (games with ≥1 missed-threat leak)
│
├── Better openings
│   ├── Repertoire adherence    (games entering prepared lines; depth followed)
│   ├── Opening win/leak rates  (per ECO family, min-sample gated)
│   └── Trap conversion         (drills completed in blunder trainer)
│
├── Better endgames
│   ├── Endgame accuracy        (per material signature, ≥4-my-move floor)
│   └── Conversion rate         (winning endgames actually won)
│
├── Better clock discipline
│   └── Time-trouble blunder rate  (blunder rate by remaining-clock bucket)
│
└── (observability) Game accuracy % + est. Elo   — vanity-adjacent; see caveat
```

**North star: blunder rate per user move**, trended weekly. It is the single
metric most correlated with game outcomes at club level, it moves with every
driver above, and the app measures it identically across all games. Target
direction: down. The training loop (review → insights → blunder trainer) is
the mechanism; this tree is how we check the mechanism works.

## Metric dictionary

Conventions used below: **user move** = a ply where `game_plies.is_user_move=1`
(requires the game's `my_color` tag); **analyzed game** = `analysis_status='done'`;
**leak** = a stored mistake/blunder row in `leaks`. All evals are White-POV
centipawns from Stockfish at `REVIEW_BG_DEPTH` (default 10) — comparable
within the app, not across engines/depths. Small-sample gating: any rate with
`n < 5` renders as "insufficient sample" (`insights.MIN_SAMPLE`, `gated()`).

| Metric | Definition | Computed in | Honest caveat |
|---|---|---|---|
| **Blunder rate** | Leaks with `severity='blunder'` ÷ analyzed user moves. A blunder is a move dropping the mover's win probability ≥ 20 points (`analysis.leak_severity`; `BLUNDER_WP_DROP=0.20`, mistakes ≥ 10 via `MISTAKE_WP_DROP=0.10`); win prob uses the Lichess model in `analysis.win_prob_from_cp` | `app/review.py::analyze_game` computes severity + writes rows via `storage.write_leaks` into `leaks.severity`; rates aggregated in `app/profile.py::_top_leaks_by_category` and `app/insights.py::_time_trouble` over `game_plies.is_user_move` | Depth-`REVIEW_BG_DEPTH` (default 10) evals; a deeper engine would re-label some borderline moves. Win-prob axis is tuned for ~800–1100 play by design |
| **Foreseeable-blunder %** | Fraction of leaks where the punished threat existed ≥ 2 plies before the mistake (`leaks.lead_in_ply < leaks.ply − 1`) | `app/insights.py::_foreseeable` | The strict two-plies-early rule **under-claims** deliberately: `app/review.py::analyze_game` writes `lead_in_ply = ply − 1` as a display-timing default on every leak, so counting the one-ply case would read a vacuous 100% |
| **Hope-chess rate** | Analyzed games containing ≥ 1 `category='missed_threat'` leak ÷ analyzed games | `app/profile.py::_hope_chess_rate` over `leaks.category` | Game-level flag, not per-move — one merely-sloppy game and one disastrous game count the same |
| **Move quality labels** (play mode) | Centipawn loss between matched-limit evals before/after the move, five buckets: ≤ 10 best, ≤ 50 good, ≤ 100 inaccuracy, ≤ 250 mistake, > 250 blunder (`analysis.classify`; `BEST_MAX`/`GOOD_MAX`/`INACCURACY_MAX`/`MISTAKE_MAX`) | `app/analysis.py`, live `/api/move` | Different axis (cp-loss) from review severities (win-prob drop) **by design** — the two may disagree on borderline moves; play mode favors opening-prep feedback |
| **Repertoire adherence** | A game is on-repertoire when its `game_plies.uci` sequence enters a prepared line; `avg_followed_prep_depth` = plies matched before first user deviation, with the deviating move + prepared answer recorded | `app/insights.py::_walk_repertoire`/`_adherence` walking `repertoire.tree()` (from `data/repertoire.json`) | Only measures lines the user *prepared* — a thin repertoire yields a high "off-book" rate that says nothing about the quality of those off-book moves |
| **Opening performance** | Win/draw/loss + leak rate per ECO family (games grouped to family level) | `app/insights.py` openings slice | Family aggregation + min-sample 5 on purpose: per-variation win rates at n=2 are noise |
| **Endgame accuracy & conversion** | Accuracy over plies in the *stable* endgame suffix per material signature; conversion = winning endgames actually won, where "winning" = user win-prob ≥ 0.8 sustained for ≥ 4 consecutive plies in the suffix (`insights._CAP_WIN_PROB=0.8`, `_CAP_SUSTAIN_PLIES=4`), not a single-ply cp spike | signature/suffix logic in `app/endgame.py` (`endgame_signature`, `endgame_start_index`); aggregation + the ≥ 4-scored-moves floor (`_EG_MIN_MOVES`) in `app/insights.py::_endgame_types` over `game_plies.win_prob` | `game_phase` is material-based so the endgame is a suffix — the STABLE-suffix index (`endgame.endgame_start_index`) guards a morphing ending, which is bucketed entirely under its *entry* signature (a documented limitation); a game whose endgame suffix has < 4 scored user moves is excluded from the accuracy average (it still counts toward games/conversion) |
| **Time-trouble blunder rate** | Leak rate over user moves bucketed by remaining clock (`<10s`, `10s-30s`, `30s-2m`, `>2m`; `insights._CLOCK_BUCKETS`) vs the all-clocked-moves `baseline_rate` | `app/insights.py::_time_trouble` over `game_plies.clock_centis` (only rows where `is_user_move=1 AND clock_centis IS NOT NULL`) | **Data-gated:** only games imported **with the `%clk` PGN tag** carry `clock_centis`; most stored games currently have none, so `unclocked_games` is reported rather than silently mixing. It is a correlation with the clock, not causation |
| **Game accuracy %** | Chess.com-style per-side accuracy: mean of per-move accuracies from win%-drop via the Lichess model `103.17·e^(−0.0435·drop)−3.17` (`accuracy.move_accuracy`, constants `LICHESS_A/K/B`), over `game_plies.eval_cp_white`/`mate_white` — no extra engine work | `app/accuracy.py::summarize`, shown in the review bar | Anti-vanity rule: **not** aggregated across games in Insights — single-game accuracy varies wildly with opponent resistance |
| **Estimated Elo** | Linear heuristic on game accuracy: `45·acc − 2000`, clamped [100, 2900] (`accuracy.accuracy_to_elo`, `ACC_ELO_SLOPE/INTERCEPT`, `ELO_MIN/MAX`) | `app/accuracy.py::accuracy_to_elo` | A rough single-game heuristic (100% maps to ~2500; the 2900 cap only guards pathological inputs), labeled "est." in the UI. Not a rating; never trended |
| **Trend (weekly leaks)** | Leak counts bucketed by ISO week of import (`strftime('%Y-W%W', games.imported_at)`) | `app/profile.py::_trend` | Buckets by *import* date, not play date — a bulk import of old games spikes one week |
| **Trainer progress** | Leitner-box distribution + due counts per motif bucket in the blunder trainer (`trainer.is_due`, `next_box`) | `app/trainer.py` over SQLite `trainer_boxes.box`/`last_reviewed` + `trainer_attempts.outcome` (aggregated by `storage.get_attempt_stats`) | Measures drilling activity, not transfer; the transfer question is the parked "training effectiveness" analysis (roadmap Later) |

## How to read this tree in practice

1. **Weekly**: is the north star (blunder rate, `profile.trend`) drifting down
   over the last ~50 games? If yes, keep doing whatever you're doing.
2. **If flat/up**: walk the drivers. Foreseeable % high → tactics/board-vision
   drilling (blunder trainer). Adherence low → repertoire practice. Endgame
   conversion low → endgame study. Time-trouble rate ≫ baseline → clock
   discipline, not chess knowledge.
3. **Never** react to a metric flagged `sufficient: false` — the min-sample
   gate exists precisely so five bad blitz games don't rewrite the training plan.

*Related: [State of my chess](state-of-my-chess.md) applies these definitions
to the live database. Definitions verified against code on 2026-07-12.*
