"""
tests/test_insights.py — Unit tests for app/insights.py (Openings slice).

Seeds a temp DB (storage.init(tmp_path)), inserts games + plies via storage
CRUD helpers, drives repertoire/book state explicitly, then asserts
build_openings_insights() returns correct, honesty-gated aggregates.

No engine, no network, no Stockfish.
"""

from __future__ import annotations

import json
from pathlib import Path

import chess
import pytest

import app.storage as storage
from app import book, repertoire
from app.accuracy import summarize
from app.insights import (
    CLUSTER_GATE,
    MIN_SAMPLE,
    build_mistakes_insights,
    build_openings_insights,
    gated,
)
from app.storage import LeakRecord

BOOK_FIXTURE = "tests/fixtures/book_sample.json"  # firstMoves = ["e2e4"]
MISSING = "tests/fixtures/does_not_exist.json"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_modules(tmp_path):
    """Fresh temp DB + empty repertoire/book for every test; reset after."""
    storage.init(str(tmp_path / "test_games.db"))
    repertoire.load(MISSING)
    book.load(MISSING)
    yield
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


def _plies_from_san(
    sans: list[str],
    evals: list[int] | None = None,
    win_probs: list[float] | None = None,
) -> list[dict]:
    """Replay SAN moves from the start into game_plies-shaped dicts (1-based)."""
    board = chess.Board()
    rows = []
    for i, san in enumerate(sans):
        fen_before = board.fen()
        move = board.parse_san(san)
        rows.append({
            "ply": i + 1,
            "san": san,
            "uci": move.uci(),
            "fen_before": fen_before,
            "eval_cp_white": evals[i] if evals else 0,
            "win_prob": win_probs[i] if win_probs else None,
        })
        board.push(move)
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
# Honesty gate (T0.3)
# ---------------------------------------------------------------------------


class TestGate:
    def test_below_min_sample_insufficient(self):
        assert gated(0.5, 4) == {"value": 0.5, "n": 4, "sufficient": False}

    def test_at_min_sample_sufficient(self):
        assert gated(0.5, MIN_SAMPLE) == {"value": 0.5, "n": 5, "sufficient": True}


# ---------------------------------------------------------------------------
# Win% by opening (T1.1)
# ---------------------------------------------------------------------------


class TestWinRates:
    def _seed_sicilian(self):
        # 3 Najdorf + 2 Dragon games as Black: family n=5, each line sub-min.
        najdorf = "Sicilian Defense: Najdorf Variation"
        dragon = "Sicilian Defense: Dragon Variation"
        _insert_game(content_hash="n1", my_color="black", opening=najdorf, result="0-1")
        _insert_game(content_hash="n2", my_color="black", opening=najdorf, result="1-0")
        _insert_game(content_hash="n3", my_color="black", opening=najdorf, result="1/2-1/2")
        _insert_game(content_hash="d1", my_color="black", opening=dragon, result="0-1")
        _insert_game(content_hash="d2", my_color="black", opening=dragon, result="0-1")

    def test_family_aggregation_and_score(self):
        self._seed_sicilian()
        fams = build_openings_insights()["win_rates"]["families"]
        assert len(fams) == 1
        fam = fams[0]
        assert fam["opening"] == "Sicilian Defense"
        assert fam["color"] == "black"
        # Black's perspective: 0-1 = win. wins=3, draws=1, losses=1.
        assert (fam["wins"], fam["draws"], fam["losses"]) == (3, 1, 1)
        assert fam["n"] == 5
        assert fam["score"] == pytest.approx(0.7)
        assert fam["sufficient"] is True

    def test_lines_sub_min_sample_gated(self):
        self._seed_sicilian()
        lines = build_openings_insights()["win_rates"]["lines"]
        assert len(lines) == 2
        for line in lines:
            assert line["family"] == "Sicilian Defense"
            assert line["sufficient"] is False
        najdorf = next(ln for ln in lines
                       if ln["opening"] == "Sicilian Defense: Najdorf Variation")
        assert najdorf["n"] == 3

    def test_unknown_result_and_unqualified_games_excluded(self):
        self._seed_sicilian()
        _insert_game(content_hash="x1", my_color="black",
                     opening="Sicilian Defense: Najdorf Variation", result="*")
        _insert_game(content_hash="x2", my_color=None,
                     opening="Sicilian Defense: Najdorf Variation", result="0-1")
        _insert_game(content_hash="x3", my_color="black",
                     opening="Sicilian Defense: Najdorf Variation", result="0-1",
                     analysis_status="pending")
        fam = build_openings_insights()["win_rates"]["families"][0]
        assert fam["n"] == 5  # none of x1/x2/x3 counted

    def test_missing_opening_falls_back_to_eco(self):
        _insert_game(content_hash="e1", my_color="white", opening=None,
                     eco="B20", result="1-0")
        fams = build_openings_insights()["win_rates"]["families"]
        assert fams[0]["opening"] == "B20"


