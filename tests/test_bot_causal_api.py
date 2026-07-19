"""API tests for the B5 causal-blunder gate wired into ``POST /api/bot/move``.

The bot engine is a FAKE injected via ``app.dependency_overrides[get_bot_engine]``
(like ``tests/test_bot_personas_api.py``), so the suite runs with no Stockfish
binary. These tests exercise T3 — the gate-FIRST wiring in the persona path:

- a PLANTED off-plan-threat position (bot to move, opponent threatening a hanging
  minor on the far wing, ``recentMoves`` establishing a disjoint kingside plan) +
  a high-blunderRate persona (casey) + a firing seed ⇒ the route plays a move that
  does NOT address the threat (the gated causal blunder), via ONE candidates()
  call at k=CAND_K.
- a QUIET late-ply position (no threat) ⇒ the UNCHANGED B4 path: k=1 + best.
- a bare ``{fen}`` (no persona) ⇒ B3-identical (k=1, elo=None, candidate 0).
- mover-POV is respected inside the gate: a Black bot's survivor selection picks
  the best-FOR-BLACK survivor (most-negative White-POV score).
"""

from __future__ import annotations

import chess
import pytest
from fastapi.testclient import TestClient

from app.bot_engine import get_bot_engine
from app.main import CAND_K, app

# --- planted positions -------------------------------------------------------

# White to move, middlegame (game_phase → 'middlegame'), NO back-rank (king has
# luft on h3): a White knight on a4 (far queenside wing) is hanging to ...b5xa4.
# The bot's plan (recentMoves) is entirely kingside → the a4 threat is fully
# off-plan (off_plan_score == 1.0 > casey.threatDistance).
BLUNDER_FEN = "r2q1rk1/pp3ppp/2n1pn2/1p6/N7/5NPP/PP2PPB1/R2Q1RK1 w - - 0 20"
BLUNDER_PLAN = ["g2g3", "h2h3", "f3g5", "g5f3"]  # kingside, disjoint from a4
A4_SQUARE = chess.A4  # the hanging knight's square (the threat target)
FIRING_SEED = 1  # casey fires should_blunder at this seed / ply=40 for BLUNDER_FEN
FIRING_PLY = 40

# Black to move, middlegame: a Black knight on a5 (far queenside) is hanging.
# Used to prove the mover-POV flip inside pick_survivor for a Black bot.
BLACK_BLUNDER_FEN = "r2q1rk1/pp2ppb1/5npp/n7/1P6/2N1PN2/PPP2PPP/R2Q1RK1 b - - 0 20"
BLACK_BLUNDER_PLAN = ["g8f6", "f6g8", "f8g7", "g7f8"]  # kingside
A5_SQUARE = chess.A5

# Quiet middlegame (no threat on the null-move board) at a late ply → B4 path.
QUIET_FEN = "r4rk1/pp2bppp/4p3/3p4/3P4/4PN2/PP3PPP/R4RK1 w - - 0 24"

START_FEN = chess.STARTING_FEN


class RecordingBot:
    """Fake bot recording each ``candidates`` call and returning up to ``k`` legal
    moves, each with a White-POV ``scoreCp`` from ``score_map`` (uci→cp) or 0."""

    def __init__(self, score_map: dict[str, int] | None = None) -> None:
        self.calls: list[dict] = []
        self.score_map = score_map or {}

    async def candidates(self, fen: str, k: int = 1, elo: int | None = None) -> list[dict]:
        self.calls.append({"fen": fen, "k": k, "elo": elo})
        board = chess.Board(fen)
        out: list[dict] = []
        for move in list(board.legal_moves)[:k]:
            uci = move.uci()
            out.append(
                {"uci": uci, "san": board.san(move), "scoreCp": self.score_map.get(uci, 0)}
            )
        return out

    async def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


@pytest.fixture
def client():
    fake = RecordingBot()
    app.dependency_overrides[get_bot_engine] = lambda: fake
    with TestClient(app) as c:
        c.fake_bot = fake  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


def _make_client(score_map: dict[str, int] | None = None):
    fake = RecordingBot(score_map=score_map)
    app.dependency_overrides[get_bot_engine] = lambda: fake
    c = TestClient(app)
    c.fake_bot = fake  # type: ignore[attr-defined]
    return c


# --- the gated causal blunder -----------------------------------------------


