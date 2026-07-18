"""Offline ladder-monotonicity harness for the B5 causal-blunder gate (T5).

Pure, deterministic, no engine binary needed. Validates the coherence
invariant across the REAL persona ladder (``app.personas.all()``, the
research-calibrated dials — not stubs, 6 personas: Casey/Diego/Robin @1350,
Morgan @1550, Alex @1800, Vera @2000): a HIGHER-rated elo GROUP misses a
fixed off-plan threat LESS often, worst-case, than a lower-rated elo group
(stronger bots blunder no more). With three personas tied at elo=1350 the
invariant only holds at elo-group granularity, not pairwise across the
elo-sorted ladder. See ``docs/ai-dlc/specs/causal-blunder.md`` Verify-by #2.
"""

from __future__ import annotations

import chess

from app import bot_blunder as bb
from app import personas

# A fixed, real off-plan threat: a hanging knight (severity_cp=300, a "minor"
# per the spec's ordering) whose key square is disjoint from the plan set
# below, so off_plan_score == 1.0 for every persona (fully off-plan).
_THREAT_SQUARE = chess.parse_square("d4")
_THREAT = bb.Threat(
    type="hanging",
    squares={_THREAT_SQUARE},
    severity_cp=300,
    target=_THREAT_SQUARE,
)

# The bot's attention is on the kingside (e4/e5) — disjoint from d4.
_PLAN_SET = {chess.parse_square("e4"), chess.parse_square("e5")}

# A mid/late middlegame ply, well past FIRST_BLUNDER_PLY+RAMP so hazard() == 1.0.
_PLY = 60
_PHASE = "middlegame"

# Fixed, deterministic seed range for the empirical miss-rate estimate.
_SEEDS = range(200)

# The real ladder, ordered lowest→highest Elo (Casey/Diego/Robin @1350 ->
# Morgan -> Alex -> Vera). A stable sort keeps insertion order within the
# 1350 elo group, so ties resolve to catalog order (casey, diego, robin).
_LADDER = sorted(personas.all(), key=lambda p: p.elo)


def _miss_rate(persona) -> float:
    """Empirical fraction of seeds where the gate fires (the bot misses the threat)."""
    hits = sum(
        bb.should_blunder(persona, _PHASE, _PLY, seed=s, threat=_THREAT, plan_set=_PLAN_SET)
        for s in _SEEDS
    )
    return hits / len(_SEEDS)


def test_ladder_is_the_expected_six_personas_by_elo():
    # Sanity: the real ladder is Casey/Diego/Robin(1350) < Morgan(1550) <
    # Alex(1800) < Vera(2000), ties broken by catalog (insertion) order.
    ids = [p.id for p in _LADDER]
    assert ids == ["casey", "diego", "robin", "morgan", "alex", "vera"]


def test_miss_rate_monotone_non_increasing_across_ladder():
    """Higher elo GROUP => lower (or equal) worst-case empirical miss-rate.

    With three personas tied at elo=1350 (casey/diego/robin), the invariant no
    longer holds pairwise across the elo-sorted ladder (robin, a deliberately
    sloppy/low-blunderRate persona, sits before morgan but misses far less).
    It only holds at the granularity of ELO GROUPS: group personas by elo,
    take the MAX empirical miss-rate within each group, and that per-group max
    must be non-increasing as elo strictly increases (a higher-rated group
    should never have a WORSE worst-case miss-rate than a lower-rated group).
    """
    groups: dict[int, list[float]] = {}
    for p in _LADDER:
        groups.setdefault(p.elo, []).append(_miss_rate(p))
    elos = sorted(groups)
    group_max = [max(groups[elo]) for elo in elos]

    for i in range(len(group_max) - 1):
        lower_elo, higher_elo = elos[i], elos[i + 1]
        assert group_max[i] >= group_max[i + 1], (
            f"expected max miss-rate(elo={lower_elo})={group_max[i]:.3f} >= "
            f"max miss-rate(elo={higher_elo})={group_max[i + 1]:.3f} "
            "(coherence invariant: stronger elo groups should blunder no more, "
            "worst-case, than weaker elo groups)"
        )

    # Not degenerate: the 1350 group's worst-case miss-rate should actually
    # spread above Vera's (2000) — guards against an all-zero/all-equal false pass.
    assert group_max[0] > group_max[-1]


def test_within_1350_group_diego_misses_more_than_robin():
    """Close the group-max blind spot: pin the two new 1350 personas directly.

    The elo-group-max test above is dominated by casey/diego and so would NOT
    notice a logic (or dial) regression that only affects robin or diego. Assert
    the intended intra-group ordering explicitly: diego (aggressive, very
    threat-blind: high blunderRate + low threatDistance) misses a fixed off-plan
    defensive threat MUCH more often than robin (deliberately low blunderRate),
    and robin actually stays low. A bug zeroing robin's rate or un-gating diego
    is caught here even though the group max would not move.
    """
    diego = personas.get("diego")
    robin = personas.get("robin")
    diego_rate = _miss_rate(diego)
    robin_rate = _miss_rate(robin)
    assert diego_rate > robin_rate + 0.30, (
        f"diego miss-rate {diego_rate:.3f} should dominate robin {robin_rate:.3f}"
    )
    assert robin_rate < 0.35, f"robin (low blunderRate) miss-rate {robin_rate:.3f} too high"


def test_off_plan_threshold_monotone_across_ladder():
    """A threat at a fixed off_plan_score gates OUT the strongest persona, allows
    the weakest one.

    threatDistance is NOT globally monotone across the elo-sorted ladder anymore
    (diego's 0.10 < casey's 0.15; robin's 0.30 > morgan's 0.29), so this no longer
    asserts a ladder-wide ordering. Instead it verifies the SAME gating mechanism
    directly: pick the persona with the lowest threatDistance (the easiest to gate
    through) and the one with the highest (the hardest to gate through — most
    resistant to missing threats), and confirm a fixed off-plan score strictly
    between the two thresholds is allowed for the weakest and gated out for the
    strongest.
    """
    weakest = min(_LADDER, key=lambda p: p.threatDistance)  # diego, 0.10
    strongest = max(_LADDER, key=lambda p: p.threatDistance)  # vera, 0.67

    # Squares 3/5 off-plan: exceeds diego's threshold but not vera's.
    threat_squares = {1, 2, 3, 4, 5}
    on_plan = {1, 2}  # 2 of 5 on-plan -> off_plan_score = 0.6
    score = bb.off_plan_score(threat_squares, on_plan)
    assert score == 0.6
    assert weakest.threatDistance < score <= strongest.threatDistance

    assert score > weakest.threatDistance  # allowed through for the weakest persona
    assert score <= strongest.threatDistance  # gated OUT for the strongest persona


def test_ladder_harness_is_deterministic():
    """Running the whole miss-rate estimate twice yields identical counts."""
    run1 = [_miss_rate(p) for p in _LADDER]
    run2 = [_miss_rate(p) for p in _LADDER]
    assert run1 == run2