# ---------------------------------------------------------------------------
# Repertoire adherence (T1.2)
# ---------------------------------------------------------------------------


class TestAdherence:
    def test_follow_then_deviate(self, tmp_path):
        _load_repertoire(tmp_path)
        gid = _insert_game(content_hash="g1", my_color="white")
        # Follows prep for 4 plies, then user plays 3.Bc4 where prep says 3.Bb5.
        storage.write_plies(gid, _plies_from_san(["e4", "e5", "Nf3", "Nc6", "Bc4"]))

        result = build_openings_insights()
        adh = result["adherence"]
        assert adh["n"] == 1
        game = adh["games"][0]
        assert game["game_id"] == gid
        assert game["followed_prep_depth"] == 4
        assert game["deviation_ply"] == 5
        assert game["deviation_move"] == "Bc4"
        assert game["prepared_san"] == "Bb5"
        assert game["line_ids"] == ["ruy-test"]
        assert adh["avg_followed_prep_depth"] == {
            "value": 4, "n": 1, "sufficient": False}
        line = adh["lines"][0]
        assert (line["line_id"], line["n"], line["deviations"]) == ("ruy-test", 1, 1)
        assert line["name"] == "Ruy Lopez test line"
        assert line["color"] == "white"
        assert line["sufficient"] is False
        # Off-repertoire theory section stays empty.
        assert result["theory"]["n"] == 0

    def test_opponent_deviation_is_not_a_user_deviation(self, tmp_path):
        _load_repertoire(tmp_path)
        gid = _insert_game(content_hash="g2", my_color="white")
        # Opponent leaves prep at ply 2 (1...c5 instead of 1...e5).
        storage.write_plies(gid, _plies_from_san(["e4", "c5", "Nf3"]))
        adh = build_openings_insights()["adherence"]
        assert adh["n"] == 1
        game = adh["games"][0]
        assert game["followed_prep_depth"] == 1
        assert game["deviation_ply"] is None
        assert game["deviation_move"] is None

    def test_ply1_deviation_attributed_to_prepared_line(self, tmp_path):
        """A root deviation (user's very first move) must still credit the line."""
        _load_repertoire(tmp_path)
        gid = _insert_game(content_hash="g5", my_color="white")
        storage.write_plies(gid, _plies_from_san(["d4", "d5"]))  # prep says 1.e4
        adh = build_openings_insights()["adherence"]
        assert adh["n"] == 1
        game = adh["games"][0]
        assert game["followed_prep_depth"] == 0
        assert game["deviation_ply"] == 1
        assert game["deviation_move"] == "d4"
        assert game["prepared_san"] == "e4"
        assert game["line_ids"] == ["ruy-test"]
        line = adh["lines"][0]
        assert (line["line_id"], line["n"], line["deviations"]) == ("ruy-test", 1, 1)
        assert line["avg_followed_prep_depth"] == 0

    def test_shared_node_credits_every_consistent_line(self, tmp_path):
        """A game ending on a node shared by two prepared lines credits both."""
        path = tmp_path / "repertoire.json"
        path.write_text(json.dumps({
            "lines": [
                {"id": "ruy-a", "name": "Ruy line", "parentOpening": "Ruy Lopez",
                 "yourColor": "white", "line": ["e4", "e5", "Nf3", "Nc6", "Bb5"]},
                {"id": "sicilian-b", "name": "Open Sicilian line",
                 "parentOpening": "Sicilian", "yourColor": "white",
                 "line": ["e4", "c5", "Nf3"]},
            ]
        }))
        repertoire.load(str(path))
        gid = _insert_game(content_hash="g6", my_color="white")
        # Opponent leaves prep at ply 2 (1...d5) — deepest node (after 1.e4)
        # is shared by both prepared lines.
        storage.write_plies(gid, _plies_from_san(["e4", "d5"]))
        adh = build_openings_insights()["adherence"]
        game = adh["games"][0]
        assert game["followed_prep_depth"] == 1
        assert game["deviation_ply"] is None
        assert sorted(game["line_ids"]) == ["ruy-a", "sicilian-b"]
        assert {(ln["line_id"], ln["n"], ln["deviations"]) for ln in adh["lines"]} == {
            ("ruy-a", 1, 0), ("sicilian-b", 1, 0)}

    def test_off_repertoire_game_excluded_from_adherence(self, tmp_path):
        _load_repertoire(tmp_path)  # white prep only
        gid = _insert_game(content_hash="g3", my_color="black")
        storage.write_plies(gid, _plies_from_san(["e4", "c5"]))
        result = build_openings_insights()
        assert result["adherence"]["n"] == 0
        assert result["theory"]["n"] == 1
        assert result["coverage"]["on_repertoire"] == 0
        assert result["coverage"]["off_repertoire"] == 1


