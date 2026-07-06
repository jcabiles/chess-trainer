"""
tests/test_trainer.py — Pure unit tests for app/trainer.py.

No engine, no FastAPI, no network.  Uses a temporary DB per test (tmp_path
fixture, same pattern as tests/test_storage.py); the Leitner math tests need
no DB at all.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import app.storage as storage
import app.trainer as trainer

TODAY = date(2026, 7, 5)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init(tmp_path: Path) -> str:
    """Init storage with a temp DB path and return the path string."""
    db_path = str(tmp_path / "games.db")
    storage.init(db_path)
    return db_path


def _qualified_game(content_hash: str = "h1", my_color: str | None = "white",
                    status: str = "done") -> int:
    """Insert a game and return its id (defaults pass the qualification gate)."""
    gid = storage.insert_game({
        "content_hash": content_hash,
        "pgn": "[Event \"?\"]\n1. e4 e5 *",
        "imported_at": "2026-01-01T00:00:00",
        "my_color": my_color,
    })
    storage.set_status(gid, status)
    return gid


def _seed_puzzles(gid: int, specs: list[dict]) -> None:
    """Write plies + leaks for *specs* in one shot (write_* replace per game).

    Each spec: {"ply": int, "motif": str|None, "category": str, "wpd": float,
    "severity": str} — motif/category/wpd/severity optional.
    """
    storage.write_plies(gid, [
        {"ply": s["ply"], "fen_before": f"fen-{gid}-{s['ply']}"} for s in specs
    ])
    storage.write_leaks(gid, [
        storage.LeakRecord(
            game_id=gid,
            ply=s["ply"],
            color="white",
            severity=s.get("severity", "blunder"),
            category=s.get("category", "hanging"),
            phase="middlegame",
            win_prob_before=0.7,
            win_prob_after=0.7 - s.get("wpd", 0.4),
            win_prob_drop=s.get("wpd", 0.4),
            threat_motif=s.get("motif", "fork"),
        )
        for s in specs
    ])


# ---------------------------------------------------------------------------
# natural_key serialization
# ---------------------------------------------------------------------------

class TestNaturalKey:
    def test_format(self):
        assert trainer.natural_key(12, 34, "fork") == "12:34:fork"


# ---------------------------------------------------------------------------
# next_box — Leitner transitions
# ---------------------------------------------------------------------------

class TestNextBox:
    def test_min_sample_zero_served_carries_over(self):
        assert trainer.next_box(3, []) == 3

    def test_min_sample_one_served_carries_over(self):
        """One unlucky puzzle must not erase weeks of progress."""
        assert trainer.next_box(4, ["failed"]) == 4
        assert trainer.next_box(4, ["solved"]) == 4

    def test_promote_at_exactly_70_percent(self):
        outcomes = ["solved"] * 7 + ["failed"] * 3
        assert trainer.next_box(2, outcomes) == 3

    def test_solved_alt_counts_as_solved(self):
        assert trainer.next_box(1, ["solved_alt", "solved_alt"]) == 2

    def test_revealed_counts_as_not_solved(self):
        assert trainer.next_box(3, ["revealed", "revealed"]) == 1

    def test_promotion_caps_at_box_5(self):
        assert trainer.next_box(5, ["solved", "solved"]) == 5

    def test_demote_below_40_percent(self):
        assert trainer.next_box(4, ["failed", "failed", "solved"]) == 1

    def test_stay_at_exactly_40_percent(self):
        """0.40 is not < 0.40 — the bucket stays put."""
        outcomes = ["solved"] * 2 + ["failed"] * 3
        assert trainer.next_box(3, outcomes) == 3

    def test_stay_between_thresholds(self):
        assert trainer.next_box(2, ["solved", "failed"]) == 2


# ---------------------------------------------------------------------------
# is_due — interval math across boxes
# ---------------------------------------------------------------------------

class TestIsDue:
    def test_never_reviewed_is_due(self):
        assert trainer.is_due(1, None, TODAY) is True
        assert trainer.is_due(5, None, TODAY) is True

    def test_box1_due_after_one_day(self):
        assert trainer.is_due(1, "2026-07-04", TODAY) is True

    def test_box1_not_due_same_day(self):
        assert trainer.is_due(1, "2026-07-05", TODAY) is False

    def test_box2_interval_two_days(self):
        assert trainer.is_due(2, "2026-07-04", TODAY) is False
        assert trainer.is_due(2, "2026-07-03", TODAY) is True

    def test_box5_interval_fourteen_days(self):
        assert trainer.is_due(5, "2026-06-22", TODAY) is False  # 13 days
        assert trainer.is_due(5, "2026-06-21", TODAY) is True   # 14 days

    def test_accepts_date_objects_and_iso_strings(self):
        assert trainer.is_due(1, date(2026, 7, 1).isoformat(), "2026-07-05") is True


# ---------------------------------------------------------------------------
# get_live_pool — sourcing + qualification gate
# ---------------------------------------------------------------------------

class TestLivePool:
    def test_qualified_leak_appears(self, tmp_path):
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": 5, "motif": "fork"}])
        pool = trainer.get_live_pool()
        assert list(pool) == ["fork"]
        assert pool["fork"][0]["fen_before"] == f"fen-{gid}-5"
        assert pool["fork"][0]["key"] == f"{gid}:5:fork"

    def test_untagged_game_excluded(self, tmp_path):
        _init(tmp_path)
        gid = _qualified_game(my_color=None)
        _seed_puzzles(gid, [{"ply": 5}])
        assert trainer.get_live_pool() == {}

    def test_unanalyzed_game_excluded(self, tmp_path):
        _init(tmp_path)
        gid = _qualified_game(status="pending")
        _seed_puzzles(gid, [{"ply": 5}])
        assert trainer.get_live_pool() == {}

    def test_non_mistake_severity_excluded(self, tmp_path):
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": 5, "severity": "inaccuracy"}])
        assert trainer.get_live_pool() == {}

    def test_bucket_falls_back_to_category(self, tmp_path):
        """NULL threat_motif buckets under category — B2's stats convention."""
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": 5, "motif": None, "category": "hanging"}])
        pool = trainer.get_live_pool()
        assert list(pool) == ["hanging"]
        assert pool["hanging"][0]["key"] == f"{gid}:5:hanging"


