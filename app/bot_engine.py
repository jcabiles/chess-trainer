"""Isolated weakened-Stockfish engine for the play-vs-bot mode.

This module owns a SEPARATE Stockfish UCI process from ``app.engine`` — the
shared analysis engine — and never touches its lock, options, or warm
transposition table. The two processes are fully independent: exercising or
crashing the bot engine leaves the analysis engine untouched, and vice versa.
That isolation is the load-bearing decision of the bots epic (B1 §7.1): UCI
options are process-global, so weakening one process must never degrade
concurrent human evals.

Design (mirrors ``app/engine.py``'s lifecycle discipline):

* One process only, spawned lazily on first use; reused across requests.
* ``SimpleEngine`` is synchronous and NOT thread-safe, and its ``analyse()``
  blocks — so every access runs in a thread-pool executor and is serialized
  behind ONE ``asyncio.Lock``.
* Import-safe: importing this module never launches Stockfish or raises when
  the binary is absent. Absence raises a catchable ``EngineUnavailable``.
* Hard-timeout watchdog + watchdog restart. Unlike the analysis engine — whose
  ``restart()`` re-applies only ``Threads``/``Hash`` — this engine re-applies
  the FULL weakening option set on every (re)spawn, so a restart can never
  silently drop ``UCI_LimitStrength`` / ``UCI_Elo`` and hand the user a
  full-strength bot (B1 §7.1: that gap must not be repeated here).

Weakening: ``UCI_LimitStrength=true`` + a per-instance ``UCI_Elo`` (``self._elo``,
default 1350) caps playing strength (fallback source B; floor is 1320 — B1 §1).
``Threads=1`` / ``Hash=16`` keep the bot cheap so it never competes with the
analysis engine for cores. The Elo lives in instance state (not the option dict)
so a persona switch re-pins it and a watchdog restart re-applies the CURRENT
persona's Elo — never a hardcoded default (B4).

The seam API is ``candidates(fen, k=1, elo=None)`` — a MultiPV=k list of moves
best-first (B1 §7.1: candidate distributions, not a bare bestmove) — so B4's
persona layer can consume ``k>1`` without an API break. B2 always calls ``k=1``
and plays ``[0]``. Passing ``elo`` atomically switches strength (respawn under
the single lock) before the search, so two interleaved different-persona calls
can't cross-contaminate; ``elo=None`` leaves strength unchanged (legacy path).
``scoreCp`` is White-POV centipawns and is always numeric — a forced mate maps
to signed ``±MATE_CP`` (positive when mate favors White).
"""

from __future__ import annotations

import asyncio
import glob
import os
import shutil
import signal
from pathlib import Path
from typing import List, Optional

import chess
import chess.engine as chess_engine

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

#: Environment variable that, if set, points at the Stockfish binary. Shared
#: name with the analysis engine — same binary, different processes.
STOCKFISH_PATH_ENV: str = "STOCKFISH_PATH"

#: Weakening + resource options applied on EVERY (re)spawn. Kept as one dict so
#: ``start()`` and the watchdog restart path cannot drift — the whole set is
#: always re-applied together (the gap ``engine.py`` has, avoided here). The
#: per-persona ``UCI_Elo`` is NOT in this dict — it lives in ``self._elo`` and is
#: merged in by ``start()`` so a restart re-applies the current persona's Elo.
BOT_ENGINE_OPTIONS: dict = {
    "Threads": 1,
    "Hash": 16,
    "UCI_LimitStrength": True,
}

#: Default per-instance ``UCI_Elo`` (fallback source B; floor 1320 — B1 §1). A
#: bare (no-persona) request stays at this Elo, reproducing B3 behavior exactly.
DEFAULT_BOT_ELO: int = 1350

#: Signed White-POV centipawn magnitude a forced mate maps to (positive when the
#: mate favors White, negative when it favors Black), so ``scoreCp`` is always
#: numeric and mover-POV conversion downstream preserves "winning" vs "getting
#: mated" (B4 sampling contract).
MATE_CP: int = 100000

#: Fixed per-move search budget. Small movetime keeps replies snappy and cheap;
#: the bot is deliberately weak so extra thinking time buys little.
BOT_MOVETIME_S: float = 0.3

#: Hard per-call asyncio watchdog (seconds). If the executor thread has not
#: returned by this deadline the engine is poisoned and EngineUnavailable is
#: raised. Must be > BOT_MOVETIME_S. Overridable via BOT_ENGINE_HARD_TIMEOUT.
BOT_HARD_TIMEOUT_S: float = float(os.environ.get("BOT_ENGINE_HARD_TIMEOUT", "5.0"))


