# Engine-Weakening Probe — Results (R1)

Regenerable: `STOCKFISH_PATH=... .venv/bin/python docs/ai-dlc/research/probes/probe_weakening.py`

**Question:** does *weakened* Stockfish read as HUMAN (plausible plans, understandable errors) or RANDOM (inexplicable drops, aimless shuffling)?

- Engine: `/opt/homebrew/bin/stockfish` — Stockfish 18
- Reference best/eval budget: `Limit(depth=18)` (best), `Limit(depth=16)` (scoring chosen vs best move, white-POV cp)
- Weak-play budget: `Limit(time=0.3)` (node-cap config overrides)
- Blunder threshold: cpLoss > 200
- Positions: 20 (11 from games.db, 9 curated; 6 threat-facing)

**PRIVACY:** games.db positions are referenced by index + phase + motif only; their FENs are never printed. Curated FENs are shown.

## Aggregate (per config)

| Config | avg cpLoss | median | % match-best | blunders (>200) | verdict |
|---|---|---|---|---|---|
| Skill Level 3 | 45 | 7 | 35% | 1/20 | **HUMAN-LIKE** |
| Skill Level 10 | 22 | 4 | 50% | 0/20 | **HUMAN-LIKE** |
| LimitStrength Elo 1350 | 51 | 14 | 35% | 2/20 | **HUMAN-LIKE** |
| LimitStrength Elo 1700 | 42 | 2 | 55% | 2/20 | **HUMAN-LIKE** |
| Nodes cap 500 | 16 | 2 | 55% | 0/20 | **NOT MEANINGFULLY WEAKENED** |

## Per-config verdicts

### Skill Level 3

- **Human-vs-random:** HUMAN-LIKE: avg cpLoss 45, 1/20 blunders (5%), 35% match-best. errors are small and infrequent; picks the top move often, mistakes look like understandable inaccuracies.
- **Threat-facing:** 3/6 threats handled, 3 missed. #0 opening/threat: discovered: handled | #1 middlegame/threat: hanging: MISSED (cpLoss 202) | #2 endgame/threat: hanging: MISSED (cpLoss 198) | #3 opening/threat: hanging: MISSED (cpLoss 129) | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

### Skill Level 10

- **Human-vs-random:** HUMAN-LIKE: avg cpLoss 22, 0/20 blunders (0%), 50% match-best. errors are small and infrequent; picks the top move often, mistakes look like understandable inaccuracies.
- **Threat-facing:** 5/6 threats handled, 1 missed. #0 opening/threat: discovered: MISSED (cpLoss 167) | #1 middlegame/threat: hanging: handled | #2 endgame/threat: hanging: handled | #3 opening/threat: hanging: handled | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

### LimitStrength Elo 1350

- **Human-vs-random:** HUMAN-LIKE: avg cpLoss 51, 2/20 blunders (10%), 35% match-best. errors are small and infrequent; picks the top move often, mistakes look like understandable inaccuracies.
- **Threat-facing:** 2/6 threats handled, 4 missed. #0 opening/threat: discovered: MISSED (cpLoss 104) | #1 middlegame/threat: hanging: MISSED (cpLoss 231) | #2 endgame/threat: hanging: MISSED (cpLoss 240) | #3 opening/threat: hanging: MISSED (cpLoss 108) | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

### LimitStrength Elo 1700

- **Human-vs-random:** HUMAN-LIKE: avg cpLoss 42, 2/20 blunders (10%), 55% match-best. errors are small and infrequent; picks the top move often, mistakes look like understandable inaccuracies.
- **Threat-facing:** 5/6 threats handled, 1 missed. #0 opening/threat: discovered: MISSED (cpLoss 218) | #1 middlegame/threat: hanging: handled | #2 endgame/threat: hanging: handled | #3 opening/threat: hanging: handled | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

### Nodes cap 500