# ---------------------------------------------------------------------------
# Theory fallback (T1.3)
# ---------------------------------------------------------------------------


class TestTheory:
    def test_book_exit_ply_is_last_in_theory_move(self):
        # Repertoire empty → all games off-repertoire. Book: Ruy line only.
        book.load(BOOK_FIXTURE,
                  lines=[["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]])
        gid = _insert_game(content_hash="t1", my_color="white")
        # 4 in-book plies, then 3.a3 (not book).
        storage.write_plies(gid, _plies_from_san(["e4", "e5", "Nf3", "Nc6", "a3"]))
        theory = build_openings_insights()["theory"]
        assert theory["games"][0]["book_exit_ply"] == 4
        assert theory["avg_book_exit_ply"] == {
            "value": 4, "n": 1, "sufficient": False}

    def test_never_in_book_is_zero(self):
        book.load(BOOK_FIXTURE, lines=[["e2e4", "e7e5"]])
        gid = _insert_game(content_hash="t2", my_color="white")
        storage.write_plies(gid, _plies_from_san(["d4", "d5"]))  # out of scope
        theory = build_openings_insights()["theory"]
        assert theory["games"][0]["book_exit_ply"] == 0

    def test_opening_accuracy_restricted_to_opening_phase(self):
        gid = _insert_game(content_hash="t3", my_color="white")
        eg_w = "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1"  # K+P endgame, white to move
        eg_b = "8/8/4k3/8/8/4K3/4P3/8 b - - 0 1"
        board = chess.Board()
        fen1 = board.fen()
        board.push_san("e4")
        fen2 = board.fen()
        plies = [
            {"ply": 1, "san": "e4", "uci": "e2e4", "fen_before": fen1,
             "eval_cp_white": 20},
            {"ply": 2, "san": "e5", "uci": "e7e5", "fen_before": fen2,
             "eval_cp_white": 20},
            # Endgame phase: white then throws the game (huge eval drop).
            {"ply": 3, "san": "Ke3", "uci": "e3e4", "fen_before": eg_w,
             "eval_cp_white": 20},
            {"ply": 4, "san": "Kd5", "uci": "e6d5", "fen_before": eg_b,
             "eval_cp_white": -900},
        ]
        storage.write_plies(gid, plies)
        theory = build_openings_insights()["theory"]
        # Restricted to the opening prefix, White played perfectly.
        assert theory["games"][0]["opening_accuracy"] == 100.0
        # Unrestricted, the endgame blunder would drag White's accuracy down.
        full = summarize(storage.get_plies(gid), "white")["white_accuracy"]
        assert full < 100.0

    def test_honest_named_theory_note(self):
        note = build_openings_insights()["theory"]["note"]
        assert "not the same as moves endorsed by masters" in note


# ---------------------------------------------------------------------------
# Recurring-mistake clusters (T2.1)
# ---------------------------------------------------------------------------


class TestClusters:
    def _seed(self):
        # Game A is older; game B is the most recent import.
        gid_a = _insert_game(content_hash="ca", imported_at="2026-01-10T10:00:00")
        gid_b = _insert_game(content_hash="cb", imported_at="2026-01-20T10:00:00")
        storage.write_leaks(gid_a, [
            _make_leak(gid_a, ply=10), _make_leak(gid_a, ply=12),
            _make_leak(gid_a, ply=14),
        ])  # 3× hanging/middlegame
        storage.write_leaks(gid_b, [
            _make_leak(gid_b, ply=20), _make_leak(gid_b, ply=22),  # +2 hanging
            _make_leak(gid_b, ply=2, category="knight_fork", phase="opening"),
            _make_leak(gid_b, ply=4, category="knight_fork", phase="opening"),
            _make_leak(gid_b, ply=6, category="knight_fork", phase="opening"),
            _make_leak(gid_b, ply=8, category="knight_fork", phase="opening"),
            _make_leak(gid_b, ply=30, category="pin", phase="endgame"),
            _make_leak(gid_b, ply=32, category="pin", phase="endgame"),
        ])
        return gid_a, gid_b

    def test_ranking_and_gate(self):
        self._seed()
        clusters = build_mistakes_insights()["clusters"]
        assert clusters["n_leaks"] == 11
        items = clusters["items"]
        # hanging (5) ranks above knight_fork (4); pin (2) is below CLUSTER_GATE.
        assert [(i["category"], i["phase"], i["count"]) for i in items] == [
            ("hanging", "middlegame", 5), ("knight_fork", "opening", 4)]
        assert all(i["count"] >= CLUSTER_GATE for i in items)
        assert clusters["suppressed"] == {
            "cells": 1, "leaks": 2, "gate": CLUSTER_GATE}

    def test_cluster_names_are_human(self):
        self._seed()
        for item in build_mistakes_insights()["clusters"]["items"]:
            assert item["name"]  # non-empty human name via coaching.name_cluster

    def test_example_is_most_recent_leak(self):
        _, gid_b = self._seed()
        items = build_mistakes_insights()["clusters"]["items"]
        hanging = next(i for i in items if i["category"] == "hanging")
        # Most recent import (game B), highest ply within it.
        assert hanging["example"] == {"game_id": gid_b, "ply": 22}

    def test_generic_missed_threat_labeled_honestly(self):
        gid = _insert_game(content_hash="mt")
        storage.write_leaks(gid, [
            _make_leak(gid, ply=p, category="missed_threat", phase="middlegame")
            for p in (10, 12, 14, 16)
        ])
        items = build_mistakes_insights()["clusters"]["items"]
        assert items[0]["name"] == "Other tactical misses in the middlegame"

    def test_unqualified_games_leaks_excluded(self):
        gid = _insert_game(content_hash="cu", my_color=None)
        storage.write_leaks(gid, [_make_leak(gid, ply=p) for p in (2, 4, 6, 8)])
        clusters = build_mistakes_insights()["clusters"]
        assert clusters["n_leaks"] == 0
        assert clusters["items"] == []


# ---------------------------------------------------------------------------
# Foreseeable-rate (T2.2)
# ---------------------------------------------------------------------------


class TestForeseeable:
    def test_rate_and_dominant_motif(self):
        gid = _insert_game(content_hash="f1")
        storage.write_leaks(gid, [
            _make_leak(gid, ply=20, lead_in_ply=18, threat_motif="knight_fork"),
            _make_leak(gid, ply=22, lead_in_ply=20, threat_motif="knight_fork"),
            _make_leak(gid, ply=24, lead_in_ply=24, threat_motif="pin"),  # not <
            _make_leak(gid, ply=26),  # no lead-in at all
        ])
        fore = build_mistakes_insights()["foreseeable"]
        assert fore["rate"] == {"value": 0.5, "n": 4, "sufficient": False}
        assert fore["dominant_motif"] == "knight_fork"
        assert "narrow definition" in fore["note"]

    def test_default_lead_in_ply_not_counted(self):
        """lead_in_ply == ply - 1 is the pipeline's display-timing default —
        it must NOT count as foreseeable; ply - 2 must."""
        gid = _insert_game(content_hash="f3")
        storage.write_leaks(gid, [
            _make_leak(gid, ply=20, lead_in_ply=19, threat_motif="pin"),   # default
            _make_leak(gid, ply=30, lead_in_ply=28, threat_motif="fork"),  # genuine
        ])
        fore = build_mistakes_insights()["foreseeable"]
        assert fore["rate"] == {"value": 0.5, "n": 2, "sufficient": False}
        # The excluded default leak's motif must not leak into the mode.
        assert fore["dominant_motif"] == "fork"

    def test_dominant_motif_tie_breaks_alphabetically(self):
        gid = _insert_game(content_hash="f4")
        storage.write_leaks(gid, [
            _make_leak(gid, ply=20, lead_in_ply=18, threat_motif="pin"),
            _make_leak(gid, ply=22, lead_in_ply=20, threat_motif="fork"),
        ])
        fore = build_mistakes_insights()["foreseeable"]
        assert fore["dominant_motif"] == "fork"  # 1-1 tie → alphabetical

    def test_no_motifs_gives_none(self):
        gid = _insert_game(content_hash="f2")
        storage.write_leaks(gid, [_make_leak(gid, ply=20, lead_in_ply=18)])
        fore = build_mistakes_insights()["foreseeable"]
        assert fore["rate"]["value"] == 1.0
        assert fore["dominant_motif"] is None


# ---------------------------------------------------------------------------
# Time-trouble (T2.3)
# ---------------------------------------------------------------------------


class TestTimeTrouble:
    def test_buckets_baseline_and_unclocked_note(self):
        gid_a = _insert_game(content_hash="tt1")  # clocked game
        storage.write_plies(gid_a, [
            {"ply": 1, "is_user_move": True, "clock_centis": 500},   # <10s, leak
            {"ply": 2, "is_user_move": False, "clock_centis": 800},  # opponent
            {"ply": 3, "is_user_move": True, "clock_centis": 900},   # <10s
            {"ply": 5, "is_user_move": True, "clock_centis": 20000},  # >2m
        ])
        storage.write_leaks(gid_a, [_make_leak(gid_a, ply=1)])
        gid_b = _insert_game(content_hash="tt2")  # unclocked game
        storage.write_plies(gid_b, [{"ply": 1, "is_user_move": True}])

        tt = build_mistakes_insights()["time_trouble"]
        assert tt["clocked_games"] == 1
        assert tt["unclocked_games"] == 1
        assert "1 of 2" in tt["note"]
        # 3 clocked user moves, 1 is a leak.
        assert tt["baseline_rate"] == {
            "value": pytest.approx(0.333), "n": 3, "sufficient": False}
        by_label = {b["bucket"]: b for b in tt["buckets"]}
        assert set(by_label) == {"<10s", "10s-30s", "30s-2m", ">2m"}
        assert (by_label["<10s"]["moves"], by_label["<10s"]["leaks"]) == (2, 1)
        assert by_label["<10s"]["rate"] == pytest.approx(0.5)
        assert by_label["<10s"]["sufficient"] is False
        assert (by_label[">2m"]["moves"], by_label[">2m"]["leaks"]) == (1, 0)
        assert by_label["10s-30s"] == {
            "bucket": "10s-30s", "moves": 0, "leaks": 0, "rate": None,
            "sufficient": False}

    def test_bucket_boundaries(self):
        """Edges land on the right side: lo inclusive, hi exclusive."""
        gid = _insert_game(content_hash="tt3")
        centis = [999, 1000, 2999, 3000, 11999, 12000] + [500] * 5
        storage.write_plies(gid, [
            {"ply": i + 1, "is_user_move": True, "clock_centis": c}
            for i, c in enumerate(centis)
        ])
        tt = build_mistakes_insights()["time_trouble"]
        by_label = {b["bucket"]: b for b in tt["buckets"]}
        assert by_label["<10s"]["moves"] == 6       # 999 + five 500s
        assert by_label["<10s"]["sufficient"] is True
        assert by_label["10s-30s"]["moves"] == 2    # 1000, 2999
        assert by_label["30s-2m"]["moves"] == 2     # 3000, 11999
        assert by_label[">2m"]["moves"] == 1        # 12000


# ---------------------------------------------------------------------------
# Advantage capitalization (T2.4)
# ---------------------------------------------------------------------------


class TestCapitalization:
    def test_sustained_stretch_counted_spike_ignored(self):
        # Sustained: user (White) holds >=0.8 for 5 consecutive plies but LOSES.
        gid_s = _insert_game(content_hash="cap1", result="0-1")
        storage.write_plies(gid_s, _plies_from_san(
            ["e4", "e5", "Nf3", "Nc6", "Bb5"],
            # win_prob is mover-POV: 0.9 on White's moves = 0.1 on Black's.
            win_probs=[0.9, 0.1, 0.9, 0.1, 0.9]))
        # Spike: a single winning ply must NOT count as a winning game.
        gid_p = _insert_game(content_hash="cap2", result="1-0")
        storage.write_plies(gid_p, _plies_from_san(
            ["d4", "d5", "c4", "e6", "Nc3"],
            win_probs=[0.5, 0.5, 0.9, 0.5, 0.5]))

        cap = build_mistakes_insights()["capitalization"]
        assert cap["winning_games"] == 1
        assert cap["converted"] == 0
        assert cap["rate"] == {"value": 0.0, "n": 1, "sufficient": False}
        assert "single-ply" in cap["note"]

    def test_converted_win_counts(self):
        gid = _insert_game(content_hash="cap3", result="1-0")
        storage.write_plies(gid, _plies_from_san(
            ["e4", "e5", "Nf3", "Nc6"], win_probs=[0.9, 0.1, 0.9, 0.1]))
        cap = build_mistakes_insights()["capitalization"]
        assert (cap["winning_games"], cap["converted"]) == (1, 1)
        assert cap["rate"]["value"] == 1.0

    def test_unknown_result_game_excluded(self):
        gid = _insert_game(content_hash="cap4", result="*")
        storage.write_plies(gid, _plies_from_san(
            ["e4", "e5", "Nf3", "Nc6"], win_probs=[0.9, 0.1, 0.9, 0.1]))
        cap = build_mistakes_insights()["capitalization"]
        assert (cap["winning_games"], cap["converted"]) == (0, 0)
        assert cap["rate"] == {"value": None, "n": 0, "sufficient": False}


# ---------------------------------------------------------------------------
# Empty-DB safety
# ---------------------------------------------------------------------------


class TestEmptyDB:
    def test_empty_db_returns_empty_safe_shapes(self):
        result = build_openings_insights()
        cov = result["coverage"]
        assert cov["total"] == 0
        assert cov["qualified"] == 0
        assert cov["on_repertoire"] == 0
        assert cov["off_repertoire"] == 0
        assert result["win_rates"] == {"families": [], "lines": []}
        adh = result["adherence"]
        assert adh["n"] == 0
        assert adh["avg_followed_prep_depth"] == {
            "value": None, "n": 0, "sufficient": False}
        assert adh["lines"] == []
        assert adh["games"] == []
        theory = result["theory"]
        assert theory["n"] == 0
        assert theory["avg_book_exit_ply"] == {
            "value": None, "n": 0, "sufficient": False}
        assert theory["avg_opening_accuracy"] == {
            "value": None, "n": 0, "sufficient": False}
        assert theory["games"] == []

    def test_only_unqualified_games_still_empty(self):
        _insert_game(content_hash="u1", my_color=None)
        _insert_game(content_hash="u2", my_color="white", analysis_status="pending")
        result = build_openings_insights()
        assert result["coverage"]["qualified"] == 0
        assert result["win_rates"]["families"] == []
        assert result["adherence"]["n"] == 0
        assert result["theory"]["n"] == 0

    def test_mistakes_empty_db_returns_empty_safe_shapes(self):
        result = build_mistakes_insights()
        assert result["coverage"]["qualified"] == 0
        clusters = result["clusters"]
        assert clusters["n_leaks"] == 0
        assert clusters["items"] == []
        assert clusters["suppressed"] == {
            "cells": 0, "leaks": 0, "gate": CLUSTER_GATE}
        fore = result["foreseeable"]
        assert fore["rate"] == {"value": None, "n": 0, "sufficient": False}
        assert fore["dominant_motif"] is None
        tt = result["time_trouble"]
        assert tt["clocked_games"] == 0
        assert tt["unclocked_games"] == 0
        assert tt["baseline_rate"] == {"value": None, "n": 0, "sufficient": False}
        assert len(tt["buckets"]) == 4
        assert all(b["moves"] == 0 and b["rate"] is None for b in tt["buckets"])
        cap = result["capitalization"]
        assert (cap["winning_games"], cap["converted"]) == (0, 0)
        assert cap["rate"] == {"value": None, "n": 0, "sufficient": False}
