"""API tests for ``POST /api/bot/save`` (B3 — bot games into the review pipeline).

The ANALYSIS engine is a neutral fake injected via
``app.dependency_overrides[get_engine]`` (the auto-analysis kick), so the whole
suite runs with no Stockfish binary present. Storage uses a temp DB per test.

Coverage
--------
- source='bot' rows written; headers_json == {"rated": true/false} by request.
- my_color set by userColor; White/Black names ("You" vs persona) by color.
- a 1-ply game persists (accuracy/Elo null is fine).
- SAME startedAt posted twice → 2nd is a duplicate, no new row.
- DISTINCT startedAt → two separate rows.
- empty movesUci → 400; result='*' → 400; illegal move sequence → 400.
- GameSummary carries `source`.
- an import-style call still writes headers_json=None (new param default).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.review as review_module
import app.storage as storage
from app.main import app, get_engine
from tests.engine_fakes import ScriptedEngine


@pytest.fixture(autouse=True)
def fresh_storage(tmp_path: Path, monkeypatch):
    """Fresh temp DB for every test; reset review module state."""
    db_path = str(tmp_path / "bot_save_test.db")
    monkeypatch.setenv("GAMES_DB", db_path)
    storage.init(db_path)
    review_module._interactive_pending = 0
    yield
    for gid in list(review_module._tasks.keys()):
        review_module.cancel_analysis(gid)
    review_module._interactive_pending = 0


@pytest.fixture
def client():
    """TestClient with a neutral ScriptedEngine injected for the analysis kick."""
    app.dependency_overrides[get_engine] = lambda: ScriptedEngine()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _save_body(**overrides) -> dict:
    """A valid /api/bot/save body (1.e4 e5), overridable per field."""
    body = {
        "movesUci": ["e2e4", "e7e5"],
        "userColor": "white",
        "personaLabel": "Casual sparring bot",
        "result": "1-0",
        "startedAt": "2026-07-16T12:00:00Z",
        "rated": False,
    }
    body.update(overrides)
    return body


def _stored_row(game_id: int) -> dict:
    return storage.get_game(game_id)


# --- happy path: source + headers_json --------------------------------------


def test_save_writes_bot_source_and_casual_headers(client):
    r = client.post("/api/bot/save", json=_save_body(rated=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1
    assert body["duplicates"] == 0
    g = body["games"][0]
    assert g["source"] == "bot"

    row = _stored_row(g["id"])
    assert row["source"] == "bot"
    assert json.loads(row["headers_json"]) == {"rated": False}


def test_save_rated_headers_true(client):
    r = client.post("/api/bot/save", json=_save_body(rated=True))
    assert r.status_code == 200, r.text
    row = _stored_row(r.json()["games"][0]["id"])
    assert json.loads(row["headers_json"]) == {"rated": True}


# --- names + my_color by color ----------------------------------------------


def test_save_user_white_names_and_color(client):
    r = client.post("/api/bot/save", json=_save_body(userColor="white"))
    g = r.json()["games"][0]
    assert g["my_color"] == "white"
    assert g["white"] == "You"
    assert g["black"] == "Casual sparring bot"


def test_save_user_black_names_and_color(client):
    r = client.post("/api/bot/save", json=_save_body(userColor="black"))
    g = r.json()["games"][0]
    assert g["my_color"] == "black"
    assert g["white"] == "Casual sparring bot"
    assert g["black"] == "You"


# --- result carried through --------------------------------------------------


def test_save_carries_result(client):
    r = client.post("/api/bot/save", json=_save_body(result="1/2-1/2"))
    assert r.json()["games"][0]["result"] == "1/2-1/2"


# --- 1-ply game persists -----------------------------------------------------


def test_save_one_ply_game_persists(client):
    r = client.post("/api/bot/save", json=_save_body(movesUci=["e2e4"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1
    g = body["games"][0]
    assert g["ply_count"] == 1
    # accuracy/Elo null is fine — not asserted here, not a bug.


# --- dedup by stable startedAt ----------------------------------------------


def test_save_same_started_at_dedups(client):
    body = _save_body(startedAt="2026-07-16T09:30:00Z")
    r1 = client.post("/api/bot/save", json=body)
    assert r1.json()["imported"] == 1

    r2 = client.post("/api/bot/save", json=body)
    b2 = r2.json()
    assert b2["imported"] == 0
    assert b2["duplicates"] == 1

    # No new row: exactly one game in the library.
    all_games = client.get("/api/games").json()
    assert len(all_games) == 1


def test_save_distinct_started_at_two_rows(client):
    r1 = client.post("/api/bot/save", json=_save_body(startedAt="2026-07-16T09:00:00Z"))
    r2 = client.post("/api/bot/save", json=_save_body(startedAt="2026-07-16T10:00:00Z"))
    assert r1.json()["imported"] == 1
    assert r2.json()["imported"] == 1

    all_games = client.get("/api/games").json()
    assert len(all_games) == 2


# --- validation --------------------------------------------------------------


def test_save_empty_moves_400(client):
    r = client.post("/api/bot/save", json=_save_body(movesUci=[]))
    assert r.status_code == 400
    # No row written.
    assert client.get("/api/games").json() == []


def test_save_result_star_400(client):
    r = client.post("/api/bot/save", json=_save_body(result="*"))
    assert r.status_code == 400
    assert client.get("/api/games").json() == []


def test_save_illegal_move_sequence_400(client):
    # e2e4 is fine, then e2e4 again is illegal (pawn already moved).
    r = client.post("/api/bot/save", json=_save_body(movesUci=["e2e4", "e2e4"]))
    assert r.status_code == 400
    assert client.get("/api/games").json() == []


def test_save_junk_result_400(client):
    # Only decisive/drawn results are accepted — arbitrary strings are rejected
    # so a malformed result can't pollute badges/stats downstream.
    r = client.post("/api/bot/save", json=_save_body(result="banana"))
    assert r.status_code == 400
    assert client.get("/api/games").json() == []


def test_save_empty_started_at_400(client):
    # startedAt feeds the dedup hash (Event header); an empty value is rejected.
    r = client.post("/api/bot/save", json=_save_body(startedAt="   "))
    assert r.status_code == 400
    assert client.get("/api/games").json() == []


# --- GameSummary surfaces source --------------------------------------------


def test_game_summary_carries_source(client):
    client.post("/api/bot/save", json=_save_body())
    games = client.get("/api/games").json()
    assert len(games) == 1
    assert "source" in games[0]
    assert games[0]["source"] == "bot"


# --- import path still writes headers_json=None (new-param default) ----------

_IMPORT_PGN = (
    '[Event "Test"]\n'
    '[White "Alice"]\n'
    '[Black "Bob"]\n'
    '[Result "*"]\n'
    '\n'
    '1. e4 e5 2. Nf3 *\n'
)


def test_import_still_writes_headers_json_none(client):
    r = client.post("/api/games/import", json={"pgn": _IMPORT_PGN})
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]
    row = _stored_row(g["id"])
    assert row["headers_json"] is None
    assert row["source"] == "import"
