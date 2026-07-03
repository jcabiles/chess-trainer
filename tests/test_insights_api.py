"""
tests/test_insights_api.py — API tests for GET /api/insights/openings (T1.4).

Mirrors tests/test_games_api.py's fixture idiom: fresh temp DB per test via
GAMES_DB + storage.init(), real FastAPI lifespan through TestClient (no engine
calls on this route, so no fake-engine override is needed).

The real lifespan loads the bundled data/repertoire.json + data/book.json,
which would make adherence/theory routing depend on production content. To
keep this suite deterministic (per the ticket's known facts), every test
resets repertoire/book state to empty right after the TestClient is created,
then opts back into a small, explicit fixture via repertoire.load()/book.load()
only when a scenario needs one (same idiom as tests/test_insights.py).

No engine, no network, no Stockfish.
"""

from __future__ import annotations

import json
from pathlib import Path

import chess
import pytest
from fastapi.testclient import TestClient

import app.storage as storage
from app import book, repertoire
from app.main import app

MISSING = "tests/fixtures/does_not_exist.json"
BOOK_FIXTURE = "tests/fixtures/book_sample.json"  # firstMoves = ["e2e4"]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_storage(tmp_path, monkeypatch):
    """Fresh temp DB for every test (GAMES_DB env var picked up by lifespan)."""
    db_path = str(tmp_path / "insights_api_test.db")
    monkeypatch.setenv("GAMES_DB", db_path)
    storage.init(db_path)
    yield


@pytest.fixture
def client(fresh_storage):
    """TestClient running the real lifespan, with repertoire/book reset to empty."""
    with TestClient(app) as c:
        repertoire.load(MISSING)
        book.load(MISSING)
        yield c
    repertoire.load(MISSING)
    book.load(MISSING)


def _insert_game(
    *,
    content_hash: str,
    my_color: str | None = "white",
    opening: str | None = None,
    eco: str | None = None,
    result: str | None = "1-0",
    analysis_status: str = "done",
) -> int:
    return storage.insert_game(
        {
            "content_hash": content_hash,
            "pgn": '[Event "?"]\n1. e4 e5 *',
            "imported_at": "2026-01-15T10:00:00",
            "white": "Alice",
            "black": "Bob",
            "result": result,
            "eco": eco,
            "opening": opening,
            "my_color": my_color,
            "analysis_status": analysis_status,
        }
    )


def _plies_from_san(sans: list[str]) -> list[dict]:
    """Replay SAN moves from the start into game_plies-shaped dicts (1-based)."""
    b = chess.Board()
    rows = []
    for i, san in enumerate(sans):
        fen_before = b.fen()
        move = b.parse_san(san)
        rows.append({
            "ply": i + 1,
            "san": san,
            "uci": move.uci(),
            "fen_before": fen_before,
            "eval_cp_white": 20,
        })
        b.push(move)
    return rows


