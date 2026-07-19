"""Isolated lc0/Maia engine for human-like bot moves (Maia walking skeleton).

This module owns a THIRD engine process, fully separate from both Stockfish
processes (``app.engine`` — shared analysis — and ``app.bot_engine`` — the
weakened bot). Three-way isolation is load-bearing: own subprocess, own
``asyncio.Lock``, zero shared state. Crashing lc0 must never disturb either
Stockfish process, and vice versa.

Design (mirrors ``bot_engine.py``'s lifecycle discipline, hardened):

* One lc0 process, spawned lazily on first use with ``--weights=<net>``;
  switching nets restarts the process (~1s, only on net change). The current
  net path lives in instance state (``self._net_path``) so a watchdog restart
  re-applies the CURRENT net — never a hardcoded default.
* ``SimpleEngine`` is synchronous and not thread-safe: every access runs in a
  thread-pool executor, serialized behind ONE lock. **Single-worker
  assumption:** the lock guards one uvicorn worker's event loop only;
  multi-worker deployment is out of contract for this app.
* Import-safe: importing, constructing, and ``maia_ready_for()`` never launch
  lc0 (pure detection — the ``/api/bot/status`` purity contract).
* Failure envelope: ``top_move()`` returns a LEGAL move or raises
  ``MaiaUnavailable`` — timeouts, dead processes, malformed/illegal bestmoves
  and parser crashes are all caught and rewrapped. Nothing else escapes, so
  the API layer's fallback (`except MaiaUnavailable: use Stockfish`) is the
  single, total failure path.
* Generation-bound watchdog: ``_poison(engine, pid)`` receives the handles it
  may kill and only nulls instance state when it still points at that same
  generation (``if self._engine is engine``) — a stale timeout cleanup can
  never kill or null a newer respawn (spec review finding).

Priors: lc0 at ``go nodes 1`` with ``VerboseMoveStats=true`` emits one
``info string <move> ... (P: xx.xx%) ...`` line per legal move, then a final
``info string node ...`` summary. python-chess's ``analyse()`` cannot capture
these (each info line overwrites the last in the aggregated dict — verified
against the live binary), so the search uses the STREAMING ``analysis()`` API
and collects every ``string`` line as it arrives. ``PolicyTemperature`` is
pinned to 1.0 (install default 1.359 preserves the argmax but distorts the
prior distribution the variety slice will sample from). Priors are returned
as probabilities and are NEVER mapped into a ``scoreCp`` field — they are not
centipawns and must not flow into the sampling/mistake-band machinery.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import signal
from pathlib import Path
from typing import List, Optional, Tuple

import chess
import chess.engine as chess_engine

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

#: Directory holding maia-XXXX.pb.gz weight files (overridable for tests).
MAIA_WEIGHTS_DIR_ENV: str = "MAIA_WEIGHTS_DIR"

#: Options applied on EVERY (re)spawn, as one dict so start() and the watchdog
#: restart path cannot drift. VerboseMoveStats makes lc0 emit per-move policy
#: lines; Threads=1/MinibatchSize=1 are the correct nodes=1 settings;
#: PolicyTemperature=1.0 keeps priors undistorted (default is 1.359).
MAIA_ENGINE_OPTIONS: dict = {
    "VerboseMoveStats": True,
    "Threads": 1,
    "MinibatchSize": 1,
    "PolicyTemperature": 1.0,
}

#: Persona id -> required Maia net filename. The skeleton wires exactly one
#: persona; the ladder-switch slice extends this map.
MAIA_NETS: dict = {
    "casey": "maia-1400.pb.gz",
}

#: Optional lc0 backend override (e.g. "eigen" to force CPU where the GPU is
#: unavailable — sandboxed test runs block Metal init). Unset → lc0's default.
MAIA_BACKEND_ENV: str = "MAIA_BACKEND"

#: Hard per-call watchdog (seconds). Deliberately LOW: a nodes=1 forward pass
#: is <100ms and a cold spawn ~1s, and the same-request Stockfish fallback
#: must still land inside the interactive budget after a Maia timeout.
MAIA_HARD_TIMEOUT_S: float = float(os.environ.get("MAIA_ENGINE_HARD_TIMEOUT", "2.0"))

#: VerboseMoveStats per-move line: "<uci>  (  322) N: ... (P:  8.60%) ...".
#: The summary line starts with the token "node" and must not match a UCI move.
_MOVESTAT_RE = re.compile(r"^\s*([a-h][1-8][a-h][1-8][nbrq]?)\s+\(.*?\(P:\s*([0-9.]+)%\)")


class MaiaUnavailable(RuntimeError):
    """Raised when a Maia move cannot be produced (missing binary/net, launch
    or search failure, timeout, or an unusable bestmove).

    The ONLY exception ``top_move()`` lets escape — the API layer catches it
    and falls back to the weakened-Stockfish path in the same request.
    """


def _weights_dir() -> Path:
    configured = os.environ.get(MAIA_WEIGHTS_DIR_ENV)
    if configured:
        return Path(configured)
    return Path.home() / "maia_weights"


def _net_path_for(persona_id: str) -> Optional[Path]:
    """Absolute path of the persona's required net, or None if unmapped."""
    name = MAIA_NETS.get(persona_id)
    if name is None:
        return None
    return _weights_dir() / name


