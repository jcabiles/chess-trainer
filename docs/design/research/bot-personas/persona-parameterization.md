# Persona parameterization — mapping style onto concrete knobs

How to turn "aggressive," "solid," "positional," "gambiteer" into engine
parameters and error-model biases, grounded in what Chessmaster, Fritz/
HIARCS, and Chessiverse actually expose as knobs. Execution mechanics (how a
knob is *implemented* against Stockfish/Maia) belong in
`../engine-adaptation/`; this note owns *which knobs exist and what they
should mean*.

## Chessmaster's slider system — the actual knob list (source-triangulated)

Two independent sources were cross-checked and agree on the core set:
[chess.com forum "Chessmaster personalities" thread
p.9](https://www.chess.com/forum/view/general/chessmaster-personalities-1?page=9)
(quoting/paraphrasing actual `.cmp`/text-dumped personality files) and the
[Chessmaster 10th Edition AI Personalities
FAQ](https://gamefaqs.gamespot.com/pc/921361-chessmaster-10th-edition/faqs/38373)
(index page confirms existence; full text was 403-blocked at fetch time —
⚠ FAQ content below is sourced only from the forum thread's paraphrase, not
independently re-verified against the FAQ text itself).

| Slider | Range (as documented) | What it does |
|---|---|---|
| Strength of Play | 0-100 | Overall playing strength, separate from style |
| Attack/Defense ("avd") | roughly -100 to +100 | The primary style axis: negative = defensive, positive = attacking |
| Material/Positional | -100 to +100 (also seen as 0-15+ in another dump) | Weights raw material value vs. positional factors in evaluation |
| Randomness | 0-5+ | Move-selection variability / noise |
| Max Search Depth | up to 99 | Search depth cap |
| Selective Search | numeric (examples: 9-14) | Search-pruning aggressiveness |
| Contempt of Draw | negative to positive (examples: -0.5 to 2.0) | Willingness to steer toward/away from draws |
| Piece values (Q/R/B/N/P) | e.g. Q≈9.0-9.2, R≈5.0-5.1, B/N≈3.0-3.1, P≈1.0 | Per-piece material weight, independently tunable |
| Control of Center (own/opp) | 0-150+ | Evaluation weight on center control, self and opponent separately |
| Mobility (own/opp) | 0-150+ | Evaluation weight on piece mobility |
| King Safety (own/opp) | 0-150+ | Evaluation weight on king safety, self and opponent separately |
| Passed Pawns / Pawn Weakness | 0-150+ | Structural evaluation weights |
| Opening Book | `.obk` file selection | Determines the persona's repertoire, separate from style sliders |

Independent corroboration on the **Material/Positional** mechanism
specifically: a [chess.com forum
thread](https://www.chess.com/forum/view/general/what-are-the-most-aggressive-uci-amp-winboard-engines)
cites research using Crafty 19.19 showing that moving the slider fully to
"material" multiplies material values ×3 and divides positional values ÷2
(and the inverse at the "positional" end) — i.e. the slider isn't a vague
weight, it's a concrete multiplicative rebalancing between two evaluation
components. This is a directly portable idea: **a style axis can be
implemented as a multiplier pair on existing eval terms** rather than a wholly
separate evaluation function.

**What's portable to a Stockfish/Maia-based bot today:** Stockfish doesn't
expose per-term eval weights via UCI the way Chessmaster's engine did — see
`../engine-adaptation/stockfish-weakening.md` for what Stockfish *does*
expose (`Skill Level`, `UCI_LimitStrength`/`UCI_Elo`, node/depth caps). The
Chessmaster knob list is therefore best read as a **target behavior
specification** to approximate via: (a) opening-book bias (`../openings/`),
(b) post-hoc move-list biasing among near-equal candidate moves (favor moves
that increase own king exposure for "attacker," penalize such moves for
"solid"), and (c) an error-model bias layer (below) rather than as
literally portable UCI options.

**Presentation lesson (cross-ref `engaging-vs-annoying-bots.md`):**
Chessmaster shipped these sliders as backend config, but the *player-facing*
product was narrative one-liners per character ("Cole... leaves his king
vulnerable to attack"). Expose personas to users as short behavioral
descriptions, keep the slider values as internal implementation.

## Fritz/HIARCS: a second, independently-shipped precedent

- [ChessBase Fritz Wikipedia
  summary](https://en.wikipedia.org/wiki/Fritz_(chess)) and corroborating
  [chess.com forum
  thread](https://www.chess.com/forum/view/general/fritz-handicap-and-fun-mode-accurate-elo)
  — Fritz 8 (2004) added "Handicap and Fun" mode: choose an Elo target *and* a
  style, with named style knobs. Specific named example, repeatedly cited:
  **"King's Attack" set to max** makes Fritz "really go after your king's
  defenses, often sacrificing material to break up your pawn shield." Fritz 9
  added a **"piece placement"** style knob not present in Fritz 8. This
  confirms the pattern independently of Chessmaster: (ELO target) × (a small
  number of named style dials, added incrementally over versions) is a
  proven, shippable shape for a persona system.
- Fritz also ships a distinct **Sparring mode** (separate from Handicap):
  per a [chess.com forum
  thread](https://www.chess.com/forum/view/general/fritz-13-engine-strength)
  paraphrase, sparring mode deliberately "purposely blunders to set up
  tactical shots for you" — i.e. a mode explicitly optimized for *teaching*
  (feed the human a tactic) rather than for *believable opposition*. Worth
  distinguishing as a different product goal from what this epic wants
  (believable opponents), but useful vocabulary: a "sparring" mode could be a
  distinct, clearly-labeled mode from persona bots, so its intentional
  softballing doesn't get read as the same "programmed to blunder" complaint
  from `engaging-vs-annoying-bots.md` (it's opt-in and its purpose is stated).
- **HIARCS** (same forum thread as above,
  [source](https://www.chess.com/forum/view/chess-equipment/reinventing-the-wheel-chessmaster-type-personalities-on-chess-com)):
  3 style dimensions (aggressive / active / solid) × 5 opening-book modes
  (off / wild / surprise / dynamic / tournament) = 15 opponent configs. A
  smaller, cleanly orthogonal precedent — style axis and book-behavior axis
  are separate, multiplicative dimensions rather than one entangled
  "personality" blob. **Recommend this shape**: keep the style axis
  (aggressive/solid/positional/gambiteer) and the opening-repertoire axis
  (executed via `../openings/`) as independently selectable/combinable
  dimensions, not baked into a single persona identity — it's simpler to
  implement, test, and reason about than Chessmaster's fully entangled
  per-persona file.

## Chessiverse's modern archetype set (2025-era, ships today)

From
[chessiverse.com/personaplay](https://chessiverse.com/personaplay) and
[chessiverse.com/blog/how-we-build-human-like-chess-bots](https://chessiverse.com/blog/how-we-build-human-like-chess-bots)
— five archetypes, each with a one-line behavioral description (note the
Chessmaster-style narrative framing, not slider readouts):

| Archetype | Style | Described tendency |
|---|---|---|
| Hunter | aggressive/tactical | "actively look for attacking chances, sacrifice material when they see king-side opportunities, play sharp openings" |
| Savage | sharp/risk-taking | "favor complications, unbalanced positions, aggressive piece sacrifices" |
| Guardian | solid/defensive | "favor closed positions, build positional fortresses, grind opponents down across long endgames" |
| Observer | patient/positional | "maneuver quietly, exploit small advantages," focus on structural weaknesses |
| Mediator | flexible/balanced | "adapt to whatever the position demands" — closest to "typical strong human play" |

This maps close to 1:1 onto the epic's stated must-have list
(attacking/aggressive ≈ Hunter/Savage split into "tactical-aggressive" vs.
"sacrificial-aggressive"; solid/defensive ≈ Guardian; positional ≈ Observer;
a "flexible" catch-all ≈ Mediator). Note Chessiverse splits "aggressive" into
*two* distinct flavors (calculated tactical pressure vs. speculative
sacrifice) — worth considering as a refinement if a single "aggressive"
persona feels too coarse in playtesting. ⚠ Chessiverse's own marketing
description; behavioral claims not independently verified against actual
game logs.

**Their engineering claim for how these archetypes *emerge*:** "five
personality categories emerge from neural network training" — i.e. they
report deriving styles from clustering trained-network behavior rather than
hand-authoring eval-weight sliders Chessmaster-style. ⚠ unverified/
unreplicable claim from a single blog post — no methodology detail given;
treat the *taxonomy* (five named archetypes) as useful, but do not assume
this repo can or should replicate a "styles emerge from training" pipeline —
that is a materially different (ML-training) approach than hand-tuned
weighting, and is out of scope for a hand-authored persona system on top of
Stockfish/Maia.

## Error-model bias: the "attacker over-values its own threats" idea

The epic brief itself names this pattern explicitly (an attacker
over-valuing its own threats). This research pass found no single named
academic/industry source that specifies exact numeric biases for this — it
is a design inference, not a sourced fact. ⚠ flagged: the specific mechanism
below is this note's synthesis of the sourced material above, not a directly
cited implementation.

What **is** sourced and supports the shape of this idea:
- Chessiverse's stated thesis: *"Creating believable weaknesses is harder
  than creating strength... missing tactical patterns or poor endgame
  judgment — not random piece drops."*
  ([source](https://chessiverse.com/blog/how-we-build-human-like-chess-bots))
  — i.e. the error should be a *plausible cognitive miss*, not decision
  noise.
- The Chessmaster Material/Positional multiplicative-slider mechanism (above)
  shows a working precedent for "bias the evaluation function itself" rather
  than "inject randomness after the fact."

Synthesized design pattern (not independently sourced, marked as this note's
own proposal): implement persona error bias as an **evaluation-weight
distortion applied before move selection**, not a post-hoc blunder injector:
- **Aggressive/Hunter persona**: inflate the evaluation score of the
  persona's own attacking/threat-generating moves (own king-safety and
  material-loss terms discounted relative to threat-generation terms) when
  choosing among near-equal candidates — this produces moves that are
  "genuinely believed good by an attacker" rather than random noise, directly
  answering the `engaging-vs-annoying-bots.md` finding that mistakes must be
  legible as *that persona's* mistake.
- **Solid/Guardian persona**: inflate king-safety and structural-integrity
  terms; bias against sacrifices even when objectively sound.
- **Gambiteer persona**: bias opening selection (via `../openings/`) toward
  known gambits/sharp lines, and reduce the material-loss penalty
  specifically in the opening/early-middlegame phase (matches the pattern
  that gambiteers accept known material deficits for initiative).
- This should compose with, not replace, whatever general human-like
  error-rate model exists — see
  `../human-play-modeling/computational-error-models.md` and
  `../human-play-modeling/error-rates-by-rating.md` for the rating-conditioned
  error-frequency base layer this persona bias should sit on top of.

## Trade affinity and king-safety neglect — knobs named in the epic brief, not yet found sourced elsewhere

The epic brief names "trade affinity" and "king-safety neglect" directly as
target knobs. No source in this research pass documents a named
implementation of "trade affinity" as a discrete parameter (Chessmaster's
Contempt-of-Draw is adjacent but is about draw-seeking, not trade-willingness
specifically). ⚠ Recommend treating "trade affinity" as an implementable
extension of the Chessmaster Material/Positional pattern: bias the
evaluation of trades (not just their acceptance) — a "solid" persona could
prefer simplifying trades when materially equal or ahead (grinds endgames,
matches Guardian's described "grind opponents down across long endgames"
tendency), while an "aggressive" persona avoids trades that reduce attacking
material even when the trade is objectively fine. King-safety neglect is
directly covered by the Chessmaster King Safety (own) weight-down pattern
above — high confidence this is implementable the same way.

## Load-bearing takeaways for design

1. **Two independent, shipped precedents (Chessmaster, Fritz/HIARCS) agree
   on the same basic shape: an ELO/strength axis, crossed with a small
   number (3-6) of named, independently-tunable style dials.** Don't
   over-engineer a single entangled "personality" blob — HIARCS's
   orthogonal-axes approach (style × book behavior) is simpler and still
   shipped successfully. Confidence: high (two independent sources).
2. **Style should bias the evaluation function / candidate-move selection,
   not inject post-hoc randomness** — this is the direct fix for the
   "programmed to blunder" complaint in `engaging-vs-annoying-bots.md`, and
   is consistent with both Chessmaster's multiplicative-slider mechanism and
   Chessiverse's stated design thesis. Confidence: medium-high (mechanism
   sourced from Chessmaster; the *application* to bias rather than randomness
   is this note's synthesis).
3. **Present personas to users as one-line behavioral descriptions, not
   slider values** — both Chessmaster and Chessiverse converge on narrative
   presentation despite very different backend eras/technology. Confidence:
   high (consistent across two independently-built systems 20+ years apart).
4. **Chessiverse's 5-archetype taxonomy (Hunter/Savage/Guardian/Observer/
   Mediator) is a ready-made, market-validated mapping onto the epic's
   must-have style list** — worth using as the starting vocabulary even if
   the underlying implementation differs (they claim ML-emergent, we'd be
   hand-tuned). Confidence: medium (single source, unverified methodology,
   but the *taxonomy* itself is low-risk to borrow regardless of how they
   built it).
5. **"Trade affinity" has no directly sourced precedent** — treat as a novel
   extension of the material/positional-weighting pattern rather than an
   established, named technique. Confidence: low on precedent, medium on the
   proposed implementation approach being sound (it follows the same eval-
   weighting mechanism as the sourced king-safety/attack knobs).
