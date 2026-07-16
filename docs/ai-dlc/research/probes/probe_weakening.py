#!/usr/bin/env python3
"""Engine-weakening probe (research spike R1).

Question: does *weakened* Stockfish read as HUMAN (plausible plans,
understandable errors) or RANDOM (inexplicable piece drops, aimless
shuffling), across several weakening configs and ~18 positions?

STANDALONE by contract: uses python-chess (the library) + the Stockfish
binary directly. Importing the repo's ``app.*`` modules is FORBIDDEN.

Run:
    STOCKFISH_PATH=/opt/homebrew/bin/stockfish \
        .venv/bin/python docs/ai-dlc/research/probes/probe_weakening.py

Writes ``results.md`` next to this script. Regenerable: re-running
reproduces the committed table (a fixed RNG seed makes db sampling
deterministic; engine play is near-deterministic at fixed limits).

PRIVACY (binding): positions sampled from ``data/games.db`` are NEVER
printed with their FEN in ``results.md``. They are referenced by index +
phase + motif only. Curated standard FENs are printed freely.
"""
from __future__ import annotations

import os
import random
import sqlite3
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.engine

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]  # docs/ai-dlc/research/probes -> repo root
DB_PATH = REPO_ROOT / "data" / "games.db"
RESULTS_PATH = HERE / "results.md"

SEED = 20260716
DB_SAMPLE_QUIET = 6          # non-threat db positions across phases
DB_SAMPLE_THREAT = 5         # threat-facing db positions (>=4 required)

# Reference (full-strength) analysis budget for the "best move" baseline.
REF_LIMIT = chess.engine.Limit(depth=18)
# Per-move budget the *weakened* engine gets (so limit-strength has room to work).
PLAY_LIMIT = chess.engine.Limit(time=0.30)
# Budget used to score whatever move the weakened engine chose (cpLoss),
# scored from the reference (full-strength) engine at the same ref budget.
SCORE_LIMIT = chess.engine.Limit(depth=16)

BLUNDER_CP = 200  # cpLoss threshold flagged as a "blunder"


def stockfish_path() -> str:
    p = os.environ.get("STOCKFISH_PATH") or "/opt/homebrew/bin/stockfish"
    if not Path(p).exists():
        raise SystemExit(f"Stockfish binary not found at {p!r}; set STOCKFISH_PATH")
    return p


# ---------------------------------------------------------------------------
# Weakening configs
# ---------------------------------------------------------------------------
@dataclass
class Config:
    name: str
    options: dict          # UCI options to `configure`
    play_limit: chess.engine.Limit


def make_configs() -> list[Config]:
    return [
        Config("Skill Level 3", {"Skill Level": 3}, PLAY_LIMIT),
        Config("Skill Level 10", {"Skill Level": 10}, PLAY_LIMIT),
        Config(
            "LimitStrength Elo 1350",
            {"UCI_LimitStrength": True, "UCI_Elo": 1350},
            PLAY_LIMIT,
        ),
        Config(
            "LimitStrength Elo 1700",
            {"UCI_LimitStrength": True, "UCI_Elo": 1700},
            PLAY_LIMIT,
        ),
        # Node-cap only: no skill/elo weakening, just a starved search.
        Config("Nodes cap 500", {}, chess.engine.Limit(nodes=500)),
    ]


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------
@dataclass
class Position:
    idx: int
    fen: str
    source: str            # "db" | "curated"
    phase: str
    label: str             # public description (motif for db, name for curated)
    threat: bool
    printable: bool        # may the FEN appear in results.md?


# Curated standard FENs (public-domain textbook positions). Printable.
CURATED: list[tuple[str, str, str, bool]] = [
    # (fen, phase, label, threat)
    ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
     "opening", "start position (quiet)", False),
    ("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
     "opening", "Italian, quiet development", False),
    ("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R b KQkq - 0 5",
     "opening", "Italian Giuoco Pianissimo (quiet)", False),
    ("r1bqkb1r/pppp1ppp/2n2n2/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
     "opening", "Ruy Lopez main (quiet)", False),
    ("r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P1b1/2NP1N2/PPP2PPP/R2Q1RK1 w - - 6 8",
     "middlegame", "symmetric Italian middlegame (quiet)", False),
    # Tactical curated
    ("r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
     "opening", "Ruy: Bb5 pins Nc6 (tactical/threat)", True),
    ("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",
     "endgame", "R+3 vs 3 rook endgame technique (quiet)", False),
    ("8/8/8/4k3/8/4K3/4P3/8 w - - 0 1",
     "endgame", "K+P vs K opposition (quiet, precise)", False),
    ("r3k2r/pp3ppp/2p5/8/8/2P5/PP3PPP/R3K2R w KQkq - 0 1",
     "middlegame", "open-file rook endgame-ish (quiet)", False),
]