def _load_repertoire(tmp_path: Path) -> None:
    """One prepared white line: 1.e4 e5 2.Nf3 Nc6 3.Bb5 (id 'ruy-test')."""
    path = tmp_path / "repertoire.json"
    path.write_text(json.dumps({
        "lines": [{
            "id": "ruy-test",
            "name": "Ruy Lopez test line",
            "parentOpening": "Ruy Lopez",
            "yourColor": "white",
            "line": ["e4", "e5", "Nf3", "Nc6", "Bb5"],
        }]
    }))
    repertoire.load(str(path))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_populated_sections(client, tmp_path):
    """200 with every section populated: adherence, win_rates, theory, coverage."""
    _load_repertoire(tmp_path)
    book.load(BOOK_FIXTURE, lines=[["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]])

    # Adherence: white game follows prep 4 plies, then deviates at ply 5.
    gid1 = _insert_game(content_hash="g1", my_color="white",
                        opening="Ruy Lopez", result="1-0")
    storage.write_plies(gid1, _plies_from_san(["e4", "e5", "Nf3", "Nc6", "Bc4"]))

    # Win_rates + theory: 5 black Sicilian games; repertoire is white-only so
    # these are automatically off-repertoire (feeds theory too).
    najdorf = "Sicilian Defense: Najdorf Variation"
    for i, result in enumerate(["0-1", "1-0", "1/2-1/2", "0-1", "0-1"]):
        gid = _insert_game(content_hash=f"s{i}", my_color="black",
                            opening=najdorf, result=result)
        storage.write_plies(gid, _plies_from_san(["e4", "c5", "Nf3", "d6"]))

    resp = client.get("/api/insights/openings")
    assert resp.status_code == 200
    body = resp.json()

    cov = body["coverage"]
    assert cov["qualified"] == 6
    assert cov["on_repertoire"] == 1
    assert cov["off_repertoire"] == 5

    fams = body["win_rates"]["families"]
    assert len(fams) == 2  # Sicilian (black, n=5) + Ruy Lopez (white, n=1)
    fam = next(f for f in fams if f["opening"] == "Sicilian Defense")
    assert fam["color"] == "black"
    assert fam["n"] == 5
    assert fam["sufficient"] is True  # n >= MIN_SAMPLE (5)
    lines = body["win_rates"]["lines"]
    assert any(ln["family"] == "Sicilian Defense" for ln in lines)

    adh = body["adherence"]
    assert adh["n"] == 1
    assert adh["avg_followed_prep_depth"] == {"value": 4, "n": 1, "sufficient": False}
    game = adh["games"][0]
    assert game["game_id"] == gid1
    assert game["followed_prep_depth"] == 4
    assert game["deviation_ply"] == 5
    assert game["deviation_move"] == "Bc4"
    assert game["prepared_san"] == "Bb5"
    assert game["line_ids"] == ["ruy-test"]
    line = adh["lines"][0]
    assert line["line_id"] == "ruy-test"
    assert line["name"] == "Ruy Lopez test line"
    assert line["sufficient"] is False  # n=1 < MIN_SAMPLE

    theory = body["theory"]
    assert theory["n"] == 5
    for key in ("avg_book_exit_ply", "avg_opening_accuracy"):
        gated = theory[key]
        assert set(gated) == {"value", "n", "sufficient"}
    assert theory["avg_book_exit_ply"]["n"] == 5
    assert len(theory["games"]) == 5
    assert "not the same as moves endorsed by masters" in theory["note"]


def test_empty_db_returns_empty_safe_shape(client):
    """200 with every section empty-safe when no games exist."""
    resp = client.get("/api/insights/openings")
    assert resp.status_code == 200
    body = resp.json()

    cov = body["coverage"]
    assert cov == {
        "total": 0, "tagged": 0, "analyzed": 0, "pending": 0,
        "qualified": 0, "on_repertoire": 0, "off_repertoire": 0,
    }
    assert body["win_rates"] == {"families": [], "lines": []}
    adh = body["adherence"]
    assert adh["n"] == 0
    assert adh["avg_followed_prep_depth"] == {"value": None, "n": 0, "sufficient": False}
    assert adh["lines"] == []
    assert adh["games"] == []
    theory = body["theory"]
    assert theory["n"] == 0
    assert theory["avg_book_exit_ply"] == {"value": None, "n": 0, "sufficient": False}
    assert theory["avg_opening_accuracy"] == {"value": None, "n": 0, "sufficient": False}
    assert theory["games"] == []
    assert theory["note"]


def test_only_unqualified_games_still_empty(client):
    """Games missing my_color or still pending analysis don't leak into any section."""
    _insert_game(content_hash="u1", my_color=None)
    _insert_game(content_hash="u2", my_color="white", analysis_status="pending")

    resp = client.get("/api/insights/openings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["coverage"]["qualified"] == 0
    assert body["win_rates"]["families"] == []
    assert body["adherence"]["n"] == 0
    assert body["theory"]["n"] == 0
