"""T2 tests — per-persona strength (atomic UCI_Elo) + signed mate mapping.

These exercise ``app.bot_engine.BotEngine`` with a FAKE ``SimpleEngine`` (no real
Stockfish binary): a spy that records every ``configure()`` and ``analyse()`` and
can return either a normal cp score or a forced mate. The seam is
``chess.engine.SimpleEngine.popen_uci`` — ``start()`` calls it, so patching it
lets the whole test run engine-free.

Coverage:
* ``candidates(..., elo=X)`` respawns + re-configures ONLY when X != current.
* ``elo=None`` leaves strength unchanged (legacy/B3 path).
* After a (simulated watchdog) restart, ``start()`` re-applies ``self._elo`` —
  the CURRENT persona's Elo, not a hardcoded 1350.
* A mate score maps to signed ``±MATE_CP`` (never ``None``).
* The strength switch and the search share ONE lock acquisition (structural).
"""

from __future__ import annotations

import asyncio

import chess
import chess.engine as chess_engine
import pytest

import app.bot_engine as bot_engine
from app.bot_engine import DEFAULT_BOT_ELO, MATE_CP, BotEngine

START_FEN = chess.STARTING_FEN


class FakeSimpleEngine:
    """Records configure()/analyse() calls; returns a scripted PV + score.

    ``score_kind`` selects what ``analyse`` reports for the first candidate:
    ``"cp"`` → a normal centipawn score, ``"mate_white"`` → White mates,
    ``"mate_black"`` → Black mates.
    """

    def __init__(self, score_kind: str = "cp") -> None:
        self.configured: list[dict] = []
        self.analyse_calls: int = 0
        self.quit_called = False
        self.close_called = False
        self.score_kind = score_kind

        class _Transport:
            def get_pid(self_inner) -> int:
                return 4242

        self.transport = _Transport()

    def configure(self, options: dict) -> None:
        self.configured.append(dict(options))

    def analyse(self, board, limit, multipv):  # noqa: ANN001 - fake seam
        self.analyse_calls += 1
        move = next(iter(board.legal_moves))
        if self.score_kind == "mate_white":
            pov = chess_engine.PovScore(chess_engine.Mate(3), chess.WHITE)
        elif self.score_kind == "mate_black":
            pov = chess_engine.PovScore(chess_engine.Mate(-2), chess.WHITE)
        else:
            pov = chess_engine.PovScore(chess_engine.Cp(42), chess.WHITE)
        info = {"pv": [move], "score": pov}
        if multipv > 1:
            return [info]
        return info

    def quit(self) -> None:
        self.quit_called = True

    def close(self) -> None:
        self.close_called = True


class _SpawnLog(list):
    """A list of spawned engines that also carries a mutable ``kind`` dict.

    ``kind["score"]`` selects the score each freshly spawned FakeSimpleEngine
    reports, so a test can flip the mate/cp behavior before calling candidates.
    """

    kind: dict


@pytest.fixture
def patched_popen(monkeypatch):
    """Patch the SimpleEngine popen + binary locate so start() uses a fake.

    Returns a ``_SpawnLog`` into which each spawned FakeSimpleEngine is appended,
    so a test can assert on respawn count and per-spawn configure() arguments.
    """
    spawned = _SpawnLog()
    spawned.kind = {"score": "cp"}

    def _popen(_binary):
        eng = FakeSimpleEngine(score_kind=spawned.kind["score"])
        spawned.append(eng)
        return eng

    monkeypatch.setattr(bot_engine, "_locate_binary", lambda: "/fake/stockfish")
    monkeypatch.setattr(
        chess_engine.SimpleEngine, "popen_uci", staticmethod(_popen)
    )
    # Prevent os.kill on the fake pid during _poison/restart.
    monkeypatch.setattr(bot_engine.os, "kill", lambda *a, **k: None)
    return spawned


def _last_elo(engine: FakeSimpleEngine) -> int:
    """The UCI_Elo of the most recent configure() call on a spawned engine."""
    assert engine.configured, "engine was never configured"
    return engine.configured[-1]["UCI_Elo"]


# --- default + start() ------------------------------------------------------


def test_start_applies_default_elo(patched_popen):
    bot = BotEngine()
    assert bot._elo == DEFAULT_BOT_ELO == 1350
    bot.start()
    assert len(patched_popen) == 1
    cfg = patched_popen[0].configured[-1]
    assert cfg["UCI_Elo"] == 1350
    assert cfg["UCI_LimitStrength"] is True
    assert cfg["Threads"] == 1 and cfg["Hash"] == 16


# --- strength switch only on change -----------------------------------------


def test_candidates_elo_none_leaves_strength_unchanged(patched_popen):
    bot = BotEngine()
    asyncio.run(bot.candidates(START_FEN, k=1, elo=None))
    assert bot._elo == 1350
    assert len(patched_popen) == 1  # spawned once, never respawned
    assert patched_popen[0].analyse_calls == 1


def test_candidates_elo_switch_respawns_at_new_elo(patched_popen):
    bot = BotEngine()
    # First call establishes 1350.
    asyncio.run(bot.candidates(START_FEN, k=1, elo=1350))
    assert len(patched_popen) == 1
    assert _last_elo(patched_popen[0]) == 1350

    # New persona Elo → respawn, configured at 2000.
    asyncio.run(bot.candidates(START_FEN, k=1, elo=2000))
    assert bot._elo == 2000
    assert len(patched_popen) == 2, "a differing elo must respawn the process"
    assert _last_elo(patched_popen[1]) == 2000


