"""Build the golden eval set: facts payloads for a stratified sample of games.

Reads the games DB **read-only**, mirrors the exact payload assembly of the
``/api/games/{id}/narrative`` route (``app/main.py``), sanitizes player names,
and writes one JSON file per game to ``evals/golden/``.

Stratification (so the eval set exercises different narrative shapes):
- the 3 games with the most user blunders  (worst-case narration)
- the 3 cleanest decisive games            (praise without invention)
- 2 losses and 2 wins, one per color each  (POV discipline both ways)

Usage:
    GAMES_DB=data/games.db python -m evals.build_golden

Re-running overwrites in place — the golden set is versioned in git, so a
diff shows exactly how the set changed. Player names are replaced with
"Me"/"Opponent" before writing; moves/evals stay (they are the eval subject).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app import accuracy, moments, storage

GOLDEN_DIR = Path(__file__).parent / "golden"
TARGET_COUNT = 10


def _sanitize_header(header: dict) -> dict:
    """Replace account names; keep everything the narrative needs."""
    my_color = header.get("my_color")
    out = dict(header)
    out["white"] = "Me" if my_color == "white" else "Opponent"
    out["black"] = "Me" if my_color == "black" else "Opponent"
    return out


def _build_payload(game_id: int) -> dict | None:
    row = storage.get_game(game_id)
    if row is None or row.get("analysis_status") != "done":
        return None
    plies = storage.get_plies(game_id)
    if len(plies) < 4:
        return None
    leaks = storage.get_leaks(game_id)
    acc = accuracy.summarize(plies, row.get("my_color"))
    header = _sanitize_header({
        "white": row.get("white"),
        "black": row.get("black"),
        "my_color": row.get("my_color"),
        "opening": row.get("opening"),
        "eco": row.get("eco"),
        "result": row.get("result"),
        "date": row.get("date"),
        "accuracy": acc,
    })
    epds = [moments._epd(p.get("fen_before")) for p in plies]
    pos_by_epd = storage.get_pos_cache_many([e for e in epds if e])
    # No profile clusters in golden payloads: they drift as the DB grows and
    # would churn the git diff without changing what the checks exercise.
    return moments.extract_moments(
        plies, leaks, pos_by_epd, row.get("my_color"),
        profile_context={"header": header},
    )


def _pick_game_ids(conn) -> list[int]:
    def ids(sql: str) -> list[int]:
        return [r[0] for r in conn.execute(sql).fetchall()]

    blunder_heavy = ids("""
        SELECT g.id FROM games g JOIN leaks l ON l.game_id=g.id AND l.color=g.my_color
        WHERE g.analysis_status='done' AND l.severity='blunder'
        GROUP BY g.id ORDER BY COUNT(*) DESC, g.id LIMIT 3""")
    clean_wins = ids("""
        SELECT g.id FROM games g
        WHERE g.analysis_status='done' AND g.my_color IS NOT NULL
          AND ((g.my_color='white' AND g.result='1-0') OR (g.my_color='black' AND g.result='0-1'))
          AND g.id NOT IN (SELECT game_id FROM leaks WHERE severity='blunder')
        ORDER BY g.ply_count DESC, g.id LIMIT 3""")
    losses = ids("""
        SELECT g.id FROM games g
        WHERE g.analysis_status='done' AND g.my_color IS NOT NULL
          AND ((g.my_color='white' AND g.result='0-1') OR (g.my_color='black' AND g.result='1-0'))
        ORDER BY g.my_color, g.id LIMIT 2""")
    wins_per_color = ids("""
        SELECT MIN(g.id) FROM games g
        WHERE g.analysis_status='done'
          AND ((g.my_color='white' AND g.result='1-0') OR (g.my_color='black' AND g.result='0-1'))
        GROUP BY g.my_color LIMIT 2""")

    seen: list[int] = []
    for gid in blunder_heavy + clean_wins + losses + wins_per_color:
        if gid is not None and gid not in seen:
            seen.append(gid)
    # Top up to TARGET_COUNT with the longest remaining analyzed games.
    if len(seen) < TARGET_COUNT:
        extra = ids("""
            SELECT id FROM games WHERE analysis_status='done' AND my_color IS NOT NULL
            ORDER BY ply_count DESC, id""")
        for gid in extra:
            if gid not in seen:
                seen.append(gid)
            if len(seen) >= TARGET_COUNT:
                break
    return seen[:TARGET_COUNT]


def main() -> None:
    db = os.environ.get("GAMES_DB", "data/games.db")
    storage.init(db)
    conn = storage._get_conn()
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    written = 0
    for gid in _pick_game_ids(conn):
        payload = _build_payload(gid)
        if payload is None:
            continue
        out = GOLDEN_DIR / f"game_{gid:04d}.json"
        out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
        print(f"wrote {out.name}: {len(payload['moments'])} moments, "
              f"my_color={payload['my_color']}")
        written += 1
    print(f"golden set: {written} payloads in {GOLDEN_DIR}")


if __name__ == "__main__":
    main()