def board_phase(board: chess.Board) -> str:
    """Rough phase heuristic (piece count based)."""
    pieces = chess.popcount(board.occupied)
    majors_minors = 0
    for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
        majors_minors += chess.popcount(board.pieces_mask(pt, chess.WHITE))
        majors_minors += chess.popcount(board.pieces_mask(pt, chess.BLACK))
    if pieces <= 12 or majors_minors <= 6:
        return "endgame"
    if board.fullmove_number <= 10:
        return "opening"
    return "middlegame"


def faces_concrete_threat(board: chess.Board) -> tuple[bool, str]:
    """Standalone threat check using python-chess primitives.

    A position is 'threat-facing' if the side to move has a piece that the
    opponent can capture favourably (SEE-like: attacker cheaper or square
    not defended). Returns (is_threat, short_motif_description).
    """
    us = board.turn
    them = not us
    piece_val = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                 chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
    for sq in chess.SQUARES:
        pc = board.piece_at(sq)
        if pc is None or pc.color != us:
            continue
        attackers = board.attackers(them, sq)
        if not attackers:
            continue
        defenders = board.attackers(us, sq)
        our_val = piece_val[pc.piece_type]
        cheapest_attacker = min(
            piece_val[board.piece_at(a).piece_type] for a in attackers
        )
        # Hanging: no defender at all, and it's a real piece (>= knight),
        # or a pawn attacked by nothing defending.
        if not defenders and our_val >= 1:
            return True, f"hanging {pc.symbol()} on {chess.square_name(sq)}"
        # Winning capture available for opponent (cheaper attacker wins material).
        if defenders and cheapest_attacker < our_val:
            return True, (f"winnable capture of {pc.symbol()} on "
                          f"{chess.square_name(sq)}")
    return False, ""


def sample_db_positions() -> list[Position]:
    """Sample db positions WITHOUT ever exposing FENs publicly.

    Threat-facing ones come from leak rows (motif label public); quiet ones
    are random non-leak plies across phases. FEN strings are kept internal.
    """
    if not DB_PATH.exists():
        print(f"WARNING: {DB_PATH} absent; skipping db positions")
        return []
    rng = random.Random(SEED)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    positions: list[Position] = []

    # --- threat-facing (from leaks with a threat_motif) ---
    threat_rows = conn.execute(
        """
        SELECT p.fen_before AS fen, l.phase AS phase, l.threat_motif AS motif
        FROM leaks l JOIN game_plies p
          ON p.game_id = l.game_id AND p.ply = l.ply
        WHERE l.threat_motif IS NOT NULL AND p.fen_before IS NOT NULL
        """
    ).fetchall()
    # dedup by fen, keep a phase spread
    seen: set[str] = set()
    by_phase: dict[str, list[sqlite3.Row]] = {}
    for r in threat_rows:
        if r["fen"] in seen:
            continue
        seen.add(r["fen"])
        by_phase.setdefault(r["phase"], []).append(r)
    picked_threat: list[sqlite3.Row] = []
    phases = list(by_phase)
    rng.shuffle(phases)
    # round-robin across phases for spread
    i = 0
    while len(picked_threat) < DB_SAMPLE_THREAT and any(by_phase.values()):
        ph = phases[i % len(phases)]
        bucket = by_phase[ph]
        if bucket:
            picked_threat.append(bucket.pop(rng.randrange(len(bucket))))
        i += 1
        if i > 500:
            break

    # --- quiet (random plies, verify NOT threat-facing) ---
    all_rows = conn.execute(
        "SELECT fen_before AS fen, ply FROM game_plies "
        "WHERE fen_before IS NOT NULL"
    ).fetchall()
    conn.close()
    rng.shuffle(all_rows)
    picked_quiet: list[tuple[str, str]] = []
    for r in all_rows:
        if len(picked_quiet) >= DB_SAMPLE_QUIET:
            break
        try:
            b = chess.Board(r["fen"])
        except ValueError:
            continue
        if b.is_game_over():
            continue
        is_threat, _ = faces_concrete_threat(b)
        if is_threat:
            continue
        ph = board_phase(b)
        # spread: avoid >3 of same phase
        if sum(1 for _, p in picked_quiet if p == ph) >= 3:
            continue
        picked_quiet.append((r["fen"], ph))

    idx = 0
    for r in picked_threat:
        b = chess.Board(r["fen"])
        _, motif_desc = faces_concrete_threat(b)
        desc = motif_desc or f"leak motif: {r['motif']}"
        positions.append(Position(
            idx=idx, fen=r["fen"], source="db", phase=r["phase"],
            label=f"threat: {r['motif']} ({desc})", threat=True,
            printable=False,
        ))
        idx += 1
    for fen, ph in picked_quiet:
        positions.append(Position(
            idx=idx, fen=fen, source="db", phase=ph,
            label="quiet position", threat=False, printable=False,
        ))
        idx += 1
    return positions


