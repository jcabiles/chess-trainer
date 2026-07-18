"""
personas.py — bot persona ladder + pure seeded sampling (no engine, no network).

Exposes a catalog of named bot personas (UCI_Elo 1350–2000, each with a one-line
character description and a sampling ``temperature``) and the pure helper
``weighted_choice`` used to pick among candidate moves with mild, seeded variety.

The in-memory default is the hardcoded 4-persona ladder — set at import with **no
file I/O**, so ``all()`` / ``get()`` / ``default_id()`` work before ``init`` is
ever called. ``init(path=None)`` optionally overrides the catalog from
``data/personas.json`` (env ``PERSONAS_FILE``); a missing / invalid / failing-
validation file keeps the built-in default and logs one warning, never raises.

Engine-free and unit-pure — mirrors the ``book.py`` / ``repertoire.py`` singleton
+ env-override + warn-once idiom. All strength/style is temperature-only here;
mate is already mapped to a signed ±MATE_CP upstream, so ``weighted_choice`` sees
plain mover-POV numbers.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    """A named bot persona. ``elo`` is UCI_Elo; ``temperature`` is in centipawns.

    ``blunderRate`` and ``threatDistance`` are the B5 causal-blunder dials (both
    ∈ [0,1]): ``blunderRate`` is the base middlegame fire probability for the
    input-side blunder gate; ``threatDistance`` is the off-plan-score threshold a
    missed threat must exceed to be missed (lower elo → lower threshold → misses
    more). See ``app/bot_blunder.py`` / ``docs/ai-dlc/specs/causal-blunder.md``.
    """

    id: str
    name: str
    elo: int
    style: str
    description: str
    temperature: float
    blunderRate: float
    threatDistance: float
    mistakeRate: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


# style -> default sampling temperature (cp), used when a loaded persona omits it.
_STYLE_TEMP = {"solid": 80, "tactical": 130, "aggressive": 200, "positional": 100}
_DEFAULT_TEMP = 120


def _default_blunder_rate(elo: int) -> float:
    """Elo-derived default: monotone decreasing (spec: causal-blunder.md)."""
    return max(0.03, min(0.9, 0.9 - (elo - 1300) / 1000))


def _default_threat_distance(elo: int) -> float:
    """Elo-derived default: monotone increasing (spec: causal-blunder.md)."""
    return max(0.15, min(0.85, (elo - 1200) / 1200))

DEFAULT_ID = "casey"

# Validation bounds (spec: "NEW app/personas.py" + tickets T1).
_ELO_MIN = 1320
_ELO_MAX = 3000

# The built-in ladder — hardcoded, set at import with NO file I/O. data/personas.json
# ships the same four so the committed file and this default agree.
_DEFAULT_PERSONAS: tuple[Persona, ...] = (
    Persona("casey", "Ming Ling", 1350, "solid", "Kid prodigy — steady, but misses tactics.", 80, 0.85, 0.15, 0.0),
    Persona("diego", "Nina", 1350, "attacking", "Attacking club player — hunts your king, soft on defense.", 190, 0.85, 0.10, 0.0),
    Persona("robin", "Amanda", 1350, "sloppy", "Beginner — drifts and leaks small mistakes.", 100, 0.18, 0.30, 0.50),
    Persona("morgan", "Diana", 1550, "tactical", "Focused student — punishes loose play and hangs onto material.", 130, 0.65, 0.29, 0.0),
    Persona("alex", "Melvin", 1800, "aggressive", "Casual crusher — sharp, presses for the attack.", 200, 0.40, 0.50, 0.0),
    Persona("vera", "Mandeep", 2000, "positional", "Calm veteran — grinds small edges in long games.", 100, 0.20, 0.67, 0.0),
)

# Module-level singleton — initialised to the built-in default so imports never
# raise and a missing config simply means "the built-in ladder".
_personas: tuple[Persona, ...] = _DEFAULT_PERSONAS


# ---------------------------------------------------------------------------
# Loading / validation
# ---------------------------------------------------------------------------


def _style_temp(style: str) -> int:
    return _STYLE_TEMP.get(style, _DEFAULT_TEMP)


def _parse_persona(entry: dict) -> Persona:
    """Build a Persona from a raw dict, deriving temperature/blunderRate/
    threatDistance from style/elo if absent (so an old ``data/personas.json``
    without the B5 dials still loads).

    Raises on a structurally broken entry (caught by ``_load`` → keep defaults).
    """
    elo = int(entry["elo"])
    temp = entry.get("temperature")
    if temp is None:
        temp = _style_temp(str(entry.get("style", "")))
    blunder_rate = entry.get("blunderRate")
    if blunder_rate is None:
        blunder_rate = _default_blunder_rate(elo)
    threat_distance = entry.get("threatDistance")
    if threat_distance is None:
        threat_distance = _default_threat_distance(elo)
    mistake_rate = entry.get("mistakeRate")
    if mistake_rate is None:
        mistake_rate = 0.0
    return Persona(
        id=str(entry["id"]),
        name=str(entry["name"]),
        elo=elo,
        style=str(entry["style"]),
        description=str(entry["description"]),
        temperature=float(temp),
        blunderRate=float(blunder_rate),
        threatDistance=float(threat_distance),
        mistakeRate=float(mistake_rate),
    )


def _validate(personas: list[Persona]) -> Optional[str]:
    """Return None if the loaded ladder is valid, else a short reason string."""
    if not personas:
        return "empty"
    ids = [p.id for p in personas]
    if len(set(ids)) != len(ids):
        return "duplicate ids"
    if DEFAULT_ID not in ids:
        return f"default id '{DEFAULT_ID}' missing"
    for p in personas:
        if not (_ELO_MIN <= p.elo <= _ELO_MAX):
            return f"elo {p.elo} for '{p.id}' out of range [{_ELO_MIN}, {_ELO_MAX}]"
        if not math.isfinite(p.temperature) or p.temperature <= 0:
            return f"temperature {p.temperature} for '{p.id}' not finite and > 0"
        if not (0.0 <= p.blunderRate <= 1.0):
            return f"blunderRate {p.blunderRate} for '{p.id}' out of range [0, 1]"
        if not (0.0 <= p.threatDistance <= 1.0):
            return f"threatDistance {p.threatDistance} for '{p.id}' out of range [0, 1]"
        if not (0.0 <= p.mistakeRate <= 1.0):
            return f"mistakeRate {p.mistakeRate} for '{p.id}' out of range [0, 1]"
    return None


def _load(path: Optional[str]) -> None:
    """Load + validate the catalog from a file; keep the built-in default on any problem."""
    global _personas

    resolved = path if path is not None else os.environ.get("PERSONAS_FILE", "data/personas.json")
    file_path = Path(resolved)
    if not file_path.exists():
        logger.warning("personas: config '%s' not found — using built-in ladder", file_path)
        _personas = _DEFAULT_PERSONAS
        return
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        entries = raw["personas"] if isinstance(raw, dict) else raw
        loaded = [_parse_persona(e) for e in entries]
    except Exception as exc:
        logger.warning("personas: cannot read/parse '%s': %s — using built-in ladder", file_path, exc)
        _personas = _DEFAULT_PERSONAS
        return

    reason = _validate(loaded)
    if reason is not None:
        logger.warning("personas: '%s' invalid (%s) — using built-in ladder", file_path, reason)
        _personas = _DEFAULT_PERSONAS
        return

    _personas = tuple(loaded)
    logger.info("personas: loaded %d from '%s'", len(loaded), file_path)


def init(path: Optional[str] = None) -> None:
    """Load the persona catalog at app startup (env ``PERSONAS_FILE``); never raises."""
    _load(path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def all() -> list[Persona]:
    """Return the current persona ladder (a fresh list)."""
    return list(_personas)


def get(persona_id: str) -> Optional[Persona]:
    """Return the persona with this id, or None."""
    for p in _personas:
        if p.id == persona_id:
            return p
    return None


def default_id() -> str:
    """Return the default persona id (``"casey"``)."""
    return DEFAULT_ID


# ---------------------------------------------------------------------------
# Pure sampling
# ---------------------------------------------------------------------------


def weighted_choice(scores, temperature: float, seed) -> int:
    """Pick an index over mover-POV ``scores`` via a stable, seeded softmax.

    ``w_i = exp((s_i - max(s)) / temperature)`` — a hotter ``temperature`` flattens
    the distribution. ``temperature`` is in centipawns and clamped to a floor of 1
    if ≤ 0. Scores are plain numbers (mate already mapped to ±MATE_CP upstream).

    Empty ``scores`` raises ``ValueError``; a single score returns 0. Deterministic
    for a fixed ``seed`` (draws from ``random.Random(seed)``).
    """
    n = len(scores)
    if n == 0:
        raise ValueError("weighted_choice: scores must be non-empty")
    if n == 1:
        return 0

    temp = float(temperature)
    if temp <= 0:
        temp = 1.0

    top = max(scores)
    weights = [math.exp((s - top) / temp) for s in scores]
    total = sum(weights)
    # ``top`` gives weight 1.0, so ``total`` is always ≥ 1 — no divide-by-zero.
    r = random.Random(seed).random() * total
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if r < acc:
            return i
    return n - 1  # float-rounding guard
