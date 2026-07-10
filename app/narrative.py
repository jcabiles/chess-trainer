"""Claude narrative generation for game commentary (narrative-review feature).

The app's ONLY network-aware module.  Turns the facts-only payload built by
:mod:`app.moments` into a prompt, calls the Anthropic API, and validates the
strict-JSON reply.  Everything else stays offline:

- ``build_prompt`` is pure and unit-testable (no network, no ``anthropic``).
- ``generate`` lazily imports ``anthropic`` INSIDE the function — the package
  is an optional dependency and this module must stay importable (and the
  whole test suite green) without it, mirroring how :mod:`app.engine` stays
  import-safe without a Stockfish binary.
- :class:`NarrativeUnavailable` mirrors ``EngineUnavailable`` semantics: the
  route maps it to an HTTP error; nothing is persisted on failure.

Auth is ``ANTHROPIC_API_KEY`` only (never Max/Pro OAuth — Anthropic ToS).
Env knobs: ``NARRATIVE_MODEL`` (default ``claude-sonnet-5``) and
``NARRATIVE_TIMEOUT_S`` (default 60, passed to the client).

Concurrency: ``_in_flight`` holds game ids with a generation currently
awaiting the API; the route checks membership (409 on duplicates) and wraps
add/discard in try/finally.  Never touches the engine lock or
``review._tasks``.
"""

from __future__ import annotations

import json
import os

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_TIMEOUT_S = 60.0
MAX_TOKENS = 2000

_ALLOWED_PHASES = ("opening", "middlegame", "endgame")

# Game ids with a generation currently in flight (guarded by the route's
# try/finally; tests clear it via the conftest fixture).
_in_flight: set[int] = set()


class NarrativeUnavailable(Exception):
    """Narrative generation is unavailable or failed (mirrors EngineUnavailable)."""


