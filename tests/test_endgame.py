"""Pure unit tests for app.endgame — no Stockfish, no storage, no FastAPI."""

from __future__ import annotations

from types import SimpleNamespace

import chess
import pytest

from app.endgame import SIGNATURES, endgame_signature, endgame_start_index

# ---------------------------------------------------------------------------
# Signature FEN table (contract: docs/ai-dlc/specs/insights-endgames.md
# "Signature precedence table"). One FEN per bucket, kings placed on e1/e8
# with the piece(s) under test elsewhere so the position parses cleanly.
# ---------------------------------------------------------------------------

FEN_TABLE: dict[str, str] = {
    # King + pawn only -> pawn.
    "pawn": "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1",
    # Queen vs queen, nothing else -> queen.
    "queen": "3qk3/8/8/8/8/8/8/3QK3 w - - 0 1",
    # Q+R vs Q: any queen present + another piece type anywhere -> Q+piece.
    "Q+piece (Q+R vs Q)": "3qk3/8/8/8/8/8/8/3QKR2 w - - 0 1",
    # Rook vs rook, one each side, no minors -> rook.
    "rook (R vs R)": "3rk3/8/8/8/8/8/8/3RK3 w - - 0 1",
    # Two rooks one side vs one rook the other -> two-rook.
    "two-rook (2R vs R)": "3rk3/8/8/8/8/8/8/R3K2R w - - 0 1",
    # Rook + bishop vs rook: rooks present + a minor anywhere -> R+minor.
    "R+minor (R+B vs R)": "3rk3/8/8/8/8/8/8/2B1KR2 w - - 0 1",
    # Rook vs bishop (asymmetric, no rook on black's side) -> still R+minor
    # per the precedence table ("covers asymmetric R vs minor too").
    "R+minor (R vs B)": "3bk3/8/8/8/8/8/8/3RK3 w - - 0 1",
    # Exactly one bishop each side, SAME square color (c1 and f8 are both
    # (rank+file) % 2 == 0) -> same-bishops.
    "same-bishops (Bc1 vs Bf8)": "4kb2/8/8/8/8/8/8/2B1K3 w - - 0 1",
    # Exactly one bishop each side, OPPOSITE square color (c1 is
    # (rank+file) % 2 == 0, c8 is == 1) -> opposite-bishops.
    "opposite-bishops (Bc1 vs Bc8)": "2b1k3/8/8/8/8/8/8/2B1K3 w - - 0 1",
    # Knight vs knight, no bishops -> knight.
    "knight (N vs N)": "3nk3/8/8/8/8/8/8/3NK3 w - - 0 1",
    # Bishop vs knight (mixed minor types) -> minor.
    "minor (B vs N)": "3bk3/8/8/8/8/8/8/3NK3 w - - 0 1",
    # Two minors one side (N+B) vs one minor (N) the other -> minor.
    "minor (N+B vs N)": "3nk3/8/8/8/8/8/8/3NKB2 w - - 0 1",
}

# Expected bucket per FEN_TABLE key, in the same order.
EXPECTED_SIGNATURES: dict[str, str] = {
    "pawn": "pawn",
    "queen": "queen",
    "Q+piece (Q+R vs Q)": "Q+piece",
    "rook (R vs R)": "rook",
    "two-rook (2R vs R)": "two-rook",
    "R+minor (R+B vs R)": "R+minor",
    "R+minor (R vs B)": "R+minor",
    "same-bishops (Bc1 vs Bf8)": "same-bishops",
    "opposite-bishops (Bc1 vs Bc8)": "opposite-bishops",
    "knight (N vs N)": "knight",
    "minor (B vs N)": "minor",
    "minor (N+B vs N)": "minor",
}


@pytest.mark.parametrize("name", list(FEN_TABLE))
def test_endgame_signature_fen_table(name: str) -> None:
    board = chess.Board(FEN_TABLE[name])
    assert endgame_signature(board) == EXPECTED_SIGNATURES[name]


def test_endgame_signature_bishop_square_colors_are_correct() -> None:
    """Sanity-check the same/opposite bishop fixtures' square colors directly."""

    def color(square_name: str) -> int:
        sq = chess.parse_square(square_name)
        return (chess.square_rank(sq) + chess.square_file(sq)) % 2

    assert color("c1") == color("f8")  # same-bishops fixture
    assert color("c1") != color("c8")  # opposite-bishops fixture


