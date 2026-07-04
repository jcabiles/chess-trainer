"""
endgame.py — Pure endgame material-signature classifier + stable-suffix finder.

Supports the Insights "Endgames" sub-tab (``insights.py::build_endgame_insights``,
T3.2): bucketing a position's remaining (non-pawn, non-king) material into a
canonical signature, and finding the contiguous suffix of a game's plies that is
stably endgame-phase (per :func:`app.analysis.game_phase`).

Pure module — no engine, no I/O, no database. Importable and fully
unit-testable without a Stockfish binary present (python-chess is the only
non-stdlib dependency).

Signature precedence table (binding — see docs/ai-dlc/specs/insights-endgames.md)
----------------------------------------------------------------------------
Evaluate combined piece material of BOTH sides (kings and pawns aside); first
match wins:

1. No pieces at all -> ``pawn`` (pure king+pawn).
2. Any queen on board: queens are the only piece type -> ``queen``;
   queens + any other piece -> ``Q+piece``.
3. Any rook on board (no queens): rooks are the only piece type -> ``rook``
   if no side has two or more rooks, else ``two-rook``; rooks + minors
   (bishops/knights) -> ``R+minor`` (covers asymmetric rook-vs-minor too).
4. Minors only (no queens, no rooks): exactly one bishop each side and no
   knights -> ``same-bishops`` / ``opposite-bishops`` (bishop square color
   via ``(rank + file) % 2``); knights only (no bishops) -> ``knight``; any
   other minor-only mix (bishop vs knight, two minors a side, …) -> ``minor``.
5. Anything else -> ``mixed`` (defensive fallback; unreachable given 1-4 are
   exhaustive over {queens, rooks, minors} presence — asserted in tests, not
   in this function).

``game_phase`` admits queen-on-board positions below its ``< 24`` threshold
(e.g. Q+R vs Q is 9+5+9 = 23), which is why ``queen``/``Q+piece`` exist as
reachable buckets, not dead branches.

Stable endgame suffix (design decision 1)
------------------------------------------
``game_phase`` is a function of remaining non-pawn material only, and pawn
promotion *adds* material — so phase is NOT monotone over a game: a position
can dip into "endgame" and then revert to "middlegame" when a pawn queens.
Taking the *first* endgame-phase ply would latch onto such a transient dip
and misreport the endgame slice (and, worse, feed a non-contiguous subset
into :func:`app.accuracy.summarize`, which pairs plies positionally and would
silently fabricate accuracy across the gap).

:func:`endgame_start_index` instead returns the index **after the last ply
that is NOT endgame phase** — i.e. the start of the longest suffix that is
entirely endgame-phase, excluding-by-construction any earlier dip that later
reverts. A ply whose ``fen_before`` is missing or unparseable cannot *prove*
endgame phase, so it is conservatively treated as non-endgame (it breaks /
pushes back the suffix, same as a genuine middlegame ply).

POV / purity notes
-------------------
Both functions here are pure and POV-agnostic: ``endgame_signature`` only
counts material by piece type (color is used only to detect asymmetric rook
counts and to compare bishop square colors), and ``endgame_start_index`` only
reads the ``fen_before`` field of each ply row — no eval sign-flip concerns.
"""

from __future__ import annotations

from typing import Any

import chess

from app.analysis import game_phase

# Canonical bucket order (exported; main.py imports this for the API's empty
# empty-shape fallback so bucket names are never re-hardcoded — see
# docs/ai-dlc/contracts/insights-endgames.md risk #3).
SIGNATURES: tuple[str, ...] = (
    "pawn",
    "queen",
    "Q+piece",
    "rook",
    "two-rook",
    "R+minor",
    "same-bishops",
    "opposite-bishops",
    "knight",
    "minor",
    "mixed",
)