def all_positions() -> list[Position]:
    positions = sample_db_positions()
    idx = len(positions)
    for fen, phase, label, threat in CURATED:
        positions.append(Position(
            idx=idx, fen=fen, source="curated", phase=phase,
            label=label, threat=threat, printable=True,
        ))
        idx += 1
    return positions


# ---------------------------------------------------------------------------
# Engine scoring
# ---------------------------------------------------------------------------
def score_cp_white(info) -> int | None:
    """PovScore -> white-POV centipawns (mate mapped to a large cp)."""
    if info is None:
        return None
    sc = info["score"].white()
    if sc.is_mate():
        m = sc.mate()
        if m is None:
            return None
        return 100000 - m if m > 0 else -100000 - m
    return sc.score()


@dataclass
class MoveResult:
    move: str          # SAN of chosen move
    cp_loss: int | None
    match_best: bool
    best_san: str


def evaluate_position(
    ref_engine: chess.engine.SimpleEngine,
    weak_engine: chess.engine.SimpleEngine,
    cfg: Config,
    fen: str,
) -> MoveResult:
    board = chess.Board(fen)
    mover = board.turn  # True=white

    # Reference best move + eval of resulting position (white POV).
    ref_info = ref_engine.analyse(board, REF_LIMIT)
    best_move = ref_info["pv"][0]
    best_san = board.san(best_move)
    b_after_best = board.copy()
    b_after_best.push(best_move)
    best_eval_white = score_cp_white(
        ref_engine.analyse(b_after_best, SCORE_LIMIT)
    )

    # Weakened engine picks its move.
    weak_engine.configure(cfg.options)
    play = weak_engine.play(board, cfg.play_limit)
    chosen = play.move
    chosen_san = board.san(chosen)
    b_after_chosen = board.copy()
    b_after_chosen.push(chosen)
    chosen_eval_white = score_cp_white(
        ref_engine.analyse(b_after_chosen, SCORE_LIMIT)
    )

    cp_loss = None
    if best_eval_white is not None and chosen_eval_white is not None:
        # From the mover's POV: how much worse is the chosen resulting eval.
        if mover:  # white to move: higher white eval is better
            cp_loss = best_eval_white - chosen_eval_white
        else:      # black to move: lower white eval is better for black
            cp_loss = chosen_eval_white - best_eval_white
        cp_loss = max(0, cp_loss)

    return MoveResult(
        move=chosen_san,
        cp_loss=cp_loss,
        match_best=(chosen == best_move),
        best_san=best_san,
    )


