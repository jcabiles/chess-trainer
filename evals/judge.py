"""LLM-as-judge eval run over the golden set — on-demand, never CI-blocking.

For every payload in ``evals/golden/``:
1. generate commentary with the production path (``app.narrative.generate`` —
   same prompt, model, and validation the app uses),
2. run the deterministic grounding checks (hard fails),
3. score the text with an LLM judge on a 3-axis rubric (soft scores),
then write ``evals/results/run-<model>.json`` and print a markdown summary
row per game (paste into docs/analytics/EVALS.md).

Requires ANTHROPIC_API_KEY (also enables step 1). Cost: one generation + one
judge call per golden game — ~20 calls per run, comfortably under the $5/run
ceiling in the roadmap no-gos.

Human-agreement mode: put your own 1-5 ratings in ``evals/human_ratings.json``
as ``{"game_0003": {"insight": 4, "clarity": 5, "faithfulness": 5}, ...}`` —
the run report then includes judge-vs-human mean absolute difference and
within-1 agreement per axis, which is the honest way to decide how far to
trust the judge (see EVALS.md).

Usage:
    GAMES_DB=data/games.db ANTHROPIC_API_KEY=... \
        python -m evals.judge [--model claude-sonnet-5] [--judge-model claude-haiku-4-5]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from app import narrative
from evals.grounding import check_narrative

GOLDEN_DIR = Path(__file__).parent / "golden"
RESULTS_DIR = Path(__file__).parent / "results"
RATINGS_FILE = Path(__file__).parent / "human_ratings.json"

JUDGE_SYSTEM = (
    "You are grading chess game commentary written by another model. The\n"
    "commentary was REQUIRED to use only the facts in the provided payload.\n"
    "Grade three axes, each 1-5 (5 best):\n"
    "- faithfulness: does every concrete claim trace to the payload? Penalize\n"
    "  invented moves/plans/evals hard, even plausible ones.\n"
    "- insight: does it explain WHY moments mattered (threats, swings,\n"
    "  patterns), or just restate eval numbers?\n"
    "- clarity: is it readable club-player coaching prose (short paragraphs,\n"
    "  concrete language, no filler)?\n"
    'Reply with STRICT JSON only: {"faithfulness": n, "insight": n,\n'
    '"clarity": n, "justification": "<one sentence per axis>"}'
)


async def _judge_one(client, judge_model: str, payload: dict, parsed: dict) -> dict:
    user = (
        "PAYLOAD (ground truth facts):\n" + json.dumps(payload) +
        "\n\nCOMMENTARY TO GRADE:\n" + json.dumps(parsed) +
        "\n\nReply with the strict JSON grade now."
    )
    resp = await client.messages.create(
        model=judge_model,
        max_tokens=300,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return json.loads(narrative._strip_fences(text))


async def run(gen_model: str | None, judge_model: str) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is required for a judge run.")
    if gen_model:
        os.environ["NARRATIVE_MODEL"] = gen_model

    import anthropic  # deferred so offline tooling can import this module
    client = anthropic.AsyncAnthropic()

    ratings = {}
    if RATINGS_FILE.exists():
        ratings = json.loads(RATINGS_FILE.read_text())

    results = []
    for f in sorted(GOLDEN_DIR.glob("game_*.json")):
        payload = json.loads(f.read_text())
        name = f.stem
        try:
            parsed = await narrative.generate(payload)
        except Exception as exc:
            results.append({"game": name, "error": f"generation failed: {exc}"})
            continue
        violations = [asdict(v) for v in check_narrative(payload, parsed)]
        try:
            grades = await _judge_one(client, judge_model, payload, parsed)
        except Exception as exc:
            grades = {"error": f"judge failed: {exc}"}
        results.append({
            "game": name,
            "grounding_violations": violations,
            "grades": grades,
            "human": ratings.get(name),
            "narrative": parsed,
        })
        v = len(violations)
        print(f"{name}: violations={v} grades={ {k: grades.get(k) for k in ('faithfulness','insight','clarity')} }")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"run-{(gen_model or os.environ.get('NARRATIVE_MODEL', 'default')).replace('/', '_')}.json"
    out.write_text(json.dumps(results, indent=1) + "\n")
    print(f"\nwrote {out}")

    _print_summary(results)


def _print_summary(results: list[dict]) -> None:
    print("\n| game | grounding violations | faithfulness | insight | clarity |")
    print("|---|---|---|---|---|")
    for r in results:
        if "error" in r:
            print(f"| {r['game']} | — | {r['error']} | | |")
            continue
        g = r.get("grades") or {}
        print(f"| {r['game']} | {len(r['grounding_violations'])} "
              f"| {g.get('faithfulness', '?')} | {g.get('insight', '?')} | {g.get('clarity', '?')} |")

    rated = [r for r in results if r.get("human") and r.get("grades") and "error" not in (r.get("grades") or {})]
    if rated:
        print("\nJudge vs human (n=%d):" % len(rated))
        for axis in ("faithfulness", "insight", "clarity"):
            pairs = [(r["grades"].get(axis), r["human"].get(axis)) for r in rated
                     if isinstance(r["grades"].get(axis), int) and isinstance(r["human"].get(axis), int)]
            if not pairs:
                continue
            mad = sum(abs(a - b) for a, b in pairs) / len(pairs)
            within1 = sum(abs(a - b) <= 1 for a, b in pairs) / len(pairs)
            print(f"  {axis}: mean |Δ|={mad:.2f}, within-1 agreement={within1:.0%}")
    else:
        print("\nNo human ratings found (evals/human_ratings.json) — judge "
              "agreement unreported. Rate a few runs before trusting the judge.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="generation model override")
    ap.add_argument("--judge-model", default="claude-haiku-4-5-20251001",
                    help="judge model (cheap by default; a weak judge is fine for grounding, "
                         "check agreement before trusting insight/clarity scores)")
    args = ap.parse_args()
    asyncio.run(run(args.model, args.judge_model))
