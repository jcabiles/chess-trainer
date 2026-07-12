"""API tests for POST /api/games/fetch (lichess / chess.com auto-fetch).

All network I/O is faked with ``httpx.MockTransport`` injected via the
``app.fetch._transport`` seam — the suite stays fully offline. Engine routes
use ScriptedEngine like the rest of the games-API tests.

Coverage
--------
- lichess fetch: imports games, populates game_plies.clock_centis from the
  embedded [%clk] comments, tags my_color from the fetched username (both
  colors), and passes clocks=true/max to the API.
- idempotency: re-fetch imports 0 new, counts duplicates.
- chess.com fetch: walks the monthly archives newest-first, collects PGNs,
  skips a broken month without failing the batch.
- errors: unknown user -> 404 with detail; network failure -> 502; bad
  platform -> 422 (pydantic literal).
- auto-analysis kick: fetch uses the same _kick_auto_analysis seam as import.
- end-to-end: fetched clocked games, once analyzed, populate the Insights
  time-trouble buckets (the roadmap chain: fetch -> %clk -> clock_centis ->
  time_trouble card).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import app.fetch as fetch_module
import app.review as review_module
import app.storage as storage
from app.main import app, get_engine
from tests.engine_fakes import ScriptedEngine

# ---------------------------------------------------------------------------
# PGN fixtures — two short games with [%clk] comments; the fetched account
# ("testuser") is White in game 1 and Black in game 2.
# ---------------------------------------------------------------------------

_LICHESS_GAME_1 = (
    '[Event "Rated blitz game"]\n'
    '[Site "https://lichess.org/abcd0001"]\n'
    '[White "TestUser"]\n'
    '[Black "Rival1"]\n'
    '[Result "1-0"]\n'
    '\n'
    '1. e4 { [%clk 0:03:00] } e5 { [%clk 0:03:00] } '
    '2. Nf3 { [%clk 0:02:58] } Nc6 { [%clk 0:02:57] } 1-0\n'
)

_LICHESS_GAME_2 = (
    '[Event "Rated blitz game"]\n'
    '[Site "https://lichess.org/abcd0002"]\n'
    '[White "Rival2"]\n'
    '[Black "testuser"]\n'
    '[Result "0-1"]\n'
    '\n'
    '1. d4 { [%clk 0:03:00] } d5 { [%clk 0:03:00] } '
    '2. c4 { [%clk 0:02:55] } e6 { [%clk 0:02:54] } 0-1\n'
)

_LICHESS_BODY = _LICHESS_GAME_1 + "\n\n" + _LICHESS_GAME_2

_CHESSCOM_GAME = (
    '[Event "Live Chess"]\n'
    '[Site "Chess.com"]\n'
    '[White "testuser"]\n'
    '[Black "ComRival"]\n'
    '[Result "1/2-1/2"]\n'
    '\n'
    '1. Nf3 {[%clk 0:04:59.9]} Nf6 {[%clk 0:04:58.3]} 1/2-1/2\n'
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_storage(tmp_path: Path, monkeypatch):
    """Fresh temp DB per test; CHESS_USERNAME cleared so inference is isolated."""
    db_path = str(tmp_path / "fetch_api_test.db")
    monkeypatch.setenv("GAMES_DB", db_path)
    monkeypatch.delenv("CHESS_USERNAME", raising=False)
    storage.init(db_path)
    review_module._interactive_pending = 0
    yield
    for gid in list(review_module._tasks.keys()):
        review_module.cancel_analysis(gid)
    review_module._interactive_pending = 0


@pytest.fixture
def client():
    app.dependency_overrides[get_engine] = lambda: ScriptedEngine()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _install_transport(monkeypatch, handler):
    monkeypatch.setattr(fetch_module, "_transport", httpx.MockTransport(handler))


def _lichess_handler(captured: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "lichess.org"
        if captured is not None:
            captured["params"] = dict(request.url.params)
            captured["path"] = request.url.path
        if "/api/games/user/" not in request.url.path:
            return httpx.Response(500)
        user = request.url.path.rsplit("/", 1)[-1]
        if user == "ghost":
            return httpx.Response(404)
        return httpx.Response(200, text=_LICHESS_BODY)
    return handler


def _chesscom_handler(broken_month: bool = False):
    archives = {
        "archives": [
            "https://api.chess.com/pub/player/testuser/games/2026/05",
            "https://api.chess.com/pub/player/testuser/games/2026/06",
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.chess.com"
        path = request.url.path
        if path.endswith("/games/archives"):
            return httpx.Response(200, json=archives)
        if path.endswith("/2026/06"):
            if broken_month:
                return httpx.Response(500)
            return httpx.Response(200, json={"games": [{"pgn": _CHESSCOM_GAME}]})
        if path.endswith("/2026/05"):
            return httpx.Response(200, json={"games": [{"pgn": _CHESSCOM_GAME.replace("abcd", "wxyz")}]})
        return httpx.Response(404)
    return handler


# ---------------------------------------------------------------------------
# lichess
# ---------------------------------------------------------------------------


class TestLichessFetch:
    def test_fetch_imports_games_with_clocks(self, client, monkeypatch):
        """Fetched games persist with clock_centis populated and colors tagged."""
        captured: dict = {}
        _install_transport(monkeypatch, _lichess_handler(captured))

        r = client.post(
            "/api/games/fetch",
            json={"platform": "lichess", "username": "testuser"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fetched"] == 2
        assert body["imported"] == 2
        assert body["duplicates"] == 0

        # API request shape: clocks embedded, cap respected.
        assert captured["path"].endswith("/api/games/user/testuser")
        assert captured["params"]["clocks"] == "true"
        assert captured["params"]["max"] == "30"

        # Clock data actually landed — the whole point of API fetch.
        games = body["games"]
        assert len(games) == 2
        clocked = 0
        for g in games:
            plies = storage.get_plies(g["id"])
            assert plies, "fetched game should have ply rows"
            clocked += sum(1 for p in plies if p.get("clock_centis") is not None)
        assert clocked > 0

        # my_color inferred from the FETCHED username, both colors, no env var.
        by_white = {g["white"]: g for g in games}
        assert by_white["TestUser"]["my_color"] == "white"
        assert by_white["Rival2"]["my_color"] == "black"

    def test_refetch_is_idempotent(self, client, monkeypatch):
        _install_transport(monkeypatch, _lichess_handler())
        first = client.post(
            "/api/games/fetch", json={"platform": "lichess", "username": "testuser"}
        ).json()
        assert first["imported"] == 2

        again = client.post(
            "/api/games/fetch", json={"platform": "lichess", "username": "testuser"}
        ).json()
        assert again["imported"] == 0
        assert again["duplicates"] == 2

        # No extra rows in the library.
        assert len(client.get("/api/games").json()) == 2

    def test_unknown_user_is_404(self, client, monkeypatch):
        _install_transport(monkeypatch, _lichess_handler())
        r = client.post(
            "/api/games/fetch", json={"platform": "lichess", "username": "ghost"}
        )
        assert r.status_code == 404
        assert "not found" in r.json()["detail"]

    def test_network_error_is_502(self, client, monkeypatch):
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host", request=request)
        _install_transport(monkeypatch, boom)
        r = client.post(
            "/api/games/fetch", json={"platform": "lichess", "username": "testuser"}
        )
        assert r.status_code == 502
        assert "unreachable" in r.json()["detail"]

    def test_fetch_kicks_auto_analysis(self, client, monkeypatch):
        _install_transport(monkeypatch, _lichess_handler())
        kicks = []
        import app.main as main_module
        monkeypatch.setattr(main_module, "_kick_auto_analysis", lambda engine: kicks.append(1))
        r = client.post(
            "/api/games/fetch", json={"platform": "lichess", "username": "testuser"}
        )
        assert r.status_code == 200
        assert kicks, "fetch should reuse the import auto-analysis kick"


# ---------------------------------------------------------------------------
# chess.com
# ---------------------------------------------------------------------------


class TestChesscomFetch:
    def test_fetch_walks_archives_newest_first(self, client, monkeypatch):
        _install_transport(monkeypatch, _chesscom_handler())
        r = client.post(
            "/api/games/fetch", json={"platform": "chesscom", "username": "testuser"}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fetched"] == 2
        assert body["imported"] >= 1  # the two months carry near-identical PGNs
        games = body["games"]
        plies = storage.get_plies(games[0]["id"])
        assert any(p.get("clock_centis") is not None for p in plies)
        assert games[0]["my_color"] == "white"

    def test_broken_month_is_skipped_not_fatal(self, client, monkeypatch):
        _install_transport(monkeypatch, _chesscom_handler(broken_month=True))
        r = client.post(
            "/api/games/fetch", json={"platform": "chesscom", "username": "testuser"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["fetched"] == 1  # 2026/06 broke; 2026/05 still imported


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestFetchValidation:
    def test_unknown_platform_is_422(self, client):
        r = client.post(
            "/api/games/fetch", json={"platform": "icc", "username": "x"}
        )
        assert r.status_code == 422

    def test_empty_username_is_422(self, client):
        r = client.post(
            "/api/games/fetch", json={"platform": "lichess", "username": ""}
        )
        assert r.status_code == 422

    def test_max_games_capped_at_100(self, client):
        r = client.post(
            "/api/games/fetch",
            json={"platform": "lichess", "username": "x", "max_games": 500},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Fetch → clocks → Insights time-trouble (the roadmap slice-3/4 chain)
# ---------------------------------------------------------------------------


class TestFetchLightsUpTimeTrouble:
    def test_fetched_clocked_games_populate_time_trouble(self, client, monkeypatch):
        """Fetched %clk games, once analyzed, exit the time-trouble empty state.

        This is the end-to-end version of the roadmap pass/fail: before
        auto-fetch existed, 0 stored plies had clocks and the card could only
        show 'No clock data yet.'
        """
        _install_transport(monkeypatch, _lichess_handler())
        r = client.post(
            "/api/games/fetch", json={"platform": "lichess", "username": "testuser"}
        )
        assert r.status_code == 200
        game_ids = [g["id"] for g in r.json()["games"]]

        # Run the background analysis synchronously (neutral engine: no leaks,
        # but is_user_move gets tagged and analysis_status flips to 'done').
        for gid in game_ids:
            asyncio.run(review_module.analyze_game(gid, ScriptedEngine(), depth=8))

        body = client.get("/api/insights/mistakes").json()
        tt = body["time_trouble"]
        assert tt["clocked_games"] == 2
        assert tt["unclocked_games"] == 0
        assert sum(b["moves"] for b in tt["buckets"]) > 0
