"""
tests/test_storage_narrative.py — Pure unit tests for the v3 narratives schema
(app/storage.py): migration (fresh DB + upgrading an existing v2 DB file),
get_narrative/upsert_narrative/delete_narrative, ON DELETE CASCADE, invalidation
via set_my_color/retag_colors_by_aliases, and get_pos_cache_many.

No engine, no FastAPI, no network.  Uses a temporary DB per test (tmp_path fixture).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import app.storage as storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init(tmp_path: Path, subdir: str = "games.db") -> str:
    """Init storage with a temp DB path and return the path string."""
    db_path = str(tmp_path / subdir)
    storage.init(db_path)
    return db_path


def _game(**overrides) -> dict:
    """Return a minimal valid game fields dict."""
    base = {
        "content_hash": "abc123",
        "pgn": "[Event \"?\"]\n1. e4 e5 *",
        "imported_at": "2026-01-01T00:00:00",
        "white": "White",
        "black": "Black",
        "ply_count": 2,
    }
    base.update(overrides)
    return base


# DDL for a pre-v3 (v2) database — schema_meta + games + pos_cache + game_plies +
# leaks + trainer_attempts + trainer_boxes, WITHOUT the narratives table.  Used to
# hand-craft a real v2 DB file to prove the upgrade path (no shortcuts through the
# current schema, no monkeypatching module internals).
_V2_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
    version  INTEGER NOT NULL
);

CREATE TABLE games (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash    TEXT UNIQUE NOT NULL,
    pgn             TEXT NOT NULL,
    headers_json    TEXT,
    white           TEXT,
    black           TEXT,
    result          TEXT,
    eco             TEXT,
    opening         TEXT,
    date            TEXT,
    my_color        TEXT,
    source          TEXT,
    ply_count       INTEGER,
    imported_at     TEXT NOT NULL,
    analysis_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(analysis_status IN ('pending','analyzing','done','failed'))
);

CREATE TABLE pos_cache (
    epd_key         TEXT NOT NULL,
    depth           INTEGER NOT NULL,
    eval_cp_white   INTEGER,
    mate_white      INTEGER,
    best_uci        TEXT,
    best_san        TEXT,
    pv_san_json     TEXT,
    pv2_cp_white    INTEGER,
    PRIMARY KEY (epd_key, depth)
);

CREATE TABLE game_plies (
    game_id         INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    ply             INTEGER NOT NULL,
    san             TEXT,
    uci             TEXT,
    fen_before      TEXT,
    eval_cp_white   INTEGER,
    mate_white      INTEGER,
    win_prob        REAL,
    is_user_move    INTEGER NOT NULL DEFAULT 0,
    clock_centis    INTEGER,
    PRIMARY KEY (game_id, ply)
);

CREATE TABLE leaks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    ply             INTEGER NOT NULL,
    color           TEXT NOT NULL,
    severity        TEXT NOT NULL,
    category        TEXT NOT NULL,
    motif_json      TEXT,
    phase           TEXT NOT NULL,
    win_prob_before REAL NOT NULL,
    win_prob_after  REAL NOT NULL,
    win_prob_drop   REAL NOT NULL,
    hung_square     TEXT,
    threat_uci      TEXT,
    threat_motif    TEXT,
    best_uci        TEXT,
    best_san        TEXT,
    lead_in_ply     INTEGER,
    tags_json       TEXT,
    explanation_json TEXT
);

CREATE TABLE trainer_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    ply             INTEGER NOT NULL,
    threat_motif    TEXT NOT NULL,
    attempted_uci   TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    cp_delta        INTEGER,
    check_depth     INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE trainer_boxes (
    motif           TEXT PRIMARY KEY,
    box             INTEGER NOT NULL DEFAULT 1,
    last_reviewed   TEXT,
    cursor_key      TEXT
);
"""


