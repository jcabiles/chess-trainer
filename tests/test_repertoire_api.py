"""
API tests for the repertoire trainer: GET /api/repertoire + Analysis.bestMoveUci.

A fake engine is injected so no Stockfish binary is needed. TestClient runs the
real lifespan, which loads the shipped data/repertoire.json.
"""

from __future__ import annotations

import chess
import chess.engine as chess_engine
import pytest
from fastapi.testclient import TestClient

from app import repertoire
from app.engine import AnalysisResult
from app.main import app, get_engine

START = chess.STARTING_FEN


class FakeEngine:
    """Returns the position's first legal move as a one-move PV."""

    async def analyze(self, fen: str, depth: int = 18) -> AnalysisResult:
        board = chess.Board(fen)
        score = chess_engine.PovScore(chess_engine.Cp(10), chess.WHITE)
        pv = list(board.legal_moves)[:1]
        pv_san = [board.san(pv[0])] if pv else []
        return AnalysisResult(score=score, pv=pv, pv_san=pv_san, depth=depth)

    async def analyze_interactive_multi(
        self, fen: str, depth: int = 18, multipv: int = 1
    ) -> list[AnalysisResult]:
        board = chess.Board(fen)
        score = chess_engine.PovScore(chess_engine.Cp(10), chess.WHITE)
        moves = list(board.legal_moves)[:multipv]
        results = [
            AnalysisResult(score=score, pv=[m], pv_san=[board.san(m)], depth=depth)
            for m in moves
        ]
        return results or [AnalysisResult(score=score, pv=[], pv_san=[], depth=depth)]


class NoPvEngine:
    """Returns an empty PV (no best move) — terminal-ish."""

    async def analyze(self, fen: str, depth: int = 18) -> AnalysisResult:
        score = chess_engine.PovScore(chess_engine.Cp(0), chess.WHITE)
        return AnalysisResult(score=score, pv=[], pv_san=[], depth=depth)

    async def analyze_interactive_multi(
        self, fen: str, depth: int = 18, multipv: int = 1
    ) -> list[AnalysisResult]:
        score = chess_engine.PovScore(chess_engine.Cp(0), chess.WHITE)
        return [AnalysisResult(score=score, pv=[], pv_san=[], depth=depth)]


@pytest.fixture
def client():
    app.dependency_overrides[get_engine] = lambda: FakeEngine()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --- GET /api/repertoire ---------------------------------------------------


def test_repertoire_route_shape(client):
    r = client.get("/api/repertoire")
    assert r.status_code == 200
    tree = r.json()["tree"]
    assert {"white", "black", "catalog"} <= set(tree)
    assert isinstance(tree["catalog"]["white"], list) and tree["catalog"]["white"]
    # As White, the first move is the single forced 1.e4.
    assert tree["white"]["children"][0]["uci"] == "e2e4"


def test_repertoire_empty_degrades(client):
    repertoire.load("/nonexistent/repertoire.json")
    try:
        r = client.get("/api/repertoire")
        assert r.status_code == 200
        tree = r.json()["tree"]
        assert tree["white"]["children"] == []
        assert tree["catalog"] == {"white": [], "black": []}
    finally:
        repertoire.init("data/repertoire.json")  # restore for other tests


# --- Analysis.bestMoveUci --------------------------------------------------


def test_bestmoveuci_present(client):
    r = client.post("/api/analyze", json={"fen": START})
    analysis = r.json()["analysis"]
    assert isinstance(analysis["bestMoveUci"], str)
    assert len(analysis["bestMoveUci"]) >= 4
    # SAN + UCI describe the same best move.
    assert analysis["bestMoveSan"]


def test_bestmoveuci_none_when_no_pv():
    app.dependency_overrides[get_engine] = lambda: NoPvEngine()
    try:
        with TestClient(app) as c:
            r = c.post("/api/analyze", json={"fen": START})
            assert r.json()["analysis"]["bestMoveUci"] is None
    finally:
        app.dependency_overrides.clear()
