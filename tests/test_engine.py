"""Unit tests for StockfishEngine — no real Stockfish binary required.

Each test injects a fake ``SimpleEngine``-shaped object directly into
``eng._engine`` and sets ``eng._pid = None`` so ``_poison()`` skips ``os.kill``
(never pass a real or None pid to os.kill).

Coverage:
- Cancellation safety: task.cancel() → CancelledError; engine poisoned (_engine None).
- Hard-timeout watchdog: ENGINE_HARD_TIMEOUT_S fires → EngineUnavailable; engine poisoned.
- EngineError propagation: analyse raises chess.engine.EngineError → EngineUnavailable; poisoned.
- Speed presets: analyze()/analyze_interactive_multi() build Limits from
  SPEED_PRESETS (nodes+time, no depth); unknown speed falls back to balanced;
  analyze_multi() stays depth-only.
- Threads autodetect: _detect_threads() survives os.cpu_count() returning None.
- restart() idempotence: poisons regardless of state; safe to call twice.
"""

from __future__ import annotations

import threading
import time
from typing import List

import chess
import chess.engine as chess_engine
import pytest

import app.engine as engine_module
from app.engine import (
    SPEED_PRESETS,
    EngineUnavailable,
    StockfishEngine,
)

START_FEN = chess.STARTING_FEN


# ---------------------------------------------------------------------------
# Helpers: minimal InfoDict + fake SimpleEngine shapes
# ---------------------------------------------------------------------------

def _make_info(cp: int = 20) -> chess_engine.InfoDict:
    """Return a minimal InfoDict with a White-POV centipawn score."""
    info: chess_engine.InfoDict = {}  # type: ignore[assignment]
    info["score"] = chess_engine.PovScore(chess_engine.Cp(cp), chess.WHITE)
    board = chess.Board(START_FEN)
    pv = list(board.legal_moves)[:1]
    info["pv"] = pv
    info["depth"] = 1
    return info


class _ImmediateEngine:
    """Fake SimpleEngine whose analyse() returns immediately with a valid InfoDict."""

    def __init__(self, cp: int = 20):
        self._cp = cp
        self._calls: List[chess_engine.Limit] = []
        self._multipvs: List[int] = []

    def analyse(
        self,
        board: chess.Board,
        limit: chess_engine.Limit,
        *,
        multipv: int = 1,
    ) -> chess_engine.InfoDict:
        self._calls.append(limit)
        self._multipvs.append(multipv)
        return _make_info(self._cp)

    def close(self) -> None:
        pass


class _BlockingEngine:
    """Fake SimpleEngine whose analyse() blocks on a threading.Event indefinitely."""

    def __init__(self) -> None:
        self._unblock = threading.Event()

    def analyse(
        self,
        board: chess.Board,
        limit: chess_engine.Limit,
        *,
        multipv: int = 1,
    ) -> chess_engine.InfoDict:
        # Block until unblocked (set by teardown) so the worker thread can exit.
        self._unblock.wait()
        return _make_info()

    def close(self) -> None:
        self._unblock.set()


class _SlowEngine:
    """Fake SimpleEngine that sleeps longer than the hard timeout, then returns."""

    def __init__(self, sleep_s: float = 0.5) -> None:
        self._sleep_s = sleep_s

    def analyse(
        self,
        board: chess.Board,
        limit: chess_engine.Limit,
        *,
        multipv: int = 1,
    ) -> chess_engine.InfoDict:
        time.sleep(self._sleep_s)
        return _make_info()

    def close(self) -> None:
        pass


class _ErrorEngine:
    """Fake SimpleEngine whose analyse() raises chess.engine.EngineError."""

    def analyse(
        self,
        board: chess.Board,
        limit: chess_engine.Limit,
        *,
        multipv: int = 1,
    ) -> chess_engine.InfoDict:
        raise chess_engine.EngineError("simulated engine error")

    def close(self) -> None:
        pass


def _inject(eng: StockfishEngine, fake_engine: object) -> None:
    """Inject fake_engine into eng, bypassing start(). Set _pid=None so _poison skips os.kill."""
    eng._engine = fake_engine  # type: ignore[assignment]
    eng._pid = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCancellationSafety:
    """Task cancellation poisons the engine and re-raises CancelledError."""

    @pytest.mark.anyio
    async def test_cancel_raises_cancelled_error_and_poisons(self):
        import asyncio

        eng = StockfishEngine()
        fake = _BlockingEngine()
        _inject(eng, fake)

        task = asyncio.create_task(eng.analyze(START_FEN))

        # Yield to the event loop briefly so the task enters _run_analyse and
        # acquires the lock, then cancel it.
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        # Engine must be poisoned: handle nulled, is_running False.
        assert eng._engine is None
        assert eng.is_running is False

        # Unblock the worker thread so it can exit cleanly (no thread leak).
        fake._unblock.set()


