"""
openings.py — opening name detection (pure, no engine, no network).

Loads the lichess-org/chess-openings TSVs at startup and exposes:
  - load(data_dir=None) -> OpeningsIndex
  - identify(base_fen, uci_moves) -> dict | None   (name + ECO of the current line)

EPD identity is produced exclusively by chess.Board(...).epd() (python-chess).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import chess

logger = logging.getLogger(__name__)

# The real data/ dir ships exactly these five files from lichess-org/chess-openings.
# load() scans all *.tsv in the directory so the test fixture also works.
_TSV_NAMES = ("a.tsv", "b.tsv", "c.tsv", "d.tsv", "e.tsv")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class OpeningsIndex:
    """Opening name data derived from the TSVs.

    Attributes:
        name_by_epd: epd -> (eco, name). Deepest line wins on collision.
        lines: UCI move-list of every parsed line, in load order. Retained so the
            opening-book fast-path (``app.book``) can build its position set without
            re-parsing the TSVs. Not used by name detection.
    """

    name_by_epd: dict[str, tuple[str, str]] = field(default_factory=dict)
    lines: list[list[str]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.name_by_epd


# Module-level singleton —initialised to an empty index so imports never raise.
_index: OpeningsIndex = OpeningsIndex()
_loaded_dir: Optional[str] = None  # resolved dir the current non-empty _index was built from


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _replay_uci(uci_str: str) -> tuple[list[str], list[str], str]:
    """Replay a space-separated UCI string from the starting position.

    Returns:
        (san_list, epd_list, initial_epd) where:
          - san_list and epd_list are parallel to the UCI moves (after each ply).
          - initial_epd is the EPD of the board BEFORE any moves.
        Only epd_list is used by load() (for name_by_epd); the others are kept
        for callers/tests that want them.

    Raises:
        ValueError if any move is illegal.
    """
    board = chess.Board()
    initial_epd = board.epd()
    moves = uci_str.split()
    san_list: list[str] = []
    epd_list: list[str] = []
    for uci in moves:
        move = chess.Move.from_uci(uci)
        san_list.append(board.san(move))
        board.push(move)
        epd_list.append(board.epd())
    return san_list, epd_list, initial_epd


def _parse_tsv(path: Path) -> list[dict]:
    """Parse one TSV file, skipping the header row.

    Handles both 3-column (eco, name, pgn) and 5-column (eco, name, pgn, uci, epd)
    formats. For 3-column, converts PGN notation to UCI.

    Returns a list of raw row dicts with keys: eco, name, pgn, uci, epd.
    Rows with parse errors are skipped with a warning.
    """
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("openings: cannot read %s: %s", path, exc)
        return rows

    lines = text.splitlines()
    if not lines:
        return rows

    # First line is the header — skip it.
    for lineno, line in enumerate(lines[1:], start=2):
        parts = line.split("\t")
        if len(parts) < 3:
            logger.debug("openings: %s line %d: too few columns, skipping", path.name, lineno)
            continue

        eco = parts[0]
        name = parts[1]
        pgn = parts[2]

        # If 5-column format, use uci + epd directly.
        if len(parts) >= 5:
            uci = parts[3].strip()
            epd = parts[4].strip()
            if not uci:
                continue
            rows.append({"eco": eco, "name": name, "pgn": pgn, "uci": uci, "epd": epd})
        else:
            # 3-column format (lichess): parse PGN to UCI.
            try:
                board = chess.Board()
                uci_moves: list[str] = []
                for part in pgn.strip().split():
                    # Skip move numbers (e.g. "1.", "2.")
                    if part[-1] in ".":
                        continue
                    # Parse SAN move and convert to UCI
                    move = board.push_san(part)
                    uci_moves.append(move.uci())
                if uci_moves:
                    uci = " ".join(uci_moves)
                    rows.append({"eco": eco, "name": name, "pgn": pgn, "uci": uci, "epd": None})
            except Exception as exc:
                logger.debug("openings: %s line %d (PGN '%s'): %s, skipping", path.name, lineno, pgn, exc)
                continue

    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load(data_dir: Optional[str] = None) -> OpeningsIndex:
    """Parse the 5 TSVs from *data_dir* and populate the module-level index.

    Args:
        data_dir: Path to the directory containing a.tsv … e.tsv.  Defaults to
            the ``OPENINGS_DATA_DIR`` environment variable, then ``data/openings/``
            relative to the project root.

    Returns:
        The populated (or empty) OpeningsIndex.

    This function is import-safe: if the directory is missing or empty, it
    logs one warning and returns an empty index without raising.
    """
    global _index, _loaded_dir

    if data_dir is None:
        data_dir = os.environ.get("OPENINGS_DATA_DIR", "data/openings")

    cache_key = str(Path(data_dir).resolve())
    if _loaded_dir == cache_key and not _index.empty:
        return _index

    dir_path = Path(data_dir)
    if not dir_path.is_dir():
        logger.warning(
            "openings: data directory '%s' not found — opening features disabled",
            dir_path,
        )
        _index = OpeningsIndex()
        _loaded_dir = None
        return _index

    # Collect rows from all TSVs in the directory, sorted for determinism.
    # In production only a.tsv … e.tsv exist; scanning all *.tsv also lets
    # unit tests point load() at a fixture directory with a differently-named file.
    tsv_files = sorted(dir_path.glob("*.tsv"))
    raw_rows: list[dict] = []
    for tsv_path in tsv_files:
        raw_rows.extend(_parse_tsv(tsv_path))

    if not raw_rows:
        logger.warning(
            "openings: no TSV data found in '%s' — opening features disabled",
            dir_path,
        )
        _index = OpeningsIndex()
        _loaded_dir = None
        return _index

    # Build name_by_epd: each EPD along every line maps to its opening name, with
    # the DEEPEST (most plies) line winning on collision so the name doesn't
    # flicker to a shallower opening on a shared early position.
    name_by_epd: dict[str, tuple[str, str]] = {}
    depth_by_epd: dict[str, int] = {}
    lines: list[list[str]] = []
    n_lines = 0

    for row in raw_rows:
        try:
            _san, epds, _initial_epd = _replay_uci(row["uci"])
        except Exception as exc:
            logger.debug("openings: skipping row '%s': %s", row["name"], exc)
            continue
        n_lines += 1
        lines.append(row["uci"].split())
        for depth, epd in enumerate(epds, start=1):
            if depth > depth_by_epd.get(epd, 0):
                depth_by_epd[epd] = depth
                name_by_epd[epd] = (row["eco"], row["name"])

    _index = OpeningsIndex(name_by_epd=name_by_epd, lines=lines)
    _loaded_dir = cache_key
    logger.info("openings: loaded %d lines from '%s'", n_lines, dir_path)
    return _index


def init(data_dir: Optional[str] = None) -> None:
    """Convenience wrapper — call load() at app startup."""
    load(data_dir)


def iter_lines() -> list[list[str]]:
    """Return the UCI move-list of every parsed line (in load order).

    Consumed by :mod:`app.book` to build its repertoire position set without
    re-parsing the TSVs. Returns an empty list if no data is loaded.
    """
    return _index.lines


def identify(base_fen: str, uci_moves: list[str]) -> Optional[dict]:
    """Return the deepest named opening on the played line, or None.

    The server replays *base_fen* + *uci_moves* itself and checks each
    intermediate EPD against ``name_by_epd``.  The deepest match wins so
    the name doesn't flicker to null on unnamed in-between positions.

    Args:
        base_fen:  Starting FEN (e.g. the standard starting position).
        uci_moves: List of UCI move strings, e.g. ["e2e4", "e7e5"].

    Returns:
        ``{"eco": ..., "name": ...}`` or ``None`` if no match found.
    """
    if _index.empty:
        return None

    try:
        board = chess.Board(base_fen)
    except Exception:
        return None

    best: Optional[dict] = None
    for uci in uci_moves:
        try:
            board.push_uci(uci)
        except Exception:
            break
        epd = board.epd()
        match = _index.name_by_epd.get(epd)
        if match is not None:
            best = {"eco": match[0], "name": match[1]}

    return best


def name_for_fen(fen: str) -> Optional[dict]:
    """Return ``{"eco", "name"}`` for the position in *fen*, or None.

    Looks up the position's EPD in ``name_by_epd`` (the same index ``identify``
    uses). Returns None on a bad FEN, an empty index, or an unnamed position.
    Used by the opening-book fast-path to label the "Book Move" badge with the
    line the player just entered (the resulting position's name).
    """
    if _index.empty:
        return None
    try:
        epd = chess.Board(fen).epd()
    except Exception:
        return None
    match = _index.name_by_epd.get(epd)
    if match is None:
        return None
    return {"eco": match[0], "name": match[1]}