def endgame_signature(board: chess.Board) -> str:
    """Classify a position's remaining material into a canonical bucket.

    See the module docstring's "Signature precedence table" for the full,
    binding rule set. Kings and pawns are ignored; only queens, rooks,
    bishops, and knights (both sides combined) drive the classification.

    Args:
        board: A ``chess.Board`` representing the position to classify.

    Returns:
        One of the strings in :data:`SIGNATURES`.
    """
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(
        board.pieces(chess.QUEEN, chess.BLACK)
    )
    rooks_white = len(board.pieces(chess.ROOK, chess.WHITE))
    rooks_black = len(board.pieces(chess.ROOK, chess.BLACK))
    rooks = rooks_white + rooks_black
    bishops_white = board.pieces(chess.BISHOP, chess.WHITE)
    bishops_black = board.pieces(chess.BISHOP, chess.BLACK)
    bishops = len(bishops_white) + len(bishops_black)
    knights = len(board.pieces(chess.KNIGHT, chess.WHITE)) + len(
        board.pieces(chess.KNIGHT, chess.BLACK)
    )
    minors = bishops + knights

    if queens == 0 and rooks == 0 and minors == 0:
        return "pawn"

    if queens > 0:
        if rooks == 0 and minors == 0:
            return "queen"
        return "Q+piece"

    if rooks > 0:
        if minors == 0:
            if rooks_white >= 2 or rooks_black >= 2:
                return "two-rook"
            return "rook"
        return "R+minor"

    if minors > 0:
        if knights == 0 and len(bishops_white) == 1 and len(bishops_black) == 1:
            sq_white = next(iter(bishops_white))
            sq_black = next(iter(bishops_black))
            color_white = (chess.square_rank(sq_white) + chess.square_file(sq_white)) % 2
            color_black = (chess.square_rank(sq_black) + chess.square_file(sq_black)) % 2
            return "same-bishops" if color_white == color_black else "opposite-bishops"
        if bishops == 0:
            return "knight"
        return "minor"

    # Defensive fallback: unreachable, since the branches above exhaust every
    # combination of {queens, rooks, minors} presence. Kept for safety only;
    # exhaustiveness is asserted in tests, not enforced here.
    return "mixed"


def _fen_of(row: Any) -> Any:
    """Return ``row["fen_before"]`` (dict) or ``row.fen_before`` (object).

    Mirrors the dict-first accessor pattern in ``accuracy.py::_field``
    (reimplemented locally since that helper is private to its module).
    """
    try:
        return row["fen_before"]
    except (TypeError, KeyError):
        return getattr(row, "fen_before", None)


def endgame_start_index(plies: list[Any]) -> int | None:
    """Index of the start of the stable endgame suffix, or ``None``.

    Returns the index *after* the last ply whose ``fen_before`` is NOT
    endgame phase — i.e. every ply from the returned index onward
    classifies as endgame (a genuinely contiguous suffix, safe to slice
    directly into :func:`app.accuracy.summarize`). See the module docstring
    for why this is NOT simply "the first endgame-phase ply" (promotion can
    make phase dip into endgame and then revert).

    A ply whose ``fen_before`` is ``None``/missing/unparseable cannot prove
    endgame phase, so it is treated like a non-endgame ply: it breaks (pushes
    back) the suffix. ``chess.Board`` is never allowed to raise out of this
    function.

    Args:
        plies: Ordered ply rows (dicts or attribute-style objects), each
            exposing a ``fen_before`` field.

    Returns:
        The suffix start index, or ``None`` if ``plies`` is empty, no ply
        classifies as endgame, or the final classifiable ply isn't endgame
        (the suffix would be empty).
    """
    if not plies:
        return None

    last_non_endgame = -1
    any_endgame = False
    for i, row in enumerate(plies):
        fen = _fen_of(row)
        is_endgame = False
        if fen:
            try:
                is_endgame = game_phase(chess.Board(fen)) == "endgame"
            except ValueError:
                is_endgame = False
        if is_endgame:
            any_endgame = True
        else:
            last_non_endgame = i

    if not any_endgame:
        return None

    k = last_non_endgame + 1
    if k >= len(plies):
        # The final ply is non-endgame (or unclassifiable) -> no stable
        # suffix reaches the end of the game.
        return None
    return k