class TestHardTimeoutWatchdog:
    """When the executor thread exceeds ENGINE_HARD_TIMEOUT_S, raise EngineUnavailable."""

    @pytest.mark.anyio
    async def test_timeout_raises_engine_unavailable_and_poisons(self, monkeypatch):
        # Patch the module-level constant to a tiny value so the test is fast.
        monkeypatch.setattr(engine_module, "ENGINE_HARD_TIMEOUT_S", 0.1)

        eng = StockfishEngine()
        fake = _SlowEngine(sleep_s=0.5)  # slower than the patched hard timeout
        _inject(eng, fake)

        with pytest.raises(EngineUnavailable, match="timed out"):
            await eng.analyze(START_FEN)

        # Engine must be poisoned after the timeout.
        assert eng._engine is None
        assert eng.is_running is False


class TestEngineErrorPropagation:
    """chess.engine.EngineError → EngineUnavailable; engine poisoned."""

    @pytest.mark.anyio
    async def test_engine_error_raises_unavailable_and_poisons(self):
        eng = StockfishEngine()
        fake = _ErrorEngine()
        _inject(eng, fake)

        with pytest.raises(EngineUnavailable, match="analysis failed"):
            await eng.analyze(START_FEN)

        assert eng._engine is None
        assert eng.is_running is False


class TestSpeedPresetLimits:
    """Interactive calls build node-budget Limits from SPEED_PRESETS (no depth);
    analyze_multi() stays depth-only for background reviews."""

    @pytest.mark.anyio
    async def test_analyze_defaults_to_balanced_preset(self):
        eng = StockfishEngine()
        fake = _ImmediateEngine()
        _inject(eng, fake)

        await eng.analyze(START_FEN)

        assert len(fake._calls) == 1
        limit = fake._calls[0]
        assert limit.nodes == 800_000
        assert limit.time == 0.8
        assert limit.depth is None, "interactive limits must not carry a depth"

    @pytest.mark.anyio
    async def test_analyze_fast_preset(self):
        eng = StockfishEngine()
        fake = _ImmediateEngine()
        _inject(eng, fake)

        await eng.analyze(START_FEN, speed="fast")

        limit = fake._calls[0]
        assert limit.nodes == 400_000
        assert limit.time == 0.5
        assert limit.depth is None

    @pytest.mark.anyio
    async def test_interactive_multi_deep_preset_and_multipv_passthrough(self):
        eng = StockfishEngine()
        fake = _ImmediateEngine()
        _inject(eng, fake)

        await eng.analyze_interactive_multi(START_FEN, speed="deep", multipv=2)

        limit = fake._calls[0]
        assert limit.nodes == 12_000_000
        assert limit.time == 1.4
        assert limit.depth is None
        assert fake._multipvs == [2], "multipv must pass through unchanged"

    @pytest.mark.anyio
    async def test_unknown_speed_falls_back_to_balanced(self):
        eng = StockfishEngine()
        fake = _ImmediateEngine()
        _inject(eng, fake)

        await eng.analyze_interactive_multi(START_FEN, speed="warp9")

        limit = fake._calls[0]
        assert limit.nodes == SPEED_PRESETS["balanced"].nodes
        assert limit.time == SPEED_PRESETS["balanced"].time

    @pytest.mark.anyio
    async def test_analyze_multi_stays_depth_only(self):
        eng = StockfishEngine()
        fake = _ImmediateEngine()
        _inject(eng, fake)

        await eng.analyze_multi(START_FEN)

        assert len(fake._calls) == 1
        limit = fake._calls[0]
        # Background review path: depth-only limit — no time or node cap.
        assert limit.depth == engine_module.DEFAULT_DEPTH
        assert limit.time is None
        assert limit.nodes is None


class TestThreadsAutodetect:
    """_detect_threads() honors the env override and survives cpu_count() → None."""

    def test_cpu_count_none_yields_at_least_one_thread(self, monkeypatch):
        monkeypatch.delenv("ENGINE_THREADS", raising=False)
        monkeypatch.setattr(engine_module.os, "cpu_count", lambda: None)

        threads = engine_module._detect_threads()

        assert threads >= 1

    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("ENGINE_THREADS", "6")

        assert engine_module._detect_threads() == 6


class TestRestartIdempotence:
    """restart() poisons the engine handle; safe to call multiple times."""

    @pytest.mark.anyio
    async def test_restart_with_running_engine_poisons(self):
        eng = StockfishEngine()
        fake = _ImmediateEngine()
        _inject(eng, fake)

        assert eng.is_running is True

        await eng.restart()

        assert eng._engine is None
        assert eng.is_running is False

    @pytest.mark.anyio
    async def test_restart_when_already_stopped_is_safe(self):
        """Calling restart() on a never-started / already-poisoned engine is a no-op."""
        eng = StockfishEngine()
        # _engine is None from construction — _poison(None) should be a no-op.

        await eng.restart()  # must not raise

        assert eng._engine is None
        assert eng.is_running is False

    @pytest.mark.anyio
    async def test_restart_twice_is_idempotent(self):
        eng = StockfishEngine()
        fake = _ImmediateEngine()
        _inject(eng, fake)

        await eng.restart()
        await eng.restart()  # second call on already-None engine; must not raise

        assert eng._engine is None
        assert eng.is_running is False
