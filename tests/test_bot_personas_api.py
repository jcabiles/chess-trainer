"""API tests for the persona-aware bot routes (B4 — persona ladder).

The bot engine is a FAKE injected via ``app.dependency_overrides[get_bot_engine]``
(like ``tests/test_bot_api.py``), so the whole suite runs with no Stockfish binary
present. These tests exercise the persona wiring ON TOP of the B3 routes:

- ``GET /api/bot/status`` lists the 4 personas + defaultPersonaId=='casey'.
- ``POST /api/bot/move`` with NO personaId is BYTE-IDENTICAL to B3 (k=1, cand 0).
- a persona move in the opening (ply<8) requests k=SAMPLE_K at the persona's Elo
  and SAMPLES; a late-ply move plays best (k=1).
- mover-POV sign: a Black-to-move persona samples its best-for-Black move.
- unknown personaId → 400 (move + save).
- ``POST /api/bot/save`` with personaId writes server-resolved
  ``{"rated",personaId,personaElo}`` and IGNORES a bogus client personaElo;
  without personaId it writes ``{"rated": bool}`` exactly (B3 shape intact).
"""

from __future__ import annotations

import json
from pathlib import Path

import chess
import pytest
from fastapi.testclient import TestClient

import app.review as review_module
import app.storage as storage
from app.bot_engine import get_bot_engine
from app.main import app, get_engine
from tests.engine_fakes import ScriptedEngine

START_FEN = chess.STARTING_FEN


