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
    """A named bot persona. ``elo`` is UCI_Elo; ``temperature`` is in centipawns."""

    id: str
    name: str
    elo: int
    style: str
    description: str
    temperature: float

    def as_dict(self) -> dict:
        return asdict(self)


# style -> default sampling temperature (cp), used when a loaded persona omits it.
_STYLE_TEMP = {"solid": 80, "tactical": 130, "aggressive": 200, "positional": 100}
_DEFAULT_TEMP = 120

DEFAULT_ID = "casey"

# Validation bounds (spec: "NEW app/personas.py" + tickets T1).
_ELO_MIN = 1320
_ELO_MAX = 3000

# The built-in ladder — hardcoded, set at import with NO file I/O. data/personas.json
# ships the same four so the committed file and this default agree.
_DEFAULT_PERSONAS: tuple[Persona, ...] = (
    Persona("casey", "Casey", 1350, "solid", "Casual club player — steady, but misses tactics.", 80),
    Persona("morgan", "Morgan", 1550, "tactical", "Improving — punishes loose play and hangs onto material.", 130),
    Persona("alex", "Alex", 1800, "aggressive", "Strong club player — sharp, presses for the attack.", 200),
    Persona("vera", "Vera", 2000, "positional", "Expert — grinds small edges in long games.", 100),
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
    """Build a Persona from a raw dict, deriving temperature from style if absent.

    Raises on a structurally broken entry (caught by ``_load`` → keep defaults).
    """
    temp = entry.get("temperature")
    if temp is None:
        temp = _style_temp(str(entry.get("style", "")))
    return Persona(
        id=str(entry["id"]),
        name=str(entry["name"]),
        elo=int(entry["elo"]),
        style=str(entry["style"]),
        description=str(entry["description"]),
        temperature=float(temp),
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