def maia_ready_for(persona_id: str) -> bool:
    """Pure readiness check for one persona: lc0 on PATH AND that persona's
    REQUIRED net file present ("any *.pb.gz exists" is NOT ready — spec
    review finding). Never launches or probes a process.
    """
    net = _net_path_for(persona_id)
    if net is None:
        return False
    return shutil.which("lc0") is not None and net.is_file()


def _locate_binary() -> str:
    """Resolve the lc0 binary from PATH.

    Raises:
        MaiaUnavailable: if no lc0 binary is found.
    """
    found = shutil.which("lc0")
    if found:
        return found
    raise MaiaUnavailable("lc0 binary not found on PATH.")


def parse_movestats(lines: List[str]) -> List[dict]:
    """Parse VerboseMoveStats ``info string`` lines into policy priors.

    Pure and engine-free (unit-tested on captured fixture text). Returns
    ``[{"uci": str, "p": float}, ...]`` sorted by descending prior; the
    trailing ``node ...`` summary line and any unrecognized line are skipped.
    Probabilities are percentages converted to [0, 1] fractions.
    """
    out: List[dict] = []
    for line in lines:
        m = _MOVESTAT_RE.match(line)
        if not m:
            continue
        try:
            out.append({"uci": m.group(1), "p": float(m.group(2)) / 100.0})
        except ValueError:  # pragma: no cover - regex guarantees float-able
            continue
    out.sort(key=lambda d: d["p"], reverse=True)
    return out


