// trainer.js — blunder trainer (Train section + blunder-practice drill mode).
// Receives the injected `api` from app.js at init and never imports app.js
// back (one-directional: hub → feature → leaf).
//
// Two features off the trainer API:
//   * Train section (Review tab) — idempotent preview of due buckets + box
//     levels (GET /api/trainer/session — safe on every render) and a Start
//     button.
//   * blunder-practice — Start POSTs /api/trainer/session/start (exactly once
//     per click — every call burns rotation), then drills the returned
//     puzzles: board at fen_before oriented to your color, your move is
//     verdict-checked server-side (POST /api/trainer/check), failed gets ONE
//     retry, a second fail auto-reveals with narration.
//
// Drill state machine (drill.phase):
//   'moving'    — board armed, waiting for your move (attempts 0 or 1).
//   'checking'  — /check in flight, board frozen (checkToken guards staleness).
//   'solved'    — Correct! feedback + next-up teaser showing; Next button
//                 advances (Reveal hidden). No auto-advance.
//   'advancing' — vanished-puzzle (404) skip notice showing, auto-next
//                 after a beat.
//   'revealed'  — best move + narration showing; Next button advances.
//   'summary'   — session complete; bucket outcomes flushed; Return exits.
//
// Outcome accounting (bucket-complete): ONE final outcome per puzzle — the
// puzzle's LAST resolution wins, so failed-then-solved-on-retry counts as the
// retry's verdict (solved/solved_alt), and a second fail or a Reveal press
// counts as 'revealed'/'failed' per how it ended. Reveals are counted ONLY in
// this client-side outcomes list (never POSTed to /check — the server records
// real attempts only).
//
// Owns: `drill` (active session), `trainerSnapshot` (in-memory only — never
// persisted), and `checkToken` (guards stale async check/advance across
// Return-mid-check, mirroring repertoire.js's repEngineToken).

import { INITIAL_FEN } from 'https://esm.sh/chessops@0.14.2/fen';
import { chessgroundDests } from 'https://esm.sh/chessops@0.14.2/compat';
import { parseUci } from 'https://esm.sh/chessops@0.14.2/util';

let _api = null;
let drill = null;            // active drill session (see startSession)
let trainerSnapshot = null;  // saved play game captured when entering the drill
let checkToken = 0;          // guards stale async check replies / timers

const ADVANCE_DELAY_MS = 900; // beat between a solve and the next puzzle

const byId = (id) => document.getElementById(id);
const state = () => _api.actions.getState();
const ground = () => _api.actions.getGround();

