# Bot opening books — format, sampling, and variety

Scope: how to give bots opening-book behavior that (a) never repeats the same
game twice against the user, (b) stays rating-plausible, and (c) is cheap to
implement in this repo (Python backend, python-chess already a dependency).
See `sub-1600-opening-catalog.md` for the actual lines and
`rating-banded-opening-behavior.md` for the rating-filtered popularity data
that should drive book weights. Traps in `opening-traps.md` are a separate
concern (deliberate bait lines for the traps trainer) — a bot's *normal* play
should mostly avoid intentionally walking into or laying traps unless a
persona is specifically designed to (see `../bot-personas/`, not this file).

## Polyglot format (the standard book format, and python-chess reads it natively)

Source: [Polyglot book format](https://hgm.nubati.net/book_format.html) (H.G.
Muller's canonical spec) + [python-chess polyglot docs](https://python-chess.readthedocs.io/en/latest/polyglot.html).

- A `.bin` polyglot book is a flat array of **16-byte entries**, sorted
  ascending by `key` (a 64-bit Zobrist-style hash of the position) so lookup
  is a binary search. Fields, big-endian:
  - `key` (8 bytes) — position hash (piece placement ⊕ castling rights ⊕
    en-passant file ⊕ side-to-move, XORed from a fixed pseudo-random array).
  - `move` (2 bytes) — bit-packed: to-file(0-2)/to-rank(3-5)/from-file(6-8)/
    from-rank(9-11)/promotion-piece(12-14, none=0..queen=4). Castling is
    encoded king-takes-rook style (e1→h1 for White O-O). A raw value of 0
    (a1→a1) is a sentinel meaning "no move" and should be skipped.
  - `weight` (2 bytes) — move-quality/selection weight. Convention: generators
    typically set it to `2*wins + draws` for the side to move, scaled to fit
    16 bits, but this is a convention, not a format requirement — anything
    proportional to "how good/desirable" works.
  - `learn` (4 bytes) — usually unused/zero; ignore.
- **Selection rule**: "the probability that a move is selected is its weight
  divided by the sum of the weights of all the moves in the given position"
  (same source). A weight of 0 effectively disables a move without needing to
  delete/recompact the file. Some implementations exponentiate weights before
  normalizing to sharpen or flatten the distribution — this is exactly the
  "temperature" knob described below, just not named that in chess-engine
  literature.
- **python-chess has first-class support already** (confirmed in this repo's
  venv, `python3 -c "import chess.polyglot"`): `chess.polyglot.open_reader(path)`
  returns a `MemoryMappedReader` with:
  - `.find(board)` — best (highest-weight) entry for a position.
  - `.find_all(board)` — every entry (all book moves) for a position, in
    weight order.
  - `.choice(board)` — **weighted-random** move (weights honored) — this is
    the built-in variety primitive; no need to hand-roll weighted sampling.
  - `.weighted_choice(board)` — same, explicit name.
  - Positions are looked up via `chess.polyglot.zobrist_hash(board)`, and
    python-chess ships the full `POLYGLOT_RANDOM_ARRAY` so hashes are
    cross-compatible with books built by other tools (e.g. `polyglot.exe`,
    `pgn-extract`, or hand-rolled generators).

**Implication for this repo**: we don't need to write a polyglot reader/writer
from scratch. A bot book can be a `.bin` file (or, more simply given this
repo's existing pattern of hand-authored JSON — see `data/repertoire.json`,
`data/traps.json` — a small **custom JSON weighted-line format** mirroring the
repertoire trainer's schema, avoiding a binary format entirely for a
sub-1600-scope catalog that's small and hand-curated). Polyglot only starts to
pay for itself if books get large/machine-generated from a PGN corpus; for a
hand-curated sub-1600 catalog (~15-25 openings, each ~2-4 branch points), a
JSON structure analogous to `repertoire.json`'s per-color line tree is simpler
to hand-edit, diff-review, and unit test than binary polyglot — same
weighted-choice idea, just not the wire format. ⚠ This is a build-time
recommendation, not a researched fact — flagging so the build phase makes it
a deliberate choice rather than a default.

## Sampling strategies for game-to-game variety

The "never the same game twice" requirement maps directly onto **weighted
random sampling with a temperature-like sharpness knob**, same shape as LLM
decoding sampling (temperature / top-k) even though chess opening books
predate that framing by decades:

- **Weight-proportional sampling** (polyglot's native behavior) — pick move
  `i` with probability `w_i / Σw_j`. This is the baseline: popular/strong
  moves get picked more, everything with nonzero weight is still reachable.
  Source: [Polyglot book format](https://hgm.nubati.net/book_format.html).
- **Temperature / exponent sharpening** — raise weights to a power `p` before
  normalizing (`w_i^p / Σw_j^p`). `p > 1` sharpens toward the top move (less
  variety, more "book-perfect" play — appropriate for a higher-rated/stronger
  persona); `p < 1` flattens toward uniform (more variety, more "plausible
  amateur" spread — appropriate for a lower-rated persona that shouldn't
  always find the objectively-best branch). `p → 0` is uniform-random among
  nonzero-weight moves; `p → ∞` degenerates to always-best (no variety).
- **Top-k truncation** — restrict sampling to the k highest-weight moves
  before normalizing, discarding the long tail entirely. Useful to prevent a
  bot from ever playing a move that's in the data only as noise (e.g. a rare
  miscue that leaked into a lichess-derived book with nonzero games). For a
  hand-curated catalog (this repo's approach) this matters less since there's
  no long tail to truncate — every branch was deliberately chosen.
- **No-repeat-in-session tracking** — general opening-book literature notes
  the standard trick for avoiding staleness: "random selections are not
  repeated once used" within a session/match, i.e. exclude previously-played
  branches at a given node until the pool is exhausted, then reset. Source:
  [Chess Programming Wiki — Opening Book](https://www.chessprogramming.org/Opening_Book).
  This is a stronger variety guarantee than pure weighted-random (which can
  reselect the same branch repeatedly by chance) and is cheap to implement
  server-side by tracking a per-bot (or per-bot-per-user) recently-played-line
  set, decayed/reset after N games or after the pool is exhausted.
- **Exit-depth control** — books are deeper on common lines, shallower on rare
  ones ("more common opening lines will be stored to a much higher depth than
  the uncommon ones," same Chessprogramming Wiki source); once a position
  isn't in the book, the engine/bot falls through to normal move selection
  (for this app: Stockfish at the persona's configured strength — see
  `../engine-adaptation/`). For rating-plausible bots, exit depth should track
  the sub-1600-deviation data in `rating-banded-opening-behavior.md`: real
  sub-1600 opponents typically leave book by move 4-8, so a bot book that's
  deep to move 15 in main lines is *less* rating-plausible than one that gets
  shallow and probabilistic around move 6-8, matching how actual opponents at
  that rating play. Book depth itself becomes a persona/rating tuning knob,
  not just a memory-size one.

## Persona repertoire bias (book as style expression)

- A book is naturally where "gambiteer vs system player" persona bias lives:
  weight gambit branches (Evans Gambit, Scotch Gambit, Englund) higher for an
  aggressive/sac-happy persona, weight quiet system moves (London, Giuoco
  Pianissimo c3/d3) higher for a solid/passive persona. This is a book-weight
  design choice layered on top of the popularity-based weights in
  `rating-banded-opening-behavior.md` — persona bias should perturb, not
  replace, rating-plausibility (an 1100-rated gambiteer bot should still play
  *popular-at-1100* gambits, not master-level theoretical ones).
- **Overlap with the user's own repertoire has training value.** This repo's
  `data/repertoire.json` already encodes the user's prepared lines (White:
  Italian Giuoco Pianissimo, Open Sicilian Najdorf/Dragon/Classical,
  Scandinavian main line, plus trap lines like Fried Liver/Legal
  Trap/Petrov Queen Trap; Black: Sicilian Najdorf, King's Indian Defense). A
  bot book that's deliberately weighted to walk into these exact lines (e.g.
  a bot playing 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6 5.d3 to meet the user's
  Giuoco Pianissimo prep, or 1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 to
  face the user's Najdorf) gives the user repeated reps against their own
  prepared lines from the opponent's side — directly useful for repertoire
  practice, distinct from what the Repertoire Trainer already does (which
  drills the user's own moves, not an opponent playing into them). This is a
  concrete, low-cost persona idea: one or more "sparring" bots whose books
  are literally derived from `data/repertoire.json`'s opponent-side branches.
  ⚠ Design detail (which persona, how prominent) belongs in
  `../bot-personas/`, not decided here — flagging the mechanism only.

## Sources
- [Polyglot book format (H.G. Muller)](https://hgm.nubati.net/book_format.html) — 16-byte entry structure, move encoding, weight-based selection probability.
- [python-chess: Polyglot opening book reading](https://python-chess.readthedocs.io/en/latest/polyglot.html) — `MemoryMappedReader`, `zobrist_hash`, `POLYGLOT_RANDOM_ARRAY`.
- [Chess Programming Wiki — Opening Book](https://www.chessprogramming.org/Opening_Book) — book construction from game databases, exit-depth-by-commonness convention, randomization for variety, no-repeat-once-used trick.
- Local: `python3 -c "import chess.polyglot; help(chess.polyglot)"` confirmed `MemoryMappedReader.choice()` / `.weighted_choice()` / `.find_all()` exist in the repo's installed python-chess version (queried 2026-07-16).
- Local: `data/repertoire.json` (this repo) — user's prepared lines, referenced above for the sparring-bot idea.