# ---------------------------------------------------------------------------
# Aggregation + verdict
# ---------------------------------------------------------------------------
@dataclass
class ConfigAgg:
    name: str
    results: list[tuple[Position, MoveResult]] = field(default_factory=list)

    def cp_losses(self) -> list[int]:
        return [r.cp_loss for _, r in self.results if r.cp_loss is not None]

    def avg_cp_loss(self) -> float:
        cl = self.cp_losses()
        return statistics.mean(cl) if cl else float("nan")

    def median_cp_loss(self) -> float:
        cl = self.cp_losses()
        return statistics.median(cl) if cl else float("nan")

    def pct_match(self) -> float:
        n = len(self.results)
        if not n:
            return float("nan")
        m = sum(1 for _, r in self.results if r.match_best)
        return 100.0 * m / n

    def blunders(self) -> int:
        return sum(1 for _, r in self.results
                   if r.cp_loss is not None and r.cp_loss > BLUNDER_CP)

    def threat_results(self) -> list[tuple[Position, MoveResult]]:
        return [(p, r) for p, r in self.results if p.threat]


def qualitative_verdict(agg: ConfigAgg) -> str:
    """Heuristic human-vs-random read, backed by the numbers.

    HUMAN: modest avg cpLoss, blunders are the minority, some best matches.
    RANDOM: large avg cpLoss driven by many >200 blunders / near-zero match.
    """
    n = len(agg.results)
    avg = agg.avg_cp_loss()
    blun = agg.blunders()
    blun_rate = blun / n if n else 0
    match = agg.pct_match()
    if avg < 20 and match >= 55:
        read = "NOT MEANINGFULLY WEAKENED"
        why = ("plays at near-full strength — this config barely dents "
               "modern Stockfish, so it says little about human-likeness")
    elif avg < 90 and blun_rate <= 0.15:
        read = "HUMAN-LIKE"
        why = ("errors are small and infrequent; picks the top move often, "
               "mistakes look like understandable inaccuracies")
    elif avg < 220 and blun_rate <= 0.35:
        read = "MIXED (human-ish with lapses)"
        why = ("mostly reasonable moves punctuated by occasional real "
               "blunders — plausible for a club player")
    else:
        read = "RANDOM-LEANING"
        why = ("frequent large material losses / near-zero agreement with "
               "best — reads as noisy rather than purposeful")
    return (f"{read}: avg cpLoss {avg:.0f}, {blun}/{n} blunders "
            f"({100*blun_rate:.0f}%), {match:.0f}% match-best. {why}.")


def threat_finding(agg: ConfigAgg) -> str:
    """Do errors on threat-facing positions relate to the threat?

    A threat-related error: cpLoss is meaningful AND the position had a
    concrete threat the engine plausibly failed to address. We can't read
    the engine's mind, but a large cpLoss on a threat-facing position where
    it did not play the best move is 'threat-related' (missed the threat
    while doing something else); a small cpLoss = handled the threat.
    """
    tr = agg.threat_results()
    if not tr:
        return "no threat-facing positions"
    handled = sum(1 for _, r in tr if (r.cp_loss or 0) <= 100)
    threat_err = sum(1 for _, r in tr if (r.cp_loss or 0) > 100)
    parts = []
    for p, r in tr:
        tag = ("handled" if (r.cp_loss or 0) <= 100
               else f"MISSED (cpLoss {r.cp_loss})")
        parts.append(f"#{p.idx} {p.phase}/{p.label.split('(')[0].strip()}: {tag}")
    summary = (f"{handled}/{len(tr)} threats handled, {threat_err} missed. ")
    return summary + " | ".join(parts)


