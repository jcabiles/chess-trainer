"""
insights.py — Pure read-model builders for the Insights dashboard.

Openings slice: win% by opening, repertoire adherence, and a named-theory
fallback for off-repertoire games. Mistakes slice: recurring-mistake
clusters, foreseeable-rate, time-trouble, and advantage capitalization.
Post-processing of stored ``games`` / ``game_plies`` / ``leaks`` rows only —
no engine, no asyncio, no schema change. Mirrors the SQL-then-shape idiom of
:mod:`app.profile`.

All sections are gated on games WHERE ``my_color IS NOT NULL`` AND
``analysis_status = 'done'`` (same rule as ``profile.build_profile``).

Honesty gate
------------
``gated(value, n)`` wraps any aggregate as ``{"value", "n", "sufficient"}``
with ``sufficient = n >= MIN_SAMPLE`` (default 5) so the UI can mute
thin-data rows instead of hiding or overselling them. Per-record rows carry
the same ``n`` / ``sufficient`` pair.

"In book" caveat: book membership means the line has a *name* in the bundled
openings database — named theory is **not** the same as moves endorsed by
masters. The ``theory.note`` string carries this caveat verbatim for the UI.

Public API
----------
build_openings_insights() -> dict
build_mistakes_insights() -> dict

build_openings_insights() return shape (JSON example)::

    {
      "coverage": {
        "total": 12, "tagged": 10, "analyzed": 9, "pending": 1,
        "qualified": 8, "on_repertoire": 5, "off_repertoire": 3
      },
      "win_rates": {
        "families": [
          {"opening": "Sicilian Defense", "color": "black",
           "wins": 4, "draws": 1, "losses": 2, "n": 7,
           "score": 0.643, "sufficient": true}
        ],
        "lines": [
          {"opening": "Sicilian Defense: Najdorf Variation",
           "family": "Sicilian Defense", "color": "black",
           "wins": 2, "draws": 0, "losses": 1, "n": 3,
           "score": 0.667, "sufficient": false}
        ]
      },
      "adherence": {
        "n": 5,
        "avg_followed_prep_depth": {"value": 6.4, "n": 5, "sufficient": true},
        "lines": [
          {"line_id": "italian-main", "name": "Italian Game mainline",
           "color": "white", "n": 5, "avg_followed_prep_depth": 6.4,
           "deviations": 2, "sufficient": true}
        ],
        "games": [
          {"game_id": 3, "followed_prep_depth": 4, "deviation_ply": 5,
           "deviation_move": "Bc4", "prepared_san": "Bb5",
           "line_ids": ["italian-main"]}
        ]
      },
      "theory": {
        "n": 3,
        "avg_book_exit_ply": {"value": 7.7, "n": 3, "sufficient": false},
        "avg_opening_accuracy": {"value": 91.2, "n": 3, "sufficient": false},
        "games": [
          {"game_id": 7, "book_exit_ply": 8, "opening_accuracy": 92.5}
        ],
        "note": "'In book' means the line has a name in the openings
                 database — named theory is not the same as moves endorsed
                 by masters."
      }
    }

build_mistakes_insights() return shape (JSON example)::

    {
      "coverage": {
        "total": 12, "tagged": 10, "analyzed": 9, "pending": 1, "qualified": 8
      },
      "clusters": {
        "n_leaks": 23,
        "items": [
          {"category": "hanging", "phase": "middlegame",
           "name": "Leaving pieces en prise (LPDO) in the middlegame",
           "count": 9, "example": {"game_id": 4, "ply": 33}}
        ],
        "suppressed": {"cells": 3, "leaks": 5, "gate": 4}
      },
      "foreseeable": {
        "rate": {"value": 0.435, "n": 23, "sufficient": true},
        "dominant_motif": "knight_fork",
        "note": "Foreseeable uses a narrow definition — it counts only
                 warning signs visible at least two plies before the
                 mistake. One-ply warnings cannot be distinguished from the
                 pipeline's display-timing default, so the true rate is
                 likely higher."
      },
      "time_trouble": {
        "clocked_games": 6, "unclocked_games": 2,
        "baseline_rate": {"value": 0.052, "n": 210, "sufficient": true},
        "buckets": [
          {"bucket": "<10s", "moves": 12, "leaks": 3, "rate": 0.25,
           "sufficient": true},
          {"bucket": "10s-30s", "moves": 30, "leaks": 2, "rate": 0.067,
           "sufficient": true},
          {"bucket": "30s-2m", "moves": 80, "leaks": 3, "rate": 0.038,
           "sufficient": true},
          {"bucket": ">2m", "moves": 88, "leaks": 3, "rate": 0.034,
           "sufficient": true}
        ],
        "note": "2 of 8 analyzed games have no clock data and are excluded."
      },
      "capitalization": {
        "winning_games": 6, "converted": 4,
        "rate": {"value": 0.667, "n": 6, "sufficient": true},
        "note": "A game counts as 'winning' when your win probability stayed
                 at or above 80% for at least 4 consecutive plies — single-ply
                 eval spikes do not count."
      }
    }

Notes on semantics
------------------
- ``win_rates``: score is from the user's perspective (``games.result`` vs
  ``games.my_color``); games with an unknown result (``*``/NULL) are skipped.
  Family = the opening name before the first ``:`` (lichess naming), falling
  back to the ECO code, then ``"Unknown"``. Grouping key is (opening, color).
- ``adherence``: a game is *on-repertoire* when its moves enter the user's
  prepared tree (``repertoire.tree()``) for at least one ply, or when the
  user deviates immediately at a prepared your-turn root. ``deviation_ply``/
  ``deviation_move`` are set only when the USER left prep at a your-turn
  node (1-based ply, SAN); an opponent leaving prep ends the walk with no
  deviation recorded. ``line_ids``: on a user deviation, the lines that
  prescribed the avoided move (the prepared child's lines — the tree ROOT
  carries no line ids, so a ply-1 deviation still attributes correctly);
  otherwise all prepared lines still consistent with the deepest matched
  node. Per-line aggregates credit each such line.
- ``theory`` (off-repertoire games only): ``book_exit_ply`` is the last ply
  of the initial consecutive run of in-book moves (``book.is_book_move``);
  0 when the game never entered book. ``opening_accuracy`` is the user's
  Accuracy % (``accuracy.summarize``) restricted to opening-phase plies
  (the prefix where ``analysis.game_phase`` says 'opening' — the phase is
  material-based, hence monotone, so the opening is always a prefix).
- ``clusters``: leaks grouped by (category, phase), ranked by count; cells
  below CLUSTER_GATE (4) are dropped from ``items`` and summarised in
  ``suppressed`` instead (``suppressed.gate`` echoes CLUSTER_GATE for the
  UI). Names come from ``coaching.name_cluster`` except the generic
  ``missed_threat`` bucket, honestly labeled "Other tactical misses…".
  ``example`` is the most recent leak in the cluster (by game
  ``imported_at``, then game id, then ply) for deep-linking.
- ``foreseeable``: fraction of leaks whose ``lead_in_ply < ply - 1`` — a
  warning sign at least TWO plies before the mistake. The review pipeline
  writes ``lead_in_ply = ply - 1`` as a display-timing default on every
  leak, so one-ply values carry no signal and are excluded (genuine one-ply
  warnings are indistinguishable from the default — the rate under-claims).
  ``dominant_motif`` is the most common ``threat_motif`` among those
  foreseeable leaks (None when none carry one).
- ``time_trouble``: user moves from clocked games bucketed by remaining
  clock (``game_plies.clock_centis``); a bucket's rate = leaks landing on
  those moves / moves in the bucket; ``baseline_rate`` is the same rate over
  all clocked user moves. Games with no clock data are excluded and counted
  in ``unclocked_games``. All four buckets are always present (rate None
  when a bucket has no moves).
- ``capitalization``: a qualified game with a known result counts as
  "winning" when the user's win probability (``game_plies.win_prob`` is
  mover-POV; flipped via the side to move in ``fen_before``) stayed >= 0.8
  for >= 4 consecutive plies; ``rate`` = fraction of those games the user
  actually won.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any, Optional

import chess

from app import book, coaching, repertoire, storage
from app.accuracy import summarize
from app.analysis import game_phase

# Minimum sample size before an aggregate is presented as meaningful.
MIN_SAMPLE = 5

# Minimum leak count before a (category, phase) cluster is named/listed.
CLUSTER_GATE = 4

# Advantage capitalization: "winning" = user win-prob >= this for >= N plies.
_CAP_WIN_PROB = 0.8
_CAP_SUSTAIN_PLIES = 4

# Time-trouble buckets: (label, lo_centis inclusive, hi_centis exclusive).
_CLOCK_BUCKETS = (
    ("<10s", 0, 1_000),
    ("10s-30s", 1_000, 3_000),
    ("30s-2m", 3_000, 12_000),
    (">2m", 12_000, None),
)

_THEORY_NOTE = (
    "'In book' means the line has a name in the openings database — "
    "named theory is not the same as moves endorsed by masters."
)


# ---------------------------------------------------------------------------
# Honesty gate (T0.3)
# ---------------------------------------------------------------------------


def gated(value: Any, n: int, min_n: int = MIN_SAMPLE) -> dict:
    """Wrap an aggregate as ``{"value", "n", "sufficient"}``.

    ``sufficient`` is False when the sample is below *min_n* — the UI renders
    those muted ("not enough games yet (n=…)") instead of hiding the value.
    """
    return {"value": value, "n": n, "sufficient": n >= min_n}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _qualified_games() -> list[dict]:
    """Game rows with my_color set AND analysis_status='done' (profile.py rule)."""
    conn = storage._get_conn()
    rows = conn.execute(
        "SELECT * FROM games WHERE my_color IS NOT NULL AND analysis_status = 'done'"
    ).fetchall()
    return [dict(r) for r in rows]


def _user_score(result: Optional[str], my_color: str) -> Optional[float]:
    """Game score from the user's perspective (1/0.5/0), None when unknown."""
    if result == "1/2-1/2":
        return 0.5
    if result == "1-0":
        return 1.0 if my_color == "white" else 0.0
    if result == "0-1":
        return 1.0 if my_color == "black" else 0.0
    return None


