"""Tests for app/maia_engine.py — the lc0/Maia wrapper (Maia skeleton T2).

Three tiers:
* Pure parser tests on captured VerboseMoveStats fixture text (engine-free).
* Failure-envelope + watchdog concurrency tests against a fake engine
  (engine-free — the suite must stay green with no lc0 binary).
* Live-lc0 tests behind skipif (spawn, legality, argmax==bestmove) using the
  CPU backend (Metal init is blocked in sandboxed runs).
"""

from __future__ import annotations

import asyncio

import chess
import pytest

from app import maia_engine
from app.maia_engine import (
    MAIA_NETS,
    MaiaEngine,
    MaiaUnavailable,
    maia_ready_for,
    parse_movestats,
)

# Captured from lc0 0.32.1 + maia-1400.pb.gz, go nodes 1, VerboseMoveStats
# (2026-07-18). Ordering in the stream is ascending prior; parse_movestats
# must re-sort descending and skip the trailing "node" summary line.
FIXTURE_LINES = [
    "b1a3  (34  ) N:       0 (+ 0) (P:  0.01%) (WL:  -.-----) (D: -.---) (M:  -.-) (Q:  0.03785) (U: 0.00015) (S:  0.03800) (V:  -.----) ",
    "f2f3  (346 ) N:       0 (+ 0) (P:  0.06%) (WL:  -.-----) (D: -.---) (M:  -.-) (Q:  0.03785) (U: 0.00105) (S:  0.03890) (V:  -.----) ",
    "d2d4  (293 ) N:       0 (+ 0) (P: 22.31%) (WL:  -.-----) (D: -.---) (M:  -.-) (Q:  0.03785) (U: 0.37992) (S:  0.41777) (V:  -.----) ",
    "e2e4  (322 ) N:       0 (+ 0) (P: 65.53%) (WL:  -.-----) (D: -.---) (M:  -.-) (Q:  0.03785) (U: 1.11600) (S:  1.15385) (V:  -.----) ",
    "node  (  20) N: 1 (+ 0) (P: 0.00%) (WL: 0.03595) (D: 0.331) (M: 24.9) (Q: 0.03595) (V: 0.0359) ",
]


# ---------------------------------------------------------------------------
# parse_movestats (pure)
# ---------------------------------------------------------------------------


def test_parse_movestats_extracts_and_sorts_desc():
    priors = parse_movestats(FIXTURE_LINES)
    assert [d["uci"] for d in priors] == ["e2e4", "d2d4", "f2f3", "b1a3"]
    assert priors[0]["p"] == pytest.approx(0.6553)
    assert priors[-1]["p"] == pytest.approx(0.0001)


def test_parse_movestats_skips_summary_and_garbage():
    priors = parse_movestats(
        ["node  (  20) N: 1 (+ 0) (P: 0.00%) ...", "not a movestat line", ""]
    )
    assert priors == []


def test_parse_movestats_promotion_move():
    line = "e7e8q (999 ) N:       0 (+ 0) (P: 41.00%) (WL:  -.-----) "
    assert parse_movestats([line]) == [{"uci": "e7e8q", "p": pytest.approx(0.41)}]


def test_parse_movestats_empty():
    assert parse_movestats([]) == []


# ---------------------------------------------------------------------------
# Readiness (pure detection — never launches anything)
# ---------------------------------------------------------------------------


def test_maia_ready_for_unmapped_persona_false():
    assert maia_ready_for("no-such-persona") is False


def test_maia_ready_for_missing_net_false(monkeypatch, tmp_path):
    monkeypatch.setenv("MAIA_WEIGHTS_DIR", str(tmp_path))  # empty dir
    assert maia_ready_for("casey") is False


def test_maia_ready_for_requires_the_mapped_net_not_any(monkeypatch, tmp_path):
    # A different net alone must NOT make casey ready (spec review finding).
    (tmp_path / "maia-1500.pb.gz").write_bytes(b"x")
    monkeypatch.setenv("MAIA_WEIGHTS_DIR", str(tmp_path))
    monkeypatch.setattr(maia_engine.shutil, "which", lambda _: "/usr/bin/lc0")
    assert maia_ready_for("casey") is False
    (tmp_path / MAIA_NETS["casey"]).write_bytes(b"x")
    assert maia_ready_for("casey") is True


def test_maia_ready_for_no_lc0_false(monkeypatch, tmp_path):
    (tmp_path / MAIA_NETS["casey"]).write_bytes(b"x")
    monkeypatch.setenv("MAIA_WEIGHTS_DIR", str(tmp_path))
    monkeypatch.setattr(maia_engine.shutil, "which", lambda _: None)
    assert maia_ready_for("casey") is False


# ---------------------------------------------------------------------------
# Failure envelope (engine-free)
# ---------------------------------------------------------------------------


def test_import_and_construct_never_launch():
    e = MaiaEngine()
    assert e.is_running is False


def test_top_move_invalid_fen_raises_valueerror():
    e = MaiaEngine()
    with pytest.raises(ValueError):
        asyncio.run(e.top_move("not a fen", "casey"))


