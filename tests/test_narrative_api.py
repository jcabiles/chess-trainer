"""Tests for AI game commentary: app/narrative.py + the /narrative routes.

Fully offline — NO network, NO anthropic package, NO ANTHROPIC_API_KEY:

- Route tests fake ``narrative.generate`` via monkeypatch (the route seam).
- ``generate`` unit tests inject a fake ``anthropic`` module through the lazy
  import seam (``monkeypatch.setitem(sys.modules, "anthropic", ...)``),
  proving the parse → retry-once → NarrativeUnavailable ladder without the
  real package installed.
- ``build_prompt`` is pure and tested directly.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import sys
import types
from pathlib import Path

import chess
import pytest
from fastapi.testclient import TestClient

import app.narrative as narrative
import app.review as review_module
import app.storage as storage
from app.main import app, get_engine
from tests.engine_fakes import ScriptedEngine

# ---------------------------------------------------------------------------
# Fixtures / seeding helpers
# ---------------------------------------------------------------------------

_hash_counter = itertools.count()


@pytest.fixture(autouse=True)
def fresh_storage(tmp_path: Path, monkeypatch):
    """Fresh temp DB per test; no API key unless a test sets one."""
    db_path = str(tmp_path / "narrative_test.db")
    monkeypatch.setenv("GAMES_DB", db_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    storage.init(db_path)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


_SANS = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"]


def _plies(n: int = 6) -> list[dict]:
    """n real plies of the Italian, with FENs + alternating White-POV evals."""
    board = chess.Board()
    rows = []
    for i, san in enumerate(_SANS[:n], start=1):
        fen = board.fen()
        move = board.parse_san(san)
        rows.append({
            "ply": i,
            "san": san,
            "uci": move.uci(),
            "fen_before": fen,
            "eval_cp_white": 30 if i % 2 else 10,
            "is_user_move": 1 if i % 2 else 0,  # user is White
        })
        board.push(move)
    return rows


def _seed_game(status: str = "done", n_plies: int = 6) -> int:
    gid = storage.insert_game({
        "content_hash": f"narr-{next(_hash_counter)}",
        "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 *",
        "imported_at": "2026-01-01T00:00:00",
        "white": "Alice",
        "black": "Bob",
        "my_color": "white",
        "analysis_status": status,
    })
    storage.write_plies(gid, _plies(n_plies))
    return gid


_VALID_BODY = {
    "chapters": [{"phase": "opening", "text": "A calm Italian opening."}],
    "moments": [],
    "overall": "Solid game overall.",
}


def _fake_generate(body: dict = _VALID_BODY, side_effect=None):
    """An async stand-in for narrative.generate (the route seam)."""
    async def fake(payload):
        if side_effect is not None:
            side_effect()
        return dict(body)
    return fake


# ---------------------------------------------------------------------------
# GET /api/games/{id}/narrative
# ---------------------------------------------------------------------------

class TestGetNarrative:
    def test_unknown_game_404(self, client):
        r = client.get("/api/games/9999/narrative")
        assert r.status_code == 404

    def test_no_key_enabled_false(self, client):
        gid = _seed_game()
        r = client.get(f"/api/games/{gid}/narrative")
        assert r.status_code == 200
        assert r.json() == {"enabled": False, "narrative": None}

    def test_corrupt_cached_row_returns_none(self, client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        gid = _seed_game()
        storage.upsert_narrative(gid, "m", "{not json", "2026-01-01T00:00:00")
        r = client.get(f"/api/games/{gid}/narrative")
        assert r.status_code == 200
        assert r.json() == {"enabled": True, "narrative": None}


# ---------------------------------------------------------------------------
# POST /api/games/{id}/narrative
# ---------------------------------------------------------------------------

class TestPostNarrative:
    def test_unknown_game_404(self, client):
        assert client.post("/api/games/9999/narrative").status_code == 404

    def test_no_key_503(self, client):
        gid = _seed_game()
        r = client.post(f"/api/games/{gid}/narrative")
        assert r.status_code == 503
        assert "ANTHROPIC_API_KEY" in r.json()["detail"]

    def test_analysis_not_done_409(self, client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        gid = _seed_game(status="pending")
        assert client.post(f"/api/games/{gid}/narrative").status_code == 409

    def test_too_few_plies_422(self, client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        gid = _seed_game(n_plies=3)
        r = client.post(f"/api/games/{gid}/narrative")
        assert r.status_code == 422
        assert r.json()["detail"] == "not enough analyzed moves"

    def test_in_flight_409(self, client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        gid = _seed_game()
        narrative._in_flight.add(gid)
        r = client.post(f"/api/games/{gid}/narrative")
        assert r.status_code == 409
        assert "in progress" in r.json()["detail"]

    def test_success_caches_and_get_round_trips(self, client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(narrative, "generate", _fake_generate())
        gid = _seed_game()

        r = client.post(f"/api/games/{gid}/narrative")
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        data = body["narrative"]
        assert data["model"] == narrative.model_name()
        assert data["overall"] == "Solid game overall."
        assert data["chapters"] == [{"phase": "opening", "text": "A calm Italian opening."}]

        # Cached row is present and GET round-trips the same content.
        row = storage.get_narrative(gid)
        assert row is not None
        assert json.loads(row["narrative_json"])["overall"] == "Solid game overall."
        g = client.get(f"/api/games/{gid}/narrative")
        assert g.status_code == 200
        assert g.json()["narrative"] == data
        # In-flight guard was released.
        assert gid not in narrative._in_flight

    def test_staleness_discards_and_409(self, client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        gid = _seed_game()
        # A re-analysis finishes while the API call is "in flight": the fake
        # generator mutates the DB mid-call (fewer plies + status flip).
        def reanalyze():
            storage.write_plies(gid, _plies(4))
            storage.set_status(gid, "pending")

        monkeypatch.setattr(narrative, "generate", _fake_generate(side_effect=reanalyze))
        r = client.post(f"/api/games/{gid}/narrative")
        assert r.status_code == 409
        assert r.json()["detail"] == "game re-analyzed during generation — retry"
        assert storage.get_narrative(gid) is None
        assert gid not in narrative._in_flight

    def test_generate_failure_502_nothing_cached(self, client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        async def boom(payload):
            raise narrative.NarrativeUnavailable("api timed out")

        monkeypatch.setattr(narrative, "generate", boom)
        gid = _seed_game()
        r = client.post(f"/api/games/{gid}/narrative")
        assert r.status_code == 502
        assert r.json()["detail"] == "api timed out"
        assert storage.get_narrative(gid) is None
        assert gid not in narrative._in_flight


class TestReanalyzeInvalidation:
    def test_analyze_route_deletes_cached_narrative(self, client, monkeypatch):
        gid = _seed_game()
        storage.upsert_narrative(gid, "m", json.dumps(_VALID_BODY), "2026-01-01T00:00:00")
        calls = []
        monkeypatch.setattr(review_module, "start_analysis", lambda *a, **k: calls.append(a))
        app.dependency_overrides[get_engine] = lambda: ScriptedEngine()

        r = client.post(f"/api/games/{gid}/analyze")
        assert r.status_code == 200
        assert len(calls) == 1
        assert storage.get_narrative(gid) is None


# ---------------------------------------------------------------------------
# build_prompt (pure)
# ---------------------------------------------------------------------------

_PAYLOAD = {
    "header": {"white": "Alice", "black": "Bob", "result": "1-0"},
    "profile_context": {
        "header": {"white": "Alice"},
        "clusters": [{"category": "hanging_piece", "count": 7, "coach": "Loose pieces"}],
    },
    "my_color": "white",
    "eval_arc": {"opening": {"min": 0.5, "max": 0.6, "end": 0.55}},
    "moments": [
        {"ply": 5, "san": "Bc4", "kind": "narrow_choice",
         "facts": {"pv_san": ["Bc4", "Bc5"]}},
    ],
    "moments_dropped": 0,
}


class TestBuildPrompt:
    def test_system_rules(self):
        system, _ = narrative.build_prompt(_PAYLOAD)
        assert "Never invent moves" in system
        assert "second-best move" in system
        assert "BOTH sides" in system
        assert "recurring pattern" in system
        # Strict JSON contract is stated verbatim.
        assert '"chapters"' in system and '"moments"' in system and '"overall"' in system
        assert "300-500 words" in system and "1-2 sentences" in system
        # Readability contract: short topic paragraphs, blank-line separated.
        assert "2-3 sentences" in system and "\\n\\n" in system

    def test_user_contains_facts_and_allowed_sets(self):
        _, user = narrative.build_prompt(_PAYLOAD)
        assert "Alice" in user and "Bc4" in user  # payload facts embedded
        assert "hanging_piece" in user            # profile clusters embedded
        assert "['opening']" in user              # phases from eval_arc only
        assert "[5]" in user                      # plies from payload moments only

    def test_empty_payload_is_pure_and_safe(self):
        system, user = narrative.build_prompt({"eval_arc": {}, "moments": []})
        assert "[]" in user
        assert isinstance(system, str)


# ---------------------------------------------------------------------------
# generate() — fake anthropic module via the lazy-import seam
# ---------------------------------------------------------------------------

_GEN_PAYLOAD = {"eval_arc": {"opening": {"min": 0.5, "max": 0.6, "end": 0.5}},
                "moments": [{"ply": 3}]}

_GOOD_REPLY = json.dumps({
    "chapters": [{"phase": "opening", "text": "Fine start."}],
    "moments": [{"ply": 3, "text": "Sharp moment."}],
    "overall": "Well played.",
})


def _install_fake_anthropic(monkeypatch, replies: list[str]):
    """Install a fake anthropic module; returns the recorded create() kwargs."""
    calls: list[dict] = []

    class _Messages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            text = replies[min(len(calls) - 1, len(replies) - 1)]
            block = types.SimpleNamespace(type="text", text=text)
            return types.SimpleNamespace(content=[block])

    class AsyncAnthropic:
        def __init__(self, timeout=None):
            self.timeout = timeout
            self.messages = _Messages()

    mod = types.ModuleType("anthropic")
    mod.AsyncAnthropic = AsyncAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    return calls


class TestGenerate:
    def test_package_missing_raises_unavailable(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "anthropic", None)  # import -> ImportError
        with pytest.raises(narrative.NarrativeUnavailable, match="not installed"):
            asyncio.run(narrative.generate(_GEN_PAYLOAD))

    def test_valid_first_reply(self, monkeypatch):
        calls = _install_fake_anthropic(monkeypatch, [_GOOD_REPLY])
        data = asyncio.run(narrative.generate(_GEN_PAYLOAD))
        assert data["overall"] == "Well played."
        assert data["moments"] == [{"ply": 3, "text": "Sharp moment."}]
        assert len(calls) == 1
        assert calls[0]["model"] == "claude-sonnet-5"  # NARRATIVE_MODEL default
        assert calls[0]["max_tokens"] == 2000

    def test_markdown_fences_stripped(self, monkeypatch):
        _install_fake_anthropic(monkeypatch, [f"```json\n{_GOOD_REPLY}\n```"])
        data = asyncio.run(narrative.generate(_GEN_PAYLOAD))
        assert data["chapters"] == [{"phase": "opening", "text": "Fine start."}]

    def test_invalid_then_valid_retries_with_corrective_line(self, monkeypatch):
        calls = _install_fake_anthropic(monkeypatch, ["not json at all", _GOOD_REPLY])
        data = asyncio.run(narrative.generate(_GEN_PAYLOAD))
        assert data["overall"] == "Well played."
        assert len(calls) == 2
        retry_user = calls[1]["messages"][0]["content"]
        assert "previous reply was invalid" in retry_user

    def test_invalid_twice_raises_unavailable(self, monkeypatch):
        calls = _install_fake_anthropic(monkeypatch, ["nope", "still nope"])
        with pytest.raises(narrative.NarrativeUnavailable, match="after retry"):
            asyncio.run(narrative.generate(_GEN_PAYLOAD))
        assert len(calls) == 2

    def test_unknown_moment_ply_rejected(self, monkeypatch):
        bad = json.dumps({"chapters": [], "moments": [{"ply": 99, "text": "?"}],
                          "overall": "x"})
        _install_fake_anthropic(monkeypatch, [bad, bad])
        with pytest.raises(narrative.NarrativeUnavailable, match="ply 99"):
            asyncio.run(narrative.generate(_GEN_PAYLOAD))

    def test_bad_chapter_phase_rejected(self, monkeypatch):
        bad = json.dumps({"chapters": [{"phase": "lunch break", "text": "?"}],
                          "moments": [], "overall": "x"})
        _install_fake_anthropic(monkeypatch, [bad, bad])
        with pytest.raises(narrative.NarrativeUnavailable, match="phase"):
            asyncio.run(narrative.generate(_GEN_PAYLOAD))

    def test_api_error_no_retry(self, monkeypatch):
        calls: list[dict] = []

        class _Messages:
            async def create(self, **kwargs):
                calls.append(kwargs)
                raise RuntimeError("connection refused")

        class AsyncAnthropic:
            def __init__(self, timeout=None):
                self.messages = _Messages()

        mod = types.ModuleType("anthropic")
        mod.AsyncAnthropic = AsyncAnthropic
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        with pytest.raises(narrative.NarrativeUnavailable, match="connection refused"):
            asyncio.run(narrative.generate(_GEN_PAYLOAD))
        assert len(calls) == 1

    def test_env_model_and_timeout_used(self, monkeypatch):
        monkeypatch.setenv("NARRATIVE_MODEL", "claude-test-9")
        monkeypatch.setenv("NARRATIVE_TIMEOUT_S", "5")
        timeouts: list[float] = []
        calls: list[dict] = []

        class _Messages:
            async def create(self, **kwargs):
                calls.append(kwargs)
                block = types.SimpleNamespace(type="text", text=_GOOD_REPLY)
                return types.SimpleNamespace(content=[block])

        class AsyncAnthropic:
            def __init__(self, timeout=None):
                timeouts.append(timeout)
                self.messages = _Messages()

        mod = types.ModuleType("anthropic")
        mod.AsyncAnthropic = AsyncAnthropic
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        asyncio.run(narrative.generate(_GEN_PAYLOAD))
        assert calls[0]["model"] == "claude-test-9"
        assert timeouts == [5.0]