- **Human-vs-random:** NOT MEANINGFULLY WEAKENED: avg cpLoss 16, 0/20 blunders (0%), 55% match-best. plays at near-full strength — this config barely dents modern Stockfish, so it says little about human-likeness.
- **Threat-facing:** 4/6 threats handled, 2 missed. #0 opening/threat: discovered: MISSED (cpLoss 106) | #1 middlegame/threat: hanging: MISSED (cpLoss 141) | #2 endgame/threat: hanging: handled | #3 opening/threat: hanging: handled | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

## Positions

| # | source | phase | threat | description | FEN |
|---|---|---|---|---|---|
| 0 | db | opening | yes | threat: discovered (leak motif: discovered) | _(private — db)_ |
| 1 | db | middlegame | yes | threat: hanging (hanging P on h3) | _(private — db)_ |
| 2 | db | endgame | yes | threat: hanging (hanging r on f3) | _(private — db)_ |
| 3 | db | opening | yes | threat: hanging (leak motif: hanging) | _(private — db)_ |
| 4 | db | middlegame | yes | threat: hanging (winnable capture of n on b4) | _(private — db)_ |
| 5 | db | opening | no | quiet position | _(private — db)_ |
| 6 | db | middlegame | no | quiet position | _(private — db)_ |
| 7 | db | endgame | no | quiet position | _(private — db)_ |
| 8 | db | opening | no | quiet position | _(private — db)_ |
| 9 | db | opening | no | quiet position | _(private — db)_ |
| 10 | db | middlegame | no | quiet position | _(private — db)_ |
| 11 | curated | opening | no | start position (quiet) | `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` |
| 12 | curated | opening | no | Italian, quiet development | `r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3` |
| 13 | curated | opening | no | Italian Giuoco Pianissimo (quiet) | `r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R b KQkq - 0 5` |
| 14 | curated | opening | no | Ruy Lopez main (quiet) | `r1bqkb1r/pppp1ppp/2n2n2/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4` |
| 15 | curated | middlegame | no | symmetric Italian middlegame (quiet) | `r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P1b1/2NP1N2/PPP2PPP/R2Q1RK1 w - - 6 8` |
| 16 | curated | opening | yes | Ruy: Bb5 pins Nc6 (tactical/threat) | `r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3` |
| 17 | curated | endgame | no | R+3 vs 3 rook endgame technique (quiet) | `6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1` |
| 18 | curated | endgame | no | K+P vs K opposition (quiet, precise) | `8/8/8/4k3/8/4K3/4P3/8 w - - 0 1` |
| 19 | curated | middlegame | no | open-file rook endgame-ish (quiet) | `r3k2r/pp3ppp/2p5/8/8/2P5/PP3PPP/R3K2R w KQkq - 0 1` |

## Per-position × config

