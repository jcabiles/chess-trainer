"""
tests/test_rating_api.py — API tests for GET /api/rating.

Mirrors the /api/profile harness: an autouse temp-DB fixture (GAMES_DB env +
storage.init) plus a TestClient. No engine, no network, no Stockfish — the
rating read-model is engine-free.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.storage as storage
from app import rating
from app.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_storage(tmp_path: Path, monkeypatch):
    """Fresh temp DB for every test (GAMES_DB env var + storage.init)."""
    db_path = str(tmp_path / "rating_api_test.db")
    monkeypatch.setenv("GAMES_DB", db_path)
    storage.init(db_path)
    yield


@pytest.fixture
def client():
    """TestClient over the temp DB (no engine needed for the rating read-model)."""
    with TestClient(app) as c:
        yield c


def _insert(
    *,
    content_hash: str,
    imported_at: str,
    result: str = "1-0",
    my_color: str = "white",
    source: str = "bot",
    headers: dict | None = None,
) -> int:
    return storage.insert_game(
        {
            "content_hash": content_hash,
            "pgn": '[Event "?"]\n1. e4 e5 *',
            "imported_at": imported_at,
            "result": result,
            "my_color": my_color,
            "source": source,
            "headers_json": None if headers is None else json.dumps(headers),
        }
    )


# ---------------------------------------------------------------------------
# Shape + happy path
# ---------------------------------------------------------------------------


def test_rating_empty_db_returns_full_shape(client):
    r = client.get("/api/rating")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "seedElo": 1350,
        "k": 32,
        "botElo": None,
        "gamesCounted": 0,
        "gamesSkipped": 0,
        "history": [],
    }


def test_rating_seeded_db_matches_counts_and_bot_elo(client):
    # Chronological: win vs 1550, draw vs 1300, loss vs 1400 (same as unit test).
    _insert(
        content_hash="g1",
        imported_at="2026-01-01T10:00:00",
        result="1-0",
        headers={"rated": True, "personaElo": 1550},
    )
    _insert(
        content_hash="g2",
        imported_at="2026-01-02T10:00:00",
        result="1/2-1/2",
        headers={"rated": True, "personaElo": 1300},
    )
    _insert(
        content_hash="g3",
        imported_at="2026-01-03T10:00:00",
        result="0-1",
        headers={"rated": True, "personaElo": 1400},
    )
    r = client.get("/api/rating")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gamesCounted"] == 3
    assert body["gamesSkipped"] == 0
    assert body["botElo"] == 1356
    assert [h["eloAfter"] for h in body["history"]] == [1374, 1371, 1356]
    assert [h["opponentElo"] for h in body["history"]] == [1550, 1300, 1400]


def test_rating_counts_skipped_pre_b4_rows(client):
    _insert(
        content_hash="pre_b4",
        imported_at="2026-01-01T10:00:00",
        headers={"rated": True},  # no personaElo
    )
    r = client.get("/api/rating")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gamesCounted"] == 0
    assert body["gamesSkipped"] == 1
    assert body["botElo"] is None


# ---------------------------------------------------------------------------
# RuntimeError empty-state guard (must be 200, not 500)
# ---------------------------------------------------------------------------


def test_rating_runtime_error_returns_empty_state_not_500(client, monkeypatch):
    def _boom():
        raise RuntimeError("storage not initialised")

    monkeypatch.setattr(rating, "build_rating", _boom)
    r = client.get("/api/rating")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "seedElo": 1350,
        "k": 32,
        "botElo": None,
        "gamesCounted": 0,
        "gamesSkipped": 0,
        "history": [],
    }
