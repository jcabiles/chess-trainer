"""
Unit tests for app/personas.py — persona catalog + pure seeded sampling.

No engine, no network. The default ladder is set at import with no file I/O, so
``all()`` works before any ``init`` call. ``init`` overrides from a temp JSON;
invalid files keep the built-in default.
"""

from __future__ import annotations

import json

import pytest

from app import personas


@pytest.fixture(autouse=True)
def reset_after():
    """Each test starts from and ends on the built-in default ladder."""
    personas.init(MISSING)  # missing → built-in default
    yield
    personas.init(MISSING)


MISSING = "tests/fixtures/does_not_exist_personas.json"


def _write(tmp_path, obj):
    p = tmp_path / "personas.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


VALID_LADDER = [
    {"id": "casey", "name": "Casey", "elo": 1350, "style": "solid",
     "description": "d", "temperature": 80},
    {"id": "morgan", "name": "Morgan", "elo": 1550, "style": "tactical",
     "description": "d", "temperature": 130},
]


# --------------------------------------------------------------------------- #
# Default ladder / no-I/O-at-import
# --------------------------------------------------------------------------- #


def test_default_ladder_present_without_init():
    # all() works before any explicit init in this test — proves the default is
    # set at import with no file I/O.
    ids = [p.id for p in personas.all()]
    assert ids == ["casey", "morgan", "alex", "vera"]


def test_default_id_and_casey_elo():
    assert personas.default_id() == "casey"
    casey = personas.get("casey")
    assert casey is not None
    assert casey.elo == 1350


def test_get_unknown_returns_none():
    assert personas.get("nope") is None


def test_default_persona_shape():
    p = personas.get("morgan")
    assert p.name == "Morgan" and p.style == "tactical"
    assert p.temperature == 130
    assert p.elo == 1550
    # description carried
    assert p.description


# --------------------------------------------------------------------------- #
# init() overrides + validation
# --------------------------------------------------------------------------- #


def test_init_overrides_from_temp_json(tmp_path):
    path = _write(tmp_path, {"personas": VALID_LADDER})
    personas.init(path)
    assert [p.id for p in personas.all()] == ["casey", "morgan"]


def test_init_accepts_bare_list(tmp_path):
    path = _write(tmp_path, VALID_LADDER)
    personas.init(path)
    assert [p.id for p in personas.all()] == ["casey", "morgan"]


def test_temperature_derived_from_style_when_absent(tmp_path):
    ladder = [
        {"id": "casey", "name": "Casey", "elo": 1350, "style": "solid",
         "description": "d"},
        {"id": "alex", "name": "Alex", "elo": 1800, "style": "aggressive",
         "description": "d"},
    ]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert personas.get("casey").temperature == 80      # solid
    assert personas.get("alex").temperature == 200      # aggressive


def test_missing_file_keeps_defaults():
    personas.init(MISSING)
    assert [p.id for p in personas.all()] == ["casey", "morgan", "alex", "vera"]


def test_env_override(tmp_path, monkeypatch):
    path = _write(tmp_path, {"personas": VALID_LADDER})
    monkeypatch.setenv("PERSONAS_FILE", path)
    personas.init()  # no explicit path → reads env
    assert [p.id for p in personas.all()] == ["casey", "morgan"]


@pytest.mark.parametrize("obj", [
    "not json at all",  # written raw below
])
def test_malformed_json_keeps_defaults(tmp_path, obj):
    p = tmp_path / "personas.json"
    p.write_text(obj, encoding="utf-8")
    personas.init(str(p))
    assert [x.id for x in personas.all()] == ["casey", "morgan", "alex", "vera"]


def test_duplicate_ids_keep_defaults(tmp_path):
    dup = VALID_LADDER + [dict(VALID_LADDER[0])]
    path = _write(tmp_path, {"personas": dup})
    personas.init(path)
    assert len(personas.all()) == 4  # defaults


def test_missing_casey_keeps_defaults(tmp_path):
    ladder = [dict(VALID_LADDER[1])]  # only morgan, no casey
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert personas.default_id() == "casey"
    assert [p.id for p in personas.all()] == ["casey", "morgan", "alex", "vera"]


def test_elo_out_of_range_keeps_defaults(tmp_path):
    ladder = [dict(VALID_LADDER[0], elo=1000), dict(VALID_LADDER[1])]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert len(personas.all()) == 4


def test_temp_non_positive_keeps_defaults(tmp_path):
    ladder = [dict(VALID_LADDER[0], temperature=0), dict(VALID_LADDER[1])]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert len(personas.all()) == 4


def test_empty_ladder_keeps_defaults(tmp_path):
    path = _write(tmp_path, {"personas": []})
    personas.init(path)
    assert len(personas.all()) == 4


# --------------------------------------------------------------------------- #
# weighted_choice — pure sampling
# --------------------------------------------------------------------------- #


def test_weighted_choice_empty_raises():
    with pytest.raises(ValueError):
        personas.weighted_choice([], 100, seed=0)


def test_weighted_choice_single_returns_zero():
    assert personas.weighted_choice([42], 100, seed=7) == 0


def test_weighted_choice_deterministic_under_fixed_seed():
    scores = [10, 5, 0, -20]
    a = personas.weighted_choice(scores, 100, seed=1234)
    b = personas.weighted_choice(scores, 100, seed=1234)
    assert a == b


def test_weighted_choice_prefers_top_at_low_temp():
    # Very cold: index of the max score dominates across many seeds.
    scores = [0, 100, -50]
    picks = [personas.weighted_choice(scores, 1, seed=s) for s in range(200)]
    # nearly all should be the top-scoring index (1)
    assert picks.count(1) > 190


def test_weighted_choice_hotter_temp_is_flatter():
    # Same scores; a hotter temperature spreads picks across more indices.
    scores = [0, 60, 120, 180]
    n = 400

    def distinct(temp):
        picks = [personas.weighted_choice(scores, temp, seed=s) for s in range(n)]
        # spread = how far the counts are from a single dominating index
        top_share = max(picks.count(i) for i in range(len(scores))) / n
        return top_share

    cold_top = distinct(30)
    hot_top = distinct(400)
    # Hotter temperature → flatter → the top index takes a SMALLER share.
    assert hot_top < cold_top


def test_weighted_choice_temp_floor_no_crash():
    # temperature <= 0 clamps to 1 rather than dividing by zero.
    assert personas.weighted_choice([5, 3], 0, seed=1) in (0, 1)


def test_weighted_choice_mover_pov_mate_sorts():
    # Mate mapped to ±100000 upstream; a winning-mate score should dominate.
    scores = [100000, 20, -100000]
    picks = [personas.weighted_choice(scores, 100, seed=s) for s in range(100)]
    assert set(picks) == {0}  # the +mate index always wins
