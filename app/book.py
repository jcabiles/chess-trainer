"""
book.py — opening "book" fast-path (pure, no engine, no network).

Builds a SET of known repertoire positions (EPDs) from the lichess opening lines
(scoped by ``data/book.json``) + the trap mainlines, and answers
``is_book_move()`` so ``/api/move`` can skip Stockfish on moves that stay in book.

A *move* is in book when the position it REACHES is a known repertoire position
(set membership) — naturally transposition-safe, and the deepest position on each
line is the natural depth limit (the next move falls through to the engine).

EPD identity is produced exclusively by ``chess.Board(...).epd()`` (python-chess).
This module imports neither the engine nor any network library, so the book path
works even when Stockfish is absent.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import chess

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class BookIndex:
    """Set of known repertoire EPDs (every position reached along an in-scope line)."""

    book_epds: set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not self.book_epds


# Module-level singleton — initialised empty so imports never raise and a missing
# config simply means "nothing is ever in book" (degrade to today's behavior).
_index: BookIndex = BookIndex()
_cache_sig = None  # signature of the inputs the current non-empty _index was built from


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _read_config(config_path: Optional[str]) -> dict:
    """Load the book.json config dict, or {} (disabled) on any problem."""
    if config_path is None:
        config_path = os.environ.get("BOOK_FILE", "data/book.json")
    path = Path(config_path)
    if not path.exists():
        logger.warning("book: config '%s' not found — book fast-path disabled", path)
        return {}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("book: cannot read/parse '%s': %s — disabled", path, exc)
        return {}
    if not isinstance(cfg, dict):
        logger.warning("book: '%s' is not a JSON object — disabled", path)
        return {}
    return cfg


def _epds_for_uci_line(uci_line: Iterable[str]) -> list[str]:
    """Replay a UCI move-list from the start; return the EPD after each ply.

    Returns ``[]`` if any move is illegal (the whole line is skipped — never raises).
    """
    board = chess.Board()
    epds: list[str] = []
    for uci in uci_line:
        try:
            board.push_uci(uci)
        except Exception:
            return []
        epds.append(board.epd())
    return epds


def _epds_for_san_movetext(movetext: str) -> list[str]:
    """Replay SAN movetext (move numbers like ``1.`` / ``2.`` tolerated) from the
    start; return the EPD after each ply. ``[]`` if any token is illegal."""
    board = chess.Board()
    epds: list[str] = []
    for tok in movetext.split():
        t = tok.rstrip(".")
        if not t or t.isdigit():  # move number ("1.", "12") or stray dots
            continue
        try:
            board.push_san(t)
        except Exception:
            return []
        epds.append(board.epd())
    return epds


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load(
    config_path: Optional[str] = None,
    lines: Iterable[Iterable[str]] = (),
    trap_ucis: Iterable[Iterable[str]] = (),
) -> BookIndex:
    """Build the module-level book index from the config + supplied lines.

    Args:
        config_path: Path to ``book.json``. Defaults to the ``BOOK_FILE`` env var,
            then ``data/book.json``.
        lines: All lichess opening lines as UCI move-lists (e.g.
            ``app.openings.iter_lines()``). Kept only when the first UCI is in the
            config's ``firstMoves``.
        trap_ucis: Trap mainlines as FULL UCI lines from the start (e.g.
            ``app.traps.iter_mainline_ucis()``). Included when ``includeTraps``.

    Returns:
        The populated (or empty) :class:`BookIndex`. Import-safe and graceful: a
        missing/invalid config yields an empty index (the fast-path simply never
        fires) without raising.
    """
    global _index, _cache_sig

    lines_list = [tuple(line) for line in lines]
    traps_list = [tuple(t) for t in trap_ucis]
    resolved_cfg = str(config_path if config_path is not None else os.environ.get("BOOK_FILE", "data/book.json"))
    sig = (resolved_cfg, len(lines_list), len(traps_list), hash(tuple(lines_list)), hash(tuple(traps_list)))
    if sig == _cache_sig and not _index.empty:
        return _index

    cfg = _read_config(config_path)
    if not cfg:
        _cache_sig = None
        _index = BookIndex()
        return _index

    first_moves = set(cfg.get("firstMoves", []))
    include_traps = cfg.get("includeTraps", True)
    extra_lines = cfg.get("extraLines", []) or []

    book_epds: set[str] = set()

    # 1. Lichess DB lines, scoped by first move.
    n_db = 0
    for uci_line in lines_list:
        if not uci_line:
            continue
        if first_moves and uci_line[0] not in first_moves:
            continue
        epds = _epds_for_uci_line(uci_line)
        if epds:
            book_epds.update(epds)
            n_db += 1

    # 2. Trap mainlines (already full from the start).
    n_trap = 0
    if include_traps:
        for uci_line in traps_list:
            epds = _epds_for_uci_line(uci_line)
            if epds:
                book_epds.update(epds)
                n_trap += 1

    # 3. Hand-added extra lines (SAN movetext); empty by default.
    n_extra = 0
    for entry in extra_lines:
        movetext = entry.get("moves", "") if isinstance(entry, dict) else ""
        if not movetext:
            continue
        epds = _epds_for_san_movetext(movetext)
        if epds:
            book_epds.update(epds)
            n_extra += 1

    _index = BookIndex(book_epds=book_epds)
    _cache_sig = sig
    logger.info(
        "book: %d positions (db lines=%d, trap lines=%d, extra=%d)",
        len(book_epds), n_db, n_trap, n_extra,
    )
    return _index


def init(
    config_path: Optional[str] = None,
    lines: Iterable[Iterable[str]] = (),
    trap_ucis: Iterable[Iterable[str]] = (),
) -> None:
    """Convenience wrapper — call load() at app startup."""
    load(config_path, lines, trap_ucis)


def is_book_move(fen: str, uci: str) -> bool:
    """Return True iff playing *uci* from *fen* reaches a known repertoire position.

    Pure and self-contained: returns False on a bad FEN, an unparseable/illegal
    move, or when the index is empty. Does not touch the engine.
    """
    if _index.empty:
        return False
    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
    except Exception:
        return False
    if not board.is_legal(move):
        return False
    board.push(move)
    return board.epd() in _index.book_epds