// 'knight_fork' → 'Knight fork' (display name for a motif bucket key).
function bucketLabel(motif) {
  const s = String(motif || '').replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ---------------------------------------------------------------------------
// Train section (Review tab) — idempotent preview render
// ---------------------------------------------------------------------------

async function refreshTrainSection() {
  const host = byId('trainer-section');
  if (!host) return;
  let buckets = null;
  try {
    const res = await fetch('/api/trainer/session'); // idempotent preview
    const data = await res.json();
    buckets = (data && data.buckets) || [];
  } catch (_) {
    buckets = null; // degraded — show a quiet error state, no crash
  }
  host.replaceChildren();

  const hdr = document.createElement('div');
  hdr.className = 'trainer-section-hdr';
  const title = document.createElement('span');
  title.className = 'trainer-section-title';
  title.textContent = 'Train';
  hdr.appendChild(title);

  const start = document.createElement('button');
  start.id = 'trainer-start';
  start.className = 'trainer-start';
  start.textContent = 'Start training';
  start.addEventListener('click', startSession);
  hdr.appendChild(start);
  host.appendChild(hdr);

  if (buckets === null) {
    start.disabled = true;
    host.appendChild(emptyState('Trainer unavailable — is the server running?'));
    return;
  }
  if (!buckets.length) {
    start.disabled = true;
    host.appendChild(emptyState(
      'No trainable blunders yet. Import games, tag your color, and analyze them — your mistakes become puzzles here.'
    ));
    return;
  }

  const dueCount = buckets.filter((b) => b.due).length;
  start.disabled = dueCount === 0;
  start.title = dueCount
    ? `Serve today's puzzles (${dueCount} bucket${dueCount === 1 ? '' : 's'} due)`
    : 'Nothing due today — come back tomorrow';

  const list = document.createElement('div');
  list.className = 'trainer-buckets';
  for (const b of buckets) {
    const row = document.createElement('div');
    row.className = 'trainer-bucket-row' + (b.due ? ' is-due' : '');

    const name = document.createElement('span');
    name.className = 'trainer-bucket-name';
    name.textContent = bucketLabel(b.motif);
    row.appendChild(name);

    const box = document.createElement('span');
    box.className = 'trainer-bucket-box';
    box.textContent = `Box ${b.box}/5`;
    row.appendChild(box);

    const pool = document.createElement('span');
    pool.className = 'trainer-bucket-pool';
    pool.textContent = `${b.pool_size} puzzle${b.pool_size === 1 ? '' : 's'}`;
    row.appendChild(pool);

    const due = document.createElement('span');
    due.className = 'trainer-bucket-due';
    due.textContent = b.due ? 'Due' : (b.last_reviewed ? `Reviewed ${b.last_reviewed}` : '');
    row.appendChild(due);

    list.appendChild(row);
  }
  host.appendChild(list);
}

function emptyState(text) {
  const el = document.createElement('div');
  el.className = 'trainer-empty';
  el.textContent = text;
  return el;
}

// ---------------------------------------------------------------------------
// Drill bar helpers
// ---------------------------------------------------------------------------

function setMoveHint(msg) { byId('trainer-move').textContent = msg || ''; }
function setNote(msg) { byId('trainer-note').textContent = msg || ''; }

function setFeedback(msg, kind) {
  const el = byId('trainer-feedback');
  el.hidden = !msg;
  el.textContent = msg || '';
  el.classList.remove('feedback-good', 'feedback-bad');
  if (kind === 'good') el.classList.add('feedback-good');
  else if (kind === 'bad') el.classList.add('feedback-bad');
}

// Narration dict from the server: { threat, hanging, plan, summary }.
function setNarration(narration) {
  const el = byId('trainer-narration');
  el.replaceChildren();
  const lines = [];
  if (narration) {
    for (const key of ['threat', 'hanging', 'plan', 'summary']) {
      if (narration[key]) lines.push(narration[key]);
    }
  }
  el.hidden = !lines.length;
  for (const line of lines) {
    const p = document.createElement('p');
    p.textContent = line;
    el.appendChild(p);
  }
}

function showNextButton(on) { byId('trainer-next').hidden = !on; }
function showRevealButton(on) { byId('trainer-reveal').hidden = !on; }

function showTrainerUI(on) {
  byId('trainer-bar').hidden = !on;
  document.body.classList.toggle('trainer-mode', on);
  if (on) byId('trap-chip').hidden = true;
}

// ---------------------------------------------------------------------------
// Board rendering
// ---------------------------------------------------------------------------

// Arm the board for YOUR move at the current puzzle position.
function trainerArmBoard() {
  const { hub } = _api;
  const pos = drill.board;
  ground().set({
    fen: hub.fenOf(pos).split(' ')[0],
    turnColor: pos.turn,
    orientation: drill.orientation,
    lastMove: undefined,
    movable: { free: false, color: pos.turn, dests: chessgroundDests(pos) },
    draggable: { enabled: true, deleteOnDropOff: false },
  });
}

function trainerFreeze() {
  ground().set({
    movable: { free: false, color: undefined, dests: undefined },
    draggable: { enabled: false },
  });
}

// Render the position after a played UCI (frozen), highlighting the move.
function trainerShowMove(uci) {
  const { hub } = _api;
  ground().set({
    fen: hub.fenOf(drill.board).split(' ')[0],
    turnColor: drill.board.turn,
    orientation: drill.orientation,
    lastMove: hub.lastMoveSquares(uci),
    movable: { free: false, color: undefined, dests: undefined },
    draggable: { enabled: false },
  });
}

// Draw attention to the threat the blunder allowed: a red arrow for
// threat_uci and/or a red circle on the hanging square (chessground
// autoShapes — cleared on every new puzzle / exit).
function showThreatShapes(puzzle) {
  const shapes = [];
  if (puzzle.threat_uci && puzzle.threat_uci.length >= 4) {
    shapes.push({
      orig: puzzle.threat_uci.slice(0, 2),
      dest: puzzle.threat_uci.slice(2, 4),
      brush: 'red',
    });
  }
  if (puzzle.hung_square) {
    shapes.push({ orig: puzzle.hung_square, brush: 'red' });
  }
  ground().set({ drawable: { autoShapes: shapes } });
}

function clearShapes() {
  ground().set({ drawable: { autoShapes: [] } });
}

// ---------------------------------------------------------------------------
// Drill flow
// ---------------------------------------------------------------------------

// Start button → serve a session. POSTs the MUTATING start endpoint exactly
// once per click (each call advances the server-side rotation cursors).
async function startSession() {
  const { hub } = _api;
  if (state().mode === 'blunder-practice') return;
  const btn = byId('trainer-start');
  if (btn) btn.disabled = true;

  let data;
  try {
    data = await hub.postJSON('/api/trainer/session/start', {});
  } catch (_) {
    if (btn) btn.disabled = false;
    _api.emit('toast:show', 'Could not start a session — server unreachable.');
    return;
  }

  const puzzles = (data && data.puzzles) || [];
  if (!puzzles.length) {
    if (btn) btn.disabled = false;
    _api.emit('toast:show', 'Nothing due right now.');
    refreshTrainSection();
    return;
  }

  // Review mode has no registered exit handler (ensurePlay no-ops there), so
  // leave it explicitly before snapshotting — otherwise we'd snapshot the
  // reviewed game as "your game" and Return would restore the wrong state.
  if (state().mode === 'review') _api.actions.exitReview();
  hub.ensurePlay();

  checkToken++; // invalidate anything stale from a prior session
  trainerSnapshot = hub.snapshotPlay();
  hub.setMode('blunder-practice');

  drill = {
    puzzles,
    index: 0,
    board: null,
    orientation: 'white',
    attempts: 0,       // failed checks on the current puzzle (retry-once rule)
    results: [],       // final outcome per puzzle index (see header comment)
    flushed: false,    // bucket-complete posted (guards double-flush on exit)
    awaitingCheck: false,
    phase: 'moving',
  };
  showTrainerUI(true);
  loadPuzzle();
}

function loadPuzzle() {
  const { hub } = _api;
  const puzzle = drill.puzzles[drill.index];
  drill.attempts = 0;
  drill.awaitingCheck = false;
  drill.phase = 'moving';
  drill.board = hub.positionFromFen(puzzle.fen_before);
  // You are always the mover in these positions; orient to your color, and
  // fall back to fen_before's side-to-move if the color field is ever absent.
  drill.orientation =
    puzzle.color === 'white' || puzzle.color === 'black'
      ? puzzle.color
      : drill.board.turn;

  byId('trainer-title').textContent =
    `Blunder Drill — ${drill.index + 1}/${drill.puzzles.length} · ${bucketLabel(puzzle.bucket)}`;
  setMoveHint('Your move — find the better continuation.');
  setNote(
    `From one of your games: you played a ${puzzle.severity} here. ` +
    'One retry on a miss, then the answer is revealed.'
  );
  setFeedback('', null);
  setNarration(null);
  showNextButton(false);
  showRevealButton(true);
  clearShapes();
  trainerArmBoard();
}

// Your move handler in blunder-practice (registered with the hub's registry).
async function onTrainerMove(orig, dest) {
  const { hub } = _api;
  if (state().mode !== 'blunder-practice' || !drill) return;
  // Outside the 'moving' phase the board is frozen (no dests), so this can't
  // fire — bail without touching the board if it somehow does.
  if (drill.phase !== 'moving' || drill.awaitingCheck) return;

  const puzzle = drill.puzzles[drill.index];
  let promo = '';
  if (hub.isPromotion(drill.board, orig, dest)) {
    try {
      promo = await hub.askPromotion();
    } catch (_) {
      trainerArmBoard(); // promotion cancelled — snap back
      return;
    }
  }
  const uci = orig + dest + promo;

  drill.awaitingCheck = true;
  drill.phase = 'checking';
  trainerFreeze();
  setMoveHint('Checking…');

  const token = ++checkToken;
  const body = {
    game_id: puzzle.game_id,
    ply: puzzle.ply,
    bucket: puzzle.bucket, // ALWAYS the served bucket — never a raw threat_motif
    attempted_uci: uci,
  };

  let data;
  try {
    data = await hub.postJSON('/api/trainer/check', body);
  } catch (_) {
    // 503 — engine unavailable. Degrade to the offline exact-match check
    // (verdict vs the stored best move, recorded with check_depth=0).
    try {
      data = await hub.postJSON('/api/trainer/check', { ...body, offline: true });
    } catch (_2) {
      if (token !== checkToken || !drill) return;
      drill.awaitingCheck = false;
      drill.phase = 'moving';
      setMoveHint('Your move.');
      setFeedback('Could not check the move — server unreachable. Try again.', 'bad');
      trainerArmBoard();
      return;
    }
  }

  // Stale guard: the user may have hit Return (or started over) mid-check.
  if (token !== checkToken || !drill || state().mode !== 'blunder-practice') return;
  drill.awaitingCheck = false;

  if (!data || data.detail) { // 404 — puzzle vanished (re-analysis mid-session)
    drill.phase = 'advancing';
    setFeedback('This puzzle is no longer available — skipping.', 'bad');
    finishPuzzle('failed');
    scheduleAdvance(token);
    return;
  }
  if (!data.legal) {
    drill.phase = 'moving';
    setMoveHint('Your move.');
    setFeedback('Illegal move — try again.', 'bad');
    trainerArmBoard();
    return;
  }

  handleVerdict(data, uci);
}

function handleVerdict(data, uci) {
  const offNote = data.offline ? ' (offline check — engine unavailable)' : '';

  if (data.verdict === 'solved' || data.verdict === 'solved_alt') {
    // Show your move on the board while the Correct! pause holds.
    try { drill.board.play(parseUci(uci)); trainerShowMove(uci); } catch (_) { trainerFreeze(); }
    setFeedback(
      data.verdict === 'solved'
        ? `Correct! — ${data.attempted_san} is the engine's move.${offNote}`
        : `Correct! — ${data.attempted_san} holds the position (best was ${data.best_san || '?'}).${offNote}`,
      'good'
    );
    setMoveHint('');
    const next = drill.index + 1;
    setNote(
      next < drill.puzzles.length
        ? `Next: ${bucketLabel(drill.puzzles[next].bucket)}`
        : 'Last one — Next shows your session summary.'
    );
    finishPuzzle(data.verdict);
    drill.phase = 'solved';
    showRevealButton(false);
    showNextButton(true);
    return;
  }

  // failed
  if (drill.attempts === 0) {
    drill.attempts = 1;
    drill.phase = 'moving';
    setMoveHint('Your move — one more try.');
    setFeedback(`${data.attempted_san} still loses ground.${offNote} Try once more.`, 'bad');
    trainerArmBoard(); // snap back to the puzzle position
  } else {
    revealCurrent(data); // second miss → auto-reveal with narration
  }
}

// Reveal the answer. `checkData` carries best_san + narration when the reveal
// came from a second failed check; a manual Reveal press passes null and uses
// the stored (background-depth) best from the puzzle payload instead.
function revealCurrent(checkData) {
  const puzzle = drill.puzzles[drill.index];
  const bestSan = (checkData && checkData.best_san) || puzzle.best_san;
  const bestUci = (checkData && checkData.best_uci) || puzzle.best_uci;

  drill.phase = 'revealed';
  // Play the best move on the board so the answer is SEEN, not just read.
  if (bestUci) {
    try { drill.board.play(parseUci(bestUci)); trainerShowMove(bestUci); } catch (_) { trainerFreeze(); }
  } else {
    trainerFreeze();
  }
  showThreatShapes(puzzle);

  setMoveHint('');
  setFeedback(bestSan ? `Best was ${bestSan}.` : 'No stored best move for this one.', 'bad');
  setNarration(checkData ? checkData.narration : null);
  // Final outcome: a second failed check ends as 'revealed' too — the answer
  // had to be shown either way (the server already recorded both real attempts).
  finishPuzzle('revealed');
  showNextButton(true);
}

// Record the current puzzle's FINAL outcome exactly once (last resolution wins).
function finishPuzzle(outcome) {
  drill.results[drill.index] = outcome;
}

function scheduleAdvance(token) {
  setTimeout(() => {
    if (token !== checkToken || !drill || state().mode !== 'blunder-practice') return;
    advance();
  }, ADVANCE_DELAY_MS);
}

function advance() {
  if (!drill) return;
  drill.index += 1;
  if (drill.index >= drill.puzzles.length) {
    endSession();
  } else {
    loadPuzzle();
  }
}

// Session complete: summary + flush bucket outcomes. Board stays frozen on
// the last position; Return restores the play game.
function endSession() {
  drill.phase = 'summary';
  trainerFreeze();
  clearShapes();
  showNextButton(false);

  const total = drill.results.filter(Boolean).length;
  const solved = drill.results.filter((o) => o === 'solved' || o === 'solved_alt').length;
  byId('trainer-title').textContent = 'Blunder Drill — session complete';
  setMoveHint('');
  setNote('Return to your game, or start another session from the Review tab.');
  setFeedback(`Session complete — ${solved}/${total} solved.`, solved > 0 ? 'good' : null);
  setNarration(null);

  flushOutcomes(); // fire-and-forget; guarded against double-flush
}

// POST one bucket-complete per served bucket with the accumulated final
// outcomes (drives the Leitner box transitions). Puzzles abandoned mid-way
// (no final outcome) are simply not counted — the min-sample guard server-side
// keeps a 1-sample bucket from moving.
function flushOutcomes() {
  if (!drill || drill.flushed) return;
  drill.flushed = true;
  const byBucket = {};
  drill.puzzles.forEach((p, i) => {
    const outcome = drill.results[i];
    if (!outcome) return;
    (byBucket[p.bucket] = byBucket[p.bucket] || []).push(outcome);
  });
  const { hub } = _api;
  (async () => {
    for (const [motif, outcomes] of Object.entries(byBucket)) {
      try {
        await hub.postJSON('/api/trainer/bucket-complete', { motif, outcomes });
      } catch (_) {
        // Best-effort: a lost flush only delays a box transition.
      }
    }
    refreshTrainSection(); // reflect new boxes / last_reviewed in the preview
  })();
}

// Manual Reveal press (counts as 'revealed'; no /check POST — reveals are
// accounted client-side only).
function onRevealClick() {
  if (state().mode !== 'blunder-practice' || !drill) return;
  if (drill.phase !== 'moving' || drill.awaitingCheck) return;
  checkToken++; // cancel any pending timers
  revealCurrent(null);
}

function onNextClick() {
  if (state().mode !== 'blunder-practice' || !drill) return;
  if (drill.phase !== 'revealed' && drill.phase !== 'solved') return;
  advance();
}

// Exit: restore the play game (mirrors repertoire.js's exitRepPractice
// sequence exactly) and flush any accumulated bucket outcomes.
function exitTrainer() {
  const { hub } = _api;
  checkToken++; // invalidate any in-flight check reply / advance timer
  if (drill) flushOutcomes(); // fire-and-forget (Return mid-session counts too)
  hub.restorePlay(trainerSnapshot || { baseFen: INITIAL_FEN, moves: [], cursor: 0 });
  hub.setMode('play');
  trainerSnapshot = null;
  drill = null;
  showTrainerUI(false);
  clearShapes();
  hub.syncBoard();
  hub.refreshAnalysis();
  hub.refreshOpeningThenTraps();
  hub.persist();
}

// --- init --------------------------------------------------------------------

export function initTrainer(api) {
  _api = api;

  // Drill bar controls
  byId('trainer-return').addEventListener('click', exitTrainer);
  byId('trainer-reveal').addEventListener('click', onRevealClick);
  byId('trainer-next').addEventListener('click', onNextClick);

  // The hub's dispatcher and ensurePlay() route through this registration.
  api.hub.registerModeHandlers('blunder-practice', { onMove: onTrainerMove, exit: exitTrainer });

  // Initial Train-section render (idempotent preview — safe on every call).
  refreshTrainSection();
}