def _make_v2_db(db_path: Path) -> int:
    """Hand-craft a real v2 DB file (no narratives table) with one game row.

    Returns the inserted game's id.
    """
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_V2_DDL)
    conn.execute("INSERT INTO schema_meta (version) VALUES (2)")
    conn.execute(
        """
        INSERT INTO games
            (content_hash, pgn, white, black, ply_count, imported_at, analysis_status)
        VALUES
            ('v2hash', '[Event "?"]\n1. e4 e5 *', 'White', 'Black', 2,
             '2026-01-01T00:00:00', 'done')
        """
    )
    conn.commit()
    gid = conn.execute("SELECT id FROM games WHERE content_hash = 'v2hash'").fetchone()[0]
    conn.close()
    return gid


# ---------------------------------------------------------------------------
# Migration: fresh DB
# ---------------------------------------------------------------------------

class TestMigrationFreshDB:
    def test_narratives_table_created(self, tmp_path):
        db_path = _init(tmp_path)
        conn = sqlite3.connect(db_path)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "narratives" in tables

    def test_schema_stamped_v3(self, tmp_path):
        db_path = _init(tmp_path)
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT version FROM schema_meta").fetchone()
        conn.close()
        assert row[0] == storage._SCHEMA_VERSION == 3


# ---------------------------------------------------------------------------
# Migration: upgrading an existing v2 DB file
# ---------------------------------------------------------------------------

class TestMigrationV2Upgrade:
    def test_gains_narratives_table(self, tmp_path):
        db_path = tmp_path / "games.db"
        _make_v2_db(db_path)
        storage.init(str(db_path))

        conn = sqlite3.connect(str(db_path))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "narratives" in tables

    def test_version_stamp_updated(self, tmp_path):
        db_path = tmp_path / "games.db"
        _make_v2_db(db_path)
        storage.init(str(db_path))

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT version FROM schema_meta").fetchone()
        conn.close()
        assert row[0] == 3

    def test_no_data_loss(self, tmp_path):
        db_path = tmp_path / "games.db"
        gid = _make_v2_db(db_path)
        storage.init(str(db_path))

        row = storage.get_game(gid)
        assert row is not None
        assert row["content_hash"] == "v2hash"
        assert row["analysis_status"] == "done"


# ---------------------------------------------------------------------------
# get_narrative / upsert_narrative / delete_narrative
# ---------------------------------------------------------------------------

class TestNarrativeCRUD:
    def test_get_narrative_absent_returns_none(self, tmp_path):
        _init(tmp_path)
        gid = storage.insert_game(_game())
        assert storage.get_narrative(gid) is None

    def test_upsert_then_get_round_trip(self, tmp_path):
        _init(tmp_path)
        gid = storage.insert_game(_game())
        storage.upsert_narrative(gid, "claude-sonnet-5", '{"overall": "hi"}', "2026-07-07T00:00:00")

        row = storage.get_narrative(gid)
        assert row is not None
        assert row["game_id"] == gid
        assert row["model"] == "claude-sonnet-5"
        assert row["narrative_json"] == '{"overall": "hi"}'
        assert row["created_at"] == "2026-07-07T00:00:00"

    def test_upsert_overwrites_existing(self, tmp_path):
        _init(tmp_path)
        gid = storage.insert_game(_game())
        storage.upsert_narrative(gid, "claude-sonnet-5", '{"overall": "v1"}', "2026-07-07T00:00:00")
        storage.upsert_narrative(gid, "claude-sonnet-5", '{"overall": "v2"}', "2026-07-08T00:00:00")

        row = storage.get_narrative(gid)
        assert row["narrative_json"] == '{"overall": "v2"}'
        assert row["created_at"] == "2026-07-08T00:00:00"

        conn = storage._get_conn()
        count = conn.execute(
            "SELECT COUNT(*) FROM narratives WHERE game_id = ?", (gid,)
        ).fetchone()[0]
        assert count == 1  # one row per game, not appended

    def test_delete_narrative(self, tmp_path):
        _init(tmp_path)
        gid = storage.insert_game(_game())
        storage.upsert_narrative(gid, "claude-sonnet-5", '{"overall": "hi"}', "2026-07-07T00:00:00")
        storage.delete_narrative(gid)
        assert storage.get_narrative(gid) is None

    def test_delete_narrative_absent_is_noop(self, tmp_path):
        _init(tmp_path)
        gid = storage.insert_game(_game())
        storage.delete_narrative(gid)  # no row exists — should not raise


