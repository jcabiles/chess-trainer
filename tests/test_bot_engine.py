"""Unit tests for BotEngine — no real Stockfish binary required.

Mirrors ``tests/test_engine.py``'s fake-injection approach: a fake
``SimpleEngine``-shaped object is placed directly into ``bot._engine`` (with
``bot._pid = None`` so ``_poison()`` skips ``os.kill``), bypassing ``start()``.
For the spawn/restart tests we instead monkeypatch ``popen_uci`` +
``_locate_binary`` so a fake process is created through the real ``start()``
path and we can assert the FULL option set is (re)applied.

Coverage (spec Verify-by-1, bot_engine unit):
- lock serializes concurrent ``candidates()`` calls (no overlap);
- hard-timeout → watchdog restart → FULL option set re-applied (all four);
- lazy-start failure surfaces ``EngineUnavailable`` (import-safe);
- ``close()`` shuts down cleanly and is idempotent;
- isolation: exercising/failing the bot engine leaves an analysis-engine fake
  untouched;
- ``detect_maia()`` shape.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import List

import chess
import chess.engine as chess_engine
import pytest

import app.bot_engine as bot_module
from app.bot_engine import (
    BOT_ENGINE_OPTIONS,
    BotEngine,
    EngineUnavailable,
    detect_maia,
    get_bot_engine,
)

START_FEN = chess.STARTING_FEN


# ---------------------------------------------------------------------------
# Helpers: minimal InfoDict + fake SimpleEngine shapes
# ---------------------------------------------------------------------------

def _make_info(cp: int = 20) -> chess_engine.InfoDict:
    """Minimal InfoDict with a White-POV score and a one-move PV."""
    info: chess_engine.InfoDict = {}  # type: ignore[assignment]
    info["score"] = chess_engine.PovScore(chess_engine.Cp(cp), chess.WHITE)
    board = chess.Board(START_FEN)
    info["pv"] = list(board.legal_moves)[:1]
    info["depth"] = 1
    return info


class _ImmediateEngine:
    """Fake SimpleEngine: analyse() returns immediately; records config calls."""

    def __init__(self, cp: int = 20):
        self._cp = cp
        self.configured: List[dict] = []
        self.closed = False

    def configure(self, options: dict) -> None:
        self.configured.append(dict(options))

    def analyse(self, board, limit, *, multipv: int = 1) -> chess_engine.InfoDict:
        return _make_info(self._cp)

    def quit(self) -> None:
        self.closed = True

    def close(self) -> None:
        self.closed = True


class _SerialisingEngine:
    """Fake whose analyse() records concurrent entries to prove the lock holds.

    Each call sleeps briefly while tracking how many calls are *inside*
    analyse() at once; ``max_concurrent`` must stay 1 if the lock serializes.
    """

    def __init__(self) -> None:
        self._active = 0
        self.max_concurrent = 0
        self._guard = threading.Lock()

    def configure(self, options: dict) -> None:
        pass

    def analyse(self, board, limit, *, multipv: int = 1) -> chess_engine.InfoDict:
        with self._guard:
            self._active += 1
            self.max_concurrent = max(self.max_concurrent, self._active)
        time.sleep(0.05)
        with self._guard:
            self._active -= 1
        return _make_info()

    def quit(self) -> None:
        pass

    def close(self) -> None:
        pass


class _SlowEngine:
    """Fake that sleeps past the hard timeout, then returns."""

    def __init__(self, sleep_s: float = 0.5) -> None:
        self._sleep_s = sleep_s
        self.configured: List[dict] = []

    def configure(self, options: dict) -> None:
        self.configured.append(dict(options))

    def analyse(self, board, limit, *, multipv: int = 1) -> chess_engine.InfoDict:
        time.sleep(self._sleep_s)
        return _make_info()

    def quit(self) -> None:
        pass

    def close(self) -> None:
        pass


def _inject(bot: BotEngine, fake: object) -> None:
    """Place a fake engine into bot, bypassing start(); _pid=None skips os.kill."""
    bot._engine = fake  # type: ignore[assignment]
    bot._pid = None


def _patch_spawn(monkeypatch, factory) -> List[object]:
    """Route BotEngine.start() through *factory*, capturing every spawned fake.

    Patches ``_locate_binary`` (so no real binary is needed) and
    ``SimpleEngine.popen_uci`` (so a fake is returned). Each spawned fake also
    gets a ``.transport.get_pid`` returning None so no os.kill fires. Returns the
    live list of spawned fakes (append-on-spawn).
    """
    spawned: List[object] = []

    def _fake_transport():
        class _T:
            @staticmethod
            def get_pid():
                return None

        return _T()

    def _popen(binary):
        fake = factory()
        fake.transport = _fake_transport()  # type: ignore[attr-defined]
        spawned.append(fake)
        return fake

    monkeypatch.setattr(bot_module, "_locate_binary", lambda: "/fake/stockfish")
    monkeypatch.setattr(chess_engine.SimpleEngine, "popen_uci", staticmethod(_popen))
    return spawned


# ---------------------------------------------------------------------------
# Lock serialization
# ---------------------------------------------------------------------------

class TestLockSerialisation:
    @pytest.mark.anyio
    async def test_concurrent_candidates_never_overlap(self):
        bot = BotEngine()
        fake = _SerialisingEngine()
        _inject(bot, fake)

        await asyncio.gather(
            bot.candidates(START_FEN),
            bot.candidates(START_FEN),
            bot.candidates(START_FEN),
        )

        assert fake.max_concurrent == 1, "lock must serialize concurrent searches"


# ---------------------------------------------------------------------------
# Hard-timeout → restart → FULL option set re-applied
# ---------------------------------------------------------------------------

class TestTimeoutRestartReappliesFullOptions:
    @pytest.mark.anyio
    async def test_timeout_poisons_then_restart_reapplies_all_four_options(
        self, monkeypatch
    ):
        monkeypatch.setattr(bot_module, "BOT_HARD_TIMEOUT_S", 0.1)
        # First spawn is slow (triggers timeout); the relaunch is immediate.
        factories = iter([lambda: _SlowEngine(sleep_s=0.5), _ImmediateEngine])

        def _factory():
            return next(factories)()

        spawned = _patch_spawn(monkeypatch, _factory)

        bot = BotEngine()

        # First call lazily starts the SLOW engine and times out → poisoned.
        with pytest.raises(EngineUnavailable, match="timed out"):
            await bot.candidates(START_FEN)
        assert bot._engine is None, "engine must be poisoned after timeout"

        # Next call relaunches a fresh process (lazy restart).
        result = await bot.candidates(START_FEN)
        assert result, "relaunched engine returns a candidate move"

        # Two processes were spawned; the SECOND got the FULL option set.
        assert len(spawned) == 2
        relaunch = spawned[1]
        assert relaunch.configured, "restart must re-configure the fresh process"
        applied = relaunch.configured[-1]
        # All four weakening options re-applied — the engine.py gap must NOT recur.
        assert applied["Threads"] == 1
        assert applied["Hash"] == 16
        assert applied["UCI_LimitStrength"] is True
        assert applied["UCI_Elo"] == 1350
        assert set(applied) == set(BOT_ENGINE_OPTIONS)


# ---------------------------------------------------------------------------
# Lazy-start failure → EngineUnavailable (import-safe)
# ---------------------------------------------------------------------------

class TestLazyStartFailure:
    def test_import_is_safe_with_no_binary(self, monkeypatch):
        # Importing + constructing must never raise, even with no binary.
        monkeypatch.delenv("STOCKFISH_PATH", raising=False)
        monkeypatch.setattr(bot_module.shutil, "which", lambda name: None)
        bot = BotEngine()  # construction never touches the binary
        assert bot.is_running is False

    @pytest.mark.anyio
    async def test_missing_binary_surfaces_engine_unavailable(self, monkeypatch):
        monkeypatch.delenv("STOCKFISH_PATH", raising=False)
        monkeypatch.setattr(bot_module.shutil, "which", lambda name: None)

        bot = BotEngine()
        with pytest.raises(EngineUnavailable, match="not found"):
            await bot.candidates(START_FEN)


# ---------------------------------------------------------------------------
# Clean shutdown
# ---------------------------------------------------------------------------

class TestShutdown:
    @pytest.mark.anyio
    async def test_close_quits_and_nulls(self):
        bot = BotEngine()
        fake = _ImmediateEngine()
        _inject(bot, fake)

        await bot.close()

        assert fake.closed is True
        assert bot._engine is None
        assert bot.is_running is False

    @pytest.mark.anyio
    async def test_close_is_idempotent_when_never_started(self):
        bot = BotEngine()
        await bot.close()  # must not raise
        await bot.close()
        assert bot._engine is None


# ---------------------------------------------------------------------------
# Isolation: bot-engine failure leaves an analysis-engine fake untouched
# ---------------------------------------------------------------------------

class TestIsolationFromAnalysisEngine:
    @pytest.mark.anyio
    async def test_bot_timeout_does_not_touch_analysis_engine(self, monkeypatch):
        from tests.engine_fakes import ScriptedEngine

        # Stand-in "analysis engine" — a fully separate object with observable
        # state. The bot engine must never reach into it.
        analysis = ScriptedEngine()
        assert analysis.is_running is True

        monkeypatch.setattr(bot_module, "BOT_HARD_TIMEOUT_S", 0.1)
        bot = BotEngine()
        _inject(bot, _SlowEngine(sleep_s=0.5))

        with pytest.raises(EngineUnavailable):
            await bot.candidates(START_FEN)

        # Bot poisoned; the analysis fake is completely unaffected.
        assert bot._engine is None
        assert analysis.is_running is True
        # And the analysis engine still answers normally afterwards.
        result = await analysis.analyze(START_FEN)
        assert result is not None


# ---------------------------------------------------------------------------
# candidates() shape + best-first ordering
# ---------------------------------------------------------------------------

class TestCandidatesShape:
    @pytest.mark.anyio
    async def test_candidate_dict_shape(self):
        bot = BotEngine()
        _inject(bot, _ImmediateEngine(cp=42))

        cands = await bot.candidates(START_FEN, k=1)

        assert len(cands) == 1
        c = cands[0]
        assert set(c) == {"uci", "san", "scoreCp"}
        assert isinstance(c["uci"], str)
        assert isinstance(c["san"], str)
        assert c["scoreCp"] == 42

    @pytest.mark.anyio
    async def test_invalid_fen_raises_value_error(self):
        bot = BotEngine()
        _inject(bot, _ImmediateEngine())
        with pytest.raises(ValueError, match="Invalid FEN"):
            await bot.candidates("not a fen")


# ---------------------------------------------------------------------------
# detect_maia + accessor
# ---------------------------------------------------------------------------

class TestDetectMaia:
    def test_shape_and_no_lc0(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bot_module.shutil, "which", lambda name: None)
        monkeypatch.setattr(bot_module.Path, "home", staticmethod(lambda: tmp_path))

        result = detect_maia()

        assert set(result) == {"lc0", "weights"}
        assert result["lc0"] is False
        assert result["weights"] == []

    def test_detects_lc0_and_weights(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bot_module.shutil, "which", lambda name: "/usr/bin/lc0")
        wdir = tmp_path / "maia_weights"
        wdir.mkdir()
        (wdir / "maia-1500.pb.gz").write_text("x")
        monkeypatch.setattr(bot_module.Path, "home", staticmethod(lambda: tmp_path))

        result = detect_maia()

        assert result["lc0"] is True
        assert result["weights"] == [str(wdir / "maia-1500.pb.gz")]


class TestAccessor:
    def test_get_bot_engine_returns_singleton(self):
        bot_module._bot_engine = None
        a = get_bot_engine()
        b = get_bot_engine()
        assert a is b
        assert isinstance(a, BotEngine)
