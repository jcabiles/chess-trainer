"""
tests/test_insights_api.py — API tests for the Insights routes.

Covers GET /api/insights/openings (T1.4) and GET /api/insights/mistakes (T2.5).

Mirrors tests/test_games_api.py's fixture idiom: fresh temp DB per test via
GAMES_DB + storage.init(), real FastAPI lifespan through TestClient (no engine
calls on either route, so no fake-engine override is needed).

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
from app.insights import CLUSTER_GATE
from app.main import app
from app.models import EndgameInsightsResponse
from app.storage import LeakRecord

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
    imported_at: str = "2026-01-15T10:00:00",
) -> int:
    return storage.insert_game(
        {
            "content_hash": content_hash,
            "pgn": '[Event "?"]\n1. e4 e5 *',
            "imported_at": imported_at,
            "white": "Alice",
            "black": "Bob",
            "result": result,
            "eco": eco,
            "opening": opening,
            "my_color": my_color,
            "analysis_status": analysis_status,
        }
    )


def _plies_from_san(sans: list[str], win_probs: list[float] | None = None) -> list[dict]:
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
            "win_prob": win_probs[i] if win_probs else None,
        })
        b.push(move)
    return rows


def _make_leak(
    game_id: int,
    *,
    ply: int = 20,
    color: str = "white",
    category: str = "hanging",
    phase: str = "middlegame",
    lead_in_ply: int | None = None,
    threat_motif: str | None = None,
) -> LeakRecord:
    return LeakRecord(
        game_id=game_id,
        ply=ply,
        color=color,
        severity="blunder",
        category=category,
        phase=phase,
        win_prob_before=0.65,
        win_prob_after=0.35,
        win_prob_drop=0.30,
        lead_in_ply=lead_in_ply,
        threat_motif=threat_motif,
    )


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


# ---------------------------------------------------------------------------
# GET /api/insights/mistakes (T2.5)
# ---------------------------------------------------------------------------


def test_mistakes_populated_sections(client):
    """200 with clusters, foreseeable, time_trouble, capitalization populated."""
    gid = _insert_game(content_hash="m1", my_color="white", result="1-0")
    storage.write_leaks(gid, [
        _make_leak(gid, ply=10, lead_in_ply=8, threat_motif="knight_fork"),
        _make_leak(gid, ply=12, lead_in_ply=10, threat_motif="knight_fork"),
        _make_leak(gid, ply=14),
        _make_leak(gid, ply=16),
    ])
    storage.write_plies(gid, [
        {"ply": 1, "is_user_move": True, "clock_centis": 500},    # <10s bucket
        {"ply": 3, "is_user_move": True, "clock_centis": 20000},  # >2m bucket
    ])

    # A second, sustained-winning game for capitalization.
    gid2 = _insert_game(content_hash="m2", my_color="white", result="1-0")
    storage.write_plies(gid2, _plies_from_san(
        ["e4", "e5", "Nf3", "Nc6", "Bb5"], win_probs=[0.9, 0.1, 0.9, 0.1, 0.9]))

    resp = client.get("/api/insights/mistakes")
    assert resp.status_code == 200
    body = resp.json()

    assert body["coverage"]["qualified"] == 2

    clusters = body["clusters"]
    assert clusters["n_leaks"] == 4
    items = clusters["items"]
    assert len(items) == 1
    assert items[0]["category"] == "hanging"
    assert items[0]["count"] == 4
    assert items[0]["name"]  # non-empty human name
    assert items[0]["example"] == {"game_id": gid, "ply": 16}
    assert clusters["suppressed"] == {"cells": 0, "leaks": 0, "gate": CLUSTER_GATE}

    fore = body["foreseeable"]
    assert fore["rate"] == {"value": 0.5, "n": 4, "sufficient": False}
    assert fore["dominant_motif"] == "knight_fork"
    assert "narrow definition" in fore["note"]

    tt = body["time_trouble"]
    assert tt["clocked_games"] == 1
    assert tt["unclocked_games"] == 1
    by_label = {b["bucket"]: b for b in tt["buckets"]}
    assert set(by_label) == {"<10s", "10s-30s", "30s-2m", ">2m"}
    assert by_label["<10s"]["moves"] == 1
    assert by_label[">2m"]["moves"] == 1

    cap = body["capitalization"]
    assert cap["winning_games"] == 1
    assert cap["converted"] == 1
    assert cap["rate"] == {"value": 1.0, "n": 1, "sufficient": False}
    assert "single-ply" in cap["note"]


def test_mistakes_empty_db_returns_empty_safe_shape(client):
    """200 with every section empty-safe when no games/leaks exist."""
    resp = client.get("/api/insights/mistakes")
    assert resp.status_code == 200
    body = resp.json()

    assert body["coverage"] == {
        "total": 0, "tagged": 0, "analyzed": 0, "pending": 0, "qualified": 0,
    }
    clusters = body["clusters"]
    assert clusters["n_leaks"] == 0
    assert clusters["items"] == []
    assert clusters["suppressed"] == {"cells": 0, "leaks": 0, "gate": CLUSTER_GATE}
    fore = body["foreseeable"]
    assert fore["rate"] == {"value": None, "n": 0, "sufficient": False}
    assert fore["dominant_motif"] is None
    assert fore["note"]
    tt = body["time_trouble"]
    assert tt["clocked_games"] == 0
    assert tt["unclocked_games"] == 0
    assert tt["baseline_rate"] == {"value": None, "n": 0, "sufficient": False}
    assert len(tt["buckets"]) == 4  # all four buckets always present
    assert all(b["rate"] is None for b in tt["buckets"])
    assert tt["note"]
    cap = body["capitalization"]
    assert cap == {
        "winning_games": 0, "converted": 0,
        "rate": {"value": None, "n": 0, "sufficient": False},
        "note": cap["note"],
    }
    assert cap["note"]


def test_mistakes_cluster_item_example_round_trips(client):
    """A cluster item's example carries the exact game_id/ply of a real leak."""
    gid_a = _insert_game(content_hash="ex1", imported_at="2026-01-10T10:00:00")
    gid_b = _insert_game(content_hash="ex2", imported_at="2026-01-20T10:00:00")
    storage.write_leaks(gid_a, [_make_leak(gid_a, ply=p) for p in (10, 12)])
    storage.write_leaks(gid_b, [_make_leak(gid_b, ply=p) for p in (20, 22)])

    resp = client.get("/api/insights/mistakes")
    assert resp.status_code == 200
    items = resp.json()["clusters"]["items"]
    assert len(items) == 1
    example = items[0]["example"]
    # Most recent import (game B), highest ply within it — proves the nested
    # ClusterExample model round-trips game_id/ply, not just aggregate counts.
    assert example == {"game_id": gid_b, "ply": 22}


