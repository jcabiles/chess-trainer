"""API tests for the play-vs-bot routes (B2).

The bot engine is a FAKE injected via FastAPI dependency override
(``app.dependency_overrides[get_bot_engine]``), so the whole suite runs with no
Stockfish binary present. The routes own the validation ladder — the fake bot's
``candidates()`` is only reached for already-valid, non-terminal positions.
"""

from __future__ import annotations

import chess
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.bot_engine import EngineUnavailable, get_bot_engine
from app.main import BOT_PERSONA_LABEL, app

START_FEN = chess.STARTING_FEN


class FakeBot:
    """Minimal stand-in for BotEngine.

    ``candidates(fen, k)`` returns the position's first legal move (best-first,
    length 1) — enough to exercise the route wiring + SAN/FEN consistency. The
    route owns FEN validity + terminal checks, so this is only reached for
    playable positions. Does NOT itself validate is_valid/terminal, matching the
    real seam.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def candidates(
        self, fen: str, k: int = 1, elo: int | None = None
    ) -> list[dict]:
        # Real-signature fake: the persona branch passes elo= (a FakeBot
        # without it TypeErrors into a 500 — pre-existing gap closed at T4).
        self.calls.append((fen, k))
        board = chess.Board(fen)
        move = next(iter(board.legal_moves))
        return [{"uci": move.uci(), "san": board.san(move), "scoreCp": 0}]

    async def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


class DownBot:
    """Fake bot whose ``candidates`` always raises EngineUnavailable (binary down)."""

    async def candidates(self, fen: str, k: int = 1) -> list[dict]:
        raise EngineUnavailable("no binary")

    async def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


@pytest.fixture
def client():
    fake = FakeBot()
    app.dependency_overrides[get_bot_engine] = lambda: fake
    with TestClient(app) as c:
        c.fake_bot = fake  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def down_client():
    app.dependency_overrides[get_bot_engine] = lambda: DownBot()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --- /api/bot/move: happy path ---------------------------------------------


def test_bot_move_legal_reply(client):
    resp = client.post("/api/bot/move", json={"fen": START_FEN})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"moveUci", "moveSan", "fen", "engine"}
    assert body["engine"] == "stockfish"
    # The move is legal in the starting position.
    board = chess.Board(START_FEN)
    assert chess.Move.from_uci(body["moveUci"]) in board.legal_moves


def test_bot_move_as_white_first_move(client):
    """Bot-as-White first move: pass the standard start, get a legal White move."""
    resp = client.post("/api/bot/move", json={"fen": START_FEN})
    assert resp.status_code == 200
    board = chess.Board(START_FEN)
    assert board.turn == chess.WHITE
    assert chess.Move.from_uci(resp.json()["moveUci"]) in board.legal_moves


def test_bot_move_san_fen_consistency(client):
    """Applying moveUci to the INPUT fen yields the returned fen; moveSan matches."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    resp = client.post("/api/bot/move", json={"fen": fen})
    assert resp.status_code == 200
    body = resp.json()

    board = chess.Board(fen)
    move = chess.Move.from_uci(body["moveUci"])
    assert body["moveSan"] == board.san(move)
    board.push(move)
    assert board.fen() == body["fen"]


# --- /api/bot/move: validation ladder --------------------------------------


def test_bot_move_unparseable_fen(client):
    resp = client.post("/api/bot/move", json={"fen": "not a fen at all"})
    assert resp.status_code == 400
    assert "unparseable" in resp.json()["detail"].lower()
    assert client.fake_bot.calls == []  # never reached the engine


def test_bot_move_valid_syntax_but_illegal_position(client):
    # Syntactically well-formed FEN but an illegal position: two white kings.
    resp = client.post(
        "/api/bot/move",
        json={"fen": "4k3/8/8/8/8/8/8/4K1K1 w - - 0 1"},
    )
    assert resp.status_code == 400
    assert "illegal position" in resp.json()["detail"].lower()
    assert client.fake_bot.calls == []


def test_bot_move_terminal_checkmate(client):
    # Fool's mate — Black is checkmated, White delivered mate.
    fen = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
    resp = client.post("/api/bot/move", json={"fen": fen})
    assert resp.status_code == 400
    assert "checkmate" in resp.json()["detail"].lower()
    assert client.fake_bot.calls == []


def test_bot_move_terminal_stalemate(client):
    # Classic stalemate: Black to move, no legal move, not in check.
    fen = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    resp = client.post("/api/bot/move", json={"fen": fen})
    assert resp.status_code == 400
    assert "stalemate" in resp.json()["detail"].lower()
    assert client.fake_bot.calls == []


def test_bot_move_terminal_insufficient_material(client):
    # King vs king — insufficient material, a draw.
    fen = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
    resp = client.post("/api/bot/move", json={"fen": fen})
    assert resp.status_code == 400
    assert "insufficient" in resp.json()["detail"].lower()
    assert client.fake_bot.calls == []


def test_bot_move_terminal_reasons_are_distinct(client):
    mate = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
    stale = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    insuf = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
    details = {
        client.post("/api/bot/move", json={"fen": f}).json()["detail"]
        for f in (mate, stale, insuf)
    }
    assert len(details) == 3  # each terminal reason is distinct


# --- /api/bot/move: engine down --------------------------------------------


def test_bot_move_engine_down_503(down_client):
    resp = down_client.post("/api/bot/move", json={"fen": START_FEN})
    assert resp.status_code == 503
    assert "detail" in resp.json()


class EmptyBot:
    """Fake bot whose ``candidates`` returns [] for a non-terminal position
    (engine yielded no usable PV at the fixed budget)."""

    async def candidates(self, fen: str, k: int = 1) -> list[dict]:
        return []

    async def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


