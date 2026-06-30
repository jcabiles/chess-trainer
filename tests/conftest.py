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
