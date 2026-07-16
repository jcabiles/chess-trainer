# Computational models of human move choice and error

The models in the literature that turn "a human of rating R" into a move
distribution — and which of them are implementable deterministically atop
Stockfish MultiPV output. Execution mechanics (how to run the engine to get
candidates cheaply) → `../engine-adaptation/`; persona parameters →
`../bot-personas/`.

## 1. Regan–Haworth: rating-parameterized probability over engine candidates

[Regan & Haworth, "Intrinsic Chess Ratings" (AAAI 2011)](https://cse.buffalo.edu/~regan/papers/pdf/ReHa11c.pdf)
is the canonical *analytic* model: given the engine's evaluation of each legal
move, predict the probability a player of a given strength chooses each one.

- For move *i* with evaluation deficit δᵢ (centipawns behind the best move),
  the model fits an inverse-exponential proxy **yᵢ = exp(−(δᵢ/s)^c)** linking
  each inferior move's selection probability to the best move's
  ([search-verified summary of the paper](https://www.researchgate.net/publication/221606300_Intrinsic_Chess_Ratings)).
  ⚠ The proxy acts on a log-probability scale (yᵢ = 1 ⇒ pᵢ = p₁; yᵢ → 0 ⇒
  pᵢ → 0); verify the exact link function in the paper before implementing.
- **s ("sensitivity")** scales δ: small s magnifies small eval differences —
  the ability to discriminate between moderately inferior moves.
  **c ("consistency")** is an exponent that, when large, sharply suppresses
  clearly poor moves — the tendency to avoid moves you *can* discriminate as
  bad ([paper](https://cse.buffalo.edu/~regan/papers/pdf/ReHa11c.pdf)).
- Fitted by regression on large sets of rated tournament games, (s, c) map
  smoothly onto Elo century marks, giving **Intrinsic Performance Ratings**
  (rate a player purely from move quality) — and the mapping is stable across
  decades ([paper](https://cse.buffalo.edu/~regan/papers/pdf/ReHa11c.pdf);
  [Regan's compendium](https://cse.buffalo.edu/~regan/papers/pdf/Reg12IPRs.pdf)).
- ⚠ δ is not raw centipawns: Regan damps eval differences when the position is
  already far from equal (a 100cp slip matters less at +5 than at 0.0) —
  re-derive the exact damping from the papers.
- The same machinery powers Regan's FIDE cheating-detection screening (move-
  match z-scores vs the (s,c)-predicted baseline; a ~2100 player matches
  Stockfish ≈50 moves per 100
  ([ChessBase overview](https://en.chessbase.com/post/prof-regan-s-statistical-system))).

**Why this matters for us:** it is exactly the shape our bot needs — a
**two-parameter, rating-indexed softmax-like distribution over MultiPV
candidates**, evaluated per-move, trivially seedable (draw one uniform per move
from a seeded RNG and invert the CDF). Two independent dials map cleanly onto
persona design: s = "how precisely I compare decent moves," c = "how reliably I
veto obviously bad ones."

## 2. Anderson et al.: difficulty-conditioned error rate

[Anderson, Kleinberg & Mullainathan (KDD 2016)](https://arxiv.org/abs/1606.04956)
add the missing causal ingredient: error probability should be driven by
**blunder potential** β(P) = (# blunder moves)/(# legal moves). Their fitted
skill curve — blunder rate ≈ β/(c−(c−1)β), c≈15 amateur vs c≈100 GM ⚠ (see
`error-rates-by-rating.md` for caveats) — is a one-parameter, deterministic
function computable from MultiPV output (count candidates losing ≥ threshold).
Difficulty features predict blunders at 0.73 accuracy vs 0.55 for skill — so a
model that *only* randomizes by rating and ignores β(P) is empirically wrong.

## 3. Maia: learned human policy per rating band

[Maia (McIlroy-Young et al., KDD 2020)](https://arxiv.org/abs/2006.01855) is
AlphaZero's policy network retrained to predict *the human's* move, one model
per 100-point band (1100–1900), no tree search. Key properties:

- 12M lichess games per band; predicts the played move at 50.8%–52.9% top-1
  accuracy (rising with band), vs ~46% for tuned Leela and 33–41% for
  depth-limited Stockfish ([paper](https://arxiv.org/abs/2006.01855)).
- **Unimodal skill targeting**: each model peaks at the band it was trained on
  — it captures band-*specific* patterns, not just "weaker play"
  ([paper](https://arxiv.org/abs/2006.01855)).
- It models errors, not just good moves: when a human hangs a queen, Maia
  predicts *the exact howler* >25% of the time
  ([CSSLab blog](http://csslab.cs.toronto.edu/blog/2020/08/24/maia_chess_kdd/)).
- A separate Maia head predicts *whether* the human will blunder (win-prob drop
  ≥10pp) from the position at 71.7% accuracy
  ([paper](https://arxiv.org/abs/2006.01855)) — i.e. threat-visibility and
  plan-salience features are learnable from the board alone.
- [Maia-2 (NeurIPS 2024)](https://arxiv.org/abs/2409.20553) unifies the bands
  into one model with skill-aware attention, takes **both players' ratings**
  as inputs, reaches 53.25% avg accuracy, and fixes skill-coherence (correct-
  move probability rises monotonically with skill in 27% of positions vs 1%
  for Maia-1). Weights are open ([github.com/CSSLab/maia2](https://github.com/CSSLab/maia2)).
- Fine-tuning on one player's games adds ~4–5pp accuracy (58.0% at 40K games)
  and captures error style so distinctly that players can be identified from
  their mistakes alone
  ([McIlroy-Young et al., KDD 2022](https://arxiv.org/abs/2008.10086)).

**Fit for our stack:** Maia is the gold standard for humanness but is a second
neural engine (ONNX/lc0 weights) — an architectural cost; see
`../engine-adaptation/` for the isolation question. Sampling its policy with a
seeded RNG is deterministic. A Stockfish-only alternative can *approximate*
Maia's behavior with model #1 + #2 conditioning.

## 4. Stockfish Skill Level: the cautionary baseline

What Skill Level actually does
([commit ef4822a](https://github.com/official-stockfish/Stockfish/commit/ef4822aa8d5945d490acca674eb1db8c3c38e9d5);
[FAQ](https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html)):
search normally, take ≥4 MultiPV candidates, add to each score a
weakness-scaled **deterministic term plus a uniform random term**, play the
perturbed argmax; the pick uses the search state at depth 1 + level. This is
*uniform value-noise conditioned on nothing* — precisely the "inexplicable
random drop" experience the epic forbids. Its one salvageable idea: doing the
perturbation over MultiPV scores is cheap and engine-native. See
`../engine-adaptation/` for the full critique of skill-level mechanisms.

## 5. Assembling a causal error model (synthesis)

The literature supports a layered, fully deterministic-given-seed design:

1. **Candidate set**: Stockfish MultiPV (k≈8–16) → evals per candidate.
2. **Base choice distribution**: Regan-style softmax over damped deficits with
   rating-indexed (s, c) (§1) — this alone produces plausible *magnitudes*.
3. **Difficulty conditioning**: scale error mass by blunder potential β(P)
   (§2) — errors cluster in trappy positions, not uniformly over the game.
4. **Causal feature gates** (the "misses your threat while attacking" layer):
   raise the probability of moves that continue the bot's own plan and lower
   the visibility of opponent-threat refutations when attention features say
   so. Evidence base: Einstellung attention capture and motif-difficulty
   ordering → `attention-and-motif-blindness.md`; taxonomy → `../blunders/`.
   ⚠ No published parameterization of this layer exists — Maia learns it
   implicitly; a hand-built version must be validated (see
   `humanness-metrics.md`).
5. **Determinism**: one seeded RNG stream per game, one draw per move;
   identical seed + position + params ⇒ identical move. All inputs (MultiPV
   evals at fixed nodes, β(P), feature gates) are already deterministic.
   Caveat: fixed-*node* search is reproducible; fixed-*time* search is not —
   matches this repo's existing node-budget `SPEED_PRESETS` approach.

## Cross-references

- Executing candidates/limits on the engine, Maia-runtime isolation →
  `../engine-adaptation/`
- Persona dials (aggression, plan-stickiness) over this substrate →
  `../bot-personas/`
- Calibrating (s, c, β-scaling) to a target Elo → `../rating-calibration/`