def test_gate_fires_plays_move_that_ignores_the_threat(client):
    """Planted off-plan threat + casey + firing seed ⇒ the route plays a move that
    does NOT address the hanging knight (a survivor), via ONE k=CAND_K call."""
    resp = client.post(
        "/api/bot/move",
        json={
            "fen": BLUNDER_FEN,
            "personaId": "casey",
            "ply": FIRING_PLY,
            "seed": FIRING_SEED,
            "recentMoves": BLUNDER_PLAN,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Exactly ONE engine call, at the widened blunder budget + casey's Elo.
    assert len(client.fake_bot.calls) == 1
    assert client.fake_bot.calls[0]["k"] == CAND_K
    assert client.fake_bot.calls[0]["elo"] == 1350  # casey

    # The played move must LEAVE the a4 knight where it is (a survivor) — it must
    # NOT be a knight move from a4 (which would neutralize the threat).
    move = chess.Move.from_uci(body["moveUci"])
    assert move.from_square != A4_SQUARE, "gate should ignore the threat, not move the knight"


def test_gate_is_deterministic_under_seed(client):
    """Same (fen, persona, ply, seed, recentMoves) ⇒ the same gated move twice."""
    body = {
        "fen": BLUNDER_FEN,
        "personaId": "casey",
        "ply": FIRING_PLY,
        "seed": FIRING_SEED,
        "recentMoves": BLUNDER_PLAN,
    }
    a = client.post("/api/bot/move", json=body).json()["moveUci"]
    b = client.post("/api/bot/move", json=body).json()["moveUci"]
    assert a == b


def test_high_elo_persona_defends_the_same_threat(client):
    """Vera (low blunderRate, high threatDistance) does NOT blunder the same
    position at the same seed — the gate stays closed → the B4 late path (k=1)."""
    resp = client.post(
        "/api/bot/move",
        json={
            "fen": BLUNDER_FEN,
            "personaId": "vera",
            "ply": FIRING_PLY,
            "seed": FIRING_SEED,
            "recentMoves": BLUNDER_PLAN,
        },
    )
    assert resp.status_code == 200, resp.text
    # Gate closed ⇒ B4 post-opening path: a single k=1 call at vera's Elo.
    assert client.fake_bot.calls == [{"fen": BLUNDER_FEN, "k": 1, "elo": 2000}]


# --- mover-POV inside the gate (Black bot) -----------------------------------


def test_black_bot_gate_picks_best_for_black_survivor():
    """Black-to-move planted blunder: all first-5 legal moves are survivors, given
    distinct White-POV scores. pick_survivor must choose the best-FOR-BLACK one
    (most-negative White-POV) — proving the mover-POV flip inside the gate."""
    board = chess.Board(BLACK_BLUNDER_FEN)
    legal = list(board.legal_moves)[:CAND_K]
    white_scores = [300, 100, -50, -200, -500][: len(legal)]
    score_map = {m.uci(): s for m, s in zip(legal, white_scores)}
    best_for_black_uci = min(score_map, key=lambda u: score_map[u])  # most-negative

    c = _make_client(score_map=score_map)
    try:
        resp = c.post(
            "/api/bot/move",
            json={
                "fen": BLACK_BLUNDER_FEN,
                "personaId": "casey",
                "ply": FIRING_PLY,
                "seed": FIRING_SEED,
                "recentMoves": BLACK_BLUNDER_PLAN,
            },
        )
        assert resp.status_code == 200, resp.text
        move = chess.Move.from_uci(resp.json()["moveUci"])
        # It ignored the a5 threat (a survivor) ...
        assert move.from_square != A5_SQUARE
        # ... and among survivors it picked the best FOR BLACK.
        assert resp.json()["moveUci"] == best_for_black_uci
    finally:
        app.dependency_overrides.clear()


# --- quiet late position: B4 parity (k=1 + best) -----------------------------


def test_quiet_late_position_plays_best_k1(client):
    """No off-plan threat at a late ply ⇒ the UNCHANGED B4 post-opening path:
    a single k=1 call at the persona's Elo, playing candidate 0 (best)."""
    resp = client.post(
        "/api/bot/move",
        json={
            "fen": QUIET_FEN,
            "personaId": "casey",
            "ply": FIRING_PLY,
            "seed": FIRING_SEED,
            "recentMoves": BLUNDER_PLAN,
        },
    )
    assert resp.status_code == 200, resp.text
    assert client.fake_bot.calls == [{"fen": QUIET_FEN, "k": 1, "elo": 1350}]
    # Best = candidate 0 = first legal move.
    board = chess.Board(QUIET_FEN)
    first = next(iter(board.legal_moves))
    assert resp.json()["moveUci"] == first.uci()


# --- bare {fen} + no persona: B3-identical (regression) ----------------------


def test_bare_fen_is_b3_identical(client):
    """No personaId ⇒ legacy branch: exactly one k=1 call, elo=None, candidate 0 —
    the gate never touches the legacy path. recentMoves default keeps it valid."""
    resp = client.post("/api/bot/move", json={"fen": START_FEN})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"moveUci", "moveSan", "fen", "engine"}
    assert client.fake_bot.calls == [{"fen": START_FEN, "k": 1, "elo": None}]

    board = chess.Board(START_FEN)
    first = next(iter(board.legal_moves))
    assert body["moveUci"] == first.uci()
    board.push(first)
    assert body["fen"] == board.fen()
