# Maia / lc0 — human-like play via policy networks

Maia is a family of neural networks trained to *predict human moves* at
specific rating bands, run inside the lc0 engine with search disabled. This
note covers what it is, verified accuracy claims, runtime requirements, and
the Mac install path. Persona/style layering on top → `../bot-personas/`;
the human-error science behind it → `../human-play-modeling/`.

## What Maia is

- Nine supervised-learning models, **maia-1100 … maia-1900** (100-Elo bands),
  each trained on **12 million lichess games per rating bin** (validation sets
  of 120k games each)
  ([McIlroy-Young et al., KDD 2020, arXiv:2006.01855](https://arxiv.org/abs/2006.01855),
  [CSSLab/maia-chess](https://github.com/CSSLab/maia-chess)).
- Architecture: small residual CNN — **6 residual blocks × 64 filters**, board
  encoded as 8×8×17 planes
  ([chessprogramming.org/Maia_Chess](https://www.chessprogramming.org/Maia_Chess)).
  This is tiny by modern NN-engine standards (weights ≈ 1.3 MB gzipped, below).
- **No search.** Maia "only predicts moves by probing the net without any
  search"; in UCI terms you run `go nodes 1`
  ([maia-chess README](https://github.com/CSSLab/maia-chess),
  [chessprogramming.org](https://www.chessprogramming.org/Maia_Chess)).
  In python-chess: `engine.play(board, chess.engine.Limit(nodes=1))`.

## Move-matching accuracy (the headline claim, verified)

From the KDD 2020 paper (test positions exclude the first 10 ply and any move
made with <30s on the clock; ~500k positions per rating band)
([arXiv:2006.01855, full text](https://ar5iv.labs.arxiv.org/html/2006.01855)):

- **Maia: ~46% up to 52.9%** move-matching accuracy; each model peaks near its
  own training band (maia-1900 hits 52.9% on 1900-rated test players; its
  *worst* case, predicting 1100s, is still 46%).
- **Depth-limited Stockfish variants: 33–41%** — and, notably, weakened
  Stockfish does not become better at predicting weaker humans.
- **Leela nets (ordinary self-play-trained): peak ~46%**.

Two behavioral caveats verified from primary sources:

- **Maia is stronger than its label.** The README states the models "are also
  stronger than the rating they are trained on since they make the average
  move of a player at that rating"
  ([CSSLab/maia-chess](https://github.com/CSSLab/maia-chess)). Averaging washes
  out the tail of individual blunders. Expect maia-1500 to *play* above 1500.
  ⚠ No published Elo-vs-humans measurement per model found; the lichess bots'
  live ratings are the best proxy.
- **Maia is deterministic.** Policy argmax at nodes=1 → same move in the same
  position, every game. The official lichess bots (`maia1`, `maia5`, `maia9`)
  bolt on opening books precisely because "the models play the same move every
  time" ([CSSLab/maia-chess](https://github.com/CSSLab/maia-chess)). A bot
  built on Maia needs variety injected — opening books (→ `../openings/`)
  and/or policy *sampling* instead of argmax. ⚠ lc0 has historically exposed
  temperature-style options that sample from the policy, but current-version
  support/flags were not verified — check `lc0 --help` on the installed build
  before designing around it. Community reports also note Maia "doesn't
  recognize threefold repetition" and can wobble against offbeat openings
  ([lichess forum: How to configure Maia locally](https://lichess.org/forum/general-chess-discussion/how-to-configure-maia-locally)) ⚠ anecdote.

## maia2 (NeurIPS 2024) — unified model, different runtime

- One **skill-aware model spanning the rating spectrum** (attention mechanism
  conditions on both players' Elo), fixing the original's incoherence across
  independent per-band models; "significantly enhance[s] alignment" but the
  abstract publishes no headline accuracy number
  ([arXiv:2409.20553](https://arxiv.org/abs/2409.20553)).
- Distribution: **pip-installable PyTorch package**, Python 3.10–3.12, runs on
  "CUDA, Apple MPS, or CPU", **MIT license**
  ([CSSLab/maia2](https://github.com/CSSLab/maia2)).
- **Not a UCI engine.** No lc0 weights, no UCI wrapper in the repo — using it
  means in-process PyTorch inference inside the FastAPI app (a heavyweight
  dependency this repo doesn't have) rather than a subprocess behind
  python-chess. Elo inputs like `active_elo`/`opponent_elo` are per-call —
  one model serves every band, and continuous ratings (not 100-point steps).
- The maia ecosystem continues (Maia-3 / ICML 2026 referenced on
  [maiachess.com](https://www.maiachess.com/), which states coverage "from 600
  to 2600" on the lichess scale for the newer work). ⚠ Maia-3 not evaluated;
  original 9-model maia remains the only drop-in UCI option.

## Runtime: lc0 on Apple Silicon

- **Backends**: lc0 ships GPU backends (CUDA, ONNX, **Apple Metal**) and CPU
  backends (OpenBLAS, DNNL, Eigen, **Accelerate on macOS**)
  ([lc0 README](https://github.com/LeelaChessZero/lc0)).
- **Homebrew**: `brew install lc0` → v0.32.1 (as of 2026-07), builds natively
  for Apple Silicon (sonoma/sequoia/tahoe bottles), depends only on Eigen at
  runtime, GPL-3.0-or-later
  ([formulae.brew.sh/formula/lc0](https://formulae.brew.sh/formula/lc0)).
- **Speed at nodes=1 is a non-issue.** A Maia move is a *single forward pass*
  of a 6×64 net (~1.3 MB). Community consensus is that CPU-only lc0 is
  sufficient for Maia because "the node limitation prevents intensive
  computation" ([lichess forum](https://lichess.org/forum/general-chess-discussion/how-to-configure-maia-locally));
  M1 benchmark threads show lc0 CPU throughput in the hundreds-to-thousands
  of nps range on small nets ([TalkChess M1 thread](https://talkchess.com/forum3/viewtopic.php?f=2&t=75911&p=874456)).
  Expected per-move latency on an M-series CPU: **well under 100 ms** — far
  inside the app's 1–2 s interactive budget. ⚠ exact latency not benchmarked
  here; measure once installed (trivial: `lc0 benchmark` or time a
  `go nodes 1`).
- Config notes from field reports: 1 CPU thread and minibatch-size 1 are
  appropriate at nodes=1; GUIs need workarounds to send `go nodes 1`, but we
  drive UCI directly via python-chess so this gotcha doesn't apply
  ([lichess forum](https://lichess.org/forum/general-chess-discussion/how-to-configure-maia-locally)).

## Mac install path (local-first / offline)

1. `brew install lc0` (GPL-3, Apple Silicon native)
   ([formulae.brew.sh](https://formulae.brew.sh/formula/lc0)).
2. Download the desired `maia-XXXX.pb.gz` weights from the
   [maia-chess repo's `maia_weights/`](https://github.com/CSSLab/maia-chess)
   — each file is **1.24–1.33 MB** (verified via GitHub API: maia-1100
   1,313,193 B … maia-1900 1,262,607 B); all nine together ≈ 11.6 MB. Do not
   unpack the `.gz`.
3. Launch per band: `lc0 --weights=/path/maia-1500.pb.gz` (or swap weights to
   change difficulty — one process per active band).
4. Fully **offline after download** — no network at runtime, matching the
   app's local-first constraint.

**Licensing:** lc0 binary GPL-3, maia-chess repo (incl. weights) GPL-3
([CSSLab/maia-chess](https://github.com/CSSLab/maia-chess)), maia2 MIT. As a
local, single-user, non-distributed app, GPL imposes nothing here; it only
matters if the app is ever redistributed *bundling* lc0/weights (subprocess
use of a separately installed GPL binary is the standard clean pattern). ⚠
GPL-boundary reading is standard practice, not legal advice.

## Bottom line for the bots epic

Maia is the only off-the-shelf option whose *errors are learned from humans*
(the epic's causal-blunder requirement); it beats weakened Stockfish at
human-move prediction by ~10–19 points of accuracy. Costs: a second engine
process (lc0), one process (or a weights-swap restart) per rating band,
determinism that demands variety injection, bands capped at 1100–1900, and
"plays slightly above its label." Install burden on macOS is one brew formula
plus ~12 MB of weights, CPU-only is fine.
