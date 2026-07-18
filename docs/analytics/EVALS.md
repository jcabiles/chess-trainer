# Evals — AI game commentary

The app's one LLM feature (Claude narrates Stockfish findings in game review)
ships with an eval harness instead of vibes. This page is the methodology and
the results ledger. Code: [`evals/`](../../evals/) — golden set, deterministic
grounding checks, LLM-as-judge runner.

## What's being evaluated

`app/narrative.py` sends a **facts-only payload** (moves, evals, win-prob
swings, motifs — extracted by `app/moments.py`) and asks for chaptered
commentary + per-moment notes. The design bet is *grounding by construction*:
the model never sees a position it could analyze itself, only facts. Evals
exist to measure whether that bet holds — and how good the writing is when
it does.

## Eval design

**Dataset.** `evals/golden/` — 10 real games from my database, stratified so
the narrative task varies: 3 blunder-heavy games, 3 clean decisive games,
losses and wins as both colors. Player names sanitized to Me/Opponent;
rebuild with `python -m evals.build_golden` (the git diff then shows exactly
how the set changed — that's the freshness story).

**Layer 1 — deterministic grounding checks** (`evals/grounding.py`, runs in
CI offline via `tests/test_evals_grounding.py`):

| Check | Catches |
|---|---|
| `unknown_san` | any move named in the text that isn't the moment's move, its engine best, or a payload PV move |
| `unreached_phase` | a chapter narrating a phase the game never reached (the runtime parser doesn't close this) |
| `bad_move_number` | "at move 60" in a 25-move game |
| `second_best_named` | a "better was Nf3" claim on a narrow-choice moment — the payload never carries a second-best move, so any named alternative is invented |
| `motif_mismatch` | a tactical motif named in prose (hanging / fork / pin / skewer / discovered attack / back-rank) that no moment's `facts.category` or `facts.threat_motif` supports — the keyword set is sourced from `app/motifs.py`, and generic words ("attack", "pressure", "threat") never fire |

Only falsifiable checks live in this layer; each red result is a hard fail,
not an opinion. The planted-violation tests prove every class is actually
catchable; the echo-narrative test proves zero false positives over all 10
real payloads.

**Layer 2 — LLM-as-judge** (`evals/judge.py`, on-demand, never CI-blocking):
generates commentary through the production path, then a separate (cheaper)
model grades faithfulness / insight / clarity, 1–5 each. Cost ≈ 20 API calls
per run, under the $5 ceiling.

**Layer 3 — judge calibration.** The judge is not trusted by default. Human
ratings go in `evals/human_ratings.json`; the runner reports mean |Δ| and
within-1 agreement per axis. Trust policy:

- **Grounding**: never delegated to the judge at all — layer 1 is
  deterministic precisely because "did it invent a move" must not be a
  model's opinion.
- **Faithfulness score**: usable as a *ranking* signal once within-1
  agreement ≥ 80%; individual scores stay advisory.
- **Insight/clarity**: the axes most likely to diverge from my taste —
  treated as noise until agreement is measured, and never used as a
  regression gate.

## Results

> **Status: harness complete; model runs pending.** Generation requires
> `ANTHROPIC_API_KEY`, which never enters the sandboxed build environment.
> First real run: `GAMES_DB=data/games.db ANTHROPIC_API_KEY=… python -m
> evals.judge`, then paste the printed table below and commit alongside
> `evals/results/`.

| run | model | judge | games | grounding violations | faithfulness | insight | clarity |
|---|---|---|---|---|---|---|---|
| _pending_ | | | 10 | | | | |

**Judge-vs-human agreement:** _pending human ratings._

### Failure modes to watch (hypotheses until the first run)

1. **Plausible invented alternatives** — "better was Nf3" on narrow-choice
   moments (why `second_best_named` exists; the system prompt forbids it,
   belt + suspenders).
2. **Phase spillover** — narrating an endgame that never happened in short
   games (why `unreached_phase` exists).
3. **Eval-language drift** — describing a +0.4 position as "winning";
   deterministic checks can't catch adjectives, so this lands on the judge's
   faithfulness axis. If the first runs show it often, the fix is a payload
   change (bucketed eval labels), not a prompt tweak.

## Regression policy

- Layer-1 checks run in every `pytest` invocation — a code change that lets
  an ungrounded narrative through fails CI without any API call.
- Judge runs are manual, per model/prompt change: run, paste the table above,
  commit `evals/results/run-<model>.json`. Two comparable rows = a regression
  check between prompt or model versions (e.g. Sonnet vs Haiku cost/quality).
- The golden set only changes via `build_golden` commits, so every results
  row is traceable to the exact dataset version that produced it.