# ---------------------------------------------------------------------------
# assemble_session — rotation, caps, hygiene, reserve-vs-hardest-first
# ---------------------------------------------------------------------------

class TestAssembleSession:
    def test_empty_db_yields_empty_session(self, tmp_path):
        _init(tmp_path)
        assert trainer.assemble_session(TODAY) == {"buckets": [], "puzzles": []}

    def test_per_bucket_cap_and_cursor_advance(self, tmp_path):
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": p, "motif": "fork"} for p in (1, 2, 3, 4, 5)])
        session = trainer.assemble_session(TODAY)
        assert [p["ply"] for p in session["puzzles"]] == [1, 2, 3]
        assert session["buckets"] == [{
            "motif": "fork", "box": 1, "last_reviewed": None,
            "pool_size": 5, "served": 3,
        }]
        boxes = storage.get_trainer_boxes()
        assert boxes[0]["cursor_key"] == f"{gid}:3:fork"

    def test_rotation_never_repeats_within_a_cycle(self, tmp_path):
        """Consecutive sessions walk the whole bucket before any repeat."""
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": p, "motif": "fork"} for p in (1, 2, 3, 4, 5)])
        first = trainer.assemble_session(TODAY)
        second = trainer.assemble_session(TODAY)
        served = [p["ply"] for p in first["puzzles"] + second["puzzles"]]
        assert served == [1, 2, 3, 4, 5, 1]  # ply 1 resurfaces only after 2-5

    def test_cursor_recovery_on_vanished_key(self, tmp_path):
        """A stale cursor (re-analysis/deletion) restarts at the first item."""
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": p, "motif": "fork"} for p in (1, 2, 3)])
        storage.upsert_trainer_box("fork", box=1, cursor_key="999:99:fork")
        session = trainer.assemble_session(TODAY)
        assert [p["ply"] for p in session["puzzles"]] == [1, 2, 3]

    def test_box_reset_on_empty_motif_pool(self, tmp_path):
        """A stale box-5 schedule must not survive an emptied weakness pool."""
        _init(tmp_path)
        _qualified_game()  # no leaks at all
        storage.upsert_trainer_box(
            "pin", box=5, last_reviewed="2026-01-01", cursor_key="1:5:pin"
        )
        trainer.assemble_session(TODAY)
        rows = storage.get_trainer_boxes()
        assert rows == [{
            "motif": "pin", "box": 1, "last_reviewed": None, "cursor_key": None,
        }]

    def test_not_due_bucket_is_skipped(self, tmp_path):
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": 1, "motif": "fork"}])
        storage.upsert_trainer_box(
            "fork", box=5, last_reviewed=TODAY.isoformat()
        )
        assert trainer.assemble_session(TODAY) == {"buckets": [], "puzzles": []}

    def test_reserve_one_slot_per_bucket_beats_hardest_first(self, tmp_path):
        """An all-easy bucket still gets its reserved slot when hard buckets
        could fill the whole session (naive hardest-first would starve it)."""
        _init(tmp_path)
        gid = _qualified_game()
        specs = (
            [{"ply": p, "motif": "fork", "wpd": w}
             for p, w in ((1, 0.90), (2, 0.89), (3, 0.88))]
            + [{"ply": p, "motif": "pin", "wpd": w}
               for p, w in ((4, 0.80), (5, 0.79), (6, 0.78))]
            + [{"ply": p, "motif": "hanging", "wpd": w}
               for p, w in ((7, 0.70), (8, 0.69), (9, 0.68))]
            + [{"ply": p, "motif": "skewer", "wpd": w}
               for p, w in ((10, 0.05), (11, 0.04), (12, 0.03))]
        )
        _seed_puzzles(gid, specs)
        session = trainer.assemble_session(TODAY)
        served = {b["motif"]: b["served"] for b in session["buckets"]}
        assert len(session["puzzles"]) == trainer.SESSION_CAP  # cap holds
        assert served == {"fork": 3, "pin": 3, "hanging": 3, "skewer": 1}

    def test_fill_is_hardest_first(self, tmp_path):
        """With capacity for exactly one extra puzzle, the bucket with the
        hardest next-in-rotation candidate gets it — not the first bucket in
        iteration order (fork sorts before pin but pin's 2nd puzzle is harder)."""
        _init(tmp_path)
        gid = _qualified_game()
        # 7 single-puzzle buckets + fork (2 puzzles) + pin (2 puzzles):
        # 9 due buckets reserve 9 slots, leaving 1 to fill from
        # fork's 0.25 vs pin's 0.90 next candidate.
        easy = [{"ply": p, "motif": f"b{p}", "wpd": 0.1} for p in range(1, 8)]
        forks = [{"ply": 8, "motif": "fork", "wpd": 0.20},
                 {"ply": 9, "motif": "fork", "wpd": 0.25}]
        pins = [{"ply": 10, "motif": "pin", "wpd": 0.30},
                {"ply": 11, "motif": "pin", "wpd": 0.90}]
        _seed_puzzles(gid, easy + forks + pins)
        session = trainer.assemble_session(TODAY)
        served = {b["motif"]: b["served"] for b in session["buckets"]}
        assert len(session["puzzles"]) == trainer.SESSION_CAP
        assert served["pin"] == 2
        assert served["fork"] == 1