class RecordingBot:
    """Fake bot that records each ``candidates`` call's (fen, k, elo).

    Returns up to ``k`` legal moves. Each carries a White-POV ``scoreCp`` drawn
    from ``score_map`` (uci -> White-POV cp) if provided, else 0 — so a test can
    assert WHICH move sampling picked and prove the mover-POV sign flip.
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


@pytest.fixture
def client():
    fake = RecordingBot()
    app.dependency_overrides[get_bot_engine] = lambda: fake
    with TestClient(app) as c:
        c.fake_bot = fake  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


# --- /api/bot/status: persona ladder ----------------------------------------


def test_status_lists_six_personas_and_default(client):
    resp = client.get("/api/bot/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["defaultPersonaId"] == "casey"
    ids = [p["id"] for p in body["personas"]]
    assert ids == ["casey", "diego", "robin", "morgan", "alex", "vera"]
    # personaLabel stays back-compat = the default persona's name.
    assert body["personaLabel"] == "Ming Ling"
    # Each persona dict carries the full shape (B5 added blunderRate +
    # threatDistance + mistakeRate — additive causal-blunder dials).
    for p in body["personas"]:
        assert set(p) == {
            "id",
            "name",
            "elo",
            "style",
            "description",
            "temperature",
            "blunderRate",
            "threatDistance",
            "mistakeRate",
        }
    casey = next(p for p in body["personas"] if p["id"] == "casey")
    assert casey["elo"] == 1350


# --- /api/bot/move: bare {fen} is B3-identical (regression) ------------------


def test_bare_fen_move_is_b3_identical(client):
    """No personaId ⇒ legacy branch: candidates(fen, k=1) with elo left unchanged
    (None), candidate 0 played, same {moveUci,moveSan,fen} body — no sampling."""
    resp = client.post("/api/bot/move", json={"fen": START_FEN})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"moveUci", "moveSan", "fen", "engine"}

    # Exactly one engine call: k=1, elo=None (no strength change ⇒ stays 1350).
    assert client.fake_bot.calls == [{"fen": START_FEN, "k": 1, "elo": None}]

    # The played move is candidate 0 (first legal move), applied to the input FEN.
    board = chess.Board(START_FEN)
    first = next(iter(board.legal_moves))
    assert body["moveUci"] == first.uci()
    assert body["moveSan"] == board.san(first)
    board.push(first)
    assert body["fen"] == board.fen()


# --- /api/bot/move: persona threads Elo + samples in opening ----------------


def test_persona_opening_samples_at_persona_elo(client):
    """Opening ply (<8) + personaId ⇒ candidates(k=SAMPLE_K, elo=persona.elo)."""
    resp = client.post(
        "/api/bot/move",
        json={"fen": START_FEN, "personaId": "vera", "ply": 0, "seed": 42},
    )
    assert resp.status_code == 200
    call = client.fake_bot.calls[-1]
    assert call["k"] == 5  # SAMPLE_K
    assert call["elo"] == 2000  # vera's Elo, threaded through
    # A legal move was returned.
    board = chess.Board(START_FEN)
    assert chess.Move.from_uci(resp.json()["moveUci"]) in board.legal_moves


def test_persona_late_ply_plays_best(client):
    """At/after OPENING_PLIES the persona plays best (k=1) at its Elo — no sample."""
    resp = client.post(
        "/api/bot/move",
        json={"fen": START_FEN, "personaId": "alex", "ply": 8, "seed": 42},
    )
    assert resp.status_code == 200
    call = client.fake_bot.calls[-1]
    assert call["k"] == 1
    assert call["elo"] == 1800  # alex
    # Best = candidate 0 = first legal move.
    board = chess.Board(START_FEN)
    first = next(iter(board.legal_moves))
    assert resp.json()["moveUci"] == first.uci()


def test_persona_move_is_deterministic_under_seed(client):
    """Same (seed, ply, fen) ⇒ same sampled move (weighted_choice is seeded)."""
    body = {"fen": START_FEN, "personaId": "morgan", "ply": 2, "seed": 777}
    a = client.post("/api/bot/move", json=body).json()["moveUci"]
    b = client.post("/api/bot/move", json=body).json()["moveUci"]
    assert a == b


# --- mover-POV sign: a Black bot samples its best-for-Black move -------------


def test_black_bot_samples_best_for_black_move(monkeypatch):
    """Prove the mover-POV flip. Black to move; candidates carry White-POV scores.

    With a near-zero temperature the softmax collapses to the argmax over
    MOVER-POV scores. For Black, mover-POV = -White-POV, so the chosen move must
    be the one with the MOST-NEGATIVE White-POV score (best FOR Black). If the
    route sampled raw White-POV, it would pick the LEAST-negative (worst for Black).
    """
    import app.personas as personas_mod

    # Black to move in the starting-mirror: 1.e4, Black on move.
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    board = chess.Board(fen)
    legal = list(board.legal_moves)[:5]
    # Assign distinct White-POV scores; the LOWEST White-POV = best for Black.
    # e.g. -500 (great for Black) ... +300 (bad for Black).
    white_scores = [300, 100, -50, -200, -500][: len(legal)]
    score_map = {m.uci(): s for m, s in zip(legal, white_scores)}
    best_for_black_uci = min(score_map, key=lambda u: score_map[u])  # most-negative

    # Force casey's temperature to a tiny value so the softmax = argmax(mover-POV).
    orig_get = personas_mod.get

    def _get(pid):
        p = orig_get(pid)
        if p is not None and p.id == "casey":
            return personas_mod.Persona(
                p.id,
                p.name,
                p.elo,
                p.style,
                p.description,
                0.01,
                blunderRate=p.blunderRate,
                threatDistance=p.threatDistance,
            )
        return p

    monkeypatch.setattr(personas_mod, "get", _get)

    bot = RecordingBot(score_map=score_map)
    app.dependency_overrides[get_bot_engine] = lambda: bot
    try:
        with TestClient(app) as c:
            resp = c.post(
                "/api/bot/move",
                json={"fen": fen, "personaId": "casey", "ply": 0, "seed": 1},
            )
        assert resp.status_code == 200
        assert resp.json()["moveUci"] == best_for_black_uci
    finally:
        app.dependency_overrides.clear()


# --- unknown personaId → 400 ------------------------------------------------


def test_unknown_persona_move_400(client):
    resp = client.post(
        "/api/bot/move", json={"fen": START_FEN, "personaId": "nope", "ply": 0}
    )
    assert resp.status_code == 400
    # The engine was never asked (rejected before search).
    assert client.fake_bot.calls == []


# --- /api/bot/save: server-resolved persona metadata ------------------------


@pytest.fixture(autouse=True)
def fresh_storage(tmp_path: Path, monkeypatch):
    db_path = str(tmp_path / "bot_personas_test.db")
    monkeypatch.setenv("GAMES_DB", db_path)
    storage.init(db_path)
    review_module._interactive_pending = 0
    yield
    for gid in list(review_module._tasks.keys()):
        review_module.cancel_analysis(gid)
    review_module._interactive_pending = 0


@pytest.fixture
def save_client():
    """TestClient with a neutral analysis engine (for the auto-analysis kick)."""
    app.dependency_overrides[get_engine] = lambda: ScriptedEngine()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _save_body(**overrides) -> dict:
    body = {
        "movesUci": ["e2e4", "e7e5"],
        "userColor": "white",
        "personaLabel": "Casual sparring bot",
        "result": "1-0",
        "startedAt": "2026-07-16T12:00:00Z",
        "rated": True,
    }
    body.update(overrides)
    return body


def test_save_with_persona_resolves_from_catalog(save_client):
    """personaId present ⇒ headers_json = {"rated",personaId,personaElo} with the
    CATALOG Elo + persona name, ignoring any bogus client-sent personaElo/label."""
    body = _save_body(
        userColor="white",
        personaId="alex",
        personaLabel="LIE — not the real name",
        rated=True,
    )
    # Sneak a bogus personaElo into the body; the model ignores unknown fields and
    # the server never reads it — this documents that it can't leak through.
    body["personaElo"] = 9999
    r = save_client.post("/api/bot/save", json=body)
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]

    row = storage.get_game(g["id"])
    assert json.loads(row["headers_json"]) == {
        "rated": True,
        "personaId": "alex",
        "personaElo": 1800,  # catalog Elo, NOT the bogus 9999
    }
    # PGN name is the catalog persona name, NOT the client-sent label.
    assert g["black"] == "Melvin"


def test_save_without_persona_writes_exact_b3_shape(save_client):
    """No personaId ⇒ headers_json is EXACTLY {"rated": bool} (B3 shape intact)."""
    r = save_client.post("/api/bot/save", json=_save_body(rated=False, personaId=None))
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]
    row = storage.get_game(g["id"])
    assert json.loads(row["headers_json"]) == {"rated": False}
    # Name falls back to the client personaLabel (B3 behavior).
    assert g["black"] == "Casual sparring bot"


def test_save_unknown_persona_400(save_client):
    r = save_client.post("/api/bot/save", json=_save_body(personaId="ghost"))
    assert r.status_code == 400
    # No row written.
    assert save_client.get("/api/games").json() == []


# --- /avatars static mount (board-bots-ux T2) --------------------------------


def test_avatars_mount_serves_when_dir_present(client):
    """When data/avatars/ exists (gitignored, user-supplied), /avatars serves it.

    Skips on a fresh clone with no avatars — the mount is conditional at import
    and the frontend falls back to initials.
    """
    from app.main import AVATARS_DIR

    if not AVATARS_DIR.is_dir():
        pytest.skip("data/avatars/ absent — conditional mount not registered")
    files = sorted(AVATARS_DIR.glob("*.png"))
    if not files:
        pytest.skip("data/avatars/ empty")
    r = client.get(f"/avatars/{files[0].name}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # Unknown avatar → 404 (frontend initials fallback path).
    assert client.get("/avatars/nope.png").status_code == 404


def test_avatars_dir_constant_is_gitignored_location():
    """AVATARS_DIR lives under data/ (never committed) per the spec."""
    from app.main import AVATARS_DIR, BASE_DIR

    assert AVATARS_DIR == BASE_DIR / "data" / "avatars"
