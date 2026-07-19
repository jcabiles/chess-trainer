"""API tests for the sloppy-persona MISTAKE tier (T3 wiring in /api/bot/move).

The bot engine is a FAKE injected via ``app.dependency_overrides[get_bot_engine]``
(like ``tests/test_bot_personas_api.py``), so the whole suite runs with no
Stockfish binary. These tests exercise ONLY the mistake sub-branch added to the
persona post-opening ``else`` block:

- a Robin (``mistakeRate=0.5``) request at a post-opening ply with a seed that
  trips ``should_mistake`` plays a sub-optimal IN-BAND candidate (index != 0),
  deterministic across two identical requests, via a SINGLE candidates() call;
- a Casey / Vera request (``mistakeRate=0``) at the SAME ply plays best (index 0)
  — B4 late-ply parity, mistake sub-branch unreachable;
- a bare ``{fen}`` (no personaId) stays B3-identical (k=1, elo=None, cand 0);
- a Black-to-move Robin request selects by MOVER-POV correctly.

The scenario position is a reduced-material MIDDLEGAME (``game_phase`` != opening,
so ``should_mistake``'s ``phase_gate`` is 1.0) with NO opponent threat (so the B5
blunder gate cannot fire and short-circuit the mistake path). Seed=0, ply=24 is a
firing draw for ``should_mistake`` at ``mistakeRate=0.5``.
"""

from __future__ import annotations

import chess
import pytest
from fastapi.testclient import TestClient

from app.bot_engine import get_bot_engine
from app.main import app

# Reduced-material middlegame, no immediate threat for the side to move.
# White to move; the mirror Black-to-move FEN is used for the mover-POV test.
MID_FEN_W = "r4rk1/ppp2ppp/2n5/4p3/4P3/2N5/PPP2PPP/R4RK1 w - - 0 15"
MID_FEN_B = "r4rk1/ppp2ppp/2n5/4p3/4P3/2N5/PPP2PPP/R4RK1 b - - 0 15"

# A post-opening ply whose seeded draw trips should_mistake at mistakeRate=0.5.
FIRE_PLY = 24
FIRE_SEED = 0


class ScoredBot:
    """Fake bot returning up to ``k`` legal moves with a White-POV ``scoreCp``.

    ``score_map`` (uci -> White-POV cp) fixes the eval of the first candidates so a
    test can assert WHICH move ``pick_mistake`` traded down to. Records every
    ``candidates`` call so single-call discipline is checkable.
    """

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


def _client(bot: ScoredBot) -> TestClient:
    app.dependency_overrides[get_bot_engine] = lambda: bot
    c = TestClient(app)
    c.fake_bot = bot  # type: ignore[attr-defined]
    return c


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _first_ucis(fen: str, k: int) -> list[str]:
    board = chess.Board(fen)
    return [m.uci() for m in list(board.legal_moves)[:k]]


# --- (a) Robin drifts to a sub-optimal in-band candidate, deterministically ---


def test_robin_post_opening_plays_in_band_mistake():
    ucis = _first_ucis(MID_FEN_W, 5)
    # White to move ⇒ mover-POV == White-POV. cands[0] is best (300); losses vs
    # best: [0, 100, 200, 50, 260]. In-band (i>=1, 50<=loss<=250): {1,2,3}. The
    # seeded pick over sorted([1,2,3]) is deterministic (idx 1 here).
    scores = {ucis[0]: 300, ucis[1]: 200, ucis[2]: 100, ucis[3]: 250, ucis[4]: 40}
    client = _client(ScoredBot(scores))

    resp = client.post(
        "/api/bot/move",
        json={"fen": MID_FEN_W, "personaId": "robin", "ply": FIRE_PLY, "seed": FIRE_SEED},
    )
    assert resp.status_code == 200
    played = resp.json()["moveUci"]

    # NOT the best move (index 0) — a real inaccuracy was injected.
    assert played != ucis[0]
    # It is one of the in-band candidates (loss 50..250), never the 260cp outlier.
    assert played in {ucis[1], ucis[2], ucis[3]}
    assert played != ucis[4]

    # (e) exactly ONE candidates() call, at MISTAKE_K (==5) and the persona Elo.
    assert len(client.fake_bot.calls) == 1
    assert client.fake_bot.calls[0] == {"fen": MID_FEN_W, "k": 5, "elo": 1350}