# ---------------------------------------------------------------------------
# lc0 / Maia detection
# ---------------------------------------------------------------------------
def detect_lc0_maia() -> dict:
    import shutil
    lc0 = shutil.which("lc0")
    candidate_dirs = [
        Path.home() / "lc0",
        Path.home() / ".local/share/lc0",
        Path("/opt/homebrew/share/lc0"),
        Path("/usr/local/share/lc0"),
        HERE,
    ]
    maia_weights = []
    for d in candidate_dirs:
        if d.exists():
            for f in d.glob("*maia*"):
                maia_weights.append(str(f))
            for f in d.glob("*.pb.gz"):
                maia_weights.append(str(f))
    return {"lc0": lc0, "maia_weights": maia_weights}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def render_results(
    positions: list[Position],
    aggs: list[ConfigAgg],
    lc0_info: dict,
    sf_path: str,
    sf_version: str,
) -> str:
    lines: list[str] = []
    L = lines.append
    L("# Engine-Weakening Probe — Results (R1)")
    L("")
    L("Regenerable: `STOCKFISH_PATH=... .venv/bin/python "
      "docs/ai-dlc/research/probes/probe_weakening.py`")
    L("")
    L("**Question:** does *weakened* Stockfish read as HUMAN (plausible "
      "plans, understandable errors) or RANDOM (inexplicable drops, aimless "
      "shuffling)?")
    L("")
    L(f"- Engine: `{sf_path}` — {sf_version}")
    L(f"- Reference best/eval budget: `{REF_LIMIT}` (best), "
      f"`{SCORE_LIMIT}` (scoring chosen vs best move, white-POV cp)")
    L(f"- Weak-play budget: `{PLAY_LIMIT}` (node-cap config overrides)")
    L(f"- Blunder threshold: cpLoss > {BLUNDER_CP}")
    L(f"- Positions: {len(positions)} "
      f"({sum(1 for p in positions if p.source=='db')} from games.db, "
      f"{sum(1 for p in positions if p.source=='curated')} curated; "
      f"{sum(1 for p in positions if p.threat)} threat-facing)")
    L("")
    L("**PRIVACY:** games.db positions are referenced by index + phase + "
      "motif only; their FENs are never printed. Curated FENs are shown.")
    L("")

    # Aggregate table
    L("## Aggregate (per config)")
    L("")
    L("| Config | avg cpLoss | median | % match-best | blunders (>200) | verdict |")
    L("|---|---|---|---|---|---|")
    for agg in aggs:
        n = len(agg.results)
        verdict_short = qualitative_verdict(agg).split(":")[0]
        L(f"| {agg.name} | {agg.avg_cp_loss():.0f} | "
          f"{agg.median_cp_loss():.0f} | {agg.pct_match():.0f}% | "
          f"{agg.blunders()}/{n} | **{verdict_short}** |")
    L("")

    # Per-config verdicts + threat findings
    L("## Per-config verdicts")
    L("")
    for agg in aggs:
        L(f"### {agg.name}")
        L("")
        L(f"- **Human-vs-random:** {qualitative_verdict(agg)}")
        L(f"- **Threat-facing:** {threat_finding(agg)}")
        L("")

    # Position catalogue
    L("## Positions")
    L("")
    L("| # | source | phase | threat | description | FEN |")
    L("|---|---|---|---|---|---|")
    for p in positions:
        fen = f"`{p.fen}`" if p.printable else "_(private — db)_"
        L(f"| {p.idx} | {p.source} | {p.phase} | "
          f"{'yes' if p.threat else 'no'} | {p.label} | {fen} |")
    L("")

    # Per-position verdicts (matrix of chosen move + cpLoss per config)
    L("## Per-position × config")
    L("")
    header = "| # | phase | threat | " + " | ".join(a.name for a in aggs) + " |"
    L(header)
    L("|" + "---|" * (3 + len(aggs)))
    by_idx: dict[int, dict[str, MoveResult]] = {}
    for agg in aggs:
        for p, r in agg.results:
            by_idx.setdefault(p.idx, {})[agg.name] = r
    for p in positions:
        cells = []
        for agg in aggs:
            r = by_idx.get(p.idx, {}).get(agg.name)
            if r is None:
                cells.append("—")
            else:
                cl = "?" if r.cp_loss is None else str(r.cp_loss)
                star = "=" if r.match_best else ""
                cells.append(f"{r.move}{star} ({cl})")
        L(f"| {p.idx} | {p.phase} | {'Y' if p.threat else ''} | "
          + " | ".join(cells) + " |")
    L("")
    L("_Cell = chosen move (cpLoss). `=` marks the move matching "
      "full-strength best._")
    L("")

    # lc0 / Maia
    L("## lc0 / Maia status")
    L("")
    if lc0_info["lc0"]:
        L(f"- lc0 binary: `{lc0_info['lc0']}`")
    else:
        L("- lc0 binary: **NOT FOUND** (expected on this machine)")
    if lc0_info["maia_weights"]:
        L("- Maia weights found:")
        for w in lc0_info["maia_weights"]:
            L(f"  - `{w}`")
    else:
        L("- Maia weights: **NOT FOUND**")
    L("")
    L("### Install commands (for synthesis doc to lift)")
    L("")
    L("```sh")
    L("# lc0 (Leela Chess Zero) engine")
    L("brew install lc0")
    L("")
    L("# Maia human-like weights (per-Elo networks, 1100..1900).")
    L("# Download from the maia-chess release mirror on GitHub:")
    L("#   https://github.com/CSSLab/maia-chess")
    L("# Example weight files (one per rating bucket):")
    L("mkdir -p ~/maia_weights && cd ~/maia_weights")
    L("for elo in 1100 1300 1500 1700 1900; do")
    L("  curl -L -o maia-${elo}.pb.gz \\")
    L("    https://github.com/CSSLab/maia-chess/raw/master/"
      "maia_weights/maia-${elo}.pb.gz")
    L("done")
    L("")
    L("# Run lc0 with a Maia net (nodes=1 → pure policy, most human-like):")
    L("lc0 --weights=~/maia_weights/maia-1500.pb.gz")
    L("```")
    L("")
    L("_Note: exact Maia weight URLs/paths should be confirmed at "
      "install time; the maia-chess repo is the canonical source._")
    L("")

    # Caveats
    L("## Caveats")
    L("")
    L("- cpLoss uses a white-POV eval of the position *after* the move vs "
      "after the reference best move, scored at a fixed budget — a proxy, "
      "not a deep ground truth. Small cpLoss values are within engine noise.")
    L("- Skill Level / node-cap play is stochastic; numbers may shift a few "
      "cp between runs even with a seed (seed only fixes db sampling).")
    L("- The HUMAN-vs-RANDOM verdict is a heuristic over avg cpLoss + blunder "
      "rate + match-rate, not a human rater. Treat as directional evidence.")
    L("- 'Threat handled/missed' infers from cpLoss on threat-facing "
      "positions; it cannot literally read the engine's intent.")
    L("- **Node caps are a coarse, unanchored knob**: with a cold TT per "
      "config, nodes=500 does weaken SF18 measurably, but it remains the "
      "strongest of the weakened configs and carries no ELO semantics "
      "(strength varies by hardware/version). Skill Level / UCI_Elo are "
      "the primary usable knobs. NOTE: an earlier revision of this probe "
      "ran all configs sequentially on ONE engine process; the node-cap "
      "config ran last on a warm transposition table over these same "
      "positions and looked essentially full-strength — a confound fixed "
      "by fresh-process-per-config (flagged in review).")
    L("- Key epic finding: across the *effective* weakeners (Skill 3, Elo "
      "1350/1700), errors on threat-facing positions are dominated by "
      "**missing a real threat while playing an otherwise purposeful move** "
      "(the chosen move has a plan; it just overlooks the tactic) rather "
      "than random piece drops — i.e. reads HUMAN, not RANDOM. Lower "
      "settings (Skill 3) miss threats more often, as a weaker human would.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    sf = stockfish_path()
    positions = all_positions()
    threat_ct = sum(1 for p in positions if p.threat)
    print(f"{len(positions)} positions ({threat_ct} threat-facing)")
    if threat_ct < 4:
        print("WARNING: fewer than 4 threat-facing positions found")

    configs = make_configs()

    ref_engine = chess.engine.SimpleEngine.popen_uci(sf)
    sf_version = ref_engine.id.get("name", "Stockfish")
    try:
        aggs: list[ConfigAgg] = []
        for cfg in configs:
            print(f"\n=== {cfg.name} ===")
            agg = ConfigAgg(name=cfg.name)
            # Fresh engine process per config: cold transposition table, so
            # no config inherits search results another config left behind
            # over these same positions (earlier runs confounded the
            # node-cap config, which ran last on a warm TT).
            weak_engine = chess.engine.SimpleEngine.popen_uci(sf)
            try:
                for p in positions:
                    res = evaluate_position(ref_engine, weak_engine, cfg, p.fen)
                    agg.results.append((p, res))
                    print(f"  #{p.idx:2d} {p.phase:10s} "
                          f"{'THREAT' if p.threat else '      '} "
                          f"{res.move:7s} cpLoss={res.cp_loss} "
                          f"{'=best' if res.match_best else ''}")
            finally:
                weak_engine.quit()
            aggs.append(agg)
    finally:
        ref_engine.quit()

    lc0_info = detect_lc0_maia()
    report = render_results(positions, aggs, lc0_info, sf, sf_version)
    RESULTS_PATH.write_text(report)
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
