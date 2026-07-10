// Regression script for the undo/turn corruption race (spec: docs/ai-dlc/specs/undo-move-race.md).
//
// This repo has NO headless JS test harness (the suite is pytest; UI is verified via
// Playwright-MCP on a live server). So this is a re-runnable Playwright snippet, not CI:
// paste its body into an MCP `browser_run_code_unsafe` call, or drive it with a plain
// Playwright script whose `page` points at a running `uvicorn app.main:app --port 8001`.
//
//   PRE-FIX  → throws (move list corrupts to "1. e4 e5 2. Nf3 Bc4", Nc6 dropped).
//   POST-FIX → returns { ok: true } (Nc6 preserved, stale Bc4 dropped, turn intact).
//
// The race it reproduces: onUserMove awaits /api/move (Stockfish, ~1-2s), then writes
// history; undo/redo/mode-switch mutate the cursor during that await. The fix captures
// the cursor + a moveToken at drag time and drops any stale response.

export async function run(page, { base = 'http://localhost:8001/' } = {}) {
  const SQ = 60, X = 206, Y = 64.5; // board geometry at the default 480px size (white orientation)
  const center = (s) => ({ x: X + (s.charCodeAt(0) - 97 + 0.5) * SQ, y: Y + (8 - +s[1] + 0.5) * SQ });
  const drag = async (from, to) => {
    const a = center(from), b = center(to);
    await page.mouse.move(a.x, a.y); await page.mouse.down();
    await page.mouse.move(b.x, b.y, { steps: 8 }); await page.mouse.up();
  };
  const listText = () => page.evaluate(() =>
    (document.getElementById('move-list') || {}).innerText?.replace(/\s+/g, ' ').trim() || '');
  const waitList = (exp) => page.waitForFunction((e) =>
    ((document.getElementById('move-list') || {}).innerText || '').replace(/\s+/g, ' ').trim() === e,
    exp, { timeout: 15000 });
  const assert = (cond, msg) => { if (!cond) throw new Error('REGRESSION: ' + msg); };

  await page.goto(base);
  await page.evaluate(() => localStorage.clear());
  await page.reload(); await page.waitForTimeout(400);

  // 1) Build the line e4 e5 Nf3 Nc6 (cursor=4, White to move).
  await drag('e2', 'e4'); await waitList('1. e4');
  await drag('e7', 'e5'); await waitList('1. e4 e5');
  await drag('g1', 'f3'); await waitList('1. e4 e5 2. Nf3');
  await drag('b8', 'c6'); await waitList('1. e4 e5 2. Nf3 Nc6');

  // 2) THE RACE: delay /api/move, drag a White bishop move, undo before it resolves.
  await page.evaluate(() => {
    const o = window.fetch; window.__o = o;
    window.fetch = (u, x) => (typeof u === 'string' && u.includes('/api/move'))
      ? new Promise((r) => setTimeout(() => r(o(u, x)), 2500)) : o(u, x);
  });
  await drag('f1', 'c4');            // Bc4 — fires onUserMove, awaits the delayed /api/move
  await page.waitForTimeout(150);
  await page.keyboard.press('ArrowLeft'); // undo mid-analysis -> cursor 3 (Black to move)
  await page.waitForTimeout(3200);        // let the delayed response land
  await page.evaluate(() => { if (window.__o) { window.fetch = window.__o; delete window.__o; } });

  const afterRace = await listText();
  assert(afterRace === '1. e4 e5 2. Nf3 Nc6',
    `history corrupted by stale move response: got "${afterRace}" (expected Nc6 intact, Bc4 dropped)`);

  // 3) TURN INTEGRITY at cursor 3 (Black to move): a White move must be rejected,
  //    a Black move must commit. This is what "forgets whose turn it is" would break.
  await drag('d2', 'd4'); await page.waitForTimeout(600);
  assert((await listText()) === '1. e4 e5 2. Nf3 Nc6', 'White move accepted at Black\'s turn (turn parity flipped)');
  await drag('d7', 'd5'); await page.waitForTimeout(900);
  assert((await listText()) === '1. e4 e5 2. Nf3 d5', 'Black move did not commit at cursor 3');

  // Leave the session clean.
  await page.evaluate(() => {
    const b = document.getElementById('reset') || document.querySelector('[data-action="reset"]');
    if (b) b.click(); localStorage.clear();
  });
  return { ok: true };
}
