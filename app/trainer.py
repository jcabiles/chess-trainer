"""
trainer.py — Pure spaced-repetition (Leitner) logic for the blunder trainer.

The Leitner unit is the BUCKET (motif), not the position: boxes 1..5 with
review intervals of 1/2/4/7/14 days.  A bucket review serves the next
positions in rotation (via trainer_boxes.cursor_key), so consecutive reviews
of "fork" show *different* forks — the identical board resurfaces only after
the whole bucket cycles (the de la Maza requirement, deterministically).

Puzzle identity is the natural key ``"game_id:ply:bucket"`` — leaks.id is
reissued on every re-analysis and is never stored (contract 1).  A bucket is
``COALESCE(threat_motif, category)``, the same fallback get_attempt_stats
joins on, so attempts written under a bucket always re-join in stats.

Notes
-----
- Engine-free and framework-free: importable and fully unit-testable with no
  Stockfish binary anywhere in the import chain.
- Read-only SQL queries run against the storage module's connection via
  storage._get_conn() (profile.py precedent); writes go through storage
  functions (upsert_trainer_box).  trainer.py does NOT edit storage.py.
- Deterministic time: every logic function takes ``today`` explicitly (a
  ``date`` or ISO string); only the public seams default to date.today().
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from app import storage

# Leitner review intervals in days, per box. A bucket in box N is due when
# today - last_reviewed >= INTERVAL_DAYS[N]; a never-reviewed bucket is due.
INTERVAL_DAYS: dict[int, int] = {1: 1, 2: 2, 3: 4, 4: 7, 5: 14}
MAX_BOX: int = 5

# Session shape: total cap and per-bucket cap.
SESSION_CAP: int = 10
PER_BUCKET_CAP: int = 3

# Box transitions, evaluated over one session's served outcomes:
#   solve rate >= PROMOTE_RATE -> box+1 (cap MAX_BOX)
#   solve rate <  DEMOTE_RATE  -> box 1
#   otherwise                  -> stay
# — but ONLY when >= MIN_SERVED puzzles were served; with fewer the box
# carries over unchanged (refuter: N=1 samples can only be 0%/100%).
PROMOTE_RATE: float = 0.70
DEMOTE_RATE: float = 0.40
MIN_SERVED: int = 2

# Outcomes that count as solved for the box-transition rate.
SOLVED_OUTCOMES = frozenset({"solved", "solved_alt"})


# ---------------------------------------------------------------------------
# Pure Leitner math
# ---------------------------------------------------------------------------

def natural_key(game_id: int, ply: int, bucket: str) -> str:
    """Serialize a puzzle's natural key as ``"game_id:ply:bucket"``.

    Stable across re-analysis (never uses leaks.id).  Safe to split on ':'
    from the left: game_id and ply are integers and the closed motif vocab
    contains no ':'.
    """
    return f"{game_id}:{ply}:{bucket}"


def _as_date(value: date | str) -> date:
    """Coerce a date or ISO string (date or datetime) to a ``date``."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def is_due(box: int, last_reviewed: Optional[str], today: date | str) -> bool:
    """Return whether a bucket is due for review on *today*.

    A never-reviewed bucket (last_reviewed None) is always due.  Otherwise
    due when ``today - last_reviewed >= INTERVAL_DAYS[box]``.  Out-of-range
    boxes are clamped to 1..MAX_BOX.
    """
    if last_reviewed is None:
        return True
    interval = INTERVAL_DAYS[max(1, min(box, MAX_BOX))]
    return (_as_date(today) - _as_date(last_reviewed)).days >= interval


def next_box(box: int, outcomes: list[str]) -> int:
    """Return the bucket's next Leitner box after a session's outcomes.

    'solved' and 'solved_alt' both count as solved; 'failed' and 'revealed'
    do not.  With fewer than MIN_SERVED outcomes the box carries over
    unchanged (min-sample guard).
    """
    served = len(outcomes)
    if served < MIN_SERVED:
        return box
    solved = sum(1 for o in outcomes if o in SOLVED_OUTCOMES)
    rate = solved / served
    if rate >= PROMOTE_RATE:
        return min(box + 1, MAX_BOX)
    if rate < DEMOTE_RATE:
        return 1
    return box


# ---------------------------------------------------------------------------
# Puzzle sourcing (read-only SQL; qualification gate per contract 9)
# ---------------------------------------------------------------------------

