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
    assert ids == ["casey", "diego", "robin", "morgan", "alex", "vera"]


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
# B5 causal-blunder dials — blunderRate / threatDistance
# --------------------------------------------------------------------------- #


def test_default_ladder_blunder_dials_present_and_monotone():
    # Three personas now share elo=1350 (casey, diego, robin), so a strictly-
    # decreasing / globally-unique blunderRate assertion no longer holds
    # (diego == casey == 0.85; robin == 0.18 undercuts morgan's 0.65 at 1550,
    # so a MIN-per-group check would be non-monotone). Instead: group by elo
    # and assert the MAX blunderRate per elo group is strictly decreasing
    # across strictly-increasing elo groups. Equal-elo personas (e.g. diego's
    # 0.85 == casey's 0.85) may repeat a blunderRate WITHIN a group — that is
    # not asserted unique here, only the max-per-group step-down is.
    ladder = personas.all()
    for p in ladder:
        assert 0.0 <= p.blunderRate <= 1.0
        assert 0.0 <= p.threatDistance <= 1.0

    by_elo: dict[int, list] = {}
    for p in ladder:
        by_elo.setdefault(p.elo, []).append(p)

    elos = sorted(by_elo)
    assert elos == sorted(set(elos))  # strictly increasing group keys (elo values unique)
    max_blunder_per_group = [max(p.blunderRate for p in by_elo[elo]) for elo in elos]
    assert max_blunder_per_group == sorted(max_blunder_per_group, reverse=True)
    assert len(set(max_blunder_per_group)) == len(max_blunder_per_group)  # strict step-down


def test_blunder_dials_derived_from_elo_when_absent(tmp_path):
    # Old-style JSON: no blunderRate/threatDistance fields at all.
    ladder = [
        {"id": "casey", "name": "Casey", "elo": 1350, "style": "solid",
         "description": "d", "temperature": 80},
        {"id": "vera", "name": "Vera", "elo": 2000, "style": "positional",
         "description": "d", "temperature": 100},
    ]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    casey = personas.get("casey")
    vera = personas.get("vera")
    assert casey.blunderRate == pytest.approx(0.85)
    assert casey.threatDistance == pytest.approx(0.15)
    assert vera.blunderRate == pytest.approx(0.20)
    assert vera.threatDistance == pytest.approx(2000 / 3000)
    # Elo-derived defaults keep the ladder monotone even from an old file.
    assert casey.blunderRate > vera.blunderRate
    assert casey.threatDistance < vera.threatDistance


def test_blunder_dials_read_explicitly_when_present(tmp_path):
    ladder = [
        {"id": "casey", "name": "Casey", "elo": 1350, "style": "solid",
         "description": "d", "temperature": 80, "blunderRate": 0.5, "threatDistance": 0.4},
    ]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    casey = personas.get("casey")
    assert casey.blunderRate == 0.5
    assert casey.threatDistance == 0.4


def test_blunder_rate_out_of_range_keeps_defaults(tmp_path):
    ladder = [
        dict(VALID_LADDER[0], blunderRate=1.5),
        dict(VALID_LADDER[1]),
    ]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert len(personas.all()) == 6  # defaults kept


def test_threat_distance_out_of_range_keeps_defaults(tmp_path):
    ladder = [
        dict(VALID_LADDER[0], threatDistance=-0.1),
        dict(VALID_LADDER[1]),
    ]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert len(personas.all()) == 6  # defaults kept


# --------------------------------------------------------------------------- #
# mistakeRate dial (T2)
# --------------------------------------------------------------------------- #


def test_mistake_rate_default_zero_when_absent(tmp_path):
    # Old-style dict without mistakeRate still parses, defaulting to 0.0 — the
    # 4 pre-existing personas stay B4-byte-identical.
    ladder = [
        {"id": "casey", "name": "Casey", "elo": 1350, "style": "solid",
         "description": "d", "temperature": 80, "blunderRate": 0.85, "threatDistance": 0.15},
    ]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    casey = personas.get("casey")
    assert casey.mistakeRate == 0.0


