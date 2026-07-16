# Reconciling the two Elo estimates — accuracy→Elo vs results→Elo

The repo already ships **one** Elo estimator; slice B8 will add a **second**.
They measure different things and will disagree. This note documents what each
one is, why they diverge, and how to present them without contradicting each
other. Read-only inputs: `app/accuracy.py`,
`../../../ai-dlc/contracts/game-accuracy-elo.md`.

## Estimator 1 — accuracy→Elo (exists today, `app/accuracy.py`)

- **Input:** the *quality of the moves* in a single reviewed game (per-ply
  centipawn drops → Lichess per-move accuracy % → a linear Elo map).
- **Map:** `accuracy_to_elo(acc) = clamp(round(45*acc - 2000), 100, 2900)`.
  Anchors (from the module docstring): 70% → ~1150, 80% → ~1600, 90% → ~2050,
  95% → ~2275. `app/accuracy.py`
- **What it is, per its own docstring:** "a rough single-game heuristic — **not**
  a calibrated rating claim." `app/accuracy.py`
- **Population it's anchored to:** the Lichess accuracy model, itself fit on
  Lichess games — so it is *loosely* human-anchored, but per **one game** and via
  **move quality**, not results.

## Estimator 2 — results→Elo (slice B8, new)

- **Input:** *win/draw/loss results* against bots of known rating, accumulated
  over many games (see [rating-systems-math.md](rating-systems-math.md)).
- **Map:** Elo/Glicko-2 expected-score update; produces a rating **mean + RD**.
- **What it is:** a running strength estimate in the classical rating sense — the
  thing "your rating" normally means.
- **Population it's anchored to:** the *bots' ratings* — which are themselves
  uncertain (see [engine-elo-vs-human-elo.md](engine-elo-vs-human-elo.md)). Its
  honesty is capped by the bot-labeling honesty.

## Why they will disagree (and that's fine)

| | Estimator 1 (accuracy) | Estimator 2 (results) |
|---|---|---|
| Measures | how *cleanly* you played | whether you *won* |
| Window | one game | many games (cumulative) |
| Anchored to | Lichess move-quality model | the bots' (fuzzy) ratings |
| Volatility | high (one lucky clean game spikes it) | smoothed (RD/K damps it) |
| Failure mode | a won-but-sloppy game reads *low*; a lost-but-clean game reads *high* | inherits the bots' ±100–200 bias |

A player can **win a sloppy game** (accuracy→Elo low, results→Elo up) or **lose a
clean game** (accuracy→Elo high, results→Elo down). Neither is wrong — they
answer different questions. Chess.com itself shows *both* a per-game "estimated
performance" and a persistent rating, and they routinely differ. ⚠ (Analogy to
chess.com's dual display; not a cited claim about their internals.)

## How to present them without contradiction

1. **Don't average them into one "your Elo."** They have different units of
   meaning; a blended number would be defensible to neither. Keep them **labeled
   distinctly**: "This game played like ~1600" (accuracy) vs. "Your estimated
   rating: ~1350 ± 120" (results).
2. **Results→Elo is the persistent "your rating."** It's the one that behaves
   like a rating (updates on outcomes, has a confidence interval). Accuracy→Elo
   stays a **per-game readout**, exactly as it is today.
3. **Use each to sanity-check the other, not to overwrite it.** Large persistent
   gaps are *signal*: if results→Elo sits well below accuracy→Elo, the user plays
   well but loses (time trouble? blunders in won positions?) — a coaching insight,
   not a bug. This is a feature the two-estimator design unlocks.
4. **Carry uncertainty through to the UI on both.** Accuracy→Elo already
   self-labels as rough; results→Elo should show its **RD/confidence band** and a
   provisional flag while young (see rating-systems note). Given the upstream bot
   uncertainty, a bare precise number on either would overclaim.

## Can results-vs-BOTS meaningfully estimate the user's rating at all?

Yes, **with explicit uncertainty** — this is the honest answer to the key
question. The chain is: bot label (±100–200 vs humans) → user estimate. The bias
is real but bounded and **partly self-correcting**:

- If the *whole ladder* is biased by a roughly constant offset, the user's
  estimate is shifted by ~that offset but its **shape and movement stay correct**
  (improvement still shows up). A systematic offset is far less harmful than
  random noise.
- The **monotonic-ladder + external-anchor** validation (see
  [honest-bot-rating-assignment.md](honest-bot-rating-assignment.md), procedures
  1 & 3) directly bounds that offset. Anchoring even one rung to a human-derived
  reference (a Maia bin or a lichess bot's earned rating) pins the whole scale.
- Glicko-2's **RD is the honesty valve**: while bot ratings are unvalidated, RD
  stays wide and the number is shown as provisional; as the ladder gets anchored
  and more games arrive, RD tightens.

**This is essentially how chess.com/lichess treat bot games too:** platforms
generally **do not rate human-vs-bot games into the human pool**, precisely
because bot strength is uncertain — bot games are practice, not rated. ⚠
(Platform-policy generalization; commonly stated but I did not pin a single
authoritative citation for each platform.) Our app is single-user and *wants* a
bot-derived estimate, so the honest move is to **keep it a clearly-labeled
practice estimate with a visible confidence band**, not present it as a
FIDE/lichess-equivalent rating.

## One-line guidance for B8

Ship **results→Elo (Glicko-2, with RD shown)** as the persistent "estimated
rating," keep **accuracy→Elo as the per-game readout**, never merge them, and
gate the persistent number's *precision claim* on the bot ladder being
validated (monotonic + at least one human anchor).

## Sources

- `app/accuracy.py` (repo, read-only) — accuracy→Elo heuristic + self-described "not a calibrated rating claim"
- `../../../ai-dlc/contracts/game-accuracy-elo.md` (repo, read-only) — per-game accuracy/Elo contract
- [rating-systems-math.md](rating-systems-math.md) — Glicko-2 RD as the uncertainty valve
- [engine-elo-vs-human-elo.md](engine-elo-vs-human-elo.md) — the ±100–200 bot-label uncertainty this inherits
- [honest-bot-rating-assignment.md](honest-bot-rating-assignment.md) — the validation procedures that bound the offset
