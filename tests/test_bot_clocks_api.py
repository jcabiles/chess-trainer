"""API tests for `%clk` emission on ``POST /api/bot/save`` (B7 — T1).

The ANALYSIS engine is a neutral fake injected via
``app.dependency_overrides[get_engine]`` (the auto-analysis kick), so the whole
suite runs with no Stockfish binary present. Storage uses a temp DB per test.

Coverage
--------
- ``moveTimes`` aligned to ``movesUci`` -> PGN movetext carries ``%clk``
  comments matching ``app.pgn``'s reader regex.
- Round-trip: ``storage.get_plies`` (fed by ``app.pgn.parse_games`` at import
  time) yields ``clock_centis`` equal to the sent centis within tenths
  rounding (+/- 5 centis).
- ``moveTimes=[]`` -> no ``%clk`` anywhere in the stored PGN (B3 back-compat).
- length mismatch (``len(moveTimes) != len(movesUci)``) -> 200 OK, no ``%clk``,
  no exception.
- ``_format_clk`` edge cases: sub-minute, multi-minute, >=1h.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.review as review_module
import app.storage as storage
from app.main import _format_clk, app, get_engine
from app.pgn import _parse_clock_centis
from tests.engine_fakes import ScriptedEngine


@pytest.fixture(autouse=True)
def fresh_storage(tmp_path: Path, monkeypatch):
    """Fresh temp DB for every test; reset review module state."""
    db_path = str(tmp_path / "bot_clocks_test.db")
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
    """A valid /api/bot/save body (1.e4 e5 2.Nf3), overridable per field."""
    body = {
        "movesUci": ["e2e4", "e7e5", "g1f3"],
        "userColor": "white",
        "personaLabel": "Casual sparring bot",
        "result": "1-0",
        "startedAt": "2026-07-18T12:00:00Z",
        "rated": False,
    }
    body.update(overrides)
    return body


def _stored_row(game_id: int) -> dict:
    return storage.get_game(game_id)


# --- happy path: %clk emitted + round-trips ----------------------------------


def test_save_with_move_times_emits_clk_comments(client):
    move_times = [59700, 58800, 57900]  # centis remaining after each ply
    r = client.post("/api/bot/save", json=_save_body(moveTimes=move_times))
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]

    row = _stored_row(g["id"])
    pgn_text = row["pgn"]
    assert "%clk" in pgn_text
    # Exactly 3 %clk comments, one per ply.
    assert pgn_text.count("%clk") == 3


def test_save_with_move_times_round_trips_clock_centis(client):
    move_times = [59700, 58800, 57900]
    r = client.post("/api/bot/save", json=_save_body(moveTimes=move_times))
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]

    plies = storage.get_plies(g["id"])
    assert len(plies) == 3
    for ply, expected in zip(plies, move_times):
        assert ply["clock_centis"] is not None
        assert abs(ply["clock_centis"] - expected) <= 5


def test_save_with_move_times_matches_pgn_reader_regex(client):
    """Directly verify the emitted comment matches pgn._CLK_RE via _parse_clock_centis."""
    move_times = [5730, 12345, 360050]
    r = client.post("/api/bot/save", json=_save_body(moveTimes=move_times))
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]

    row = _stored_row(g["id"])
    pgn_text = row["pgn"]
    # Find each %clk comment substring and confirm it parses back correctly.
    import re

    matches = re.findall(r"\[%clk\s+\d+:\d+:\d+(?:\.\d+)?\]", pgn_text)
    assert len(matches) == 3
    for comment, expected in zip(matches, move_times):
        parsed = _parse_clock_centis(comment)
        assert parsed is not None
        assert abs(parsed - expected) <= 5


# --- back-compat: empty moveTimes emits no %clk -------------------------------


def test_save_empty_move_times_emits_no_clk(client):
    r = client.post("/api/bot/save", json=_save_body())  # no moveTimes key -> default []
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]

    row = _stored_row(g["id"])
    assert "%clk" not in row["pgn"]

    plies = storage.get_plies(g["id"])
    assert len(plies) == 3
    for ply in plies:
        assert ply["clock_centis"] is None


def test_save_explicit_empty_move_times_list_emits_no_clk(client):
    r = client.post("/api/bot/save", json=_save_body(moveTimes=[]))
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]
    row = _stored_row(g["id"])
    assert "%clk" not in row["pgn"]


# --- length mismatch: skip %clk, never raise ----------------------------------


def test_save_move_times_length_mismatch_no_clk_no_exception(client):
    # 3 moves, but only 2 move times -> mismatch, should skip %clk entirely.
    r = client.post("/api/bot/save", json=_save_body(moveTimes=[59700, 58800]))
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]

    row = _stored_row(g["id"])
    assert "%clk" not in row["pgn"]

    plies = storage.get_plies(g["id"])
    assert len(plies) == 3
    for ply in plies:
        assert ply["clock_centis"] is None


def test_save_move_times_too_long_no_clk_no_exception(client):
    r = client.post(
        "/api/bot/save", json=_save_body(moveTimes=[59700, 58800, 57900, 57000])
    )
    assert r.status_code == 200, r.text
    g = r.json()["games"][0]
    row = _stored_row(g["id"])
    assert "%clk" not in row["pgn"]


# --- fmt edge cases ------------------------------------------------------------


@pytest.mark.parametrize(
    "centis,expected",
    [
        (5730, "0:00:57.3"),
        (12345, "0:02:03.5"),
        (360050, "1:00:00.5"),
        (0, "0:00:00.0"),
        (100, "0:00:01.0"),
    ],
)
def test_format_clk_edge_cases(centis, expected):
    assert _format_clk(centis) == expected
