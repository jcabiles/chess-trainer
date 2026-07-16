# Sub-1600 opening catalog

Priority coverage of the openings most-played and most-relevant at sub-1600
ratings, per `SCOPE.md`. **Not comprehensive** — this is the short list a bot
opening book should actually weight, not a full theory reference. Traps
(bait/refutation lines) live in `opening-traps.md` and are cross-referenced
inline rather than repeated. Rating-popularity evidence and its sourcing
caveats live in `rating-banded-opening-behavior.md` — read that note's
verification-gap section before treating any percentage here as settled; this
catalog's "bot-book weight" notes are directional, not weight-table-ready.

Format per opening: name + ECO, main line in SAN to ~move 6-8, 2-4 common
branch points with sub-1600-popular continuations, typical non-trap
deviations, trap cross-refs, and a bot-book weight note.

---

## White repertoire

### 1. Italian Game — Giuoco Piano / Giuoco Pianissimo (C50-C54)
**Main line**: `1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6 5.d3 d6 6.O-O O-O`

- **Branch at move 3 (Black's bishop square)**: `3...Bc5` (Giuoco Piano,
  most common) vs `3...Nf6` (Two Knights Defense — see separate entry below,
  sharper and more theory-dependent). Sub-1600 players favor `3...Bc5` because
  it avoids the forcing `4.Ng5` tactics of the Two Knights.
  [Wikibooks — 1.e4 e5 2.Nf3 Nc6 3.Bc4](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...e5/2._Nf3/2...Nc6/3._Bc4).