def is_enabled() -> bool:
    """True when an ANTHROPIC_API_KEY is present in the environment (call-time check)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def model_name() -> str:
    """The Anthropic model to use (env NARRATIVE_MODEL, default claude-sonnet-5)."""
    return os.environ.get("NARRATIVE_MODEL", DEFAULT_MODEL)


def _timeout_s() -> float:
    try:
        return float(os.environ.get("NARRATIVE_TIMEOUT_S", DEFAULT_TIMEOUT_S))
    except ValueError:
        return DEFAULT_TIMEOUT_S


# ---------------------------------------------------------------------------
# Prompt building (pure)
# ---------------------------------------------------------------------------

def build_prompt(payload: dict) -> tuple[str, str]:
    """Build the (system, user) prompt pair for a moments payload.  Pure.

    The system prompt pins the coach voice and the facts-only rules; the user
    message carries the full JSON payload plus the exact output contract
    (which phases may appear as chapters, which plies may appear as moments).
    """
    eval_arc = payload.get("eval_arc") or {}
    phases = [p for p in _ALLOWED_PHASES if p in eval_arc]
    plies = sorted({m["ply"] for m in payload.get("moments") or []})

    system = (
        "You are a supportive, concrete chess coach writing game commentary "
        "for a club-level player.\n"
        "Rules — follow every one:\n"
        "- Narrate ONLY facts present in the provided payload (moves, evals, "
        "win-probability swings, phases, motifs). Never invent moves, "
        "variations, or evaluations that are not in the payload.\n"
        "- You may quote the provided pv_san lines verbatim as concrete "
        "variations, but never extend or alter them.\n"
        "- Never name or guess a second-best move — the payload never "
        "contains one. For narrow_choice moments, say the alternatives were "
        "much worse without naming any.\n"
        "- Comment on BOTH sides' play, not just the user's.\n"
        "- When profile_context clusters match this game's mistake "
        "categories, connect them explicitly (e.g. \"a recurring pattern for "
        "you\").\n"
        "- Output STRICT JSON only — no markdown fences, no prose outside "
        "the JSON object. Schema: {\"chapters\": [{\"phase\": "
        "\"opening\"|\"middlegame\"|\"endgame\", \"text\": str}], "
        "\"moments\": [{\"ply\": int, \"text\": str}], \"overall\": str}.\n"
        "- Include chapters ONLY for phases the game reached (listed in the "
        "user message); include moments ONLY for the plies listed in the "
        "user message.\n"
        "- 300-500 words total across the chapters; 1-2 sentences per "
        "moment; \"overall\" is a short takeaway for the player.\n"
        "- Break every chapter's \"text\" (and \"overall\") into short "
        "paragraphs of 2-3 sentences max, one topic per paragraph, separated "
        "by a blank line (a literal \\n\\n inside the JSON string). Never "
        "write a single wall-of-text paragraph."
    )

    user = (
        "Analysis payload for one game (all facts you may use):\n"
        f"{json.dumps(payload)}\n\n"
        f"Chapters allowed (phases present in this game): {phases}\n"
        f"Moment plies allowed: {plies}\n"
        "Reply with the strict JSON object now."
    )
    return system, user


# ---------------------------------------------------------------------------
# Response parsing / validation
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Defensively strip a markdown code fence around a JSON reply."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rstrip()
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _parse_and_validate(text: str, payload: dict) -> dict:
    """Parse a model reply into {chapters, moments, overall}; ValueError on any violation."""
    try:
        data = json.loads(_strip_fences(text))
    except (TypeError, ValueError):
        raise ValueError("reply was not valid JSON")
    if not isinstance(data, dict):
        raise ValueError("reply was not a JSON object")

    chapters = data.get("chapters")
    moments = data.get("moments")
    overall = data.get("overall")
    if not isinstance(chapters, list) or not isinstance(moments, list):
        raise ValueError("reply must have 'chapters' and 'moments' lists")
    if not isinstance(overall, str):
        raise ValueError("reply must have a string 'overall'")

    allowed_plies = {m["ply"] for m in payload.get("moments") or []}

    out_chapters = []
    for ch in chapters:
        if not isinstance(ch, dict) or ch.get("phase") not in _ALLOWED_PHASES:
            raise ValueError(f"invalid chapter phase: {ch!r}")
        if not isinstance(ch.get("text"), str):
            raise ValueError("chapter 'text' must be a string")
        out_chapters.append({"phase": ch["phase"], "text": ch["text"]})

    out_moments = []
    for m in moments:
        if not isinstance(m, dict) or not isinstance(m.get("ply"), int):
            raise ValueError(f"invalid moment entry: {m!r}")
        if m["ply"] not in allowed_plies:
            raise ValueError(f"moment ply {m['ply']} is not a payload moment")
        if not isinstance(m.get("text"), str):
            raise ValueError("moment 'text' must be a string")
        out_moments.append({"ply": m["ply"], "text": m["text"]})

    return {"chapters": out_chapters, "moments": out_moments, "overall": overall}


def _response_text(resp) -> str:
    """Concatenate the text blocks of an Anthropic Messages response."""
    parts = []
    for block in getattr(resp, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Generation (the only networked call in the app)
# ---------------------------------------------------------------------------

async def generate(payload: dict) -> dict:
    """Call Claude on a moments payload; return {chapters, moments, overall}.

    Lazy-imports ``anthropic`` (the package may not be installed).  Retries
    ONCE on a parse/validation failure with a corrective line appended to the
    user message, then raises :class:`NarrativeUnavailable`.  API/transport
    failures raise :class:`NarrativeUnavailable` immediately.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise NarrativeUnavailable(
            "anthropic package not installed — pip install -r requirements.txt"
        ) from exc

    system, user = build_prompt(payload)
    client = anthropic.AsyncAnthropic(timeout=_timeout_s())

    last_error = "empty response"
    for attempt in range(2):
        try:
            resp = await client.messages.create(
                model=model_name(),
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            raise NarrativeUnavailable(f"Anthropic API call failed: {exc}") from exc
        try:
            return _parse_and_validate(_response_text(resp), payload)
        except ValueError as exc:
            last_error = str(exc)
            if attempt == 0:
                user += (
                    f"\n\nYour previous reply was invalid ({last_error}). "
                    "Reply again with the STRICT JSON object only, exactly "
                    "matching the required schema and allowed phases/plies."
                )
    raise NarrativeUnavailable(f"invalid narrative response after retry: {last_error}")