# ---------------------------------------------------------------------------
# GET /api/insights/endgames (T3.3)
# ---------------------------------------------------------------------------

# King+rook-only endgame, kings on e1/e8 with f1/f8 empty — a legal,
# signature-stable position whose material buckets as "rook"
# (app.endgame.endgame_signature); mirrors tests/test_insights.py's fixture.
ROOK_ENDGAME_FEN = "3rk3/8/8/8/8/8/8/3RK3 w - - 0 1"


def _rook_endgame_suffix(n_plies: int = 8, win_probs: list[float] | None = None) -> list[dict]:
    """A legal, signature-stable "rook" endgame suffix (kings shuffle e<->f).

    win_prob is stored MOVER-POV (storage.py:91), same convention as
    tests/test_insights.py::_suffix_from_fen.
    """
    board = chess.Board(ROOK_ENDGAME_FEN)
    rows = []
    for i in range(n_plies):
        fen_before = board.fen()
        color = board.turn
        e_sq = chess.E1 if color == chess.WHITE else chess.E8
        san = "Kf1" if color == chess.WHITE else "Kf8"
        if board.king(color) != e_sq:
            san = "Ke1" if color == chess.WHITE else "Ke8"
        move = board.parse_san(san)
        rows.append({
            "ply": i + 2,  # ply 1 is the non-endgame prefix below
            "san": san,
            "uci": move.uci(),
            "fen_before": fen_before,
            "eval_cp_white": 0,
            "win_prob": win_probs[i] if win_probs else None,
        })
        board.push(move)
    return rows


