# Research — making Stockfish analysis faster (analysis-speed)

Web research 2026-07-11 for the "faster analysis display" feature. Companion to
`contracts/analysis-speed.md`.

## 1. UCI limit tuning (depth vs movetime vs nodes)

- Elo returns per ply flatten fast: depth 8→7 ≈ +190 Elo (peak), depth 15→14 ≈ +67,
  depth 18→17 ≈ +52 ([SF wiki Useful data](https://official-stockfish.github.io/docs/stockfish-wiki/Useful-data.html)).
- Depth 18–20 catches all tactical blunders + most positional mistakes; 22–26 is
  "serious analysis"; >30 rarely changes verdicts.
- **Lichess fishnet is node-limited, not depth-limited**: ~2.25M NNUE nodes/move
  ([fishnet](https://github.com/lichess-org/fishnet)). Lichess browser engine stops ~depth 23.
  Chess.com Game Review also node-based.
- Latency arithmetic: modern 4-core ≈ 5 MN/s → 2.25M nodes ≈ ~450 ms; 500k nodes
  (≈ depth 18–22 warm) ≈ ~100–150 ms. Order-of-magnitude only.
- `nodes` limit → consistent quality AND latency; `depth` → wildly variable latency;
  best interactive pattern: `Limit(nodes=..., time=...)` (first reached wins).
- Shallow evals unstable on outliers (depth-10 +5.89 → +1.16 by depth 15,
  [arXiv](https://arxiv.org/pdf/2512.14319)) — argues for streaming refinement over a
  very low fixed limit.

## 2. Engine options

- **Threads:** near-linear time-to-depth gains, 1→8 threads ≈ 83% efficiency (~+327 Elo STC).
  Cheapest multiplier: Threads = physical cores − 1. (Current app: 2.)
- **Hash:** persists across `go` calls unless `ucinewgame` sent. 64–256 MB fine for ~1M-node
  searches. **Warm hash across sequential same-game positions is a large real effect** —
  next position was inside previous PV tree. python-chess `game=` parameter controls
  `ucinewgame`: pass same game object across moves to keep TT warm
  ([python-chess docs](https://python-chess.readthedocs.io/en/latest/engine.html)).
- **MultiPV:** expensive — MultiPV 2 ≈ −97 Elo (≈2× cost), 3 ≈ −157, 5 ≈ −235 at fixed time
  ([SF wiki](https://official-stockfish.github.io/docs/stockfish-wiki/Useful-data.html)).
  Keep multipv=1 on hot path; fetch extra lines lazily. (Current app: multipv=2 both calls.)
- **NNUE:** leave on — ~20% NPS cost but far stronger per node; off = strictly worse tradeoff.

## 3. Progressive / streaming display

- UCI streams `info depth N score cp X pv ...` per iteration; depth 10–12 arrives in tens
  of ms native. python-chess seam: `engine.analysis()` iterator (vs blocking `analyse()`),
  `.stop()` to abort anytime.
- Transport: SSE (`StreamingResponse`/`text/event-stream`) simpler than WebSocket for
  one-way eval push in FastAPI.
- Lichess UX: eval number + bar update every iteration, "DEPTH 18/23" label, "CLOUD" badge
  for cached. Perceived speed ≈ instant even when final depth takes seconds.

## 4. Client-side WASM engine — SKIP

- WASM ≈ ⅓–½ native throughput; threaded WASM needs COOP/COEP cross-origin isolation.
- Localhost round-trip ~1 ms — WASM's main benefit (no server hop) buys nothing here.
  Native engine 2–3× faster on same machine. Only useful if analysis must survive
  server-down.

## 5. Caching

- Lichess cloud-eval model: cache keyed by **normalized FEN** (pieces, turn, castling, ep —
  no move counters), stores depth/knodes/PVs, serve if cached ≥ requested
  ([lila #14278](https://github.com/lichess-org/lila/issues/14278)).
- Locally: dict/SQLite `normalized_fen → {cp, depth, pv}` makes undo/redo/move-list
  navigation instant — big share of analysis views are revisits.
- PV reuse ("app-level ponderhit"): after analyzing P, if user plays PV[0], child's line is
  PV[1:] — show instantly as provisional while engine confirms.

## 6. Anticipatory analysis / pondering

- Classic ponder hit-rate ~50% (chessprogramming wiki; time-gain folklore ~30%).
- App-level schemes while user thinks (engine idle): (a) keep deepening current position,
  stream improvements; (b) pre-analyze top-N likely replies (PV move + 2nd-best already
  computed) to same node budget, cache. Existing lock + note_interactive_start/end yield
  seam is the needed preemption; speculation must abort instantly via `.stop()`.

## 7. Perceived-latency UX

- Instant low-depth number that refines + ticking "depth N/M" label.
- Animated eval bar masks iteration jumps.
- Cache badge (lichess "CLOUD") builds trust for instant served evals.
- **Debounce rapid navigation** (~150–300 ms rest) + cancel in-flight search on every board
  change — skimming stops queuing stale searches behind the lock.
- Never block board update on eval; eval pane fills async.

## 8. Stockfish version / build

- SF 17 ≈ +46 Elo over SF 16 at matched time; SF17 vs SF14 ≈ ~6× faster for equal quality
  (Chessify claim). SF 18 current.
- Right binary matters: AVX2/BMI2 5–10%+ over generic; Apple Silicon needs native ARM
  dotprod build. Homebrew bottle is per-arch (already native ARM) — verify version ≥ 17.

## Ranked shortlist (researcher's)

| # | Lever | Impact | Effort |
|---|-------|--------|--------|
| 1 | Streaming eval (`engine.analysis()` + SSE), depth label + animated bar | Perceived latency → ~instant | Medium |
| 2 | Node-based limit (~300k–600k, ~1s time ceiling) for interactive | Hard-bounds latency ~100–300 ms at good quality | Trivial |
| 3 | Server eval cache by normalized FEN + book cutoff | Navigation/revisits → 0 ms | Low |
| 4 | Threads = cores−1, Hash 256 MB, same `game=` across moves (warm TT) | Large time-to-depth cut | Trivial |
| 5 | Speculative pre-analysis on idle (PV move + top replies) | ~50% of moves feel instant | Medium-high |
| 6 | multipv=1 hot path, 2nd line lazy | Halves interactive search cost | Low |
| 7 | Debounce navigation + instant cancel of in-flight search | Kills stale-search queuing | Low |
| 8 | Verify SF ≥ 17 native ARM build | Up to multi-× time-to-quality if outdated | Trivial |

Skip: browser WASM, NNUE-off.