- **Branch at move 4 (White's plan)**: `4.c3` (classical, preparing d4,
  matches this repo's own repertoire — see `data/repertoire.json`'s
  "Giuoco Pianissimo" entry: `e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3`) vs `4.d3`
  (immediately quiet/flexible) vs `4.O-O` vs `4.b4` (Evans Gambit — sharper,
  pawn sac for development/attack). The modern `c3`+`d3` "Giuoco Pianissimo"
  approach became especially popular starting in the 1980s and is a common
  club-level choice because it sidesteps forcing theory.
  [Wikipedia — Giuoco Piano](https://en.wikipedia.org/wiki/Giuoco_Piano).
- **Branch at move 5-6 (central break)**: `4.c3 Nf6 5.d4` (classical, strikes
  center immediately, leads to `exd4 6.cxd4 Bb4+ 7.Bd2`) vs `5.d3` (modern
  Pianissimo, delays the break, more maneuvering). Sub-1600 games skew toward
  whichever the opponent's book/instinct favors; `5.d3` is lower-theory and
  more forgiving of imprecision.
- **Typical sub-1600 deviations (non-trap)**: Black recapturing on d4 with
  the wrong piece order, premature `...d5` breaks without adequate
  preparation, White delaying castling too long chasing material. These are
  inaccuracies, not traps — contrast with the *deliberate* bait lines at
  `opening-traps.md` A1 (Legal's Trap, Philidor/Italian-adjacent) and A3
  (Blackburne Shilling Gambit, `3...Nd4?!` off this same tabiya).
- **Bot-book weight**: `4.c3 Nf6 5.d3` (Pianissimo) should be the **highest
  weight** branch for personas ~1000-1400 — it's this app's own user
  repertoire line (sparring value, see `bot-opening-books.md`), low-theory,
  and forgiving. `4.c3 ... 5.d4` (sharper classical main line) and `4.b4`
  Evans Gambit should scale up in weight for a ~1500+ or "aggressive
  gambiteer" persona.

### 2. Italian Game — Two Knights Defense (C55-C59)
**Main line**: `1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Na5`

- **Branch at move 4 (White's try)**: `4.Ng5` (Knight/Fried Liver Attack,
  aggressive, attacks f7) vs `4.d3` (quiet, avoids tactics, often transposes
  to Giuoco Pianissimo after `4...Bc5`). At sub-1600, `4.Ng5` scores well in
  practice specifically *because* Black frequently misdefends it: only
  **47.61%** of ~1000-rated players find the correct `4...d5`; the majority
  play an inferior move. [MyChessPosters — Two Knights 4.Ng5 Crushes at 1000
  ELO](https://mychessposters.com/two-knights-defense-ng5-1000-elo/) ⚠
  secondary source, see `rating-banded-opening-behavior.md` verification gap.
- **Branch at move 5 (Black's knight retreat)**: `5...Na5` (Polerio Defense,
  most common, hits the c4 bishop) vs `5...Nxd5` vs `5...b5` (Ulvestad,
  sharper, uncommon at this level). This tabiya **is** the Fried Liver Attack
  covered in `opening-traps.md` A4 — that note has the `6.Nxf7!` sacrifice
  line and its refutation (`5...Na5!`); this entry only adds the
  rating-popularity angle (how often sub-1600 Black actually plays the
  refutation vs walks into trouble).
- **Typical sub-1600 deviations (non-trap)**: Black playing `4...Bc5` (fine,
  transposes) but then mishandling the resulting IQP/gambit structures;
  White playing `4.Ng5` without following through on `Bxf7+`/`Qf3` follow-ups
  because the tactics weren't calculated, just pattern-matched.
- **Bot-book weight**: `4.Ng5` is rating-plausible and practically strong for
  a White persona ~1000-1400 (matches this repo's own repertoire — see
  `data/repertoire.json`'s "Fried Liver Attack" entry). Weight should
  *decrease* for personas 1600+ where `4.Ng5`'s edge shrinks (51% win rate
  at 1800+ per the same source) and `4.d3` becomes more representative.

### 3. Scotch Game (C44-C45)
**Main line**: `1.e4 e5 2.Nf3 Nc6 3.d4 exd4 4.Nxd4 Bc5` (or `4...Nf6`)

- **Branch at move 3-4**: `3...exd4 4.Nxd4` (main line) vs `4.Bc4` (Scotch
  Gambit, pawn sac for development) vs `4.c3` (Göring Gambit). Main line is
  most common and lowest-theory.
- **Branch at move 4 (Black's reply)**: `4...Bc5` and `4...Nf6` are both
  "good and offer Black chances for an equal game" per
  [Wikipedia — Scotch Game](https://en.wikipedia.org/wiki/Scotch_Game); no
  strong sub-1600 popularity skew found between the two in this pass.
- **Typical sub-1600 deviations**: natural piece development on both sides
  tends to keep this line close to book longer than sharper e4 openings
  precisely because it's "low in theory" and reachable by general principles
  rather than memorization — beginners' instinctive moves often *are* the
  book moves here.
- **Bot-book weight**: good secondary/variety branch for a White persona at
  any sub-1600 band — its low forced-theory nature means bot deviations
  (once out of book) look natural rather than jarring. Useful as a
  lower-weight alternative to Italian in a varied book so the bot doesn't
  always play Italian.

### 4. Ruy Lopez / Spanish (C60-C99)
**Main line**: `1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7`

- **Branch at move 3 (Black's reply)**: `3...a6` (Morphy Defense, by far most
  popular) vs `3...Nf6` (Berlin Defense — very solid, "Berlin Wall" endgame,
  more of a titled-player choice, lower sub-1600 frequency) vs the trap-prone
  `3...Nge7`/other tries.
- **Branch at move 5 (Black's setup)**: `5...Be7` (Closed/Morphy main line,
  "most played system of the Ruy Lopez," patient maneuvering) vs `5...Nxe4`
  (Open Variation, sharper) vs `5...b5` first. Closed is more representative
  at sub-1600 because it doesn't require memorizing the Open's forcing lines.
  [ChessKlub — Ruy Lopez](https://chessklub.com/ruy-lopez/).
- **Typical sub-1600 deviations (non-trap)**: White grabbing `Bxc6` too early
  without follow-up plan (gives up the bishop pair for little), Black
  delaying `...a6` and allowing `Bxc6` doubling structures without
  compensation understanding. Contrast with the deliberate **Noah's Ark
  Trap** (`opening-traps.md` A6, pawns a6-b5-c4 trapping a b3 bishop) and
  **Fishing Pole Trap** (A5, Berlin-adjacent `4...Ng4` bait) — both live in
  the trap note, not here.
- **Bot-book weight**: lower overall weight than Italian/Scotch for
  ~1000-1300 personas (more theory-dependent to play well; a bot playing the
  Closed Ruy convincingly needs a deeper book than Italian does before
  falling back to raw engine play). Reasonable secondary branch for a
  ~1400-1600 "more theoretical" persona.

### 5. London System (D00, sometimes A45/A46 by transposition)
**Main line**: `1.d4 d5 2.Bf4 Nf6 3.Nf3 e6 4.e3 Bd6 5.Bg3 O-O 6.Nbd2 c5`
(alt move order `1.d4 2.Nf3 3.Bf4` reaches the same structures; modern theory
prefers leading with `2.Bf4` since it's harder for Black to sidestep.)

- **Branch at move 2 (move order)**: `2.Bf4` (modern, harder for Black to
  avoid) vs `2.Nf3` then `3.Bf4` (older main line). Functionally converges;
  not a Black-facing branch so much as a White-side book-construction choice.
  [365Chess — London System](https://www.365chess.com/chess-openings/London-System).
- **Branch at Black's setup**: Black `...d5`+`...Nf6`+`...e6` (classical
  setup) vs `...g6` (King's Indian-style fianchetto vs the London) vs `...c5`
  early. The London's whole appeal is that White's first 4-5 moves
  (Bf4/Nf3/e3/c3/Nbd2) are nearly independent of Black's setup — this is
  *why* it's a low-theory, high-plausibility bot-book choice: the White side
  of the tree barely branches.
- **Typical sub-1600 deviations**: Black players unfamiliar with the London
  sometimes play `...Qb6` hitting b2 too early without follow-through — this
  IS a named trap (`opening-traps.md` B4, London System Trap, confirmed sound
  ~+3.0 for White) — cross-reference rather than repeat. Non-trap deviations
  include Black delaying development to grab the h7 sac square awareness too
  late (the London's thematic `Bxh7+`/`Ne5` ideas).
- **Bot-book weight**: excellent **top weight for a "system player"
  persona** (see `bot-opening-books.md` persona-bias section) across the
  whole sub-1600 band — low branching means a shallow book still covers
  nearly all Black replies, which is exactly the low-maintenance,
  high-plausibility property a bot book wants. This app doesn't currently
  have a London line in `data/repertoire.json` (the user's White 1.d4 isn't
  represented at all there — repertoire.json is e4-heavy), so a London-based
  bot doesn't get "sparring value" against the user's own prep, but that's
  fine — its value here is pure rating-plausibility as an opponent.

### 6. Queen's Gambit (Declined / Accepted / Slav as White's 2.c4 tree) (D06-D69)
**Main line (Declined)**: `1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.Nf3 Be7 5.Bg5 O-O`
**Main line (Slav)**: `1.d4 d5 2.c4 c6 3.Nf3 Nf6 4.Nc3 dxc4`

- **Branch at move 2 (Black's response to 2.c4)**: at master level, `2...c6`
  Slav (50%), `2...e6` QGD (34%), `2...dxc4` QGA (12%) —
  [Wikipedia — Queen's Gambit Declined](https://en.wikipedia.org/wiki/Queen's_Gambit_Declined).
  ⚠ This split is **master-level**, not sub-1600 — flagged in
  `rating-banded-opening-behavior.md`; treat as a rough prior only, sub-1600
  Black is less likely to know the Slav's precise move order and may
  transpose/deviate into QGD-like structures regardless of intent.
- **Branch at move 4 (Declined tree)**: `4.Bg5` (Classical, pins the knight)
  vs `4.cxd5` (Exchange, has become a practical main line since `4...exd5`
  frees Black's light-squared bishop less than it looks) vs `4.Nf3` (flexible
  Three Knights, keeps all plans open). [Modern Chess — QGD
  guide](https://www.modern-chess.com/opening/queens-gambit-declined/).
- **Typical sub-1600 deviations (non-trap)**: Black playing an early
  `...dxc4` without following up correctly (loses time regaining the pawn),
  or playing the Slav's `...Bf5` a tempo too early (`4...Bf5` before securing
  `...dxc4` cleanly) — walks into lines where White gains the bishop pair or
  tempo via `Qb3`. Contrast with the deliberate **Elephant Trap** (`opening-traps.md`
  B1, QGD `...Nbd7` piece-win line) — that's a bait/punish structure, this is
  just an inaccuracy.
- **Bot-book weight**: `4.Bg5` Classical is the most representative
  "textbook" QGD branch for a ~1200-1500 persona; `4.cxd5` Exchange is a good
  secondary weight for a more positional/patient persona since it's simple to
  play well from a shallow book (few forcing lines).

---

## Black repertoire vs 1.e4

### 7. Open Games / …e5 (C20-C99, covers Italian/Ruy/Scotch as Black)
See White-side entries above (3-4) — the Black replies documented there
(`3...Bc5` Giuoco Piano, `3...a6` Morphy Defense, `4...Bc5`/`4...Nf6` vs
Scotch) are the same branch points from the other side of the board. Not
re-listing to avoid duplication; this app's book-builder should treat
White-opens/Black-replies as one shared tree per opening rather than two
separate catalogs.

### 8. French Defense (C00-C19)
**Main line**: `1.e4 e6 2.d4 d5 3.Nc3 Nf6 4.e5 Nfd7` (Classical/Steinitz) or
`3.Nc3 Bb4` (Winawer)

- **Branch at move 3 (White's setup)**: `3.Nc3` (played in **over 40%** of
  games reaching `1.e4 e6 2.d4 d5`) vs `3.Nd2` (Tarrasch, avoids the
  Winawer pin) vs `3.e5` (Advance) vs `3.exd5` (Exchange, most drawish/simple).
  [Chessable — French Defense](https://www.chessable.com/blog/french-defense/).
- **Branch at move 3-reply (Black vs 3.Nc3)**: `3...Nf6` (Classical, has
  overtaken `3...Bb4` in popularity since the 1980s) vs `3...Bb4` (Winawer,
  sharper, more theory-dependent) vs `3...dxe4` (Rubinstein, simplifying).
  Convenient beginner property: Black can meet **both** `3.Nc3` and `3.Nd2`
  with the same `3...Nf6` or `3...dxe4`, reducing prep burden — a real
  reason the French suits lower-theory-budget players.
  [Chessable — French Defense](https://www.chessable.com/blog/french-defense/).
- **Typical sub-1600 deviations (non-trap)**: Black's light-squared bishop
  getting stuck behind the e6/d5 pawn chain without a clear plan to activate
  it (the French's classic structural problem, often mishandled rather than
  exploited tactically); White over-extending the Advance Variation's
  kingside pawn storm without king safety. Cross-ref
  `opening-traps.md` B7 (French — Tarrasch Greek Gift, `Bxh7+` sac,
  substituted in for the murkier "French Burn" trap).
- **Bot-book weight**: `3.Nc3 Nf6` and `3.Nd2` are the highest-weight,
  lowest-theory branches for a Black persona ~1000-1400. Winawer (`3...Bb4`)
  should scale up only for a sharper/higher-rated persona — it demands more
  precise follow-up than a low-theory-budget bot book should promise.

### 9. Pirc / Philidor / "…d6" setups (B07-B09, C41)
**Main line (Pirc)**: `1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.f4 Bg7` (Austrian Attack)
or quieter `4.Nf3 Bg7 5.Be2 O-O`
**Main line (Philidor/Hanham)**: `1.e4 d6 2.d4 Nf6 3.Nc3 e5` (transposes from
Pirc move order) or `1.e4 e5 2.Nf3 d6` (old Philidor move order)

- **Branch at move order**: `1...d6` first (flexible, can go Pirc-`...g6` or
  Philidor-`...e5`/Hanham) vs `1...e5 2.Nf3 d6` (commits to Philidor
  structures immediately, "Old Philidor"). The `1...d6` move order is more
  flexible and better suited to a bot book that wants to keep both Pirc and
  Philidor structures reachable from one root.
  [Wikibooks — 1.e4 d6](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...d6).
- **Branch at move 3-4 (Pirc-specific)**: `4.f4` Austrian Attack (most
  ambitious/testing) vs `4.Nf3`/`4.Be2` (quieter). The Hanham Variation of
  the Philidor (`...Be7, ...Nbd7, ...Re8, ...c6` development scheme) "repeats
  in most lines," making it one of the easiest `...e5` structures to learn —
  good low-theory beginner property.
  [Chessdoctrine — Philidor Defense](https://chessdoctrine.com/chess-openings/kings-pawn/philidor-defense/).
- **Typical sub-1600 deviations (non-trap)**: Black fianchettoing (`...g6`)
  without timing the central `...e5`/`...c5` break correctly, leaving White a
  free hand in the center; premature `...d5` breaks that just open lines for
  White's better-developed pieces. This family is directly adjacent to
  `opening-traps.md` A1 (**Legal's Trap**, Philidor/Italian-hybrid tabiya,
  `4...Bg4?? 5.Nxe5!` pseudo-sac → `Bxd1?? 6.Bxf7+ Ke7 7.Nd5#`, confirmed
  mate) — that trap specifically punishes the Hanham-adjacent `...Bg4` pin
  before `...Nbd7`/`...Be7`; don't re-derive it here.
- **Bot-book weight**: solid variety branch for a Black persona wanting an
  alternative to `...e5` and Sicilian without taking on French-level
  structural complexity. Good for a lower-rated defensive/solid persona.

### 10. Sicilian Defense — Open, sub-1600-common branches (B20-B99)
**Main line (Open)**: `1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3` then
branches by Black's 5th move.

- **Branch at move 5 (Black's system) — this is the big one**:
  - `5...a6` **Najdorf** — most popular Sicilian overall and the line
    already in this repo's `data/repertoire.json` (both as White's opponent
    prep target and as the user's own Black repertoire entry), but
    **"not recommended for players under 2000"** per multiple sources due to
    its theoretical depth — a sub-1600 bot playing the Najdorf plausibly
    needs a shallow book (it should look like an underprepared player
    reaching Najdorf structures by instinct, not a memorized 15-move line).
  - `5...g6` **Dragon** — "easier to learn... relies more on grasp of broad
    strategies rather than memorizing specific lines" and "scores better for
    Black than the Najdorf at club level" — likely the **best sub-1600-book
    default** for a Black Sicilian persona.
  - `5...Nc6` **Classical** — "best for beginners and early-intermediate
    players, with natural piece development and less forced theory than the
    Najdorf or Dragon" — arguably the single best low-theory Open Sicilian
    branch for a bot book.
  - `4...a6` **Kan** (a move earlier, avoiding `...d6`/`...Nc6` commitments)
    — "solid yet spirited, relatively easy to learn, and scores very highly
    at amateur level."
  All four bullet points: [365Chess — Sicilian Defense
  guide](https://www.365chess.com/chess-openings/Sicilian-Defense) and
  [ChessKlub — Sicilian Defense](https://chessklub.com/chess-openings/sicilian-defense/).
  ⚠ These are secondary-source characterizations ("easier to learn," "scores
  well") not explorer popularity percentages — treat as directional for
  book-weighting, not as hard popularity numbers.
- **Typical sub-1600 deviations (non-trap)**: Black delaying `...a6`/`...e5`
  central commitments and drifting into passive setups; White over-pressing
  the attack before completing development (a common Open Sicilian beginner
  mistake on both sides given how sharp the structures can get). Cross-ref
  `opening-traps.md` B7's sibling entries aren't Sicilian-specific in this
  batch; no direct Sicilian trap currently cataloged there.
- **Bot-book weight**: **Classical (`5...Nc6`) or Dragon (`5...g6`) should be
  the primary sub-1600 Black-Sicilian book weight**, not Najdorf, *despite*
  Najdorf being this repo's own user repertoire — the user's Najdorf prep is
  better served by a **sparring bot** that specifically plays into it (see
  `bot-opening-books.md` persona section) rather than by making Najdorf the
  *default* rating-plausible Sicilian branch, since real sub-1600 Najdorf
  players are themselves playing above their rating's typical depth.

### 11. Scandinavian Defense (B01)
**Main line**: `1.e4 d5 2.exd5 Qxd5 3.Nc3 Qa5 4.d4 c6 5.Nf3 Nf6 6.Bc4 Bf5`

- **Branch at move 3-reply (queen retreat)**: `3...Qa5` (main line, "the most
  popular option by far") vs `3...Qd6` vs `3...Qd8` (both playable, less
  common, more passive). Also present in this repo's own
  `data/repertoire.json` as a **White** entry ("Main Line (3...Qa5)" —
  i.e. the user has prepared the White side against this Black defense).
  [Wikibooks — 1.e4 d5](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...d5).
- **Branch at move 2**: `2...Qxd5` (immediate recapture, by far most common)
  vs `2...Nf6` (Modern/Icelandic-Gambit-adjacent, delays recapture, less
  common at this level).
- **Typical sub-1600 deviations (non-trap)**: Black's queen getting harassed
  repeatedly by White's developing pieces (`Nc3`, `Bc4`, `d4`) and losing
  tempo rather than time-loss being punished tactically; Black delaying
  `...c6` and allowing `Nb5` ideas. Cross-ref `opening-traps.md` B5
  (Scandinavian Trap) for the deliberate bait/punish version of this family.
- **Bot-book weight**: excellent low-theory Black default vs `1.e4` for a
  ~1000-1400 persona — cited across sources as reliable specifically because
  "the theory black needs to learn is limited." Also directly useful as a
  **sparring** opponent for the user's own White-side Scandinavian prep in
  `data/repertoire.json`.

### 12. Indian Defenses vs 1.d4 (King's Indian primary; …d6/Indian family) (A48-A79, E60-E99)
**Main line (KID, Fianchetto)**: `1.d4 Nf6 2.c4 g6 3.Nf3 Bg7 4.g3 O-O 5.Bg2 d6 6.O-O`
**Main line (KID, Classical)**: `1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5`

- **Branch at move 3-4 (White's system)**: Classical (`Nc3`+`e4`, most
  ambitious, most theoretical) vs Fianchetto (`g3`+`Bg2`, more positional,
  "one of the most popular lines at the grandmaster level" but also common
  at club level since it's more natural to play without deep prep) vs
  Sämisch (`f3`+`Be3`, aggressive, less common at sub-1600 due to setup
  complexity). [PPQTY — King's Indian
  Defense](https://ppqty.com/kings-indian-defense/).
- **Branch at move 6-8 (Black's central break)**: `...e5` (classical KID
  break, matches this repo's own user repertoire — `data/repertoire.json`'s
  "King's Indian Defense" entry is tagged Black) vs `...c5` (Benoni-style
  break, more positional). `...e5` is the thematic, most-taught KID break
  and the more beginner-natural choice.
- **Typical sub-1600 deviations (non-trap)**: Black playing `...e5` before
  king safety/development is complete, allowing White simplifying central
  tension favorably; White neglecting queenside space-gaining (`b4`/`c5`
  plans) and letting Black's kingside attack develop for free — the KID's
  classic "race" dynamic mishandled by both sides through impatience rather
  than tactics.
- **Bot-book weight**: `...e5` break via either Classical or Fianchetto White
  setups is the highest-weight default for a Black "Indian" persona at
  sub-1600 — matches the user's own repertoire (sparring value) and is the
  most-taught, most-recognizable KID structure. Benoni-style `...c5` is a
  reasonable lower-weight variety branch but demands more precise move-order
  understanding, better suited to a ~1500+ persona.

---

## Coverage summary
12 opening families covering the full scope list:
- **White**: 1.d4 systems — London (#5), Queen's Gambit Declined/Slav/Accepted
  under one entry (#6); 1.e4 — Italian Giuoco Piano/Pianissimo (#1), Italian
  Two Knights (#2), Scotch (#3), Ruy Lopez (#4).
- **Black vs 1.d4**: the Queen's Gambit entry (#6) doubles as Black's `...d5`
  reply tree (QGD/Slav branch points documented from Black's side); Indian/
  King's Indian Defense (#12) covers the `...d6`/Indian-setup side of scope.
- **Black vs 1.e4**: Open Games/`...e5` (#7, cross-referenced to the White
  Italian/Ruy/Scotch entries rather than duplicated), French `...e6` (#8),
  Pirc/Philidor `...d6` (#9), Sicilian `...c5` (#10), Scandinavian `...d5`
  (#11, also a listed White repertoire entry in `data/repertoire.json`).

Popularity data source throughout: secondary write-ups citing lichess
Opening Explorer and community/advice-genre consensus — **no live explorer
query was executed this pass** (network access gap, see
`rating-banded-opening-behavior.md`'s verification-gap section); every
percentage is flagged ⚠ pending-verification at its point of use. Most-
common-first ordering follows each entry's own cited evidence.
**Not comprehensive** — omits e.g. Caro-Kann, Nimzo-Indian, Catalan, Vienna,
King's Gambit, and English/flank openings entirely, per scope (sub-1600-focus
priority list, not full theory coverage).