class EngineUnavailable(RuntimeError):
    """Raised when the bot's Stockfish binary cannot be located or launched.

    Distinct class from ``app.engine.EngineUnavailable`` so the API layer can
    map a bot-engine failure to a 503 without conflating it with the analysis
    engine's health.
    """


def _locate_binary() -> str:
    """Resolve the path to the Stockfish binary (same order as ``engine.py``).

    Lookup order:
      1. The ``STOCKFISH_PATH`` environment variable, if set (must be an
         executable file at that path).
      2. ``shutil.which("stockfish")`` on the system ``PATH``.

    Raises:
        EngineUnavailable: if no usable binary is found.
    """
    configured = os.environ.get(STOCKFISH_PATH_ENV)
    if configured:
        if os.path.isfile(configured) and os.access(configured, os.X_OK):
            return configured
        raise EngineUnavailable(
            f"{STOCKFISH_PATH_ENV}={configured!r} is not an executable file."
        )

    found = shutil.which("stockfish")
    if found:
        return found

    raise EngineUnavailable(
        "Stockfish binary not found. Install it (e.g. `brew install stockfish`) "
        f"or set the {STOCKFISH_PATH_ENV} environment variable to its path."
    )


def detect_maia() -> dict:
    """Report Maia/lc0 readiness. Pure detection — never launches lc0.

    Checks whether an ``lc0`` binary is on ``PATH`` and enumerates any Maia
    weight files in the conventional ``~/maia_weights/`` folder. This is a
    readiness signal only (user-mandated at Gate 1); B2 has no lc0 move path.

    Returns:
        ``{"lc0": bool, "weights": [str, ...]}`` — ``lc0`` true when the binary
        is resolvable; ``weights`` a sorted list of discovered ``*.pb.gz`` paths
        (empty when the folder is absent).
    """
    lc0_present = shutil.which("lc0") is not None

    weights_dir = Path.home() / "maia_weights"
    weights = sorted(glob.glob(str(weights_dir / "*.pb.gz")))

    return {"lc0": lc0_present, "weights": weights}