def test_top_move_unmapped_persona_raises_maia_unavailable():
    e = MaiaEngine()
    with pytest.raises(MaiaUnavailable):
        asyncio.run(e.top_move(chess.STARTING_FEN, "no-such-persona"))


def test_top_move_missing_net_raises_maia_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("MAIA_WEIGHTS_DIR", str(tmp_path))
    e = MaiaEngine()
    with pytest.raises(MaiaUnavailable):
        asyncio.run(e.top_move(chess.STARTING_FEN, "casey"))
    assert e.is_running is False


def test_top_move_missing_binary_raises_maia_unavailable(monkeypatch, tmp_path):
    (tmp_path / MAIA_NETS["casey"]).write_bytes(b"x")
    monkeypatch.setenv("MAIA_WEIGHTS_DIR", str(tmp_path))
    monkeypatch.setattr(maia_engine.shutil, "which", lambda _: None)
    e = MaiaEngine()
    with pytest.raises(MaiaUnavailable):
        asyncio.run(e.top_move(chess.STARTING_FEN, "casey"))


class _HangingEngine:
    """Fake SimpleEngine whose analysis blocks past the watchdog."""

    def __init__(self, delay: float):
        self._delay = delay

    def analysis(self, board, limit):
        import time

        fake = self

        class _Ctx:
            def __enter__(self_inner):
                time.sleep(fake._delay)
                raise RuntimeError("should have timed out first")

            def __exit__(self_inner, *a):
                return False

        return _Ctx()

    def close(self):
        pass

    def quit(self):
        pass


def _prepared_engine(monkeypatch, tmp_path, fake) -> MaiaEngine:
    """A MaiaEngine whose _start injects *fake* instead of spawning lc0."""
    (tmp_path / MAIA_NETS["casey"]).write_bytes(b"x")
    monkeypatch.setenv("MAIA_WEIGHTS_DIR", str(tmp_path))
    e = MaiaEngine()

    def fake_start(net_path):
        e._engine = fake
        e._pid = None
        e._net_path = net_path

    monkeypatch.setattr(e, "_start", fake_start)
    return e


def test_timeout_rewrapped_as_maia_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(maia_engine, "MAIA_HARD_TIMEOUT_S", 0.05)
    e = _prepared_engine(monkeypatch, tmp_path, _HangingEngine(delay=0.5))
    with pytest.raises(MaiaUnavailable):
        asyncio.run(e.top_move(chess.STARTING_FEN, "casey"))
    # Watchdog poisoned this generation.
    assert e.is_running is False


def test_illegal_bestmove_rewrapped(monkeypatch, tmp_path):
    class _IllegalEngine:
        def analysis(self, board, limit):
            class _Ctx:
                def __enter__(self_inner):
                    class _An:
                        def __iter__(self):
                            return iter([])

                        def wait(self):
                            class _BM:
                                move = chess.Move.from_uci("a1a8")  # illegal

                            return _BM()

                    return _An()

                def __exit__(self_inner, *a):
                    return False

            return _Ctx()

        def close(self):
            pass

        def quit(self):
            pass

    e = _prepared_engine(monkeypatch, tmp_path, _IllegalEngine())
    with pytest.raises(MaiaUnavailable):
        asyncio.run(e.top_move(chess.STARTING_FEN, "casey"))


def test_generation_bound_poison_spares_newer_generation(monkeypatch, tmp_path):
    """A stale generation's poison must not null a newer respawn."""
    e = MaiaEngine()
    old = _HangingEngine(delay=0)
    new = _HangingEngine(delay=0)
    e._engine = new
    e._pid = None
    e._net_path = tmp_path / "x.pb.gz"
    # Poisoning the OLD generation leaves the NEW one installed.
    e._poison(old, None)
    assert e._engine is new
    # Poisoning the CURRENT generation clears it.
    e._poison(new, None)
    assert e._engine is None


def test_close_idempotent_without_start():
    e = MaiaEngine()
    asyncio.run(e.close())
    asyncio.run(e.close())
    assert e.is_running is False


# ---------------------------------------------------------------------------
# Live lc0 tests (skipped when lc0/net absent). CPU backend: sandboxed runs
# cannot init Metal.
# ---------------------------------------------------------------------------

_live = pytest.mark.skipif(
    not maia_ready_for("casey"), reason="lc0 + maia-1400 not installed"
)


@_live
def test_live_top_move_legal_and_argmax(monkeypatch):
    monkeypatch.setenv("MAIA_BACKEND", "eigen")
    e = MaiaEngine()

    async def run():
        r1 = await e.top_move(chess.STARTING_FEN, "casey")
        r2 = await e.top_move(chess.STARTING_FEN, "casey")
        await e.close()
        return r1, r2

    r1, r2 = asyncio.run(run())
    board = chess.Board()
    assert chess.Move.from_uci(r1["uci"]) in board.legal_moves
    # Determinism within a pinned instance/run.
    assert r1["uci"] == r2["uci"]
    # Priors cover legal moves; bestmove == max prior of the SAME run
    # (no cross-backend golden move — spec review finding).
    assert len(r1["priors"]) == board.legal_moves.count()
    assert r1["priors"][0]["uci"] == r1["uci"]
    assert 0.0 < r1["priors"][0]["p"] <= 1.0