def test_endgames_empty_db_returns_empty_safe_shape(client):
    """200 with the typed zero shape when no games exist."""
    resp = client.get("/api/insights/endgames")
    assert resp.status_code == 200
    body = resp.json()

    assert body["coverage"] == {
        "total": 0, "tagged": 0, "analyzed": 0, "pending": 0,
        "qualified": 0, "reached_endgame": 0,
    }
    assert body["types"] == []
    assert body["weakest"] is None
    assert body["note"]

    validated = EndgameInsightsResponse.model_validate(body)
    assert validated.coverage.qualified == 0
    assert validated.types == []
    assert validated.weakest is None


def test_endgames_populated_sections(client):
    """200 with a rook-type row: gated accuracy/conversion + a deep-link example."""
    # Sustained win-prob (mover-POV) for the first 4 suffix plies -> a
    # "winning" endgame that the user goes on to win (converted).
    sustained_wp = [0.9, 0.05, 0.9, 0.05, 0.5, 0.5, 0.5, 0.5]
    gid = _insert_game(content_hash="eg1", my_color="white", result="1-0")
    prefix = [{"ply": 1, "fen_before": chess.STARTING_FEN}]
    storage.write_plies(gid, prefix + _rook_endgame_suffix(win_probs=sustained_wp))

    resp = client.get("/api/insights/endgames")
    assert resp.status_code == 200
    body = resp.json()

    assert body["coverage"]["qualified"] == 1
    assert body["coverage"]["reached_endgame"] == 1

    types = body["types"]
    assert len(types) == 1
    rook = types[0]
    assert rook["signature"] == "rook"
    assert rook["games"] == 1
    assert set(rook["accuracy"]) == {"value", "n", "sufficient"}
    assert rook["accuracy"]["value"] == 100.0
    assert rook["conversion"]["winning"] == 1
    assert rook["conversion"]["converted"] == 1
    assert set(rook["conversion"]["rate"]) == {"value", "n", "sufficient"}
    assert rook["example"] == {"game_id": gid, "ply": 2}

    # Only one sufficient-or-not signature exists with n=1 games (< MIN_SAMPLE)
    # so accuracy isn't "sufficient" and weakest stays None.
    assert rook["accuracy"]["sufficient"] is False
    assert body["weakest"] is None

    validated = EndgameInsightsResponse.model_validate(body)
    assert validated.types[0].example.game_id == gid
    assert validated.types[0].example.ply == 2


def test_endgames_fallback_on_storage_runtime_error(client, monkeypatch):
    """Drift guard: the except-branch fallback dict validates against the
    model, exercising the real RuntimeError path (storage-uninitialised)."""
    def _raise():
        raise RuntimeError("storage.init() has not been called or failed to open the DB")

    monkeypatch.setattr("app.main.insights.build_endgame_insights", _raise)

    resp = client.get("/api/insights/endgames")
    assert resp.status_code == 200
    body = resp.json()

    assert body["coverage"] == {
        "total": 0, "tagged": 0, "analyzed": 0, "pending": 0,
        "qualified": 0, "reached_endgame": 0,
    }
    assert body["types"] == []
    assert body["weakest"] is None
    assert body["note"]

    validated = EndgameInsightsResponse.model_validate(body)
    assert validated.coverage.reached_endgame == 0
