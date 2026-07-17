"""
tests/test_rating.py — Unit tests for app/rating.py.

Pure Elo math (elo_update, user_score) plus build_rating() over a temp DB
seeded via the storage CRUD API. No engine, no network, no Stockfish.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.storage as storage
from app.rating import SEED_ELO, K, build_rating, elo_update, user_score

# ---------------------------------------------------------------------------
# elo_update — pure math
# ---------------------------------------------------------------------------


def test_elo_update_win_vs_higher_gains_more_than_win_vs_lower():
    gain_higher = elo_update(1350, 1550, 1.0, K) - 1350
    gain_lower = elo_update(1350, 1150, 1.0, K) - 1350
    assert gain_higher > gain_lower > 0


def test_elo_update_draw_vs_equal_is_near_zero():
    assert elo_update(1500, 1500, 0.5, K) == pytest.approx(1500.0)


def test_elo_update_hand_computed_example():
    # cur=1350, opp=1550, win: expected = 1/(1+10**(200/400)) ≈ 0.2402,
    # cur += 32*(1 - expected) → 1374.3119...
    assert elo_update(1350, 1550, 1.0, K) == pytest.approx(1374.3119016527346)


def test_elo_update_loss_vs_lower_drops_more_than_loss_vs_higher():
    drop_lower = 1350 - elo_update(1350, 1150, 0.0, K)
    drop_higher = 1350 - elo_update(1350, 1550, 0.0, K)
    assert drop_lower > drop_higher > 0


# ---------------------------------------------------------------------------
# user_score — result → user POV, guarded on color
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "result,my_color,expected",
    [
        ("1-0", "white", 1.0),
        ("0-1", "white", 0.0),
        ("1/2-1/2", "white", 0.5),
        ("1-0", "black", 0.0),
        ("0-1", "black", 1.0),
        ("1/2-1/2", "black", 0.5),
    ],
)
def test_user_score_all_six_cases(result, my_color, expected):
    assert user_score(result, my_color) == expected


@pytest.mark.parametrize("my_color", [None, "", "purple"])
def test_user_score_invalid_color_is_none_even_on_decisive(my_color):
    assert user_score("1-0", my_color) is None


def test_user_score_unknown_result_is_none():
    assert user_score("*", "white") is None
    assert user_score(None, "black") is None


# ---------------------------------------------------------------------------
# build_rating — over a seeded temp DB
# ---------------------------------------------------------------------------


def _init_db(tmp_path: Path) -> None:
    storage.init(str(tmp_path / "test_games.db"))


def _insert(
    *,
    content_hash: str,
    imported_at: str,
    result: str | None = "1-0",
    my_color: str | None = "white",
    source: str | None = "bot",
    headers: dict | str | None = None,
) -> int:
    if isinstance(headers, dict) or headers is None:
        headers_json = None if headers is None else json.dumps(headers)
    else:
        headers_json = headers  # raw string (for malformed-JSON tests)
    return storage.insert_game(
        {
            "content_hash": content_hash,
            "pgn": '[Event "?"]\n1. e4 e5 *',
            "imported_at": imported_at,
            "result": result,
            "my_color": my_color,
            "source": source,
            "headers_json": headers_json,
        }
    )


def test_build_rating_empty_db_returns_none(tmp_path):
    _init_db(tmp_path)
    out = build_rating()
    assert out == {
        "seedElo": SEED_ELO,
        "k": K,
        "botElo": None,
        "gamesCounted": 0,
        "gamesSkipped": 0,
        "history": [],
    }


def test_build_rating_running_sequence(tmp_path):
    _init_db(tmp_path)
    # Chronological: win vs 1550, draw vs 1300, loss vs 1400.
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
    out = build_rating()
    assert out["gamesCounted"] == 3
    assert out["gamesSkipped"] == 0
    assert out["botElo"] == 1356  # hand-computed
    assert [h["eloAfter"] for h in out["history"]] == [1374, 1371, 1356]
    assert [h["opponentElo"] for h in out["history"]] == [1550, 1300, 1400]
    assert [h["score"] for h in out["history"]] == [1.0, 0.5, 0.0]


def test_build_rating_orders_by_imported_at_then_id(tmp_path):
    _init_db(tmp_path)
    # Insert out of chronological order; same timestamp tie broken by id ASC.
    _insert(
        content_hash="later",
        imported_at="2026-02-01T10:00:00",
        result="0-1",
        headers={"rated": True, "personaElo": 1400},
    )
    _insert(
        content_hash="earlier",
        imported_at="2026-01-01T10:00:00",
        result="1-0",
        headers={"rated": True, "personaElo": 1550},
    )
    out = build_rating()
    # earliest game (win vs 1550) applied first.
    assert out["history"][0]["opponentElo"] == 1550
    assert out["history"][1]["opponentElo"] == 1400


def test_build_rating_excludes_casual_and_non_bot(tmp_path):
    _init_db(tmp_path)
    _insert(
        content_hash="rated_bot",
        imported_at="2026-01-01T10:00:00",
        headers={"rated": True, "personaElo": 1500},
    )
    _insert(
        content_hash="casual_bot",
        imported_at="2026-01-02T10:00:00",
        headers={"rated": False, "personaElo": 1500},
    )
    _insert(
        content_hash="rated_import",
        imported_at="2026-01-03T10:00:00",
        source="import",
        headers={"rated": True, "personaElo": 1500},
    )
    out = build_rating()
    assert out["gamesCounted"] == 1
    assert out["gamesSkipped"] == 0
    assert len(out["history"]) == 1


def test_build_rating_pre_b4_rated_no_persona_elo_is_skipped(tmp_path):
    _init_db(tmp_path)
    _insert(
        content_hash="pre_b4",
        imported_at="2026-01-01T10:00:00",
        headers={"rated": True},  # no personaElo
    )
    out = build_rating()
    assert out["gamesCounted"] == 0
    assert out["gamesSkipped"] == 1
    assert out["botElo"] is None


@pytest.mark.parametrize(
    "opp",
    ["1500", True, False, float("nan"), float("inf"), None],
)
def test_build_rating_invalid_persona_elo_is_skipped(tmp_path, opp):
    _init_db(tmp_path)
    _insert(
        content_hash="bad_opp",
        imported_at="2026-01-01T10:00:00",
        headers={"rated": True, "personaElo": opp},
    )
    out = build_rating()
    assert out["gamesCounted"] == 0
    assert out["gamesSkipped"] == 1


@pytest.mark.parametrize(
    "raw",
    [None, "[]", "null", "{bad json", '"scalar"', "42"],
)
def test_build_rating_malformed_headers_json_skipped_without_crash(tmp_path, raw):
    _init_db(tmp_path)
    _insert(
        content_hash="malformed",
        imported_at="2026-01-01T10:00:00",
        headers=raw,  # raw string / None straight into headers_json
    )
    out = build_rating()
    assert out["gamesCounted"] == 0
    assert out["gamesSkipped"] == 0
    assert out["botElo"] is None


def test_build_rating_null_color_row_not_counted(tmp_path):
    _init_db(tmp_path)
    # my_color IS NULL → filtered out by SQL, never miscounted.
    _insert(
        content_hash="null_color",
        imported_at="2026-01-01T10:00:00",
        my_color=None,
        headers={"rated": True, "personaElo": 1500},
    )
    out = build_rating()
    assert out["gamesCounted"] == 0
    assert out["gamesSkipped"] == 0