def test_bot_move_empty_candidates_503():
    """A non-terminal position with no engine candidate is a recoverable 503,
    not an unhandled 500 (IndexError on cands[0])."""
    app.dependency_overrides[get_bot_engine] = lambda: EmptyBot()
    try:
        with TestClient(app) as c:
            resp = c.post("/api/bot/move", json={"fen": START_FEN})
        assert resp.status_code == 503
        assert "detail" in resp.json()
    finally:
        app.dependency_overrides.clear()


# --- /api/bot/status -------------------------------------------------------


def test_bot_status_available_true(monkeypatch):
    monkeypatch.setattr(main, "_locate_binary", lambda: "/usr/bin/stockfish")
    monkeypatch.setattr(main, "detect_maia", lambda: {"lc0": False, "weights": []})
    with TestClient(app) as c:
        resp = c.get("/api/bot/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["personaLabel"] == BOT_PERSONA_LABEL
    assert body["maia"] == {
        "lc0": False,
        "weights": [],
        "personas": {"casey": False},
    }


def test_bot_status_available_false(monkeypatch):
    def _raise() -> str:
        raise EngineUnavailable("no binary")

    monkeypatch.setattr(main, "_locate_binary", _raise)
    monkeypatch.setattr(main, "detect_maia", lambda: {"lc0": False, "weights": []})
    with TestClient(app) as c:
        resp = c.get("/api/bot/status")
    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_bot_status_maia_shape(monkeypatch):
    monkeypatch.setattr(main, "_locate_binary", lambda: "/usr/bin/stockfish")
    monkeypatch.setattr(
        main,
        "detect_maia",
        lambda: {"lc0": True, "weights": ["/home/u/maia_weights/maia-1500.pb.gz"]},
    )
    with TestClient(app) as c:
        resp = c.get("/api/bot/status")
    maia = resp.json()["maia"]
    assert set(maia) == {"lc0", "weights", "personas"}
    assert isinstance(maia["lc0"], bool)
    assert isinstance(maia["weights"], list)
    # Per-persona readiness (Maia skeleton): conftest's _maia_off fixture
    # points MAIA_WEIGHTS_DIR at an empty dir, so casey reads not-ready here.
    assert maia["personas"] == {"casey": False}


# --- Maia-first branch (Maia skeleton) --------------------------------------
# The route serves a Maia-wired persona (casey) from the lc0/Maia engine when
# ready, bypassing the SF persona pipeline; ANY MaiaUnavailable falls through
# to the SF path in the SAME request. Seam: monkeypatch main.maia_ready_for +
# main.get_maia_engine (bare-name imports — the spec-pinned patch target).

from app.maia_engine import MaiaUnavailable  # noqa: E402


class FakeMaia:
    """Real-signature Maia fake: top_move(fen, persona_id)."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail = fail

    async def top_move(self, fen: str, persona_id: str) -> dict:
        self.calls.append((fen, persona_id))
        if self._fail is not None:
            raise self._fail
        board = chess.Board(fen)
        move = chess.Move.from_uci("e2e4")
        return {"uci": move.uci(), "san": board.san(move), "priors": []}

    async def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


def _maia_client(monkeypatch, maia: FakeMaia):
    monkeypatch.setattr(main, "maia_ready_for", lambda pid: pid == "casey")
    monkeypatch.setattr(main, "get_maia_engine", lambda: maia)
    fake = FakeBot()
    app.dependency_overrides[get_bot_engine] = lambda: fake
    return fake


def test_casey_served_by_maia_when_ready(monkeypatch):
    maia = FakeMaia()
    fake = _maia_client(monkeypatch, maia)
    with TestClient(app) as c:
        resp = c.post(
            "/api/bot/move",
            json={"fen": START_FEN, "personaId": "casey", "ply": 0, "seed": 1},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine"] == "maia"
    assert body["moveUci"] == "e2e4"
    assert maia.calls == [(START_FEN, "casey")]
    assert fake.calls == []  # SF pipeline fully bypassed


def test_maia_unavailable_falls_back_same_request(monkeypatch):
    maia = FakeMaia(fail=MaiaUnavailable("lc0 died"))
    fake = _maia_client(monkeypatch, maia)
    with TestClient(app) as c:
        resp = c.post(
            "/api/bot/move",
            json={"fen": START_FEN, "personaId": "casey", "ply": 20, "seed": 1},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine"] == "stockfish"  # same-request SF fallback, not 503
    assert len(maia.calls) == 1
    assert len(fake.calls) == 1  # SF pipeline served the move


def test_non_maia_persona_never_touches_maia(monkeypatch):
    maia = FakeMaia()
    fake = _maia_client(monkeypatch, maia)
    with TestClient(app) as c:
        resp = c.post(
            "/api/bot/move",
            json={"fen": START_FEN, "personaId": "morgan", "ply": 20, "seed": 1},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["engine"] == "stockfish"
    assert maia.calls == []
    assert len(fake.calls) == 1


def test_maia_not_ready_uses_sf_directly(monkeypatch):
    # Readiness false (the suite-wide default) → Maia engine never consulted.
    maia = FakeMaia()
    monkeypatch.setattr(main, "get_maia_engine", lambda: maia)
    fake = FakeBot()
    app.dependency_overrides[get_bot_engine] = lambda: fake
    with TestClient(app) as c:
        resp = c.post(
            "/api/bot/move",
            json={"fen": START_FEN, "personaId": "casey", "ply": 20, "seed": 1},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["engine"] == "stockfish"
    assert maia.calls == []