class BotEngine:
    """Lifecycle + serialized async access to a single weakened Stockfish process.

    Fully isolated from ``app.engine.StockfishEngine``: its own subprocess, its
    own lock, its own options. Construction is cheap and never touches the
    binary; the subprocess is spawned lazily on first ``candidates()`` (or by an
    explicit ``start()`` in the FastAPI lifespan).

    Typical usage from FastAPI::

        bot = BotEngine()
        # lifespan startup: bot.start()  (optional — lazy start also works)
        moves = await bot.candidates(fen, k=1)     # play moves[0]["uci"]
        # lifespan shutdown:
        await bot.close()
    """

    def __init__(self) -> None:
        self._engine: Optional[chess_engine.SimpleEngine] = None
        # OS pid of the subprocess, captured in start(); used by _poison() to
        # SIGKILL without relying on a possibly-hung engine.close().
        self._pid: Optional[int] = None
        # Serializes ALL engine access — SimpleEngine is not thread-safe and the
        # executor is concurrent, so at most one search is in flight at a time.
        self._lock = asyncio.Lock()
        # Current persona strength (UCI_Elo). start() applies THIS value, so a
        # watchdog restart re-pins the current persona's Elo, never a hardcoded
        # default. candidates(elo=...) mutates it atomically under the lock.
        self._elo: int = DEFAULT_BOT_ELO

    # -- lifecycle ----------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether the bot's Stockfish subprocess has been launched."""
        return self._engine is not None

    def start(self) -> None:
        """Launch and configure the bot's Stockfish process (idempotent).

        Locates the binary, opens ONE UCI process, and applies the FULL option
        set — ``BOT_ENGINE_OPTIONS`` (Threads + Hash + UCI_LimitStrength) merged
        with ``UCI_Elo=self._elo`` (the current persona's strength). Applying
        ``self._elo`` here is what lets a watchdog restart re-pin the current
        persona's Elo rather than a hardcoded default. No-op if already running.

        Raises:
            EngineUnavailable: if the binary is missing or fails to launch.
        """
        if self._engine is not None:
            return

        binary = _locate_binary()
        try:
            engine = chess_engine.SimpleEngine.popen_uci(binary)
        except Exception as exc:  # FileNotFoundError, EngineError, OSError, ...
            raise EngineUnavailable(
                f"Failed to launch bot Stockfish at {binary!r}: {exc}"
            ) from exc

        try:
            # Apply the WHOLE weakening set on every spawn — never a subset —
            # with the CURRENT persona's Elo merged in (one dict, no drift).
            engine.configure({**BOT_ENGINE_OPTIONS, "UCI_Elo": self._elo})
        except Exception as exc:
            try:
                engine.quit()
            except Exception:
                pass
            raise EngineUnavailable(
                f"Failed to configure bot Stockfish: {exc}"
            ) from exc

        pid: Optional[int] = None
        try:
            pid = engine.transport.get_pid()
        except Exception:
            pid = None

        self._pid = pid
        self._engine = engine

    async def close(self) -> None:
        """Cleanly shut down the bot's Stockfish process (idempotent, async).

        Runs the blocking ``engine.quit()`` (which joins the subprocess) in an
        executor so a FastAPI lifespan shutdown never blocks the event loop.
        Safe to call when the engine was never started; never raises.
        """
        engine, self._engine = self._engine, None
        self._pid = None
        if engine is None:
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, engine.quit)
        except Exception:
            # Best-effort shutdown; the process is being torn down anyway.
            pass

    # -- poison / restart ---------------------------------------------------

    def _poison(self, engine: Optional[chess_engine.SimpleEngine]) -> None:
        """Force-terminate *engine* and null the handle. SYNC, never awaits.

        Called from ``_run_search``'s exception handlers and ``restart()``.
        Never raises. Nulls the handle first (so no later caller reuses a
        poisoned engine), SIGKILLs the pid (instant, non-blocking — ``quit()``
        can block on ``process.wait()`` if the engine thread is hung), then
        schedules a fire-and-forget ``close()`` as residual cleanup.
        """
        if engine is None:
            return

        pid = self._pid

        self._engine = None
        self._pid = None

        if pid is not None:
            try:
                os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            except Exception:
                pass  # process may already be dead; ignore

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, engine.close)
        except Exception:
            pass  # best-effort; if we can't schedule, drop it

    async def restart(self) -> None:
        """Force-restart the engine (lock-free, idempotent).

        Poisons the current process without acquiring the lock (it may be held
        by a wedged call) and nulls the handle so the next ``candidates()``
        lazily re-``start()``s a fresh process — which re-applies the FULL
        option set. Safe if the engine was never started.
        """
        self._poison(self._engine)

    # -- search -------------------------------------------------------------

    async def _run_search(
        self,
        board: chess.Board,
        multipv: int,
        elo: Optional[int] = None,
    ) -> List[chess_engine.InfoDict]:
        """Run ``engine.analyse`` at the fixed bot budget under lock + watchdog.

        Serializes via ``self._lock``, lazily starts the engine, shields the
        executor future from client-cancellation, and enforces the hard-timeout
        watchdog. Returns a list of ``InfoDict`` (always a list; normalized from
        a bare dict when ``multipv`` is effectively 1).

        The strength switch and the search share ONE lock acquisition: when
        *elo* differs from ``self._elo``, the persona Elo is re-pinned and the
        process respawned (``start()`` re-applies the new Elo) BEFORE the search,
        all inside the same critical section — so two interleaved different-
        persona calls can never cross-contaminate. ``elo=None`` leaves strength
        unchanged (legacy path).

        Raises:
            EngineUnavailable: on timeout, EngineError, or EngineTerminatedError.
            asyncio.CancelledError: re-raised after poisoning.
        """
        async with self._lock:
            # Atomic strength switch: re-pin the persona Elo and respawn so the
            # fresh process applies it, all before this same-lock search runs.
            if elo is not None and elo != self._elo:
                self._elo = elo
                self._poison(self._engine)
            if self._engine is None:
                self.start()
            # Local reference: _call closes over this, NOT self._engine, so that
            # _poison() nulling self._engine cannot AttributeError the running
            # executor thread.
            engine = self._engine
            assert engine is not None  # start() guarantees this or raised

            loop = asyncio.get_running_loop()
            limit = chess_engine.Limit(time=BOT_MOVETIME_S)

            def _call() -> List[chess_engine.InfoDict]:
                # No game= passed → no ucinewgame; the bot process keeps its own
                # (separate) warm TT. Never affects the analysis engine's TT.
                result = engine.analyse(board, limit, multipv=multipv)
                if isinstance(result, list):
                    return result
                return [result]

            fut = loop.run_in_executor(None, _call)

            try:
                info = await asyncio.wait_for(
                    asyncio.shield(fut), timeout=BOT_HARD_TIMEOUT_S
                )
            except asyncio.CancelledError:
                self._poison(engine)
                raise
            except asyncio.TimeoutError:
                self._poison(engine)
                raise EngineUnavailable("Bot Stockfish timed out; engine restarted")
            except chess_engine.EngineTerminatedError as exc:
                self._engine = None
                raise EngineUnavailable(
                    f"Bot Stockfish process terminated unexpectedly: {exc}"
                ) from exc
            except chess_engine.EngineError as exc:
                self._poison(engine)
                raise EngineUnavailable(
                    f"Bot Stockfish search failed: {exc}"
                ) from exc

        return info

    async def candidates(
        self, fen: str, k: int = 1, elo: Optional[int] = None
    ) -> List[dict]:
        """Return up to *k* candidate moves for *fen*, best-first.

        Implemented as MultiPV=k at the fixed bot budget (``BOT_MOVETIME_S``).
        B2 calls ``k=1`` and plays index 0; B4's persona layer consumes ``k>1``.

        Args:
            fen: The position to move in, in Forsyth-Edwards Notation.
            k: Number of ranked candidate moves to return (>= 1).
            elo: Persona strength to switch to before searching. When it differs
                from the current ``self._elo`` the process is respawned at the
                new Elo — the switch and the search share ONE lock acquisition,
                so interleaved different-persona calls can't cross-contaminate.
                ``None`` (default) leaves strength unchanged (legacy/B3 path).

        Returns:
            A list of ``{"uci": str, "san": str, "scoreCp": int}`` dicts, index
            0 = best. ``scoreCp`` is White-POV centipawns and is always numeric:
            a forced mate maps to signed ``±MATE_CP`` (positive for a mate
            favoring White). The list may be shorter than *k* when fewer legal
            moves exist.

        Raises:
            EngineUnavailable: if the binary is missing or the engine cannot run.
            ValueError: if ``fen`` is not a valid FEN.
        """
        try:
            board = chess.Board(fen)
        except ValueError as exc:
            raise ValueError(f"Invalid FEN: {fen!r} ({exc})") from exc

        infos = await self._run_search(board, multipv=max(1, k), elo=elo)

        # --- post-processing (outside the lock; pure, no engine access) ---
        out: List[dict] = []
        for info in infos:
            pv: List[chess.Move] = list(info.get("pv", []))
            if not pv:
                continue
            move = pv[0]
            try:
                san = board.san(move)
            except (AssertionError, ValueError):
                continue

            score = info.get("score")
            score_cp = self._score_to_white_cp(score)

            out.append({"uci": move.uci(), "san": san, "scoreCp": score_cp})

        return out

    @staticmethod
    def _score_to_white_cp(score: Optional[chess_engine.PovScore]) -> int:
        """Map a ``PovScore`` to an always-numeric White-POV centipawn value.

        A normal score returns White-POV centipawns. A forced mate returns
        signed ``±MATE_CP`` — positive when the mate favors White, negative when
        it favors Black — so downstream mover-POV conversion preserves "winning
        mate" vs "getting mated" (B4 sampling contract). ``None`` (no score)
        maps to 0 as a neutral fallback.
        """
        if score is None:
            return 0
        white = score.white()
        cp = white.score()
        if cp is not None:
            return cp
        # Forced mate: white.mate() is +N (White mates in N) or -N (White is
        # mated in N); a mate-for-White is a winning White-POV score.
        mate = white.mate()
        if mate is None:  # pragma: no cover - PovScore is either cp or mate
            return 0
        return MATE_CP if mate > 0 else -MATE_CP


#: Module-level singleton, mirroring the analysis engine's accessor idiom. Kept
#: private; callers use get_bot_engine() so tests can dependency-override it.
_bot_engine: Optional[BotEngine] = None


def get_bot_engine() -> BotEngine:
    """Return the process-wide BotEngine singleton (lazily constructed).

    The API layer (T2) uses this as a FastAPI dependency so tests can override
    it with a fake via ``app.dependency_overrides[get_bot_engine]``. Construction
    is cheap and touches no binary — import-safe.
    """
    global _bot_engine
    if _bot_engine is None:
        _bot_engine = BotEngine()
    return _bot_engine
