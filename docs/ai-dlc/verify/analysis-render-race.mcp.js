// Regression script for the analysis-render race ("engine calculates the wrong side").
//
// Sibling to undo-move-race.mcp.js. Same harness note: no headless JS runner exists —
// paste the body into an MCP `browser_run_code_unsafe`, or drive with Playwright whose
// `page` points at a running `uvicorn app.main:app --port 8001`.
//
//   PRE-FIX  → throws (a stale refreshAnalysis repaints the panel with the previous
//              position's eval/PV — every field changes after the move settles).
//   POST-FIX → returns { ok: true } (the panel is stable; the stale response drops).
//
// The race: onUserMove renders the analysis panel directly (applyMoveResponse), OUTSIDE
// the refreshAnalysis analysisToken machinery, and moves the cursor without bumping the
// token. So a refreshAnalysis still in flight from an earlier undo/redo passes its own
// token check and repaints THIS position's panel with the OLD position's (wrong-side)
// eval. Fix: onUserMove (and loadFen) bump analysisToken to invalidate it.
//
// Detection needs an OFF-BOOK line — book moves render a badge, not an eval, so the
// panel signal would be blank. h4/a5/h3 leaves book immediately.

export async function run(page, { base = 'http://localhost:8001/' } = {}) {
  const SQ = 60, X = 206, Y = 64.5;
  const center = (s) => ({ x: X + (s.charCodeAt(0) - 97 + 0.5) * SQ, y: Y + (8 - +s[1] + 0.5) * SQ });
  const drag = async (from, to) => {
    const a = center(from), b = center(to);
    await page.mouse.move(a.x, a.y); await page.mouse.down();
    await page.mouse.move(b.x, b.y, { steps: 8 }); await page.mouse.up();
  };
  const waitIdle = () => page.waitForFunction(() => {
    const s = document.getElementById('status'); return !s || !/Analyz/i.test(s.textContent);
  }, { timeout: 15000 });
  const bundle = () => page.evaluate(() => {
    const g = (id) => ((document.getElementById(id) || {}).textContent || '').replace(/\s+/g, ' ').trim();
    return { eval: g('eval'), best: g('best-move'), pv: g('pv').slice(0, 40),
             second: g('best-second'), retroBest: g('retro-best'), retroPv: g('retro-pv').slice(0, 40) };
  });
  const assert = (cond, msg) => { if (!cond) throw new Error('REGRESSION: ' + msg); };

  await page.goto(base);
  await page.evaluate(() => localStorage.clear());
  await page.reload(); await page.waitForTimeout(400);

  // 1) Off-book line so every ply yields a real engine eval. cursor 4, White to move.
  for (const [f, t] of [['h2','h4'], ['a7','a5'], ['h1','h3'], ['a5','a4']]) { await drag(f, t); await waitIdle(); }

  // 2) Delay ONLY refreshAnalysis's /api/move (its body has no "analyze" field).
  await page.evaluate(() => {
    const o = window.fetch; window.__o = o;
    window.fetch = (u, x) => (typeof u === 'string' && u.includes('/api/move') && x && x.body && !x.body.includes('"analyze"'))
      ? new Promise((r) => setTimeout(() => r(o(u, x)), 2600)) : o(u, x);
  });

  // 3) undo (fires the slow refreshAnalysis for the Black-to-move h3 position), then
  //    immediately play a move so onUserMove renders the new position's analysis first.
  await page.keyboard.press('ArrowLeft');   // cursor 4 -> 3
  await page.waitForTimeout(120);
  await drag('b8', 'c6');                    // Nc6 -> cursor 4 (White to move)

  await page.waitForTimeout(1800); const afterMove = await bundle();   // settled move analysis
  await page.waitForTimeout(2600); const afterStale = await bundle();  // stale refreshAnalysis has now landed

  await page.evaluate(() => { if (window.__o) { window.fetch = window.__o; delete window.__o; } });

  const changed = Object.keys(afterMove).filter((k) => afterMove[k] !== afterStale[k]);
  assert(changed.length === 0,
    `analysis panel clobbered by stale refreshAnalysis — fields changed: ${changed.join(', ')} ` +
    `(before=${JSON.stringify(afterMove)} after=${JSON.stringify(afterStale)})`);

  await page.evaluate(() => {
    const b = document.getElementById('reset') || document.querySelector('[data-action="reset"]');
    if (b) b.click(); localStorage.clear();
  });
  return { ok: true };
}