def get_live_pool() -> dict[str, list[dict]]:
    """Return live qualifying puzzles grouped by bucket.

    Qualification gate: leaks from games with my_color IS NOT NULL AND
    analysis_status='done', severity IN ('mistake','blunder'), joined to
    game_plies.fen_before for the puzzle position (rows without a stored
    fen_before are unusable and skipped).  Bucket = COALESCE(threat_motif,
    category) — the same fallback get_attempt_stats joins on.

    Each puzzle dict carries the leak's display fields plus 'bucket' and the
    serialized natural 'key'.  Within a bucket, puzzles are in a fixed
    deterministic rotation order (game_id, then ply).
    """
    conn = storage._get_conn()
    rows = conn.execute(
        """
        SELECT
            l.game_id,
            l.ply,
            COALESCE(l.threat_motif, l.category) AS bucket,
            l.color,
            l.severity,
            l.win_prob_drop,
            l.hung_square,
            l.threat_uci,
            l.best_uci,
            l.best_san,
            p.fen_before
        FROM leaks l
        JOIN games g      ON g.id = l.game_id
        JOIN game_plies p ON p.game_id = l.game_id AND p.ply = l.ply
        WHERE g.my_color IS NOT NULL
          AND g.analysis_status = 'done'
          AND l.severity IN ('mistake', 'blunder')
          AND p.fen_before IS NOT NULL
        ORDER BY bucket, l.game_id, l.ply
        """
    ).fetchall()
    pool: dict[str, list[dict]] = {}
    for r in rows:
        puzzle = dict(r)
        puzzle["key"] = natural_key(puzzle["game_id"], puzzle["ply"], puzzle["bucket"])
        pool.setdefault(puzzle["bucket"], []).append(puzzle)
    return pool


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------

def _rotate(puzzles: list[dict], cursor_key: Optional[str], count: int) -> list[dict]:
    """Return the next *count* puzzles after *cursor_key* in rotation order.

    Starts just after the cursor and wraps; never returns the same puzzle
    twice in one call (serves at most len(puzzles)).  Cursor recovery: when
    the stored key no longer matches a live puzzle (re-analysis/deletion),
    rotation restarts at the first item — never errors, never skips the
    bucket.
    """
    n = len(puzzles)
    if n == 0:
        return []
    keys = [p["key"] for p in puzzles]
    start = (keys.index(cursor_key) + 1) % n if cursor_key in keys else 0
    return [puzzles[(start + i) % n] for i in range(min(count, n))]


# ---------------------------------------------------------------------------
# Session assembly
# ---------------------------------------------------------------------------

def _reset_empty_boxes(pool: dict[str, list[dict]], boxes: dict[str, dict]) -> None:
    """Box hygiene: reset rows whose motif has zero live qualifying leaks.

    Idempotent — a stale box-5 schedule must not apply to a future,
    effectively-new weakness pool.
    """
    for motif in boxes:
        if motif not in pool:
            storage.upsert_trainer_box(motif, box=1, last_reviewed=None, cursor_key=None)


def _bucket_states(
    pool: dict[str, list[dict]], boxes: dict[str, dict], today: date | str
) -> list[dict]:
    """Per-pool-bucket state + due flag, in deterministic (motif) order.

    A bucket with no trainer_boxes row is box 1, never reviewed — due.
    """
    states: list[dict] = []
    for motif in sorted(pool):
        row = boxes.get(motif)
        box = row["box"] if row else 1
        last_reviewed = row["last_reviewed"] if row else None
        states.append({
            "motif": motif,
            "box": box,
            "last_reviewed": last_reviewed,
            "cursor_key": row["cursor_key"] if row else None,
            "pool_size": len(pool[motif]),
            "due": is_due(box, last_reviewed, today),
        })
    return states


def preview_due_buckets(today: Optional[date | str] = None) -> list[dict]:
    """Peek at bucket/due status WITHOUT serving puzzles or moving cursors.

    Idempotent read seam for the Train section (safe to call on every
    render): never touches cursor_key, never serves a puzzle.  Box hygiene
    DOES run here — resetting a stale row for an emptied pool is idempotent
    and keeps the displayed box levels honest — and hygiene only ever touches
    rows whose motif has zero live leaks, which are precisely the rows this
    preview does not report.

    Returns one dict per live-pool bucket:
    ``{motif, box, last_reviewed, pool_size, due}``.
    """
    if today is None:
        today = date.today()
    pool = get_live_pool()
    boxes = {r["motif"]: r for r in storage.get_trainer_boxes()}
    _reset_empty_boxes(pool, boxes)
    return [
        {k: s[k] for k in ("motif", "box", "last_reviewed", "pool_size", "due")}
        for s in _bucket_states(pool, boxes, today)
    ]