def _opening_names(game: dict) -> tuple[str, str]:
    """Return (family, line) display names for a game row.

    Lichess opening names read "Family: Variation" — the family is the part
    before the first colon. Falls back to the ECO code, then 'Unknown'.
    """
    opening = game.get("opening")
    eco = game.get("eco")
    if opening:
        return opening.split(":")[0].strip(), opening
    fallback = eco or "Unknown"
    return fallback, fallback


def _win_rates(games: list[dict]) -> dict:
    """Group scored games by (family, color) and (line, color)."""
    fams: dict[tuple[str, str], dict] = {}
    lines: dict[tuple[str, str], dict] = {}
    for g in games:
        score = _user_score(g.get("result"), g["my_color"])
        if score is None:
            continue
        family, line = _opening_names(g)
        for bucket, name in ((fams, family), (lines, line)):
            rec = bucket.setdefault(
                (name, g["my_color"]),
                {"wins": 0, "draws": 0, "losses": 0, "family": family},
            )
            if score == 1.0:
                rec["wins"] += 1
            elif score == 0.5:
                rec["draws"] += 1
            else:
                rec["losses"] += 1

    def shape(bucket: dict, with_family: bool) -> list[dict]:
        out = []
        for (name, color), rec in bucket.items():
            n = rec["wins"] + rec["draws"] + rec["losses"]
            row = {"opening": name}
            if with_family:
                row["family"] = rec["family"]
            row.update({
                "color": color,
                "wins": rec["wins"],
                "draws": rec["draws"],
                "losses": rec["losses"],
                "n": n,
                "score": round((rec["wins"] + 0.5 * rec["draws"]) / n, 3),
                "sufficient": n >= MIN_SAMPLE,
            })
            out.append(row)
        out.sort(key=lambda r: (-r["n"], r["opening"], r["color"]))
        return out

    return {"families": shape(fams, False), "lines": shape(lines, True)}


