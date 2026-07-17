"""
rating.py — Running bot-ELO read-model (pure, engine-free).

Recomputes a standard Elo rating from stored RATED bot games on each call
(seed 1350 / K=32, updated per game result vs the persona's `personaElo`).
No persisted Elo, no DB schema change — a stateless recompute-from-history
read-model over the `games` table (mirrors profile.py).

Public API
----------
elo_update(cur, opponent, score, k) -> float   # pure Elo step
user_score(result, my_color) -> float | None    # result → user-POV score
build_rating() -> dict

Return shape of build_rating():
    {
        "seedElo": int,        # 1350
        "k": int,              # 32
        "botElo": int | None,  # round(cur), None when no counted games
        "gamesCounted": int,
        "gamesSkipped": int,   # rated bot games with no valid personaElo
        "history": [{"gameId", "opponentElo", "score", "eloAfter"} ...],
    }

Notes
-----
- Engine-free, no Stockfish, no game_plies access. Import-safe.
- build_rating() raises RuntimeError from storage._get_conn() if the DB was
  never opened — the endpoint (T2) guards it; NOT swallowed here.
- user_score is implemented locally (guarded) rather than importing the private
  insights._user_score, which treats any non-"white" color as Black and would
  miscount a null-color decisive row.
"""

from __future__ import annotations

import json

from app import storage

SEED_ELO = 1350
K = 32


def elo_update(cur: float, opponent: float, score: float, k: float) -> float:
    """Standard Elo update: expected score then cur += k * (score - expected)."""
    expected = 1 / (1 + 10 ** ((opponent - cur) / 400))
    return cur + k * (score - expected)


def user_score(result: str | None, my_color: str | None) -> float | None:
    """Game score from the user's perspective (1.0/0.5/0.0), None when unknown.

    Requires my_color in {"white", "black"} FIRST — a null/invalid color on a
    decisive result returns None (not a loss), unlike insights._user_score.
    """
    if my_color not in {"white", "black"}:
        return None
    if result == "1/2-1/2":
        return 0.5
    if result == "1-0":
        return 1.0 if my_color == "white" else 0.0
    if result == "0-1":
        return 1.0 if my_color == "black" else 0.0
    return None


def build_rating() -> dict:
    """Recompute the running bot-ELO from stored rated bot games.

    Raises RuntimeError if storage has not been initialised (not swallowed).
    """
    rows = (
        storage._get_conn()
        .execute(
            "SELECT id, result, my_color, headers_json, imported_at FROM games "
            "WHERE source='bot' AND my_color IS NOT NULL "
            "ORDER BY imported_at ASC, id ASC"
        )
        .fetchall()
    )

    cur: float = SEED_ELO
    games_counted = 0
    games_skipped = 0
    history: list[dict] = []

    for row in rows:
        try:
            headers = json.loads(row["headers_json"] or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(headers, dict):
            continue
        if headers.get("rated") is not True:
            continue
        opp = headers.get("personaElo")
        if not (isinstance(opp, int) and not isinstance(opp, bool)):
            games_skipped += 1
            continue
        score = user_score(row["result"], row["my_color"])
        if score is None:
            continue
        cur = elo_update(cur, opp, score, K)
        games_counted += 1
        history.append(
            {
                "gameId": row["id"],
                "opponentElo": opp,
                "score": score,
                "eloAfter": round(cur),
            }
        )

    return {
        "seedElo": SEED_ELO,
        "k": K,
        "botElo": round(cur) if games_counted else None,
        "gamesCounted": games_counted,
        "gamesSkipped": games_skipped,
        "history": history,
    }