# ---------------------------------------------------------------------------
# ON DELETE CASCADE
# ---------------------------------------------------------------------------

class TestNarrativeCascade:
    def test_delete_game_cascades_to_narrative(self, tmp_path):
        _init(tmp_path)
        gid = storage.insert_game(_game())
        storage.upsert_narrative(gid, "claude-sonnet-5", '{"overall": "hi"}', "2026-07-07T00:00:00")

        storage.delete_game(gid)

        conn = storage._get_conn()
        row = conn.execute("SELECT * FROM narratives WHERE game_id = ?", (gid,)).fetchone()
        assert row is None


# ---------------------------------------------------------------------------
# Invalidation on set_my_color / retag_colors_by_aliases
# ---------------------------------------------------------------------------

class TestNarrativeInvalidation:
    def test_set_my_color_deletes_narrative(self, tmp_path):
        _init(tmp_path)
        gid = storage.insert_game(_game())
        storage.upsert_narrative(gid, "claude-sonnet-5", '{"overall": "hi"}', "2026-07-07T00:00:00")

        storage.set_my_color(gid, "white")

        assert storage.get_narrative(gid) is None

    def test_retag_colors_by_aliases_deletes_narrative(self, tmp_path):
        _init(tmp_path)
        gid = storage.insert_game(_game(white="Magnus", black="Hikaru", content_hash="h1"))
        storage.upsert_narrative(gid, "claude-sonnet-5", '{"overall": "hi"}', "2026-07-07T00:00:00")

        count = storage.retag_colors_by_aliases(["Magnus"])

        assert count == 1
        assert storage.get_narrative(gid) is None

    def test_retag_leaves_unmatched_narrative_untouched(self, tmp_path):
        _init(tmp_path)
        gid = storage.insert_game(_game(white="Magnus", black="Hikaru", content_hash="h1"))
        storage.upsert_narrative(gid, "claude-sonnet-5", '{"overall": "hi"}', "2026-07-07T00:00:00")

        storage.retag_colors_by_aliases(["AliceUnknown"])

        assert storage.get_narrative(gid) is not None


# ---------------------------------------------------------------------------
# get_pos_cache_many
# ---------------------------------------------------------------------------

class TestGetPosCacheMany:
    def test_empty_keys_returns_empty_dict(self, tmp_path):
        _init(tmp_path)
        assert storage.get_pos_cache_many([]) == {}

    def test_no_matches_returns_empty_dict(self, tmp_path):
        _init(tmp_path)
        assert storage.get_pos_cache_many(["nonexistent-epd"]) == {}

    def test_returns_deepest_row_per_epd(self, tmp_path):
        _init(tmp_path)
        storage.upsert_pos_cache("epdA", 10, 50, None, "e2e4", "e4", "[]")
        storage.upsert_pos_cache("epdA", 18, 55, None, "d2d4", "d4", "[]")
        storage.upsert_pos_cache("epdB", 10, -20, None, "g1f3", "Nf3", "[]")

        result = storage.get_pos_cache_many(["epdA", "epdB"])

        assert set(result.keys()) == {"epdA", "epdB"}
        assert result["epdA"]["depth"] == 18
        assert result["epdA"]["best_san"] == "d4"
        assert result["epdB"]["depth"] == 10
        assert result["epdB"]["best_san"] == "Nf3"

    def test_partial_match_omits_missing_keys(self, tmp_path):
        _init(tmp_path)
        storage.upsert_pos_cache("epdA", 10, 50, None, "e2e4", "e4", "[]")

        result = storage.get_pos_cache_many(["epdA", "epdMissing"])

        assert set(result.keys()) == {"epdA"}

    def test_handles_more_than_sqlite_var_limit(self, tmp_path):
        _init(tmp_path)
        storage.upsert_pos_cache("epd-hit", 12, 1, None, "e2e4", "e4", "[]")
        keys = [f"epd-{i}" for i in range(1200)] + ["epd-hit"]

        result = storage.get_pos_cache_many(keys)

        assert set(result.keys()) == {"epd-hit"}
        assert result["epd-hit"]["depth"] == 12