class MaiaEngine:
    """Lifecycle + serialized async access to a single lc0/Maia process.

    Construction is cheap and never touches the binary; the subprocess spawns
    lazily on first ``top_move()``. See the module docstring for the isolation,
    failure-envelope, and generation-bound-watchdog contracts.
    """

    def __init__(self) -> None:
        self._engine: Optional[chess_engine.SimpleEngine] = None
        self._pid: Optional[int] = None
        # Serializes ALL engine access (net switch + search share one
        # acquisition, so interleaved different-net calls can't cross-load).
        self._lock = asyncio.Lock()
        # Current net; start() applies THIS path so a watchdog restart
        # re-loads the current persona's net, never a default.
        self._net_path: Optional[Path] = None

    # -- lifecycle ----------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether the lc0 subprocess has been launched."""
        return self._engine is not None

    def _start(self, net_path: Path) -> None:
        """Launch lc0 with *net_path* and apply the full option set (idempotent
        for the same net). Caller must hold the lock.

        Raises:
            MaiaUnavailable: if the binary/net is missing or launch fails.
        """
        if self._engine is not None and self._net_path == net_path:
            return

        if not net_path.is_file():
            raise MaiaUnavailable(f"Maia net not found: {net_path}")

        # Net switch: tear down the old-generation process first.
        if self._engine is not None:
            self._poison(self._engine, self._pid)

        binary = _locate_binary()
        try:
            engine = chess_engine.SimpleEngine.popen_uci(
                [binary, f"--weights={net_path}"]
            )
        except Exception as exc:  # FileNotFoundError, EngineError, OSError, ...
            raise MaiaUnavailable(f"Failed to launch lc0 at {binary!r}: {exc}") from exc

        try:
            # Whole option set on every spawn — never a subset (no drift).
            options = dict(MAIA_ENGINE_OPTIONS)
            backend = os.environ.get(MAIA_BACKEND_ENV)
            if backend:
                options["Backend"] = backend
            engine.configure(options)
        except Exception as exc:
            try:
                engine.quit()
            except Exception:
                pass
            raise MaiaUnavailable(f"Failed to configure lc0: {exc}") from exc

        pid: Optional[int] = None
        try:
            pid = engine.transport.get_pid()
        except Exception:
            pid = None

        self._pid = pid
        self._engine = engine
        self._net_path = net_path

    async def close(self) -> None:
        """Cleanly shut down the lc0 process (idempotent, async, never raises)."""
        engine, self._engine = self._engine, None
        self._pid = None
        self._net_path = None
        if engine is None:
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, engine.quit)
        except Exception:
            pass  # best-effort shutdown

    # -- poison / restart ---------------------------------------------------

    def _poison(
        self,
        engine: Optional[chess_engine.SimpleEngine],
        pid: Optional[int],
    ) -> None:
        """Force-terminate the GIVEN engine generation. SYNC, never raises.

        Generation-bound: *engine*/*pid* are the handles captured by the caller
        when its search began; instance state is cleared only if it still
        points at that same generation, so a stale timeout's cleanup can never
        kill or null a newer respawn (spec review finding — do not copy
        ``bot_engine._poison``'s mutable-pid read).
        """
        if engine is None:
            return

        if self._engine is engine:
            self._engine = None
            self._pid = None
            self._net_path = None

        if pid is not None:
            try:
                os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            except Exception:
                pass  # already dead; ignore

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, engine.close)
        except Exception:
            pass  # best-effort

    async def restart(self) -> None:
        """Force-restart (lock-free, idempotent): poison the current process;
        the next ``top_move()`` lazily respawns with the current net."""
        self._poison(self._engine, self._pid)

    # -- search -------------------------------------------------------------

    async def top_move(self, fen: str, persona_id: str) -> dict:
        """Return Maia's move (policy argmax at ``go nodes 1``) for *fen*.

        Args:
            fen: Position to move in (FEN). Skeleton limitation, accepted at
                review: FEN-only inference — no move history is transmitted,
                so Maia sees an isolated position (full-line transmission is
                the ladder-switch slice's job).
            persona_id: Persona whose mapped net to use (``MAIA_NETS``).

        Returns:
            ``{"uci": str, "san": str, "priors": [{"uci", "p"}, ...]}`` —
            the move is guaranteed legal in *fen*; ``priors`` are parsed
            VerboseMoveStats policy fractions (possibly ``[]`` when parsing
            fails — the move still stands). Priors are NOT centipawns and are
            never exposed as ``scoreCp``.

        Raises:
            MaiaUnavailable: on ANY failure — unmapped persona, missing
                binary/net, launch/search error, timeout, or an
                illegal/absent bestmove.
            ValueError: if *fen* is not a valid FEN (caller bug, not an
                engine failure — the route validates FEN before engines).
        """
        try:
            board = chess.Board(fen)
        except ValueError as exc:
            raise ValueError(f"Invalid FEN: {fen!r} ({exc})") from exc

        net_path = _net_path_for(persona_id)
        if net_path is None:
            raise MaiaUnavailable(f"No Maia net mapped for persona {persona_id!r}")

        async with self._lock:
            self._start(net_path)
            # Local generation handles: _call closes over these, and the
            # exception paths poison THIS generation only.
            engine = self._engine
            pid = self._pid
            assert engine is not None  # _start() guarantees this or raised

            loop = asyncio.get_running_loop()

            def _call() -> Tuple[List[str], Optional[chess.Move]]:
                # Streaming API: analyse() would let each `info string` line
                # overwrite the previous one; here every line is captured as
                # it arrives, and bestmove comes from wait().
                lines: List[str] = []
                with engine.analysis(
                    board, chess_engine.Limit(nodes=1)
                ) as analysis:
                    for info in analysis:
                        s = info.get("string")
                        if s:
                            lines.append(s)
                    best = analysis.wait()
                return lines, best.move

            fut = loop.run_in_executor(None, _call)

            try:
                lines, move = await asyncio.wait_for(
                    asyncio.shield(fut), timeout=MAIA_HARD_TIMEOUT_S
                )
            except asyncio.CancelledError:
                self._poison(engine, pid)
                raise
            except asyncio.TimeoutError:
                self._poison(engine, pid)
                raise MaiaUnavailable("lc0 timed out; engine restarted")
            except chess_engine.EngineTerminatedError as exc:
                if self._engine is engine:
                    self._engine = None
                    self._pid = None
                    self._net_path = None
                raise MaiaUnavailable(f"lc0 terminated unexpectedly: {exc}") from exc
            except Exception as exc:  # EngineError, protocol/parse surprises
                self._poison(engine, pid)
                raise MaiaUnavailable(f"lc0 search failed: {exc}") from exc

        # --- post-processing (outside the lock; pure) ---
        if move is None or move not in board.legal_moves:
            raise MaiaUnavailable(f"lc0 returned unusable bestmove: {move!r}")

        try:
            priors = parse_movestats(lines)
        except Exception:  # defensive: a parser bug must not eat the move
            priors = []

        return {"uci": move.uci(), "san": board.san(move), "priors": priors}


#: Module-level singleton, mirroring the bot engine's accessor idiom.
_maia_engine: Optional[MaiaEngine] = None


def get_maia_engine() -> MaiaEngine:
    """Return the process-wide MaiaEngine singleton (lazily constructed).

    ``app/main.py`` imports this as a bare name (``from app.maia_engine import
    get_maia_engine``) so tests patch ``main.get_maia_engine`` — the same
    monkeypatch seam as ``detect_maia`` (spec: module-attr call style is
    forbidden, it would silently no-op that patch).
    """
    global _maia_engine
    if _maia_engine is None:
        _maia_engine = MaiaEngine()
    return _maia_engine