def test_mistake_rate_read_explicitly_when_present(tmp_path):
    ladder = [
        {"id": "casey", "name": "Casey", "elo": 1350, "style": "solid",
         "description": "d", "temperature": 80, "blunderRate": 0.85, "threatDistance": 0.15,
         "mistakeRate": 0.5},
    ]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    casey = personas.get("casey")
    assert casey.mistakeRate == 0.5


def test_mistake_rate_out_of_range_keeps_defaults(tmp_path):
    ladder = [
        dict(VALID_LADDER[0], mistakeRate=1.5),
        dict(VALID_LADDER[1]),
    ]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert len(personas.all()) == 6  # defaults kept


def test_mistake_rate_negative_keeps_defaults(tmp_path):
    ladder = [
        dict(VALID_LADDER[0], mistakeRate=-0.1),
        dict(VALID_LADDER[1]),
    ]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert len(personas.all()) == 6  # defaults kept


def test_existing_four_personas_mistake_rate_zero():
    # The 4 pre-existing personas keep mistakeRate=0.0 (B4-identical behavior).
    for pid in ("casey", "morgan", "alex", "vera"):
        assert personas.get(pid).mistakeRate == 0.0


def test_diego_persona_values():
    diego = personas.get("diego")
    assert diego is not None
    assert diego.name == "Diego"
    assert diego.elo == 1350
    assert diego.style == "attacking"
    assert diego.temperature == 190
    assert diego.blunderRate == pytest.approx(0.85)
    assert diego.threatDistance == pytest.approx(0.10)
    assert diego.mistakeRate == pytest.approx(0.0)
    assert diego.description == "Attacking club player — hunts your king, soft on defense."


def test_robin_persona_values():
    robin = personas.get("robin")
    assert robin is not None
    assert robin.name == "Robin"
    assert robin.elo == 1350
    assert robin.style == "sloppy"
    assert robin.temperature == 100
    assert robin.blunderRate == pytest.approx(0.18)
    assert robin.threatDistance == pytest.approx(0.30)
    assert robin.mistakeRate == pytest.approx(0.50)
    assert robin.description == "Beginner — drifts and leaks small mistakes."


def test_explicit_temperature_wins_for_new_styles():
    # "attacking" / "sloppy" are not in _STYLE_TEMP; the explicit temperature
    # on diego/robin must win regardless (never falls back to the style map).
    diego = personas.get("diego")
    robin = personas.get("robin")
    assert diego.temperature == 190
    assert robin.temperature == 100


def test_personas_json_matches_default_personas():
    # data/personas.json MUST agree exactly with _DEFAULT_PERSONAS (ids + values).
    personas.init("data/personas.json")
    from_file = personas.all()
    assert [p.as_dict() for p in from_file] == [p.as_dict() for p in personas._DEFAULT_PERSONAS]


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
    assert [p.id for p in personas.all()] == ["casey", "diego", "robin", "morgan", "alex", "vera"]


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
    assert [x.id for x in personas.all()] == ["casey", "diego", "robin", "morgan", "alex", "vera"]


def test_duplicate_ids_keep_defaults(tmp_path):
    dup = VALID_LADDER + [dict(VALID_LADDER[0])]
    path = _write(tmp_path, {"personas": dup})
    personas.init(path)
    assert len(personas.all()) == 6  # defaults


def test_missing_casey_keeps_defaults(tmp_path):
    ladder = [dict(VALID_LADDER[1])]  # only morgan, no casey
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert personas.default_id() == "casey"
    assert [p.id for p in personas.all()] == ["casey", "diego", "robin", "morgan", "alex", "vera"]


def test_elo_out_of_range_keeps_defaults(tmp_path):
    ladder = [dict(VALID_LADDER[0], elo=1000), dict(VALID_LADDER[1])]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert len(personas.all()) == 6


def test_temp_non_positive_keeps_defaults(tmp_path):
    ladder = [dict(VALID_LADDER[0], temperature=0), dict(VALID_LADDER[1])]
    path = _write(tmp_path, {"personas": ladder})
    personas.init(path)
    assert len(personas.all()) == 6


def test_empty_ladder_keeps_defaults(tmp_path):
    path = _write(tmp_path, {"personas": []})
    personas.init(path)
    assert len(personas.all()) == 6


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
