"""
API tests for the opening-book fast-path on POST /api/move.

The engine is a BoomEngine that RAISES if analyze() is ever called, so a passing
"book move" test proves the engine was skipped. A deterministic fixture book is
installed via book.load() because book.is_book_move is a module-level call (not a
dependency) and the real lifespan would otherwise load the shipped data.
No Stockfish binary needed.
"""

from __future__ import annotations

import chess
import pytest
from fastapi.testclient import TestClient

from app import book
from app.engine import EngineUnavailable
from app.main import app, get_engine

START = chess.STARTING_FEN
FIXTURE = "tests/fixtures/book_sample.json"   # firstMoves = ["e2e4"]


class BoomEngine:
    """Any engine call means the book fast-path FAILED to skip the engine."""

    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, fen: str, depth: int = 18):
        self.calls += 1
        raise EngineUnavailable("engine was called")

    async def analyze_interactive_multi(
        self, fen: str, depth: int = 18, multipv: int = 1
    ):
        # make_move funnels through here now; still a "boom" — proves the book
        # fast-path skipped the engine when calls stays 0.
        self.calls += 1
        raise EngineUnavailable("engine was called")


@pytest.fixture(scope="module")
def boom() -> BoomEngine:
    return BoomEngine()


@pytest.fixture(scope="module")
def client(boom):
    app.dependency_overrides[get_engine] = lambda: boom
    with TestClient(app) as c:   # runs the real lifespan
        # Install a deterministic book: only the 1.e4 e5 2.Nf3 line is in scope.
        book.load(FIXTURE, lines=[["e2e4", "e7e5", "g1f3"]], trap_ucis=[])
        yield c
    app.dependency_overrides.clear()
    book.load("tests/fixtures/does_not_exist.json")  # reset to empty afterwards


def test_book_move_skips_engine(client, boom):
    boom.calls = 0
    r = client.post("/api/move", json={"fen": START, "move": "e2e4", "useBook": True})
    assert r.status_code == 200
    body = r.json()
    assert body["book"] is True
    assert body["legal"] is True
    assert body["analysis"] is None
    assert body["lastMoveSan"] == "e4"
    assert boom.calls == 0   # engine never touched


def test_book_move_includes_opening_name(client, boom):
    boom.calls = 0
    # The real lifespan loaded the real openings index, so the position after 1.e4
    # resolves to a named line; the badge name rides on the book response.
    r = client.post("/api/move", json={"fen": START, "move": "e2e4", "useBook": True})
    body = r.json()
    assert body["book"] is True
    assert isinstance(body["openingName"], str) and body["openingName"]
    assert isinstance(body["openingEco"], str) and body["openingEco"]
    assert boom.calls == 0


def test_offbook_move_uses_engine(client, boom):
    boom.calls = 0
    # 1.a4 is not in book -> falls through to the engine (BoomEngine -> 503).
    r = client.post("/api/move", json={"fen": START, "move": "a2a4", "useBook": True})
    assert boom.calls == 1
    assert r.status_code == 503


def test_usebook_false_always_uses_engine(client, boom):
    boom.calls = 0
    # Even a book move must hit the engine when useBook is false (trap-practice path).
    r = client.post("/api/move", json={"fen": START, "move": "e2e4", "useBook": False})
    assert boom.calls == 1
    assert r.status_code == 503


def test_usebook_defaults_false(client, boom):
    boom.calls = 0
    # Omitting useBook entirely defaults to full analysis.
    client.post("/api/move", json={"fen": START, "move": "e2e4"})
    assert boom.calls == 1