def test_candidates_same_elo_does_not_respawn(patched_popen):
    bot = BotEngine()
    asyncio.run(bot.candidates(START_FEN, k=1, elo=1800))
    asyncio.run(bot.candidates(START_FEN, k=1, elo=1800))
    # First call: default 1350 != 1800 → set + respawn (still one spawn total,
    # since the engine was not yet started). Second: 1800 == 1800 → no respawn.
    assert bot._elo == 1800
    assert len(patched_popen) == 1
    assert patched_popen[0].analyse_calls == 2


# --- restart re-applies self._elo, not a hardcoded default ------------------


def test_watchdog_restart_reapplies_current_elo(patched_popen):
    bot = BotEngine()
    # Pin persona 2000.
    asyncio.run(bot.candidates(START_FEN, k=1, elo=2000))
    assert bot._elo == 2000
    assert len(patched_popen) == 1
    assert _last_elo(patched_popen[0]) == 2000

    # Simulate a watchdog restart: poison the process (lock-free restart).
    asyncio.run(bot.restart())
    assert bot.is_running is False
    assert bot._elo == 2000  # persona survives the restart

    # Next search lazily respawns — start() must re-apply 2000, NOT 1350.
    asyncio.run(bot.candidates(START_FEN, k=1, elo=None))
    assert len(patched_popen) == 2
    assert _last_elo(patched_popen[1]) == 2000, "restart must not reset to 1350"


def test_direct_start_after_restart_uses_current_elo(patched_popen):
    """start() itself (not just candidates) re-applies self._elo after restart."""
    bot = BotEngine()
    bot._elo = 1900
    bot.start()
    assert _last_elo(patched_popen[0]) == 1900
    asyncio.run(bot.restart())
    bot.start()
    assert len(patched_popen) == 2
    assert _last_elo(patched_popen[1]) == 1900


# --- mate → signed ±MATE_CP -------------------------------------------------


def test_mate_for_white_maps_to_positive_mate_cp(patched_popen):
    patched_popen.kind["score"] = "mate_white"
    bot = BotEngine()
    out = asyncio.run(bot.candidates(START_FEN, k=1))
    assert out[0]["scoreCp"] == MATE_CP == 100000


def test_mate_for_black_maps_to_negative_mate_cp(patched_popen):
    patched_popen.kind["score"] = "mate_black"
    bot = BotEngine()
    out = asyncio.run(bot.candidates(START_FEN, k=1))
    assert out[0]["scoreCp"] == -MATE_CP == -100000


def test_score_cp_is_never_none(patched_popen):
    for kind in ("cp", "mate_white", "mate_black"):
        patched_popen.kind["score"] = kind
        bot = BotEngine()
        out = asyncio.run(bot.candidates(START_FEN, k=1))
        assert out[0]["scoreCp"] is not None
        assert isinstance(out[0]["scoreCp"], int)


def test_score_to_white_cp_none_is_zero():
    assert BotEngine._score_to_white_cp(None) == 0


def test_normal_score_stays_cp(patched_popen):
    bot = BotEngine()
    out = asyncio.run(bot.candidates(START_FEN, k=1))
    assert out[0]["scoreCp"] == 42  # the fake's Cp(42), White-POV


# --- structural: switch + search share ONE lock acquisition -----------------


def test_switch_and_search_hold_the_lock_together(patched_popen):
    """The strength switch AND the search happen while ``self._lock`` is held.

    Structural/seam proof: the fake ``analyse`` (which runs during the search)
    asserts that the lock is locked, and records the spawn count + Elo it sees.
    Because ``_run_search`` re-pins ``self._elo`` + respawns and then searches
    all under one ``async with self._lock``, a differing ``elo`` respawns to the
    NEW value BEFORE the search runs, and the lock is held throughout — so no
    other coroutine could reconfigure the engine mid-search.
    """
    bot = BotEngine()
    observed: dict = {}

    def _make_engine() -> FakeSimpleEngine:
        eng = FakeSimpleEngine(score_kind="cp")
        real_analyse = eng.analyse

        def _analyse(board, limit, multipv):  # noqa: ANN001
            observed["locked_during_search"] = bot._lock.locked()
            observed["elo_during_search"] = bot._elo
            observed["spawns_during_search"] = len(patched_popen)
            return real_analyse(board, limit, multipv)

        eng.analyse = _analyse  # type: ignore[assignment]
        return eng

    patched_popen.clear()
    it = iter([_make_engine()])

    def _popen(_binary):
        eng = next(it)
        patched_popen.append(eng)
        return eng

    chess_engine.SimpleEngine.popen_uci = staticmethod(_popen)  # type: ignore[assignment]

    asyncio.run(bot.candidates(START_FEN, k=1, elo=2200))

    # The lock was held while searching; the switch to 2200 had already taken
    # effect (respawned once) before the search — one atomic critical section.
    assert observed["locked_during_search"] is True
    assert observed["elo_during_search"] == 2200
    assert observed["spawns_during_search"] == 1
    assert bot._elo == 2200