def _walk_repertoire(plies: list[dict], my_color: str) -> dict:
    """Walk a game's moves against the user's prepared tree for *my_color*.

    Returns {followed_prep_depth, deviation_ply, deviation_move, prepared_san,
    line_ids, on_repertoire}. A deviation is recorded only when the USER left
    prep at a your-turn node; an opponent leaving prep just ends the walk.

    line_ids: on a user deviation, the lines that prescribed the avoided move
    (the single prepared your-turn child's lineIds — the ROOT node never
    carries lineIds, so a ply-1 deviation would otherwise attribute to no
    line at all); without a deviation, the deepest matched node's lineIds.
    """
    node = repertoire.tree()[my_color]
    depth = 0
    deviation_ply: Optional[int] = None
    deviation_move: Optional[str] = None
    prepared_san: Optional[str] = None
    line_ids: Optional[list[str]] = None
    for row in plies:
        children = {c["uci"]: c for c in node["children"]}
        if not children:
            break  # end of prep (line completed) — or no prep for this color
        uci = row.get("uci")
        if not uci:
            break  # incomplete ply row; stop conservatively
        child = children.get(uci)
        if child is None:
            if node["yourTurn"]:
                # A your-turn node has exactly one prepared child (repertoire
                # invariant) — the move the user avoided.
                prepared = next(iter(children.values()))
                deviation_ply = row["ply"]
                deviation_move = row.get("san") or uci
                prepared_san = prepared["san"]
                line_ids = list(prepared["lineIds"])
            break
        depth += 1
        node = child
    if line_ids is None:
        line_ids = list(node["lineIds"])
    return {
        "followed_prep_depth": depth,
        "deviation_ply": deviation_ply,
        "deviation_move": deviation_move,
        "prepared_san": prepared_san,
        "line_ids": line_ids,
        "on_repertoire": depth >= 1 or deviation_ply is not None,
    }


