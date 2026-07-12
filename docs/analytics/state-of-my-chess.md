# State of my chess — 2026-07-12

An analytical read of my own game database: what the data says, what it
doesn't, and what to train next. Metric definitions live in the
[KPI tree](kpi-tree.md); every number below traces to a numbered SQL query in
the [appendix](#appendix--queries) and reproduces against `data/games.db`
read-only. Aggregates only — no game dumps.

**Dataset**: 150 games (74 as White, 76 as Black), all analyzed and
color-tagged, played 2026-06-17 → 2026-07-07 (Q1). Engine: Stockfish at
review depth 10. One honest gap up front: **zero games carry clock data**
(pasted PGNs lack `%clk`), so the time-management branch of the KPI tree is
unmeasurable in this report (Q13).

## Headline

Overall results are healthy — **55% wins as both colors** (82/150, Q2) — but
the *way* games are won and lost is lopsided: **one blunder cuts my win rate
in half** (71.8% in blunder-free games vs 36.1% otherwise, Q9), and **73% of
all my leaks are a single pattern: hanging material** (Q7). The data says I
don't lose to better plans; I lose pieces.

## Findings

**1. Hanging material is the leak, not a leak.**
Of 328 recorded mistakes/blunders across all my analyzed games, **240 (73%)
are `hanging`-category** — material left en prise or captured for
insufficient compensation. The next category (`missed_threat`, 36) is seven
times rarer (Q7). Any training minute not aimed at board-vision/capture
awareness is optimizing a rounding error.

**2. Blunders decide games — mine, specifically.**
I blundered (≥20-point win-probability drop) in 72 of 150 games. Win rate:
**71.8% when I don't, 36.1% when I do** (Q9). At 3.6 blunders per 100 moves
(137 blunders / 3,783 user moves, Q3), removing even a third of them is worth
far more than any opening novelty.

**3. The opening phase leaks more than it should for a prepared player.**
134 of 328 leaks (41%) happen in the opening phase — 52 of them full blunders
(Q3). The blunder table's top entries are all **opponent-chosen sidelines and
systems, not lines I prepared**: Closed Sicilian/Anti-Sveshnikov (14 blunders
in 7 games), Scotch/Benima (8 in 2), Coles Gambit (7 in 3), Colle (7 in 2),
London (7 in 2), Kalashnikov (5 in 2) (Q6) — 48 blunders in 18 games across
six lines, split between anti-Sicilian sidelines and 1.d4/1.e4 systems my
opponents steer into. My prepared trunk lines (Italian, Open Sicilian
mainlines) barely appear. The problem is *opponent deviation handling*, not
the repertoire itself.

**4. Colors are symmetric; there is no "weak color" story.**
41 wins each side; 173 leaks as Black vs 155 as White (Q2, Q10) —
a gap of ~11%, roughly proportional to games played and well inside noise at
this sample. Training split by color would be effort misallocated.

**5. Only ~19% of my blunders were foreseeable warnings I ignored.**
Using the strict two-plies-early rule, 63 of 328 leaks (19.2%) had the threat
on the board well before the mistake (Q4); hope-chess games (≥1 missed
threat) are 18% of the total (Q5). Read together with Finding 1: my typical
failure is not ignoring a developing threat — it's *creating* the loss in one
move. That points at move-time blunder-checking habits ("is anything hanging
after this move?") over deep threat-detection drills.

**6. The trend is promising but statistically thin.**
June: ~0.97 my-blunders/game over 135 games. July so far: 0.40 over 15 games
(Q12). Encouraging — the blunder trainer went live in this window — but 15
games is below any reasonable inference bar; logged here as a hypothesis for
the parked training-effectiveness analysis, not a claim.

## Recommendations (ranked)

1. **Adopt a pre-move hang-check ritual** (Finding 1, 2, 5): before releasing
   any move, scan checks/captures on the destination square. Cheapest
   possible intervention aimed at 73% of the leak mass.
2. **Drill the `hanging` bucket in the blunder trainer weekly** — it re-serves
   exactly these positions with Leitner spacing; the bucket is by far the
   deepest (Q7).
3. **Prepare anti-sideline files** for the six lines in Q6 — the
   anti-Sicilians (Anti-Sveshnikov, Coles Gambit, Kalashnikov) *and* the
   system openings (Scotch/Benima, Colle, London). 48 blunders in 18 games
   is the most concentrated fixable cluster in the database; the Scotch and
   London/Colle entries rank as high as the Sicilian ones and deserve equal
   prep time.
4. **Fetch clocked games** (auto-fetch ships with this roadmap): until
   `clock_centis` populates, the time-trouble branch of the KPI tree is
   blind — and blitz time-pressure is a plausible hidden confounder behind
   Finding 1.
5. **Re-run this report at ~200 games** and check: blunders/game trend (Q12)
   with a real July sample, and whether the hanging share moves after a month
   of recommendation 1+2.

## What this report deliberately does not claim

- No per-variation win rates (samples of 1–3 games are noise — min-sample 5
  everywhere, per the KPI tree's gating rule).
- No accuracy/Elo aggregation across games (anti-vanity rule; single-game
  estimates don't average meaningfully).
- No causal claim about the blunder trainer (Finding 6 is a hypothesis; the
  interrupted-time-series analysis is parked in the roadmap's Later column).
- Depth-10 evals: a deeper pass would re-label some borderline mistakes;
  directionally stable, individually fuzzy.

## Appendix — queries

All read-only against `data/games.db` (`sqlite3 data/games.db`). "My" rows
join `leaks.color = games.my_color`; analyzed = `analysis_status='done'`.

```sql
-- Q1 dataset overview
SELECT COUNT(*), SUM(analysis_status='done'), SUM(my_color IS NOT NULL),
       MIN(date), MAX(date) FROM games;

-- Q2 results by my color
SELECT my_color, COUNT(*),
       SUM((my_color='white' AND result='1-0') OR (my_color='black' AND result='0-1')) AS wins,
       SUM(result='1/2-1/2') AS draws
FROM games WHERE my_color IS NOT NULL AND analysis_status='done'
GROUP BY my_color;

-- Q3 my leaks by severity × phase; user-move denominator
SELECT l.severity, l.phase, COUNT(*)
FROM leaks l JOIN games g ON l.game_id=g.id
WHERE l.color=g.my_color AND g.analysis_status='done'
GROUP BY l.severity, l.phase;
SELECT COUNT(*) FROM game_plies p JOIN games g ON p.game_id=g.id
WHERE p.is_user_move=1 AND g.analysis_status='done';

-- Q4 foreseeable (strict two-plies-early rule; see KPI tree caveat)
SELECT SUM(l.lead_in_ply < l.ply - 1), COUNT(*)
FROM leaks l JOIN games g ON l.game_id=g.id
WHERE l.color=g.my_color AND g.analysis_status='done';

-- Q5 hope-chess games (exact category match — mirrors profile._hope_chess_rate)
SELECT COUNT(DISTINCT l.game_id)
FROM leaks l JOIN games g ON l.game_id=g.id
WHERE l.color=g.my_color AND l.category = 'missed_threat';

-- Q6 blunder hotspots by opening
SELECT g.opening, COUNT(*) AS my_blunders, COUNT(DISTINCT g.id) AS games
FROM leaks l JOIN games g ON l.game_id=g.id
WHERE l.color=g.my_color AND l.severity='blunder'
GROUP BY g.opening ORDER BY my_blunders DESC LIMIT 8;

-- Q7 leak categories
SELECT l.category, COUNT(*) FROM leaks l JOIN games g ON l.game_id=g.id
WHERE l.color=g.my_color GROUP BY l.category ORDER BY COUNT(*) DESC;

-- Q9 win rate: blunder-free vs blundered games
WITH blundered AS (
  SELECT DISTINCT l.game_id FROM leaks l JOIN games g ON l.game_id=g.id
  WHERE l.color=g.my_color AND l.severity='blunder')
SELECT (g.id IN (SELECT game_id FROM blundered)) AS i_blundered, COUNT(*),
       ROUND(1.0*SUM((g.my_color='white' AND g.result='1-0')
                  OR (g.my_color='black' AND g.result='0-1'))/COUNT(*),3)
FROM games g WHERE g.analysis_status='done' GROUP BY i_blundered;

-- Q10 leaks per color
SELECT g.my_color, COUNT(*), SUM(l.severity='blunder')
FROM leaks l JOIN games g ON l.game_id=g.id
WHERE l.color=g.my_color GROUP BY g.my_color;

-- Q12 monthly trend
SELECT substr(g.date,1,7), COUNT(DISTINCT g.id), SUM(l.severity='blunder')
FROM games g LEFT JOIN leaks l ON l.game_id=g.id AND l.color=g.my_color
WHERE g.analysis_status='done' GROUP BY 1;

-- Q13 clock coverage (the honest gap)
SELECT COUNT(*), SUM(clock_centis IS NOT NULL) FROM game_plies;
```
