#!/usr/bin/env python3
"""Analyze all pending games in the DB using Stockfish directly (no server needed)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import review, storage
from app.engine import StockfishEngine


async def main() -> None:
    storage.init()
    conn = storage._get_conn()
    rows = conn.execute(
        "SELECT id, white, black, date FROM games WHERE analysis_status='pending' ORDER BY id"
    ).fetchall()

    if not rows:
        print("No pending games.")
        return

    print(f"{len(rows)} pending games. Starting Stockfish…")
    engine = StockfishEngine()
    engine.start()

    for i, row in enumerate(rows, 1):
        gid, white, black, date = row
        print(f"[{i}/{len(rows)}] game {gid}: {white} vs {black} ({date})", flush=True)
        storage.set_status(gid, "analyzing")
        try:
            await review.analyze_game(gid, engine, depth=review.BACKGROUND_DEPTH)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            storage.set_status(gid, "failed")

    engine.close()
    print("\nDone.")


asyncio.run(main())
