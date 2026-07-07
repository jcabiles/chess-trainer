"""Tests for automatic analysis kick-off (_kick_auto_analysis triggers).

The helper's first guard returns immediately when CHESS_SKIP_ENGINE_AUTOSTART
is set — which the session conftest sets for every test — so the default
fixtures never exercise auto-kick. Each test here therefore deletes the env
var *after* the TestClient lifespan has run (so the lifespan still skips the
real engine autostart) and isolates GAMES_DB to a temp path.

Coverage
--------
- import with a running fake engine ⇒ singleton bulk task started (spy).
- import with the env gate set ⇒ no kick (suite safety).
- import with engine not running ⇒ 200, games stay 'pending' (never 'failed').
- retag-color with matches ⇒ kick; no matches ⇒ no kick.
- per-game color change (PATCH) ⇒ kick.
- engine restart with pending games ⇒ kick; without pending ⇒ no kick.
- lifespan ⇒ kick when the DB has pending games at boot.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.review as review_module
import app.storage as storage
from app.engine import EngineUnavailable
from app.main import app, get_engine
from tests.engine_fakes import ScriptedEngine

# A minimal game (1.e4 e5 2.Nf3).
_PGN = (
    '[Event "Test"]\n'
    '[White "Alice"]\n'
    '[Black "Bob"]\n'
    '[Result "*"]\n'
    '\n'
    '1. e4 e5 2. Nf3 *\n'
)


class StoppedEngine(ScriptedEngine):
    """A fake engine that is down and cannot be started (binary absent)."""

    @property
    def is_running(self) -> bool:
        return False

    def start(self) -> None:
        raise EngineUnavailable("no stockfish binary (test fake)")


@pytest.fixture(autouse=True)
def fresh_storage(tmp_path: Path, monkeypatch):
    """Fresh temp DB for every test; cancels stray background tasks after."""
    db_path = str(tmp_path / "auto_analyze_test.db")
    monkeypatch.setenv("GAMES_DB", db_path)
    storage.init(db_path)
    yield
    for gid in list(review_module._tasks.keys()):
        review_module.cancel_analysis(gid)


@pytest.fixture
def kick_spy(monkeypatch):
    """Replace review.start_analyze_all with a call recorder."""
    calls: list[dict] = []

    def spy(engine, **kw):
        calls.append({"engine": engine, **kw})

    monkeypatch.setattr(review_module, "start_analyze_all", spy)
    return calls


def _client(engine) -> TestClient:
    app.dependency_overrides[get_engine] = lambda: engine
    return TestClient(app)


def _enable_kick(monkeypatch) -> None:
    """Drop the env gate (call only AFTER the TestClient lifespan has run)."""
    monkeypatch.delenv("CHESS_SKIP_ENGINE_AUTOSTART", raising=False)


class TestImportKick:
    def test_import_kicks_bulk_task(self, monkeypatch, kick_spy):
        """Import with a running fake engine starts the singleton bulk task."""
        engine = ScriptedEngine()
        with _client(engine) as c:
            _enable_kick(monkeypatch)
            r = c.post("/api/games/import", json={"pgn": _PGN})
            assert r.status_code == 200
            assert r.json()["imported"] == 1
            assert len(kick_spy) == 1
            assert kick_spy[0]["engine"] is engine
            assert kick_spy[0]["depth"] == review_module.BACKGROUND_DEPTH
        app.dependency_overrides.clear()

    def test_import_env_gate_blocks_kick(self, kick_spy):
        """With CHESS_SKIP_ENGINE_AUTOSTART set (default in tests), no kick."""
        with _client(ScriptedEngine()) as c:
            r = c.post("/api/games/import", json={"pgn": _PGN})
            assert r.status_code == 200
            assert kick_spy == []
        app.dependency_overrides.clear()

    def test_import_engine_down_stays_pending(self, monkeypatch, kick_spy):
        """Engine not running: import still 200 and games stay 'pending'."""
        with _client(StoppedEngine()) as c:
            _enable_kick(monkeypatch)
            r = c.post("/api/games/import", json={"pgn": _PGN})
            assert r.status_code == 200
            game_id = r.json()["games"][0]["id"]
            assert kick_spy == []
            s = c.get(f"/api/games/{game_id}/status")
            assert s.json()["analysis_status"] == "pending"
        app.dependency_overrides.clear()


class TestRetagKick:
    def test_retag_kicks_when_updated(self, monkeypatch, kick_spy):
        """retag-color with ≥1 match starts the bulk task."""
        with _client(ScriptedEngine()) as c:
            c.post("/api/games/import", json={"pgn": _PGN})
            _enable_kick(monkeypatch)
            r = c.post("/api/games/retag-color", json={"username": "Alice"})
            assert r.status_code == 200
            assert r.json()["updated"] == 1
            assert len(kick_spy) == 1
        app.dependency_overrides.clear()

    def test_retag_no_match_no_kick(self, monkeypatch, kick_spy):
        """retag-color with zero matches does not kick."""
        with _client(ScriptedEngine()) as c:
            c.post("/api/games/import", json={"pgn": _PGN})
            _enable_kick(monkeypatch)
            r = c.post("/api/games/retag-color", json={"username": "Nobody"})
            assert r.status_code == 200
            assert r.json()["updated"] == 0
            assert kick_spy == []
        app.dependency_overrides.clear()


class TestColorChangeKick:
    def test_patch_color_kicks(self, monkeypatch, kick_spy):
        """PATCH /api/games/{id} color change starts the bulk task."""
        with _client(ScriptedEngine()) as c:
            r0 = c.post("/api/games/import", json={"pgn": _PGN})
            game_id = r0.json()["games"][0]["id"]
            _enable_kick(monkeypatch)
            r = c.patch(f"/api/games/{game_id}", json={"my_color": "white"})
            assert r.status_code == 200
            assert len(kick_spy) == 1
        app.dependency_overrides.clear()


class LazyEngine(ScriptedEngine):
    """A fake engine that is down until start() is called.

    Models the real StockfishEngine right after restart(): the process is
    poisoned (is_running False) and the next start() lazily respawns it.
    """

    def __init__(self) -> None:
        super().__init__()
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started

    def start(self) -> None:
        self._started = True


class TestRestartKick:
    def test_restart_starts_lazy_engine_and_kicks(self, monkeypatch, kick_spy):
        """Restart leaves the real engine down (lazy start); the kick's
        availability probe must start() it rather than silently skip."""
        engine = LazyEngine()
        with _client(engine) as c:
            c.post("/api/games/import", json={"pgn": _PGN})  # env gate still on: no kick
            _enable_kick(monkeypatch)
            r = c.post("/api/engine/restart")
            assert r.status_code == 200
            assert engine.is_running
            assert len(kick_spy) == 1
        app.dependency_overrides.clear()

    def test_restart_kicks_when_pending(self, monkeypatch, kick_spy):
        """POST /api/engine/restart kicks when pending games exist."""
        with _client(ScriptedEngine()) as c:
            c.post("/api/games/import", json={"pgn": _PGN})
            _enable_kick(monkeypatch)
            r = c.post("/api/engine/restart")
            assert r.status_code == 200
            assert len(kick_spy) == 1
        app.dependency_overrides.clear()

    def test_restart_no_pending_no_kick(self, monkeypatch, kick_spy):
        """POST /api/engine/restart with an empty DB does not kick."""
        with _client(ScriptedEngine()) as c:
            _enable_kick(monkeypatch)
            r = c.post("/api/engine/restart")
            assert r.status_code == 200
            assert kick_spy == []
        app.dependency_overrides.clear()


class TestLifespanKick:
    def test_lifespan_kicks_when_pending(self, monkeypatch, kick_spy):
        """Boot catch-up: lifespan kicks when the DB already has pending games.

        The env gate must be off *during* startup here, so the lifespan's own
        engine autostart is neutralised by swapping app.main.StockfishEngine
        for a fake (no real binary is ever spawned).
        """
        storage.insert_game({
            "content_hash": "lifespan-kick-test",
            "pgn": _PGN,
            "white": "Alice",
            "black": "Bob",
            "my_color": "white",
            "imported_at": datetime.now(timezone.utc).isoformat(),
        })
        monkeypatch.setattr("app.main.StockfishEngine", lambda: ScriptedEngine())
        _enable_kick(monkeypatch)
        with TestClient(app):
            assert len(kick_spy) == 1
            assert kick_spy[0]["depth"] == review_module.BACKGROUND_DEPTH