def _line_names_by_id() -> dict[str, dict]:
    """{line_id: {"name", "color"}} from the repertoire catalog."""
    catalog = repertoire.tree()["catalog"]
    out: dict[str, dict] = {}
    for color in ("white", "black"):
        for group in catalog[color]:
            for line in group["lines"]:
                out[line["id"]] = {"name": line["name"], "color": color}
    return out


def _adherence(walked: list[tuple[dict, dict]]) -> dict:
    """Shape the adherence section from (game_row, walk_result) pairs."""
    names = _line_names_by_id()
    per_line: dict[str, dict] = {}
    game_records = []
    depths = []
    for game, walk in walked:
        depths.append(walk["followed_prep_depth"])
        game_records.append({
            "game_id": game["id"],
            "followed_prep_depth": walk["followed_prep_depth"],
            "deviation_ply": walk["deviation_ply"],
            "deviation_move": walk["deviation_move"],
            "prepared_san": walk["prepared_san"],
            "line_ids": walk["line_ids"],
        })
        for line_id in walk["line_ids"]:
            rec = per_line.setdefault(line_id, {"depths": [], "deviations": 0})
            rec["depths"].append(walk["followed_prep_depth"])
            if walk["deviation_ply"] is not None:
                rec["deviations"] += 1

    lines = []
    for line_id, rec in per_line.items():
        n = len(rec["depths"])
        meta = names.get(line_id, {"name": line_id, "color": None})
        lines.append({
            "line_id": line_id,
            "name": meta["name"],
            "color": meta["color"],
            "n": n,
            "avg_followed_prep_depth": round(mean(rec["depths"]), 1),
            "deviations": rec["deviations"],
            "sufficient": n >= MIN_SAMPLE,
        })
    lines.sort(key=lambda r: (-r["n"], r["line_id"]))

    n = len(walked)
    return {
        "n": n,
        "avg_followed_prep_depth": gated(
            round(mean(depths), 1) if depths else None, n),
        "lines": lines,
        "games": game_records,
    }


def _book_exit_ply(plies: list[dict]) -> int:
    """Last ply of the initial consecutive in-book run (0 = never in book)."""
    exit_ply = 0
    for row in plies:
        fen = row.get("fen_before")
        uci = row.get("uci")
        if not fen or not uci or not book.is_book_move(fen, uci):
            break
        exit_ply = row["ply"]
    return exit_ply


def _opening_accuracy(plies: list[dict], my_color: str) -> Optional[float]:
    """User's Accuracy % restricted to opening-phase plies (or None).

    game_phase depends only on remaining material, which never increases, so
    the opening phase is always a prefix of the game. We take that prefix
    plus ONE sentinel ply so accuracy.summarize (which compares each ply to
    its successor and drops the final row) scores exactly the opening moves.
    """
    prefix: list[dict] = []
    for row in plies:
        fen = row.get("fen_before")
        if not fen:
            break
        try:
            phase = game_phase(chess.Board(fen))
        except ValueError:
            break
        prefix.append(row)
        if phase != "opening":
            break  # this row is the sentinel: successor eval for the last opening move
    # (If the whole game is opening-phase, summarize drops the final ply itself.)
    summary = summarize(prefix, my_color)
    return summary[f"{my_color}_accuracy"]


