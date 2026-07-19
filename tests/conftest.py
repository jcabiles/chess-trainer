"""Session-wide test config.

Set CHESS_SKIP_ENGINE_AUTOSTART so the FastAPI lifespan (run by every TestClient)
does NOT spawn a real Stockfish process — API tests inject fake engines via
dependency_overrides, so the real engine is never needed there. This skips only the
lifespan autostart; STOCKFISH_PATH is left untouched, so the real-engine integration
tests (which start their own engine directly) still run with the real binary.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _skip_engine_autostart():
    prev = os.environ.get("CHESS_SKIP_ENGINE_AUTOSTART")
    os.environ["CHESS_SKIP_ENGINE_AUTOSTART"] = "1"
    yield
    if prev is None:
        os.environ.pop("CHESS_SKIP_ENGINE_AUTOSTART", None)
    else:
        os.environ["CHESS_SKIP_ENGINE_AUTOSTART"] = prev


@pytest.fixture(autouse=True)
def _maia_off(request, tmp_path_factory, monkeypatch):
    """Force Maia-unready for every test by default (Maia skeleton T4).

    Machines WITH lc0 + nets installed would otherwise route persona 'casey'
    through Maia and silently bypass the SF fakes that the bot-route suites
    assert against — tests must be deterministic on any machine. Points
    MAIA_WEIGHTS_DIR at an empty dir so ``maia_ready_for()`` is False.
    ``tests/test_maia_engine.py`` (and any test that opts back in by setting
    its own MAIA_WEIGHTS_DIR / patching ``main.get_maia_engine``) is exempt.
    """
    if request.module.__name__.endswith("test_maia_engine"):
        yield
        return
    monkeypatch.setenv(
        "MAIA_WEIGHTS_DIR", str(tmp_path_factory.mktemp("no-maia-weights"))
    )
    yield


@pytest.fixture(autouse=True)
def _clear_narrative_in_flight():
    """Never leak the narrative in-flight guard across tests (same discipline
    as the manual review._tasks cleanup in tests/test_review.py)."""
    yield
    from app import narrative

    narrative._in_flight.clear()