def test_endgame_signature_exhaustive_all_buckets_in_signatures() -> None:
    for name, fen in FEN_TABLE.items():
        result = endgame_signature(chess.Board(fen))
        assert result in SIGNATURES
        assert result != "mixed", f"{name} unexpectedly hit the 'mixed' fallback"


# ---------------------------------------------------------------------------
# endgame_start_index — stable endgame suffix.
#
# game_phase weights: N/B=3, R=5, Q=9 (pawns excluded); >=56 opening,
# >=24 middlegame, <24 endgame (app/analysis.py:game_phase).
# ---------------------------------------------------------------------------

# Standard starting position: material = 2*(2*3+2*3+2*5+9) = 78 -> opening
# (non-endgame).
STARTING_FEN = chess.STARTING_FEN

# Rook vs rook + kings: material = 5 + 5 = 10 -> endgame.
ROOK_ENDGAME_FEN = "3rk3/8/8/8/8/8/8/3RK3 w - - 0 1"

# Q+R vs Q+R + kings: material = (9+5) + (9+5) = 28 -> middlegame
# (non-endgame). Used to simulate a pawn promotion pushing material back up
# above the endgame threshold (the function only reads fen_before per row,
# so a legal move sequence isn't required to model the reversion).
HEAVY_MIDDLEGAME_FEN = "3qkr2/8/8/8/8/8/8/3QKR2 w - - 0 1"


def test_endgame_start_index_simple_descent() -> None:
    plies = [
        {"fen_before": STARTING_FEN},  # middlegame/opening (non-endgame)
        {"fen_before": ROOK_ENDGAME_FEN},  # endgame
    ]
    assert endgame_start_index(plies) == 1


def test_endgame_start_index_promotion_reversion_regression() -> None:
    """Refuter-blocker regression: phase dips into endgame, then a promoted
    queen pushes material back above the endgame threshold (reverting to
    middlegame), before descending into endgame again. The suffix must start
    at the LAST descent, not the first (transient) dip.
    """
    plies = [
        {"fen_before": HEAVY_MIDDLEGAME_FEN},  # 0: non-endgame
        {"fen_before": ROOK_ENDGAME_FEN},  # 1: endgame (transient dip)
        {"fen_before": HEAVY_MIDDLEGAME_FEN},  # 2: non-endgame (reversion)
        {"fen_before": ROOK_ENDGAME_FEN},  # 3: endgame (stable descent)
    ]
    assert endgame_start_index(plies) == 3


def test_endgame_start_index_never_reaches_endgame_returns_none() -> None:
    plies = [
        {"fen_before": ROOK_ENDGAME_FEN},  # endgame
        {"fen_before": STARTING_FEN},  # ends in non-endgame
    ]
    assert endgame_start_index(plies) is None


def test_endgame_start_index_empty_list_returns_none() -> None:
    assert endgame_start_index([]) is None


def test_endgame_start_index_bad_fen_mid_descent_breaks_suffix() -> None:
    plies = [
        {"fen_before": HEAVY_MIDDLEGAME_FEN},  # 0: non-endgame
        {"fen_before": ROOK_ENDGAME_FEN},  # 1: endgame
        {"fen_before": "not-a-valid-fen"},  # 2: unclassifiable -> non-endgame
        {"fen_before": ROOK_ENDGAME_FEN},  # 3: endgame
    ]
    assert endgame_start_index(plies) == 3


def test_endgame_start_index_none_fen_breaks_suffix() -> None:
    plies = [
        {"fen_before": HEAVY_MIDDLEGAME_FEN},  # 0: non-endgame
        {"fen_before": ROOK_ENDGAME_FEN},  # 1: endgame
        {"fen_before": None},  # 2: missing -> non-endgame
        {"fen_before": ROOK_ENDGAME_FEN},  # 3: endgame
    ]
    assert endgame_start_index(plies) == 3


def test_endgame_start_index_missing_key_treated_as_non_endgame() -> None:
    plies = [
        {"fen_before": ROOK_ENDGAME_FEN},  # 0: endgame
        {},  # 1: missing key entirely -> non-endgame
        {"fen_before": ROOK_ENDGAME_FEN},  # 2: endgame
    ]
    assert endgame_start_index(plies) == 2


def test_endgame_start_index_accepts_attribute_style_rows() -> None:
    plies = [
        SimpleNamespace(fen_before=STARTING_FEN),
        SimpleNamespace(fen_before=ROOK_ENDGAME_FEN),
    ]
    assert endgame_start_index(plies) == 1