# ---------------------------------------------------------------------------
# preview_due_buckets — idempotent peek (no serving, no cursor movement)
# ---------------------------------------------------------------------------

class TestPreviewDueBuckets:
    def test_reports_status_without_creating_rows(self, tmp_path):
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": p, "motif": "fork"} for p in (1, 2)])
        preview = trainer.preview_due_buckets(TODAY)
        assert preview == [{
            "motif": "fork", "box": 1, "last_reviewed": None,
            "pool_size": 2, "due": True,
        }]
        assert storage.get_trainer_boxes() == []  # nothing persisted

    def test_flags_not_due_bucket(self, tmp_path):
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": 1, "motif": "fork"}])
        storage.upsert_trainer_box("fork", box=5, last_reviewed=TODAY.isoformat())
        preview = trainer.preview_due_buckets(TODAY)
        assert preview == [{
            "motif": "fork", "box": 5, "last_reviewed": TODAY.isoformat(),
            "pool_size": 1, "due": False,
        }]

    def test_consecutive_previews_leave_boxes_identical(self, tmp_path):
        """Preview never burns rotation: rows are byte-identical across calls
        (a stale empty-pool row is hygiene-reset once, then stable)."""
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": 1, "motif": "fork"}])
        storage.upsert_trainer_box(
            "fork", box=3, last_reviewed="2026-07-01", cursor_key=f"{gid}:1:fork"
        )
        storage.upsert_trainer_box(
            "pin", box=5, last_reviewed="2026-01-01", cursor_key="9:9:pin"
        )  # empty pool → hygiene target
        trainer.preview_due_buckets(TODAY)
        rows_after_first = storage.get_trainer_boxes()
        trainer.preview_due_buckets(TODAY)
        assert storage.get_trainer_boxes() == rows_after_first
        # fork untouched (cursor intact); pin hygiene-reset.
        assert rows_after_first == [
            {"motif": "fork", "box": 3, "last_reviewed": "2026-07-01",
             "cursor_key": f"{gid}:1:fork"},
            {"motif": "pin", "box": 1, "last_reviewed": None, "cursor_key": None},
        ]

    def test_preview_does_not_burn_rotation(self, tmp_path):
        """assemble_session serves from the first item even after previews."""
        _init(tmp_path)
        gid = _qualified_game()
        _seed_puzzles(gid, [{"ply": p, "motif": "fork"} for p in (1, 2, 3, 4, 5)])
        trainer.preview_due_buckets(TODAY)
        trainer.preview_due_buckets(TODAY)
        session = trainer.assemble_session(TODAY)
        assert [p["ply"] for p in session["puzzles"]] == [1, 2, 3]


# ---------------------------------------------------------------------------
# complete_bucket_review — persistence seam
# ---------------------------------------------------------------------------

class TestCompleteBucketReview:
    def test_creates_row_and_stamps_date(self, tmp_path):
        _init(tmp_path)
        new_box = trainer.complete_bucket_review("fork", ["solved", "solved"], TODAY)
        assert new_box == 2
        rows = storage.get_trainer_boxes()
        assert rows[0]["box"] == 2
        assert rows[0]["last_reviewed"] == "2026-07-05"

    def test_preserves_cursor_key(self, tmp_path):
        _init(tmp_path)
        storage.upsert_trainer_box("fork", box=2, cursor_key="1:5:fork")
        trainer.complete_bucket_review("fork", ["failed", "failed"], TODAY)
        rows = storage.get_trainer_boxes()
        assert rows[0]["box"] == 1  # demoted
        assert rows[0]["cursor_key"] == "1:5:fork"  # rotation continues

    def test_min_sample_carries_box_over(self, tmp_path):
        _init(tmp_path)
        storage.upsert_trainer_box("fork", box=4)
        new_box = trainer.complete_bucket_review("fork", ["failed"], TODAY)
        assert new_box == 4
        assert storage.get_trainer_boxes()[0]["box"] == 4
