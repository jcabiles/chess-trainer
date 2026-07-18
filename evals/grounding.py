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
- ``motif_mismatch``    — text names a specific tactical motif (hanging /
  fork / pin / skewer / discovered attack / back rank) that appears in NO
  moment's ``facts.category`` or ``facts.threat_motif``. Only unambiguous
  motif words are matched — generic prose ("attack", "pressure", "threat")
  never fires. Motif values sourced from ``app.motifs.detect_motifs`` /
  ``app.moments`` (``leaks.category`` / ``threat_motif``).
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


# Motif keywords → the fact values (facts.category / facts.threat_motif) that
# support them. Values are the REAL ones app/moments.py carries (from
# leaks.category / threat_motif, ultimately app.motifs.detect_motifs):
# hanging, fork, knight_fork, pin, skewer, discovered, back_rank
# (plus missed_threat / mate, which have no unambiguous prose keyword —
# "threat" and "mate" are everyday chess words, so they are never flagged).
# A concrete chess object — a NAMED piece or a board square — is what makes a
# motif word a falsifiable tactical claim ("hanging knight", "fork on f7") rather
# than ordinary English ("hanging in the balance", "pinning his hopes", "a fork in
# the road"). Generic "piece(s)" is deliberately excluded: it is too common in
# non-tactical prose ("pieces on passive squares") to disambiguate.
_CHESS_OBJECT = re.compile(
    r"\b(?:king|queen|rook|bishop|knight|pawn)s?\b|\b[a-h][1-8]\b", re.IGNORECASE
)
_OBJECT_WINDOW = 24  # chars each side of the keyword to scan for an object

# (pattern, supporting fact values, display name, needs_object). The ambiguous
# single English words require an adjacent chess object; the already-specific
# compounds ("en prise", "discovered attack/check", "back-rank") do not.
_MOTIF_PATTERNS: list[tuple[re.Pattern, frozenset[str], str, bool]] = [
    (re.compile(r"\bhanging\b|\bhangs\b", re.IGNORECASE),
     frozenset({"hanging"}), "hanging", True),
    (re.compile(r"\ben prise\b", re.IGNORECASE),
     frozenset({"hanging"}), "hanging", False),
    (re.compile(r"\bfork(?:s|ed|ing)?\b", re.IGNORECASE),
     frozenset({"fork", "knight_fork"}), "fork", True),
    (re.compile(r"\bpin(?:s|ned|ning)?\b", re.IGNORECASE),
     frozenset({"pin"}), "pin", True),
    (re.compile(r"\bskewer(?:s|ed|ing)?\b", re.IGNORECASE),
     frozenset({"skewer"}), "skewer", True),
    (re.compile(r"\bdiscovered\s+(?:attack|check)\b", re.IGNORECASE),
     frozenset({"discovered"}), "discovered", False),
    (re.compile(r"\bback[- ]rank\b", re.IGNORECASE),
     frozenset({"back_rank"}), "back_rank", False),
]


def _names_motif(text: str, pattern: re.Pattern, needs_object: bool) -> bool:
    """True if *text* makes a concrete claim of this motif.

    When ``needs_object``, a named piece or square must sit within
    ``_OBJECT_WINDOW`` chars of a keyword match, so metaphorical/idiomatic uses
    ("hanging in the balance", "pinning his hopes", "a fork in the road") are not
    treated as tactical claims. A grounding violation is a hard fail, so this
    layer only fires on falsifiable claims.
    """
    for m in pattern.finditer(text or ""):
        if not needs_object:
            return True
        window = text[max(0, m.start() - _OBJECT_WINDOW): m.end() + _OBJECT_WINDOW]
        if _CHESS_OBJECT.search(window):
            return True
    return False


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


def _payload_motifs(payload: dict) -> set[str]:
    """Every motif value the payload's moments put on the record."""
    motifs: set[str] = set()
    for m in payload.get("moments") or []:
        facts = m.get("facts") or {}
        for key in ("category", "threat_motif"):
            if facts.get(key):
                motifs.add(facts[key])
    return motifs


def _check_motif_mismatch(payload: dict, narrative: dict) -> list[Violation]:
    """Flag motif words in prose that no moment's facts support."""
    present = _payload_motifs(payload)
    violations: list[Violation] = []

    def check_text(text: str, where: str) -> None:
        for pattern, supporting, name, needs_object in _MOTIF_PATTERNS:
            if _names_motif(text, pattern, needs_object) and not (supporting & present):
                violations.append(Violation(
                    "motif_mismatch", where,
                    f"names a {name} motif, but no moment's facts carry it",
                ))

    for ch in narrative.get("chapters") or []:
        check_text(ch.get("text"), f"chapter:{ch.get('phase')}")
    for m in narrative.get("moments") or []:
        check_text(m.get("text"), f"moment:{m.get('ply')}")
    check_text(narrative.get("overall"), "overall")
    return violations


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

    violations.extend(_check_motif_mismatch(payload, narrative))

    return violations
