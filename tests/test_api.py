"""API tests for the Stockfish Analysis Board.

Engine-dependent routes use a FAKE engine injected via FastAPI dependency
overrides, so the whole suite runs with no Stockfish binary present. Routes that
reject input before any engine call (bad FEN, illegal move) are tested directly.
"""

from __future__ import annotations

import chess
import chess.engine as chess_engine
import pytest
from fastapi.testclient import TestClient

from app.engine import AnalysisResult
from app.main import app, get_engine

START_FEN = chess.STARTING_FEN


class FakeEngine:
    """Minimal stand-in for StockfishEngine.

    Returns a fixed, even evaluation regardless of position. That is enough to
    exercise the route wiring + response shapes; the *correctness* of the
    classification math is covered by tests/test_analysis.py.

    ``analyze_call_count`` is incremented on every call to ``analyze`` so tests
    can assert the engine was or was not consulted without touching any other
    part of the fake's contract.
    """

    def __init__(self, cp: int = 20):
        self._cp = cp
        self.analyze_call_count: int = 0

    @property
    def is_running(self) -> bool:
        return True

    async def restart(self) -> None:
        """No-op restart for test use."""

    async def analyze(self, fen: str, depth: int = 18) -> AnalysisResult:
        self.analyze_call_count += 1
        board = chess.Board(fen)
        score = chess_engine.PovScore(chess_engine.Cp(self._cp), chess.WHITE)
        # Render a plausible best-move SAN from the position's first legal move.
        pv = list(board.legal_moves)[:1]
        pv_san = [board.san(pv[0])] if pv else []
        return AnalysisResult(score=score, pv=pv, pv_san=pv_san, depth=depth)


@pytest.fixture
def client():
    fake = FakeEngine()
    app.dependency_overrides[get_engine] = lambda: fake
    with TestClient(app) as c:
        c.fake_engine = fake  # type: ignore[attr-defined]  # exposed for call-count assertions
        yield c
    app.dependency_overrides.clear()


# --- routes that don't need an engine --------------------------------------

def test_load_invalid_fen(client):
    r = client.post("/api/load", json={"fen": "this is not a fen"})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert body["analysis"] is None
    assert body["error"]


def test_move_illegal(client):
    # e2e5 is not a legal opening move.
    r = client.post("/api/move", json={"fen": START_FEN, "move": "e2e5"})
    assert r.status_code == 200
    assert r.json() == {
        "legal": False, "fen": None, "lastMoveSan": None, "analysis": None,
        "book": False, "openingName": None, "openingEco": None,
    }


def test_move_bad_uci(client):
    r = client.post("/api/move", json={"fen": START_FEN, "move": "zzzz"})
    assert r.status_code == 200
    assert r.json()["legal"] is False


def test_move_bad_fen(client):
    r = client.post("/api/move", json={"fen": "garbage", "move": "e2e4"})
    assert r.status_code == 200
    assert r.json()["legal"] is False


# --- routes that use the (fake) engine -------------------------------------

def test_analyze_ok(client):
    r = client.post("/api/analyze", json={"fen": START_FEN})
    assert r.status_code == 200
    analysis = r.json()["analysis"]
    assert analysis["evalWhitePov"] == 20
    assert analysis["evalCp"] == 20
    assert analysis["mate"] is None
    assert analysis["quality"] is None  # no prior move
    assert analysis["bestMoveSan"]


def test_load_valid(client):
    r = client.post("/api/load", json={"fen": START_FEN})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["fen"] == chess.Board(START_FEN).fen()
    assert body["analysis"]["quality"] is None


def test_move_legal_labels_quality(client):
    r = client.post("/api/move", json={"fen": START_FEN, "move": "e2e4"})
    assert r.status_code == 200
    body = r.json()
    assert body["legal"] is True
    assert body["lastMoveSan"] == "e4"
    # FEN advanced + black to move.
    assert body["fen"] != START_FEN
    assert " b " in body["fen"]
    # Even eval before/after via the fake → zero cpLoss → "best".
    assert body["analysis"]["quality"] in {
        "best", "good", "inaccuracy", "mistake", "blunder"
    }
    assert body["analysis"]["quality"] == "best"


def test_move_promotion_uci_accepted(client):
    # White pawn on e7, black king far away; e7e8q is the only sensible move set.
    fen = "8/4P3/8/8/8/8/k7/4K3 w - - 0 1"
    r = client.post("/api/move", json={"fen": fen, "move": "e7e8q"})
    assert r.status_code == 200
    body = r.json()
    assert body["legal"] is True
    assert body["lastMoveSan"].startswith("e8=Q")


# --- engine control routes -------------------------------------------------

def test_engine_status_ok(client):
    """GET /api/engine/status returns 200 with running:true from FakeEngine."""
    r = client.get("/api/engine/status")
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is True


def test_engine_restart_ok(client):
    """POST /api/engine/restart returns 200 with restarted:true."""
    r = client.post("/api/engine/restart")
    assert r.status_code == 200
    body = r.json()
    assert body["restarted"] is True
    assert isinstance(body["running"], bool)


def test_engine_restart_running_reflects_fake(client):
    """running field after restart matches FakeEngine.is_running (True)."""
    r = client.post("/api/engine/restart")
    assert r.status_code == 200
    assert r.json()["running"] is True


def test_move_still_works_after_restart(client):
    """Existing happy-path move route is unaffected by the new engine routes."""
    # Confirm restart doesn't disturb subsequent move analysis.
    client.post("/api/engine/restart")
    r = client.post("/api/move", json={"fen": START_FEN, "move": "e2e4"})
    assert r.status_code == 200
    body = r.json()
    assert body["legal"] is True
    assert body["lastMoveSan"] == "e4"


# --- analyze=false flag ----------------------------------------------------

# Use an endgame FEN (pawn promotion position) that is guaranteed to be outside
# any opening book, so the book fast-path never fires and the new `analyze`
# flag is the sole reason the engine is skipped.
_ENDGAME_FEN = "8/4P3/8/8/8/8/k7/4K3 w - - 0 1"
_ENDGAME_MOVE = "e7e8q"  # legal pawn promotion


def test_move_analyze_false_skips_engine(client):
    """POST /api/move with analyze:false must return legal move data but null
    analysis, and must NOT call the engine at all.
    """
    calls_before = client.fake_engine.analyze_call_count
    r = client.post(
        "/api/move",
        json={"fen": _ENDGAME_FEN, "move": _ENDGAME_MOVE, "analyze": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["legal"] is True
    assert body["analysis"] is None
    assert body["fen"] is not None
    assert body["lastMoveSan"] is not None
    # Engine must not have been called at all during this request.
    assert client.fake_engine.analyze_call_count == calls_before


def test_move_analyze_omitted_still_analyzes(client):
    """When `analyze` is omitted the default (True) applies: analysis is present
    and quality is labelled — identical to the existing happy-path behaviour.
    """
    r = client.post(
        "/api/move",
        json={"fen": _ENDGAME_FEN, "move": _ENDGAME_MOVE},
        # `analyze` intentionally absent → server default True
    )
    assert r.status_code == 200
    body = r.json()
    assert body["legal"] is True
    assert body["fen"] is not None
    assert body["lastMoveSan"] is not None
    assert body["analysis"] is not None
    assert body["analysis"]["quality"] in {
        "best", "good", "inaccuracy", "mistake", "blunder"
    }
    # Engine must have been called (before + after = 2 calls for this request).
    assert client.fake_engine.analyze_call_count >= 2