def _theory(off_games: list[tuple[dict, list[dict]]]) -> dict:
    """Named-theory fallback section from (game_row, plies) pairs."""
    game_records = []
    exits = []
    accs = []
    for game, plies in off_games:
        exit_ply = _book_exit_ply(plies)
        acc = _opening_accuracy(plies, game["my_color"])
        exits.append(exit_ply)
        if acc is not None:
            accs.append(acc)
        game_records.append({
            "game_id": game["id"],
            "book_exit_ply": exit_ply,
            "opening_accuracy": acc,
        })
    n = len(off_games)
    return {
        "n": n,
        "avg_book_exit_ply": gated(
            round(mean(exits), 1) if exits else None, n),
        "avg_opening_accuracy": gated(
            round(mean(accs), 1) if accs else None, len(accs)),
        "games": game_records,
        "note": _THEORY_NOTE,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_openings_insights() -> dict:
    """Build the Openings insights read-model (see module docstring for shape).

    Pure post-processing of stored rows: no engine, no writes. Raises
    RuntimeError when storage has not been initialised (same as profile.py).
    """
    games = _qualified_games()

    walked_on: list[tuple[dict, dict]] = []
    off_games: list[tuple[dict, list[dict]]] = []
    for game in games:
        plies = storage.get_plies(game["id"])
        walk = _walk_repertoire(plies, game["my_color"])
        if walk["on_repertoire"]:
            walked_on.append((game, walk))
        else:
            off_games.append((game, plies))

    coverage = storage.coverage()
    coverage["qualified"] = len(games)
    coverage["on_repertoire"] = len(walked_on)
    coverage["off_repertoire"] = len(off_games)

    return {
        "coverage": coverage,
        "win_rates": _win_rates(games),
        "adherence": _adherence(walked_on),
        "theory": _theory(off_games),
    }


# ---------------------------------------------------------------------------
# Mistakes slice (T2.1–T2.4)
# ---------------------------------------------------------------------------

_FORESEEABLE_NOTE = (
    "Foreseeable uses a narrow definition — it counts only warning signs "
    "visible at least two plies before the mistake. One-ply warnings cannot "
    "be distinguished from the pipeline's display-timing default, so the "
    "true rate is likely higher."
)

_CAPITALIZATION_NOTE = (
    "A game counts as 'winning' when your win probability stayed at or "
    "above 80% for at least 4 consecutive plies — single-ply eval spikes "
    "do not count."
)


def _qualified_leaks() -> list[dict]:
    """Leaks from qualified games, most recent first (imported_at, game, ply).

    The ordering makes the FIRST leak seen per cluster the deterministic
    representative example.
    """
    conn = storage._get_conn()
    rows = conn.execute(
        """
        SELECT l.* FROM leaks l
        JOIN games g ON l.game_id = g.id
        WHERE g.my_color IS NOT NULL AND g.analysis_status = 'done'
        ORDER BY g.imported_at DESC, l.game_id DESC, l.ply DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _clusters(leaks: list[dict]) -> dict:
    """Recurring-mistake clusters by (category, phase), gated at CLUSTER_GATE."""
    groups: dict[tuple[str, str], dict] = {}
    for lk in leaks:
        key = (lk["category"], lk["phase"])
        rec = groups.setdefault(
            key,
            # leaks are ordered most-recent-first: first seen = the example.
            {"count": 0, "example": {"game_id": lk["game_id"], "ply": lk["ply"]}},
        )
        rec["count"] += 1

    narrator = coaching.get_narrator()
    items = []
    suppressed_cells = 0
    suppressed_leaks = 0
    for (category, phase), rec in groups.items():
        if rec["count"] < CLUSTER_GATE:
            suppressed_cells += 1
            suppressed_leaks += rec["count"]
            continue
        if category == "missed_threat":
            # The generic bucket — labeled honestly, not oversold as a motif.
            name = f"Other tactical misses in the {phase}"
        else:
            name = narrator.name_cluster(
                category, {"count": rec["count"], "phase": phase})
        items.append({
            "category": category,
            "phase": phase,
            "name": name,
            "count": rec["count"],
            "example": rec["example"],
        })
    items.sort(key=lambda r: (-r["count"], r["category"], r["phase"]))

    return {
        "n_leaks": len(leaks),
        "items": items,
        "suppressed": {
            "cells": suppressed_cells,
            "leaks": suppressed_leaks,
            "gate": CLUSTER_GATE,
        },
    }


def _foreseeable(leaks: list[dict]) -> dict:
    """Fraction of leaks with a warning sign before the mistake + its mode."""
    n = len(leaks)
    # Strictly MORE than one ply ahead: the review pipeline writes
    # lead_in_ply = ply - 1 as a display-timing DEFAULT on every leak, so a
    # value of ply - 1 carries no signal (a genuine one-ply warning is
    # indistinguishable from that default). Honest under-claim: require >= 2.
    fore = [
        lk for lk in leaks
        if lk["lead_in_ply"] is not None and lk["lead_in_ply"] < lk["ply"] - 1
    ]
    rate = round(len(fore) / n, 3) if n else None
    motifs = Counter(lk["threat_motif"] for lk in fore if lk["threat_motif"])
    # Deterministic mode: highest count, then alphabetical.
    dominant = min(motifs, key=lambda m: (-motifs[m], m)) if motifs else None
    return {
        "rate": gated(rate, n),
        "dominant_motif": dominant,
        "note": _FORESEEABLE_NOTE,
    }


def _time_trouble(n_qualified: int, leaks: list[dict]) -> dict:
    """Blunder rate per remaining-clock bucket over clocked user moves."""
    conn = storage._get_conn()
    rows = conn.execute(
        """
        SELECT p.game_id, p.ply, p.clock_centis FROM game_plies p
        JOIN games g ON p.game_id = g.id
        WHERE g.my_color IS NOT NULL AND g.analysis_status = 'done'
          AND p.is_user_move = 1 AND p.clock_centis IS NOT NULL
        """
    ).fetchall()

    leak_plies = {(lk["game_id"], lk["ply"]) for lk in leaks}
    counts = {label: {"moves": 0, "leaks": 0} for label, _, _ in _CLOCK_BUCKETS}
    clocked_game_ids = set()
    total_leaks = 0
    for row in rows:
        clocked_game_ids.add(row["game_id"])
        centis = row["clock_centis"]
        is_leak = (row["game_id"], row["ply"]) in leak_plies
        total_leaks += is_leak
        for label, lo, hi in _CLOCK_BUCKETS:
            if centis >= lo and (hi is None or centis < hi):
                counts[label]["moves"] += 1
                counts[label]["leaks"] += is_leak
                break

    buckets = []
    for label, _, _ in _CLOCK_BUCKETS:
        moves = counts[label]["moves"]
        n_leaks = counts[label]["leaks"]
        buckets.append({
            "bucket": label,
            "moves": moves,
            "leaks": n_leaks,
            "rate": round(n_leaks / moves, 3) if moves else None,
            "sufficient": moves >= MIN_SAMPLE,
        })

    n_moves = len(rows)
    clocked = len(clocked_game_ids)
    unclocked = n_qualified - clocked
    return {
        "clocked_games": clocked,
        "unclocked_games": unclocked,
        "baseline_rate": gated(
            round(total_leaks / n_moves, 3) if n_moves else None, n_moves),
        "buckets": buckets,
        "note": (
            f"{unclocked} of {n_qualified} analyzed games have no clock data "
            "and are excluded."
        ),
    }


def _user_win_prob(row: dict, my_color: str) -> Optional[float]:
    """User-POV win prob for a ply (win_prob is stored mover-POV)."""
    wp = row.get("win_prob")
    fen = row.get("fen_before")
    if wp is None or not fen:
        return None
    try:
        mover_white = chess.Board(fen).turn == chess.WHITE
    except ValueError:
        return None
    user_is_mover = mover_white == (my_color == "white")
    return wp if user_is_mover else 1.0 - wp


def _capitalization(games: list[dict]) -> dict:
    """Converted-rate over games with a SUSTAINED winning stretch."""
    winning = 0
    converted = 0
    for game in games:
        score = _user_score(game.get("result"), game["my_color"])
        if score is None:
            continue
        run = 0
        sustained = False
        for row in storage.get_plies(game["id"]):
            user_wp = _user_win_prob(row, game["my_color"])
            if user_wp is not None and user_wp >= _CAP_WIN_PROB:
                run += 1
                if run >= _CAP_SUSTAIN_PLIES:
                    sustained = True
                    break
            else:
                run = 0
        if sustained:
            winning += 1
            converted += score == 1.0
    return {
        "winning_games": winning,
        "converted": converted,
        "rate": gated(round(converted / winning, 3) if winning else None, winning),
        "note": _CAPITALIZATION_NOTE,
    }


def build_mistakes_insights() -> dict:
    """Build the Mistakes insights read-model (see module docstring for shape).

    Pure post-processing of stored rows: no engine, no writes. Raises
    RuntimeError when storage has not been initialised (same as profile.py).
    """
    games = _qualified_games()
    leaks = _qualified_leaks()

    coverage = storage.coverage()
    coverage["qualified"] = len(games)

    return {
        "coverage": coverage,
        "clusters": _clusters(leaks),
        "foreseeable": _foreseeable(leaks),
        "time_trouble": _time_trouble(len(games), leaks),
        "capitalization": _capitalization(games),
    }
