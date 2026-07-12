"""Deterministic grounding checks for AI game commentary.

Given a facts payload (``app.moments.extract_moments`` output) and a parsed
narrative (``{chapters, moments, overall}``), return every place the text
makes a concrete chess claim the payload cannot support. Pure module — no
network, no API key, no engine; runs in the offline test suite.

Design rule: **only falsifiable checks live here.** A check either proves a
violation from the payload or stays silent — style, insight, and tone are the
LLM judge's job (``evals/judge.py``), never this module's. That split is what
makes a red result here a hard fail rather than an opinion.

Checks (each yields ``Violation(kind, where, detail)``):

- ``unreached_phase``   — a chapter narrates a phase the game never reached
  (the runtime parser only validates phase ∈ {opening,middlegame,endgame},
  not ⊆ phases actually present in ``eval_arc`` — this closes that gap).
- ``unknown_san``       — text mentions a SAN move that is neither that
  moment's played move nor in its facts (best_san / pv_san line) nor —
  for chapter/overall text — any payload moment's move. The system prompt
  forbids inventing moves; this is the falsifiable version of that rule.
- ``bad_move_number``   — text claims a move number beyond the game's length.
- ``second_best_named`` — a narrow_choice moment's text names a concrete SAN
  right after alternative-phrasing ("better was Nf3"): the payload NEVER
  carries a second-best move, so any such naming is invented. Heuristic on
  top of unknown_san (a hallucinated alternative that happens to collide
  with a pv move would otherwise pass).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# SAN token: piece moves, pawn moves/captures, promotions, castles.
# Word-boundary anchored so prose like "a1-h8 diagonal" doesn't match.
_SAN_RE = re.compile(
    r"(?<![\w=/])("
    r"[KQRBN][a-h1-8]?x?[a-h][1-8]"   # piece moves (with optional disambig/capture)
    r"|[a-h]x[a-h][1-8](?:=[QRBN])?"  # pawn captures (with promotion)
    r"|[a-h][18]=[QRBN]"              # quiet promotions
    r"|O-O-O|O-O"                     # castles
    r")[+#]?(?![\w=])"
)

_MOVE_NUM_RE = re.compile(r"\bmove\s+(\d{1,3})\b", re.IGNORECASE)

# "better was Nf3", "instead Nf3", "should have played Nf3", "Nf3 was better"
_ALTERNATIVE_RE = re.compile(
    r"(?:better|instead|should\s+have|stronger|preferable|correct)\D{0,40}?"
    r"([KQRBN][a-h1-8]?x?[a-h][1-8][+#]?|[a-h]x[a-h][1-8][+#]?|O-O-O|O-O)",
    re.IGNORECASE,
)


@dataclass
class Violation:
    kind: str
    where: str   # 'chapter:<phase>' | 'moment:<ply>' | 'overall'
    detail: str


def _normalize_san(san: str) -> str:
    """Strip check/mate suffixes — '+'/'#' presence is presentation, not identity."""
    return san.rstrip("+#")


def _payload_sans(payload: dict) -> set[str]:
    """Every SAN the payload puts on the record, normalized."""
    sans: set[str] = set()
    for m in payload.get("moments") or []:
        if m.get("san"):
            sans.add(_normalize_san(m["san"]))
        facts = m.get("facts") or {}
        if facts.get("best_san"):
            sans.add(_normalize_san(facts["best_san"]))
        for pv_san in facts.get("pv_san") or []:
            sans.add(_normalize_san(pv_san))
    return sans


def _moment_sans(moment: dict) -> set[str]:
    sans: set[str] = set()
    if moment.get("san"):
        sans.add(_normalize_san(moment["san"]))
    facts = moment.get("facts") or {}
    if facts.get("best_san"):
        sans.add(_normalize_san(facts["best_san"]))
    for pv_san in facts.get("pv_san") or []:
        sans.add(_normalize_san(pv_san))
    return sans


def check_narrative(payload: dict, narrative: dict) -> list[Violation]:
    """Return every grounding violation in a parsed narrative. Empty = clean."""
    violations: list[Violation] = []

    payload_moments = {m["ply"]: m for m in (payload.get("moments") or [])}
    all_sans = _payload_sans(payload)
    reached_phases = set((payload.get("eval_arc") or {}).keys())
    max_move_number = max(
        (m.get("move_number") or 0 for m in payload_moments.values()), default=0
    )

    def check_text(text: str, where: str, allowed_sans: set[str]) -> None:
        for match in _SAN_RE.finditer(text or ""):
            san = _normalize_san(match.group(1))
            if san not in allowed_sans:
                violations.append(Violation("unknown_san", where, f"'{match.group(0)}' is not in the payload"))
        for match in _MOVE_NUM_RE.finditer(text or ""):
            n = int(match.group(1))
            # move_number is per-moment; anything beyond the last known
            # moment's move number + a small grace window is fabricated.
            if max_move_number and n > max_move_number + 5:
                violations.append(Violation("bad_move_number", where, f"claims move {n}; last known move is {max_move_number}"))

    for ch in narrative.get("chapters") or []:
        phase = ch.get("phase")
        where = f"chapter:{phase}"
        if reached_phases and phase not in reached_phases:
            violations.append(Violation("unreached_phase", where, f"game never reached the {phase}"))
        check_text(ch.get("text"), where, all_sans)

    for m in narrative.get("moments") or []:
        ply = m.get("ply")
        where = f"moment:{ply}"
        pm = payload_moments.get(ply)
        if pm is None:
            # The runtime parser already rejects this; re-checked so the
            # harness stands alone when fed raw replies.
            violations.append(Violation("unknown_san", where, f"ply {ply} is not a payload moment"))
            continue
        check_text(m.get("text"), where, _moment_sans(pm) | all_sans)
        if pm.get("kind") == "narrow_choice":
            alt = _ALTERNATIVE_RE.search(m.get("text") or "")
            if alt:
                violations.append(Violation(
                    "second_best_named", where,
                    f"names '{alt.group(1)}' as the alternative — the payload never carries a second-best move",
                ))

    check_text(narrative.get("overall"), "overall", all_sans)

    return violations
