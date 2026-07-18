"""Offline tests for the eval harness's deterministic grounding checks.

Prove the checker catches each planted violation class and stays silent on
clean commentary — including over the real golden payloads. No API key, no
network: this is the CI-runnable slice of the eval harness.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evals.grounding import check_narrative

GOLDEN_DIR = Path(__file__).parent.parent / "evals" / "golden"


# ---------------------------------------------------------------------------
# Synthetic payload — small, fully controlled
# ---------------------------------------------------------------------------

PAYLOAD = {
    "header": {"white": "Me", "black": "Opponent", "result": "1-0"},
    "my_color": "white",
    "eval_arc": {"opening": {"min": -30, "max": 60, "end": 40},
                 "middlegame": {"min": -350, "max": 60, "end": -350}},
    "moments": [
        {"ply": 9, "san": "Nxe4", "move_number": 5, "side": "white",
         "is_user_move": True, "kind": "user_blunder", "severity": "blunder",
         "facts": {"fen_before": "x", "best_san": "exd4",
                   "pv_san": ["exd4", "Nxd4", "Bc5"]}},
        {"ply": 14, "san": "Qh5", "move_number": 7, "side": "black",
         "is_user_move": False, "kind": "narrow_choice", "severity": None,
         "facts": {"fen_before": "y"}},
    ],
    "moments_dropped": 0,
}


def _clean_narrative() -> dict:
    return {
        "chapters": [
            {"phase": "opening", "text": "A calm start on both sides."},
            {"phase": "middlegame", "text": "After Nxe4 the game swung hard; exd4 kept the balance."},
        ],
        "moments": [
            {"ply": 9, "text": "Nxe4 drops material — exd4 was the equalizer."},
            {"ply": 14, "text": "Qh5 was practically forced; the alternatives were far worse."},
        ],
        "overall": "Watch loose captures around move 5.",
    }


class TestCleanNarrative:
    def test_no_violations(self):
        assert check_narrative(PAYLOAD, _clean_narrative()) == []

    def test_pv_moves_are_allowed(self):
        n = _clean_narrative()
        n["moments"][0]["text"] = "The line exd4 Nxd4 Bc5 held everything together."
        assert check_narrative(PAYLOAD, n) == []

    def test_check_suffix_is_identity_neutral(self):
        n = _clean_narrative()
        n["moments"][0]["text"] = "Only exd4+ saved the position."  # payload has 'exd4'
        assert check_narrative(PAYLOAD, n) == []


class TestPlantedViolations:
    def test_unknown_san_is_caught(self):
        n = _clean_narrative()
        n["moments"][0]["text"] = "Better was Rxf7, winning on the spot."
        kinds = [v.kind for v in check_narrative(PAYLOAD, n)]
        assert "unknown_san" in kinds

    def test_invented_san_in_chapter_is_caught(self):
        n = _clean_narrative()
        n["chapters"][0]["text"] = "The plan with Bg5 never materialized."
        kinds = [v.kind for v in check_narrative(PAYLOAD, n)]
        assert "unknown_san" in kinds

    def test_unreached_phase_is_caught(self):
        n = _clean_narrative()
        n["chapters"].append({"phase": "endgame", "text": "A textbook conversion."})
        v = check_narrative(PAYLOAD, n)
        assert any(x.kind == "unreached_phase" and x.where == "chapter:endgame" for x in v)

    def test_absurd_move_number_is_caught(self):
        n = _clean_narrative()
        n["overall"] = "The collapse came at move 60."  # game has 7 move numbers
        kinds = [v.kind for v in check_narrative(PAYLOAD, n)]
        assert "bad_move_number" in kinds

    def test_second_best_named_on_narrow_choice(self):
        n = _clean_narrative()
        # 'Qh5' itself is known — but naming an alternative on a narrow_choice
        # moment is invention by construction (payload has no 2nd-best move).
        n["moments"][1]["text"] = "Better was Nf3, keeping everything defended."
        v = check_narrative(PAYLOAD, n)
        kinds = [x.kind for x in v]
        assert "second_best_named" in kinds
        assert "unknown_san" in kinds  # Nf3 is also simply not in the payload

    def test_foreign_ply_is_caught(self):
        n = _clean_narrative()
        n["moments"].append({"ply": 99, "text": "A quiet improvement."})
        assert any(v.where == "moment:99" for v in check_narrative(PAYLOAD, n))

    def test_motif_mismatch_is_caught(self):
        p = copy.deepcopy(PAYLOAD)
        p["moments"][0]["facts"]["category"] = "hanging"
        n = _clean_narrative()
        n["moments"][0]["text"] = "Nxe4 walked into a fork on f7."
        v = [x for x in check_narrative(p, n) if x.kind == "motif_mismatch"]
        assert len(v) == 1
        assert v[0].where == "moment:9"
        assert "fork" in v[0].detail

    def test_correct_motif_is_not_flagged(self):
        p = copy.deepcopy(PAYLOAD)
        p["moments"][0]["facts"]["category"] = "hanging"
        n = _clean_narrative()
        n["moments"][0]["text"] = "Nxe4 left the knight hanging; exd4 was safe."
        assert check_narrative(p, n) == []

    def test_threat_motif_field_supports_prose(self):
        p = copy.deepcopy(PAYLOAD)
        p["moments"][0]["facts"]["threat_motif"] = "back_rank"
        n = _clean_narrative()
        n["overall"] = "Watch the back-rank weakness around move 5."
        assert check_narrative(p, n) == []

    def test_generic_words_never_fire(self):
        # "attack", "pressure", "threat" are not motifs — no facts needed.
        n = _clean_narrative()
        n["overall"] = "The attack built pressure; every threat mattered."
        assert check_narrative(PAYLOAD, n) == []

    def test_metaphorical_motif_words_do_not_fire(self):
        # A motif word with no adjacent piece/square is ordinary English, not a
        # falsifiable tactical claim — it must never hard-fail. (PAYLOAD carries
        # no motif facts, so any fire here would be a false positive.)
        for prose in [
            "The position was hanging in the balance after this exchange.",
            "This move forks well with the earlier plan of central control.",
            "The evaluation kept hanging near equality for several moves.",
            "The players had a fork in the road: attack or consolidate.",
            "Black's pieces are pinned to passive squares by the structure.",
            "This skewers straight to the heart of the opening theory.",
            "He was pinning his hopes on a kingside initiative.",
            "The opponent was hanging around, stalling for time.",
        ]:
            n = _clean_narrative()
            n["overall"] = prose
            assert check_narrative(PAYLOAD, n) == [], prose

    def test_motif_with_object_still_fires_when_unsupported(self):
        # The tightening must not go so far it stops catching real claims: a
        # motif named next to a piece/square, with no supporting facts, fires.
        p = copy.deepcopy(PAYLOAD)
        p["moments"][0]["facts"]["category"] = "hanging"  # no 'pin' anywhere
        n = _clean_narrative()
        n["moments"][0]["text"] = "The bishop was pinned to the king on e8."
        v = [x for x in check_narrative(p, n) if x.kind == "motif_mismatch"]
        assert len(v) == 1 and "pin" in v[0].detail


# ---------------------------------------------------------------------------
# Golden payloads — the checker must run clean over real extracted facts
# when the narrative only repeats what the payload contains.
# ---------------------------------------------------------------------------

def _golden_files():
    return sorted(GOLDEN_DIR.glob("game_*.json"))


@pytest.mark.skipif(not GOLDEN_DIR.exists(), reason="golden set not built")
class TestGoldenSet:
    def test_golden_set_is_present_and_sanitized(self):
        files = _golden_files()
        assert len(files) >= 10
        for f in files:
            payload = json.loads(f.read_text())
            header = payload["header"]
            assert header["white"] in ("Me", "Opponent")
            assert header["black"] in ("Me", "Opponent")
            assert payload["moments"], f"{f.name} has no moments"

    def test_echo_narrative_is_clean_on_every_golden_payload(self):
        """A narrative built purely from payload facts must produce zero
        violations — the checker's false-positive guard over real data."""
        for f in _golden_files():
            payload = json.loads(f.read_text())
            phases = list((payload.get("eval_arc") or {}).keys())
            moments = payload["moments"][:3]
            narrative = {
                "chapters": [{"phase": p, "text": "Steady play from both sides."} for p in phases],
                "moments": [
                    {"ply": m["ply"], "text": f"{m['san']} changed the picture here."}
                    for m in moments if m.get("san")
                ],
                "overall": "Keep an eye on loose pieces.",
            }
            violations = check_narrative(payload, narrative)
            assert violations == [], f"{f.name}: {violations}"