def assemble_session(today: Optional[date | str] = None) -> dict:
    """Assemble today's training session and advance rotation cursors.

    MUTATING serve — every call advances each served bucket's cursor_key.
    Use :func:`preview_due_buckets` for read-only status display.

    Steps:
      1. Box hygiene: any trainer_boxes row whose motif has zero live
         qualifying leaks is reset (box 1, last_reviewed/cursor cleared) —
         stale box-5 schedules must not apply to a future weakness pool.
      2. Due buckets: every pool bucket whose box row says due (a bucket with
         no row is box 1, never reviewed — due).
      3. Candidates: the next <= PER_BUCKET_CAP puzzles per due bucket in
         rotation order after cursor_key.
      4. Selection: reserve >= 1 slot per due bucket FIRST, then fill the
         remaining capacity hardest-first (win_prob_drop desc) across each
         bucket's next-in-rotation candidate — prefix-constrained, so a
         bucket's rotation order is never skipped over; cap SESSION_CAP.
      5. Cursors: each served bucket's cursor_key advances to its last-served
         puzzle (persisted via storage.upsert_trainer_box).

    Returns ``{"buckets": [...], "puzzles": [...]}`` — served due-bucket
    summaries and the served puzzles (grouped by bucket, rotation order).
    Zero pool / zero due buckets yields explicit empty lists.
    """
    if today is None:
        today = date.today()

    pool = get_live_pool()
    boxes = {r["motif"]: r for r in storage.get_trainer_boxes()}

    # 1. Box hygiene — reset rows whose motif pool is empty.
    _reset_empty_boxes(pool, boxes)

    # 2. Due buckets, in deterministic (motif) order.
    due = [s for s in _bucket_states(pool, boxes, today) if s["due"]]
    due = due[:SESSION_CAP]  # a reserved slot per due bucket must fit the cap

    # 3. Rotation candidates per due bucket.
    candidates = {
        b["motif"]: _rotate(pool[b["motif"]], b["cursor_key"], PER_BUCKET_CAP)
        for b in due
    }

    # 4. Reserve one slot per due bucket first (refuter: a pure global
    # hardest-first trim can starve an easier bucket forever), then fill the
    # remaining capacity hardest-first across buckets' next candidates.
    served_count = {b["motif"]: 1 for b in due}
    capacity = SESSION_CAP - len(due)
    while capacity > 0:
        hardest: Optional[str] = None
        hardest_drop = -1.0
        for b in due:  # due order breaks ties deterministically
            motif = b["motif"]
            idx = served_count[motif]
            if idx < len(candidates[motif]):
                drop = candidates[motif][idx]["win_prob_drop"]
                if drop > hardest_drop:
                    hardest, hardest_drop = motif, drop
        if hardest is None:
            break  # every due bucket's candidates are exhausted
        served_count[hardest] += 1
        capacity -= 1

    # 5. Emit bucket-by-bucket in rotation order; advance each cursor to the
    # last-served puzzle.
    puzzles: list[dict] = []
    buckets: list[dict] = []
    for b in due:
        motif = b["motif"]
        picked = candidates[motif][: served_count[motif]]
        puzzles.extend(picked)
        storage.upsert_trainer_box(
            motif,
            box=b["box"],
            last_reviewed=b["last_reviewed"],
            cursor_key=picked[-1]["key"],
        )
        buckets.append({
            "motif": motif,
            "box": b["box"],
            "last_reviewed": b["last_reviewed"],
            "pool_size": b["pool_size"],
            "served": len(picked),
        })

    return {"buckets": buckets, "puzzles": puzzles}


# ---------------------------------------------------------------------------
# Review completion
# ---------------------------------------------------------------------------

def complete_bucket_review(
    motif: str,
    outcomes: list[str],
    today: Optional[date | str] = None,
) -> int:
    """Apply a finished bucket review: move the box and stamp last_reviewed.

    The box transition follows next_box() (including the min-sample
    carry-over); cursor_key is preserved so rotation continues where the
    session left off.  Returns the bucket's new box.
    """
    if today is None:
        today = date.today()
    row = next((r for r in storage.get_trainer_boxes() if r["motif"] == motif), None)
    box = row["box"] if row else 1
    cursor_key = row["cursor_key"] if row else None
    new_box = next_box(box, outcomes)
    storage.upsert_trainer_box(
        motif,
        box=new_box,
        last_reviewed=_as_date(today).isoformat(),
        cursor_key=cursor_key,
    )
    return new_box