| # | phase | threat | Skill Level 3 | Skill Level 10 | LimitStrength Elo 1350 | LimitStrength Elo 1700 | Nodes cap 500 |
|---|---|---|---|---|---|---|---|
| 0 | opening | Y | Nb4= (0) | O-O-O (167) | e5 (104) | O-O-O (218) | e5 (106) |
| 1 | middlegame | Y | Rh1 (202) | Rxf8+= (1) | Rh1 (231) | Rxf8+= (0) | Re1 (141) |
| 2 | endgame | Y | Re3 (198) | Rf4+= (0) | Rd3 (240) | Rf4+= (0) | Rf4+= (3) |
| 3 | opening | Y | Rc8 (129) | hxg4= (0) | Be7 (108) | hxg4= (23) | hxg4= (0) |
| 4 | middlegame | Y | Nc6= (3) | Na6 (50) | Nc6= (0) | Nc6= (27) | Nc6= (15) |
| 5 | opening |  | c6 (1) | e6= (7) | g6 (32) | c6 (7) | e5 (0) |
| 6 | middlegame |  | Nd7 (23) | Nd7 (23) | Ng6= (19) | Ng6= (0) | Ng6= (3) |
| 7 | endgame |  | g6 (6) | Re6 (30) | Qb8 (16) | Qf6 (0) | Re6 (0) |
| 8 | opening |  | Ne4= (2) | Qe7 (71) | a6 (93) | e5 (106) | Ne4= (1) |
| 9 | opening |  | a3 (14) | Nd2 (0) | O-O (12) | h3= (0) | O-O (9) |
| 10 | middlegame |  | bxc5= (6) | bxc5= (8) | bxc5= (1) | Nxe4 (376) | bxc5= (0) |
| 11 | opening |  | e4= (4) | d4 (0) | d4= (6) | d4= (0) | e4 (6) |
| 12 | opening |  | a6 (40) | Nf6= (8) | Be7 (16) | Nf6= (2) | Bc5 (2) |
| 13 | opening |  | O-O (6) | a6= (0) | d6 (4) | h6 (0) | a6= (2) |
| 14 | opening |  | d3 (8) | d3 (13) | d3 (11) | d4 (40) | Nc3 (24) |
| 15 | middlegame |  | Kh1 (111) | h3 (69) | Kh1 (118) | Nd5= (7) | Nd5= (6) |
| 16 | opening | Y | Nge7 (25) | Nf6= (0) | Nf6= (0) | Nge7 (27) | Nf6= (3) |
| 17 | endgame |  | Ra8#= (0) | Ra8#= (0) | Ra8#= (0) | Ra8#= (0) | Ra8#= (0) |
| 18 | endgame |  | Kd3= (0) | Kd2 (0) | Kf2 (1) | Kd2 (0) | Kd3 (0) |
| 19 | middlegame |  | Kd1 (117) | O-O-O= (0) | O-O-O= (0) | O-O-O= (2) | O-O-O= (0) |

_Cell = chosen move (cpLoss). `=` marks the move matching full-strength best._

## lc0 / Maia status

- lc0 binary: **NOT FOUND** (expected on this machine)
- Maia weights: **NOT FOUND**

### Install commands (for synthesis doc to lift)

```sh
# lc0 (Leela Chess Zero) engine
brew install lc0

# Maia human-like weights (per-Elo networks, 1100..1900).
# Download from the maia-chess release mirror on GitHub:
#   https://github.com/CSSLab/maia-chess
# Example weight files (one per rating bucket):
mkdir -p ~/maia_weights && cd ~/maia_weights
for elo in 1100 1300 1500 1700 1900; do
  curl -L -o maia-${elo}.pb.gz \
    https://github.com/CSSLab/maia-chess/raw/master/maia_weights/maia-${elo}.pb.gz
done

# Run lc0 with a Maia net (nodes=1 → pure policy, most human-like):
lc0 --weights=~/maia_weights/maia-1500.pb.gz
```

_Note: exact Maia weight URLs/paths should be confirmed at install time; the maia-chess repo is the canonical source._

## Caveats

- cpLoss uses a white-POV eval of the position *after* the move vs after the reference best move, scored at a fixed budget — a proxy, not a deep ground truth. Small cpLoss values are within engine noise.
- Skill Level / node-cap play is stochastic; numbers may shift a few cp between runs even with a seed (seed only fixes db sampling).
- The HUMAN-vs-RANDOM verdict is a heuristic over avg cpLoss + blunder rate + match-rate, not a human rater. Treat as directional evidence.
- 'Threat handled/missed' infers from cpLoss on threat-facing positions; it cannot literally read the engine's intent.
- **Node caps are a coarse, unanchored knob**: with a cold TT per config, nodes=500 does weaken SF18 measurably, but it remains the strongest of the weakened configs and carries no ELO semantics (strength varies by hardware/version). Skill Level / UCI_Elo are the primary usable knobs. NOTE: an earlier revision of this probe ran all configs sequentially on ONE engine process; the node-cap config ran last on a warm transposition table over these same positions and looked essentially full-strength — a confound fixed by fresh-process-per-config (flagged in review).
- Key epic finding: across the *effective* weakeners (Skill 3, Elo 1350/1700), errors on threat-facing positions are dominated by **missing a real threat while playing an otherwise purposeful move** (the chosen move has a plan; it just overlooks the tactic) rather than random piece drops — i.e. reads HUMAN, not RANDOM. Lower settings (Skill 3) miss threats more often, as a weaker human would.