def test_robin_mistake_is_deterministic_same_seed():
    ucis = _first_ucis(MID_FEN_W, 5)
    scores = {ucis[0]: 300, ucis[1]: 200, ucis[2]: 100, ucis[3]: 250, ucis[4]: 40}
    body = {"fen": MID_FEN_W, "personaId": "robin", "ply": FIRE_PLY, "seed": FIRE_SEED}

    c1 = _client(ScoredBot(dict(scores)))
    r1 = c1.post("/api/bot/move", json=body)
    app.dependency_overrides.clear()

    c2 = _client(ScoredBot(dict(scores)))
    r2 = c2.post("/api/bot/move", json=body)

    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()


# --- (b) Casey / Vera (mistakeRate=0) play best at the same ply — B4 parity ---


@pytest.mark.parametrize("persona_id", ["casey", "vera"])
def test_zero_mistake_rate_persona_plays_best(persona_id):
    ucis = _first_ucis(MID_FEN_W, 5)
    scores = {ucis[0]: 300, ucis[1]: 200, ucis[2]: 100, ucis[3]: 250, ucis[4]: 40}
    client = _client(ScoredBot(scores))

    resp = client.post(
        "/api/bot/move",
        json={"fen": MID_FEN_W, "personaId": persona_id, "ply": FIRE_PLY, "seed": FIRE_SEED},
    )
    assert resp.status_code == 200
    # mistakeRate==0 ⇒ mistake sub-branch unreachable ⇒ plain best-move fallback
    # (k=1 candidates), candidate 0 played.
    assert resp.json()["moveUci"] == ucis[0]
    assert client.fake_bot.calls == [{"fen": MID_FEN_W, "k": 1, "elo": personas_elo(persona_id)}]


def personas_elo(persona_id: str) -> int:
    from app import personas

    return personas.get(persona_id).elo


# --- (c) bare {fen} stays B3-identical (regression) --------------------------


def test_bare_fen_move_is_b3_identical():
    client = _client(ScoredBot())
    resp = client.post("/api/bot/move", json={"fen": MID_FEN_W})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"moveUci", "moveSan", "fen", "engine"}

    # Legacy branch: exactly one call, k=1, elo=None (no strength change).
    assert client.fake_bot.calls == [{"fen": MID_FEN_W, "k": 1, "elo": None}]

    board = chess.Board(MID_FEN_W)
    first = next(iter(board.legal_moves))
    assert body["moveUci"] == first.uci()


# --- (d) Black-to-move Robin selects by mover-POV correctly ------------------


def test_robin_black_to_move_mover_pov():
    ucis = _first_ucis(MID_FEN_B, 5)
    # Black to move ⇒ mover_cp = -White-POV. Best-for-Black is the MOST NEGATIVE
    # White-POV score. cands[0] best (mover +300); mover losses [0,100,200,50,260].
    scores = {ucis[0]: -300, ucis[1]: -200, ucis[2]: -100, ucis[3]: -250, ucis[4]: -40}
    client = _client(ScoredBot(scores))

    resp = client.post(
        "/api/bot/move",
        json={"fen": MID_FEN_B, "personaId": "robin", "ply": FIRE_PLY, "seed": FIRE_SEED},
    )
    assert resp.status_code == 200
    played = resp.json()["moveUci"]

    # A sub-optimal but IN-BAND move by mover-POV (not the best, not the 260cp one).
    assert played != ucis[0]
    assert played in {ucis[1], ucis[2], ucis[3]}
    assert len(client.fake_bot.calls) == 1
    assert client.fake_bot.calls[0]["k"] == 5
