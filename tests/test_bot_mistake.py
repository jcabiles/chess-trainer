"""Unit tests for the mistake tier in app.bot_blunder (T1).

Pure, engine-free: ``should_mistake`` / ``pick_mistake`` need no Stockfish
binary. Candidate dicts are hand-built (``bot_engine.candidates()`` shape:
``{uci, san, scoreCp}``, White-POV, best-for-the-mover first).
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from app import bot_blunder as bb

# ---------------------------------------------------------------------------
# Lightweight persona stub (do NOT depend on personas.py)
# ---------------------------------------------------------------------------


@dataclass
class StubPersona:
    mistakeRate: float


def _cand(score_cp: int, uci: str = "e2e4") -> dict:
    """A minimal candidate dict; only scoreCp matters for the mistake tier."""
    return {"uci": uci, "san": "?", "scoreCp": score_cp}


# ---------------------------------------------------------------------------
# should_mistake
# ---------------------------------------------------------------------------


def test_should_mistake_seeded_deterministic():
    persona = StubPersona(mistakeRate=0.5)
    a = bb.should_mistake(persona, "middlegame", 30, seed=7)
    b = bb.should_mistake(persona, "middlegame", 30, seed=7)
    assert a == b  # same (seed, ply) ⇒ same decision


def test_should_mistake_never_fires_in_opening():
    persona = StubPersona(mistakeRate=1.0)  # would always fire but for the gate
    for ply in range(0, 40):
        assert bb.should_mistake(persona, "opening", ply, seed=1) is False


def test_should_mistake_respects_zero_rate():
    persona = StubPersona(mistakeRate=0.0)
    for ply in range(0, 40):
        assert bb.should_mistake(persona, "middlegame", ply, seed=3) is False


def test_should_mistake_fires_somewhere_with_high_rate():
    persona = StubPersona(mistakeRate=0.5)
    fired = [bb.should_mistake(persona, "middlegame", ply, seed=99) for ply in range(60)]
    assert any(fired)  # a 0.5 rate should hit on some plies


# ---------------------------------------------------------------------------
# pick_mistake — in-band selection
# ---------------------------------------------------------------------------


def test_pick_mistake_picks_in_band_candidate():
    board = chess.Board()  # White to move — no POV flip
    # losses vs best: [0, 100, 300, 30]; only index 1 (100cp) is in [50, 250].
    cands = [_cand(400), _cand(300), _cand(100), _cand(370)]
    idx = bb.pick_mistake(cands, board, seed=5, ply=20)
    assert idx == 1
    loss = cands[0]["scoreCp"] - cands[idx]["scoreCp"]
    assert bb.MISTAKE_LO <= loss <= bb.MISTAKE_HI


def test_pick_mistake_deterministic():
    board = chess.Board()
    # Two in-band candidates (loss 100 and 200) → seeded choice must be stable.
    cands = [_cand(400), _cand(300), _cand(200), _cand(390)]
    first = bb.pick_mistake(cands, board, seed=42, ply=18)
    second = bb.pick_mistake(cands, board, seed=42, ply=18)
    assert first == second
    assert first in (1, 2)  # one of the two in-band indices


def test_pick_mistake_never_returns_above_band_when_empty():
    board = chess.Board()
    # losses [0, 800, 900, 1200] — all blunder-magnitude, none in (50, 250].
    cands = [_cand(0), _cand(-800), _cand(-900), _cand(-1200)]
    idx = bb.pick_mistake(cands, board, seed=1, ply=25)
    assert idx == 0  # bounded fallback must NOT return a >250cp move


def test_pick_mistake_empty_band_returns_best():
    board = chess.Board()
    # No candidate loses within [MISTAKE_LO, MISTAKE_HI] → play best (idx 0).
    # Mixed straddle: losses [0, 40, 260, 300] (40 below band, 260/300 above).
    cands = [_cand(400), _cand(360), _cand(140), _cand(100)]
    assert bb.pick_mistake(cands, board, seed=2, ply=22) == 0
    # All alternatives near-best (losses < MISTAKE_LO) → best.
    near = [_cand(400), _cand(390), _cand(380), _cand(370)]
    assert bb.pick_mistake(near, board, seed=2, ply=22) == 0
    # Losing position — every alternative is blunder-magnitude (> MISTAKE_HI).
    # The tier must NEVER pick one of these; it returns best.
    losing = [_cand(400), _cand(-400), _cand(-600), _cand(-900)]
    assert bb.pick_mistake(losing, board, seed=2, ply=22) == 0


def test_pick_mistake_skips_forced_mate_best():
    board = chess.Board()
    # cands[0] is a forced mate (bot_engine ±100000 sentinel) → skip the tier.
    cands = [_cand(100000), _cand(300), _cand(200)]
    assert bb.pick_mistake(cands, board, seed=3, ply=30) == 0
    # Also the negative mate sentinel (getting mated) is guarded.
    cands_neg = [_cand(-100000), _cand(-300), _cand(-200)]
    assert bb.pick_mistake(cands_neg, board, seed=3, ply=30) == 0


def test_pick_mistake_single_element_list():
    board = chess.Board()
    assert bb.pick_mistake([_cand(120)], board, seed=1, ply=10) == 0


def test_pick_mistake_empty_list():
    board = chess.Board()
    assert bb.pick_mistake([], board, seed=1, ply=10) == 0


# ---------------------------------------------------------------------------
# Mover-POV correctness (Black to move)
# ---------------------------------------------------------------------------


def test_pick_mistake_black_to_move_mover_pov():
    # Black to move: scoreCp is White-POV, so the mover's BEST move is the most
    # NEGATIVE White-POV score. cands are best-for-the-mover first (Black best).
    board = chess.Board()
    board.push_san("e4")  # now Black to move
    # White-POV scores; mover(Black)-POV = -scoreCp.
    #   cands[0]: -400 → mover +400 (best)
    #   cands[1]: -300 → mover +300 → loss 100 (in band)
    #   cands[2]: -100 → mover +100 → loss 300 (out of band)
    cands = [_cand(-400), _cand(-300), _cand(-100)]
    idx = bb.pick_mistake(cands, board, seed=11, ply=15)
    assert idx == 1  # loss math is mover-relative, not raw White-POV

    # Sanity: without the POV flip a naive max(scoreCp) would rank -100 as "best"
    # and mis-compute the losses; assert the mover-POV loss for the pick is 100.
    mover = lambda c: -c["scoreCp"]  # noqa: E731  Black to move
    loss = mover(cands[0]) - mover(cands[idx])
    assert loss == 100
