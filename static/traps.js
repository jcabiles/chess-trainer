// traps.js — opening-traps trainer (browse catalog, live "trap available"
// chip, watch mode, practice drill). Receives the injected `api` from app.js
// at init and never imports app.js back (hub → feature → leaf; panel.js and
// format.js are leaf imports).
//
// Owns: `trap` (active trap), `trapsData` (browse catalog), `studySnapshot`
// (in-memory only — never persisted), `trapChipDismissedFen` (sticky chip
// dismiss), and both async token guards:
//   * studyEvalToken — cancels out-of-order step evals AND stale victim
//     auto-play timers across watch/practice/back (whole token lives here;
//     never split watch from practice).
//   * trapsCheckToken — drops stale /api/traps/check chip responses.
//
// The hub's refreshOpeningThenTraps() emits 'traps:check' on the bus after the
// opening lookup resolves; the chip listener here picks it up (fire-and-forget
// with its own try/catch — exactly the contract the bus supports).

import { INITIAL_FEN, makeFen } from 'https://esm.sh/chessops@0.14.2/fen';
import { chessgroundDests } from 'https://esm.sh/chessops@0.14.2/compat';
import { parseUci } from 'https://esm.sh/chessops@0.14.2/util';
import { renderAnalysisPanel } from './panel.js';
import { formatEval } from './format.js';

let _api = null;
let trap = null;                 // active trap: { id, name, mainLine, startFen, step, fens, lastUcis, ... }
let trapsData = [];              // all trap summaries fetched on load
let studySnapshot = null;        // saved play state captured when entering a trap (restored on exit)
let studyEvalToken = 0;          // guards out-of-order async eval while stepping a trap (watch/practice)
let trapsCheckToken = 0;         // guards stale /api/traps/check responses (mirrors studyEvalToken)
let trapChipDismissedFen = null; // sticky dismiss: EPD/FEN string for which the chip was dismissed

const byId = (id) => document.getElementById(id);
const state = () => _api.actions.getState();
const ground = () => _api.actions.getGround();

// --- browse section ----------------------------------------------------------

// Fetch the trap summary list once on startup and populate the browse section.
async function loadTraps() {
  try {
    const res = await fetch('/api/traps');
    const data = await res.json();
    trapsData = (data && Array.isArray(data.traps)) ? data.traps : [];
  } catch (_) {
    trapsData = []; // degraded — empty section, no crash
  }
  renderTraps();
}

// Re-render the #traps-list applying the current name + color filters.
// All text is set via textContent (no innerHTML injection).
function renderTraps() {
  const nameFilter = byId('traps-name-filter').value.trim().toLowerCase();
  const colorFilter = byId('traps-color-filter').value; // '' | 'white' | 'black'

  const filtered = trapsData.filter((t) => {
    if (nameFilter && !t.name.toLowerCase().includes(nameFilter)) return false;
    if (colorFilter && t.color !== colorFilter) return false;
    return true;
  });

  const list = byId('traps-list');
  list.replaceChildren();

  if (!filtered.length) {
    const empty = document.createElement('div');
    empty.className = 'traps-empty empty-state';
    empty.textContent = trapsData.length
      ? 'No traps match the filter.'
      : 'No traps loaded.';
    list.appendChild(empty);
    return;
  }

  for (const t of filtered) {
    const btn = document.createElement('button');

    const nameSpan = document.createElement('span');
    nameSpan.className = 'trap-item-name';
    nameSpan.textContent = t.name; // textContent — no injection

    const metaSpan = document.createElement('span');
    metaSpan.className = 'trap-item-meta';

    const ecoSpan = document.createElement('span');
    ecoSpan.className = 'trap-item-eco';
    ecoSpan.textContent = t.eco || '';

    const colorSpan = document.createElement('span');
    colorSpan.className = 'trap-item-color';
    colorSpan.textContent = t.color || '';

    // Commonness as filled stars (1-5)
    const commSpan = document.createElement('span');
    commSpan.className = 'trap-item-commonness';
    const stars = Math.max(0, Math.min(5, t.commonness | 0));
    commSpan.textContent = '★'.repeat(stars) + '☆'.repeat(5 - stars);

    metaSpan.append(ecoSpan, colorSpan, commSpan);
    btn.append(nameSpan, metaSpan);
    btn.addEventListener('click', () => enterTrap(t.id));
    list.appendChild(btn);
  }
}

// --- live "trap available" chip (play mode only) -------------------------------

// Fire-and-forget: POST /api/traps/check with the current position.
// Guarded by trapsCheckToken so stale responses never render.
// Only fires when state.mode === 'play'.
// Must run AFTER refreshOpening() — the hub sequences that and emits
// 'traps:check' on the bus when it's our turn.
async function refreshTrapsAvailable() {
  const s = state();
  if (s.mode !== 'play') return;
  const token = ++trapsCheckToken;
  try {
    const moves = s.moves.slice(0, s.cursor);
    const data = await _api.hub.postJSON('/api/traps/check', {
      baseFen: s.baseFen,
      moves,
    });
    if (token !== trapsCheckToken) return; // stale — superseded by a newer call
    if (state().mode !== 'play') return;    // mode changed while awaiting

    const available = (data && Array.isArray(data.available)) ? data.available : [];
    if (available.length) {
      const t = available[0];
      // Build a position key for the sticky-dismiss check.
      const posKey = s.baseFen + '|' + moves.join(',');
      if (posKey === trapChipDismissedFen) return; // still dismissed for this position
      byId('trap-chip-text').textContent = `Trap available: ${t.name} — drill it`;
      byId('trap-chip').dataset.trapId = t.id;
      byId('trap-chip').hidden = false;
    } else {
      byId('trap-chip').hidden = true;
    }
  } catch (_) {
    // Isolated by design — a failed check never delays or breaks anything.
  }
}

// --- trap-watch mode -----------------------------------------------------------
//
// Mirrors the study walkthrough pattern: snapshot → fetch → set state →
// view-only board → lazy per-step eval (guarded by studyEvalToken) → restore.

// Build the trap step model from a full trap object + a chosen variation index.
// Returns { id, name, mainLine, startFen, step, fens, lastUcis, color, engineNote,
//   raw, variations, variationIndex }.
// fens[0] = startFen; fens[k] = FEN after replaying the first k UCIs from startFen.
// lastUcis[k] = UCI of the move that led into fens[k] (undefined for k=0).
function buildTrap(trapData, variationIndex = 0) {
  const variations = trapData.variations;
  const idx = Math.max(0, Math.min(variationIndex, variations.length - 1));
  const mainLine = variations[idx].mainLine;
  const startFen = trapData.startFen;

  const fens = [startFen];
  const lastUcis = [undefined];

  let pos = _api.hub.positionFromFen(startFen);
  for (const ply of mainLine) {
    pos.play(parseUci(ply.uci));
    fens.push(makeFen(pos.toSetup()));
    lastUcis.push(ply.uci);
  }

  return {
    id: trapData.id,
    name: trapData.name,
    mainLine,
    startFen,
    step: 0,
    max: mainLine.length,
    fens,
    lastUcis,
    color: trapData.color,          // the TRAPPER (the side the user plays)
    engineNote: trapData.engineNote || '',
    raw: trapData,                  // kept so the variation picker can rebuild
    variations,
    variationIndex: idx,
  };
}

// Entry point: called from trap list items and the live chip.
// From play mode: snapshot current game into studySnapshot (non-destructive).
// Re-entrant: if already in a trap mode, switch traps WITHOUT re-snapshotting.
async function enterTrap(trapId) {
  const { hub } = _api;
  // Snapshot only if coming from play mode (not already in a trap).
  if (state().mode === 'play') {
    studySnapshot = hub.snapshotPlay();
  }

  // Fetch the full trap.
  let trapData;
  try {
    const res = await fetch(`/api/traps/${encodeURIComponent(trapId)}`);
    if (!res.ok) {
      hub.setStatus(`Trap not found: ${trapId}`, true);
      return;
    }
    trapData = await res.json();
  } catch (err) {
    hub.setStatus('Failed to load trap data.', true);
    return;
  }

  trap = buildTrap(trapData, 0);
  hub.setMode('trap-watch');

  // Show trap bar, hide play controls (same body-class pattern as study-mode).
  showTrapUI(true);

  byId('trap-title').textContent = trap.name;
  byId('trap-mode-toggle').hidden = false; // watch ⇄ practice toggle available
  populateVariationPicker();               // shows the picker only when >1 variation
  applyTrapModeUI();                       // show watch controls, hide practice ones

  goToTrapStep(0);
}

// Fill the variation <select> from the current trap. Hidden when a trap has only
// one variation (nothing to choose). Each option's label comes from the data.
function populateVariationPicker() {
  const sel = byId('trap-variation');
  if (!trap || trap.variations.length < 2) {
    sel.hidden = true;
    sel.innerHTML = '';
    return;
  }
  sel.innerHTML = '';
  trap.variations.forEach((v, i) => {
    const opt = document.createElement('option');
    opt.value = String(i);
    opt.textContent = v.label || `Variation ${i + 1}`;
    sel.appendChild(opt);
  });
  sel.value = String(trap.variationIndex);
  sel.hidden = false;
}

// Switch to a different variation of the SAME trap. Rebuilds from the raw data,
// resets to step 0, and re-enters the current sub-mode (watch or practice) so the
// played/unplayed boundary is unambiguous — same rule as the watch⇄practice toggle.
function selectTrapVariation(index) {
  if (!trap) return;
  const wasPractice = state().mode === 'trap-practice';
  trap = buildTrap(trap.raw, index);
  byId('trap-variation').value = String(trap.variationIndex);
  byId('trap-feedback').textContent = '';
  if (wasPractice) {
    startPractice();
  } else {
    goToTrapStep(0);
  }
}

// Toggle the visible body class + controls for the active trap sub-mode.
// Watch: stepper visible; practice: reveal + show-refutation + feedback visible.
function applyTrapModeUI() {
  const practice = state().mode === 'trap-practice';
  document.body.classList.toggle('trap-watch-mode', state().mode === 'trap-watch');
  document.body.classList.toggle('trap-practice-mode', practice);

  byId('trap-mode-toggle').textContent = practice
    ? 'Switch to Watch'
    : 'Switch to Practice';

  byId('trap-stepper').hidden = practice;       // stepper is watch-only
  byId('trap-reveal').hidden = !practice;       // reveal/show-refutation are practice-only
  byId('trap-feedback').hidden = !practice;
}

// Flip between watch and practice. ALWAYS restarts the drill at step 0
// (startFen) — never mid-line — so the played/unplayed boundary is unambiguous.
// Reuses the existing studySnapshot (does NOT re-snapshot the game).
function toggleTrapMode() {
  const { hub } = _api;
  if (!trap) return;
  if (state().mode === 'trap-practice') {
    hub.setMode('trap-watch');
    applyTrapModeUI();
    byId('trap-feedback').textContent = '';
    goToTrapStep(0);
  } else if (state().mode === 'trap-watch') {
    hub.setMode('trap-practice');
    applyTrapModeUI();
    startPractice();
  }
}

// Navigate to step k in the trap variation.
// step 0 = startFen (no note); step k = after k plies.
function goToTrapStep(k) {
  if (!trap) return;
  trap.step = Math.max(0, Math.min(k, trap.max));

  const fen = trap.fens[trap.step];
  const pos = _api.hub.positionFromFen(fen);
  ground().set({
    fen: fen.split(' ')[0],
    turnColor: pos.turn,
    orientation: state().orientation,
    lastMove: trap.step > 0 ? _api.hub.lastMoveSquares(trap.lastUcis[trap.step]) : undefined,
    movable: { free: false, color: undefined, dests: undefined },
    draggable: { enabled: false },
  });

  renderTrapStep();
}

// Render move label, eval, and note for the current trap step.
// Uses studyEvalToken (shared with study) so switching between study and trap
// modes properly cancels any in-flight requests.
function renderTrapStep() {
  const { hub } = _api;
  const step = trap.step;

  // Move label: step 0 = start position, step k = SAN of ply k-1.
  if (step === 0) {
    byId('trap-move').textContent = 'Start position';
  } else {
    const ply = trap.mainLine[step - 1];
    // Compute a rough move-number string (startFen gives us the turn).
    const startPos = hub.positionFromFen(trap.startFen);
    const startFullMove = startPos.fullmoves;
    const startTurn = startPos.turn; // 'white' | 'black'
    // Move number at ply index i (0-based from startFen):
    //   i=0 is the first ply from startFen (startTurn's move).
    const plyIndex = step - 1; // 0-based ply index into mainLine
    let fullMove, colorLabel;
    if (startTurn === 'white') {
      fullMove = startFullMove + Math.floor(plyIndex / 2);
      colorLabel = plyIndex % 2 === 0 ? 'w' : 'b';
    } else {
      // Black moves first from startFen
      fullMove = startFullMove + Math.floor((plyIndex + 1) / 2);
      colorLabel = plyIndex % 2 === 0 ? 'b' : 'w';
    }
    byId('trap-move').textContent = `${fullMove}${colorLabel === 'w' ? '.' : '…'} ${ply.san}`;
  }

  // Lazy eval via /api/analyze — cancel stale requests with studyEvalToken.
  const token = ++studyEvalToken;
  const fen = trap.fens[step];

  hub.postJSON('/api/analyze', { fen })
    .then((d) => {
      if (token !== studyEvalToken) return; // stale — superseded
      const evalStr = formatEval(d && d.analysis);
      // Append eval to the move label.
      const cur = byId('trap-move').textContent;
      byId('trap-move').textContent = cur ? `${cur}  ${evalStr}` : evalStr;
    })
    .catch(() => { /* eval is best-effort */ });

  // Note: step 0 has no ply note; ply k-1 (0-based) has the note for step k.
  const noteEl = byId('trap-note');
  if (step === 0) {
    noteEl.textContent = 'Trap starting position.';
    return;
  }

  const ply = trap.mainLine[step - 1];
  const parts = [];

  if (ply.note) {
    parts.push(ply.note);
  }

  // Bait ply: also surface refutation.note + assessment.
  if (ply.bait && ply.refutation) {
    const ref = ply.refutation;
    if (ref.note || ref.assessment) {
      parts.push(''); // blank line separator
      if (ref.note) parts.push(`If declined: ${ref.note}`);
      if (ref.assessment) parts.push(`Assessment: ${ref.assessment}`);
    }
  }

  noteEl.textContent = parts.join('\n') || '';
}

// Show/hide the trap bar and toggle body class for play-control hiding.
// The specific watch/practice body class is owned by applyTrapModeUI(); here we
// only ensure both are cleared when the bar is hidden (on exit).
function showTrapUI(on) {
  byId('trap-bar').hidden = !on;
  if (on) {
    // Entering a trap: the play-mode "trap available" chip no longer applies.
    byId('trap-chip').hidden = true;
  } else {
    document.body.classList.remove('trap-watch-mode', 'trap-practice-mode');
  }
}

// Return to my game: restore studySnapshot, mode → play.
// Reused by #trap-return for BOTH trap-watch and trap-practice.
function exitTrap() {
  const { hub } = _api;
  hub.restorePlay(studySnapshot || { baseFen: INITIAL_FEN, moves: [], cursor: 0 });
  hub.setMode('play');
  studySnapshot = null;
  trap = null;
  showTrapUI(false);
  ground().set({ highlight: { lastMove: true, check: true } });
  hub.syncBoard();
  hub.refreshAnalysis();
  hub.refreshOpeningThenTraps();
  hub.persist();
}

// --- trap-practice mode ----------------------------------------------------
//
// Interactive drill. The trap's `color` is the TRAPPER (the side the user
// plays). In `mainLine`, victim moves are auto-played by the app; the user must
// find each trapper move. Validation is against the SCRIPT (mainLine[ply].uci) —
// any legal-but-wrong move snaps back with "try again".
//
// trap.step is the count of plies already applied (mirrors trap-watch). The
// board FEN at step k is trap.fens[k]; the move to find at step k (when it's a
// trapper ply) is trap.mainLine[k].uci.

// Begin (or restart) the drill from step 0.
function startPractice() {
  if (!trap) return;
  trap.step = 0;
  byId('trap-move').textContent = 'Practice — find the trapper’s moves.';
  byId('trap-note').textContent = '';
  byId('trap-feedback').textContent = '';
  byId('trap-feedback').classList.remove('feedback-good', 'feedback-bad');
  // Place the board at startFen, then run the loop (auto-plays any leading
  // victim move — e.g. Stafford's 4.Nxc6 — before handing control to the user).
  renderPracticeBoard();
  advancePractice();
}

// Drive the practice loop from the current step:
//   - line complete (step === max) → completion message, board frozen.
//   - victim ply → auto-play after a short beat, advance, recurse.
//   - trapper ply → make the board interactive and WAIT for onTrapMove.
function advancePractice() {
  if (!trap || state().mode !== 'trap-practice') return;

  if (trap.step >= trap.max) {
    setTrapFrozen();
    showPracticeComplete();
    return;
  }

  const ply = trap.mainLine[trap.step];
  if (ply.side === 'victim') {
    // Freeze the board, then auto-play the victim's scripted reply after a beat
    // so the user sees the trap spring (incl. the bait move).
    setTrapFrozen();
    const stepAtSchedule = trap.step;
    setTimeout(() => {
      // Guard: the user may have toggled/exited while we waited.
      if (!trap || state().mode !== 'trap-practice') return;
      if (trap.step !== stepAtSchedule) return;
      applyPracticeStep(ply.uci);
      trap.step += 1;
      advancePractice();
    }, 400);
  } else {
    // Trapper's turn — let the user move; onTrapMove validates against the script.
    setTrapInteractive();
    renderPracticeNote(); // show the note/eval for the position the user faces
  }
}

// Render the board at the current step's FEN (no interactivity changes here).
function renderPracticeBoard() {
  const fen = trap.fens[trap.step];
  const pos = _api.hub.positionFromFen(fen);
  ground().set({
    fen: fen.split(' ')[0],
    turnColor: pos.turn,
    orientation: state().orientation,
    lastMove: trap.step > 0 ? _api.hub.lastMoveSquares(trap.lastUcis[trap.step]) : undefined,
    movable: { free: false, color: undefined, dests: undefined },
    draggable: { enabled: false },
  });
}

// Apply a single scripted UCI on the board (used to auto-play victim moves and
// to commit a correct/revealed trapper move). Animates + highlights last move.
function applyPracticeStep(uci) {
  const fen = trap.fens[trap.step + 1]; // FEN after this ply
  const pos = _api.hub.positionFromFen(fen);
  ground().set({
    fen: fen.split(' ')[0],
    turnColor: pos.turn,
    orientation: state().orientation,
    lastMove: _api.hub.lastMoveSquares(uci),
    movable: { free: false, color: undefined, dests: undefined },
    draggable: { enabled: false },
  });
}

// Configure the board so ONLY the trapper can move, with ALL their legal moves
// as dests (same as play mode, restricted to trap.color). Validation of the
// CHOSEN move happens in onTrapMove against the script.
function setTrapInteractive() {
  const fen = trap.fens[trap.step];
  const pos = _api.hub.positionFromFen(fen);
  ground().set({
    fen: fen.split(' ')[0],
    turnColor: pos.turn,
    orientation: state().orientation,
    lastMove: trap.step > 0 ? _api.hub.lastMoveSquares(trap.lastUcis[trap.step]) : undefined,
    movable: { free: false, color: trap.color, dests: chessgroundDests(pos) },
    draggable: { enabled: true, deleteOnDropOff: false },
  });
}

// Freeze the board (no interaction) — used while a victim move is pending and
// when the line is complete.
function setTrapFrozen() {
  ground().set({ movable: { free: false, color: undefined, dests: undefined }, draggable: { enabled: false } });
}

function setTrapFeedback(msg, kind) {
  const el = byId('trap-feedback');
  el.textContent = msg;
  el.classList.remove('feedback-good', 'feedback-bad');
  if (kind === 'good') el.classList.add('feedback-good');
  else if (kind === 'bad') el.classList.add('feedback-bad');
}

function showPracticeComplete() {
  // The result (if any) sits on the final ply.
  const last = trap.mainLine[trap.max - 1];
  const result = last && last.result;
  const labels = {
    checkmate: 'Checkmate — the trap is complete!',
    'wins-queen': 'You win the queen — trap complete!',
    'wins-material': 'You win decisive material — trap complete!',
    'wins-piece': 'You win a piece — trap complete!',
  };
  const msg = (result && labels[result]) || 'Line complete — well done!';
  setTrapFeedback(msg, 'good');
  // Keep the final note + eval on screen.
  renderPracticeNote();
}

// onTrapMove(orig, dest) — the ONLY board-move handler in trap-practice.
// Builds the attempted UCI (with a promotion suffix via askPromotion when the
// move is a promotion), validates it against the scripted trapper move, then:
//   correct → apply + positive feedback + advance + run the loop (auto-victim).
//   wrong   → snap back via ground.set({fen: currentFen}) + "try again".
async function onTrapMove(orig, dest) {
  const { hub } = _api;
  if (state().mode !== 'trap-practice' || !trap) return;
  const ply = trap.mainLine[trap.step];
  // Defensive: only trapper plies are interactive, but guard anyway.
  if (!ply || ply.side !== 'trapper') { renderPracticeBoard(); return; }

  const fenBefore = trap.fens[trap.step];
  const posBefore = hub.positionFromFen(fenBefore);

  let promo = '';
  if (hub.isPromotion(posBefore, orig, dest)) {
    promo = await hub.askPromotion();
  }
  const attempted = orig + dest + promo;

  if (attempted === ply.uci) {
    // Correct — commit the scripted move, advance, continue (auto-victim next).
    applyPracticeStep(ply.uci);
    trap.step += 1;
    setTrapFeedback(ply.note ? `Yes! ${ply.note}` : 'Yes — that’s the move!', 'good');
    renderPracticeNote();
    advancePractice();
  } else {
    // Legal but not the scripted move (incl. wrong promotion piece) → snap the
    // piece back. setTrapInteractive() re-sets the board to fenBefore and
    // re-arms the trapper's dests (same takeback effect as play mode's
    // ground.set({fen: currentFen}) on a rejected move).
    setTrapInteractive();
    setTrapFeedback('Not quite — try again.', 'bad');
  }
}

// Reveal: play the next expected trapper move for a stuck user, then continue
// the loop (which auto-plays the following victim move).
function revealTrapMove() {
  if (state().mode !== 'trap-practice' || !trap) return;
  if (trap.step >= trap.max) return;
  const ply = trap.mainLine[trap.step];
  if (ply.side !== 'trapper') return; // only meaningful on the user's turn
  applyPracticeStep(ply.uci);
  trap.step += 1;
  setTrapFeedback(ply.note ? `${ply.san} — ${ply.note}` : `The move was ${ply.san}.`, 'good');
  renderPracticeNote();
  advancePractice();
}

// Take back: rewind to the user's PREVIOUS decision — undo their last move AND
// the opponent's auto-reply, landing on the prior trapper ply so they can re-try.
// Skips victim-only states so nothing auto-replays forward. No-op if there is no
// earlier trapper move (already at the first decision).
function trapBack() {
  if (state().mode !== 'trap-practice' || !trap) return;
  // Find the nearest trapper ply strictly before the current step.
  let prev = -1;
  for (let i = trap.step - 1; i >= 0; i--) {
    if (trap.mainLine[i].side === 'trapper') { prev = i; break; }
  }
  if (prev < 0) {
    setTrapFeedback('Already at the first move.', null);
    return;
  }
  // Bump the eval/auto-play guard token so any in-flight victim timer (its
  // stepAtSchedule will no longer match) and any stale eval are discarded.
  studyEvalToken++;
  trap.step = prev;
  setTrapInteractive();          // re-arm the trapper's move at the prior position
  renderPracticeNote();
  setTrapFeedback('Took back your last move — try again.', null);
}

// Show-refutation: read-only preview of what the victim SHOULD have played
// (from the bait ply's refutation: san + declineSan line + assessment).
// Does NOT change the drill position or step — purely fills the note/feedback.
function showTrapRefutation() {
  if (!trap) return;
  const baitPly = trap.mainLine.find((p) => p.bait && p.refutation);
  if (!baitPly) {
    setTrapFeedback('No refutation recorded for this trap.', null);
    return;
  }
  const ref = baitPly.refutation;
  const parts = [];
  parts.push(`Refutation: ${ref.san}`);
  if (ref.note) parts.push(ref.note);
  if (Array.isArray(ref.declineSan) && ref.declineSan.length) {
    parts.push(`Line: ${ref.san} ${ref.declineSan.join(' ')}`);
  }
  if (ref.assessment) parts.push(`Assessment: ${ref.assessment}`);
  byId('trap-note').textContent = parts.join('\n');
  setTrapFeedback(`If the opponent declines: ${ref.san}`, null);
}

// Render the move label (with trap-aware eval) + note for the CURRENT practice
// position. Eval is fetched lazily and the quality label is ALWAYS suppressed
// (a real "Blunder!" on a deliberately dubious trapper move never contradicts
// the lesson) — rendered via panel.js directly (feature → leaf import).
function renderPracticeNote() {
  const { hub } = _api;
  const step = trap.step;

  // The note/eval describe the position AS IT NOW STANDS. If the last applied
  // ply (step-1) carried a note, show it; on the user's turn (no ply applied
  // since the prompt) we still show the prior ply's note for context.
  const lastPly = step > 0 ? trap.mainLine[step - 1] : null;
  const noteParts = [];
  if (lastPly && lastPly.note) noteParts.push(lastPly.note);
  // On a dubious trapper ply, also surface the trap's engineNote (why the
  // engine-poor move scores in practice).
  if (lastPly && lastPly.dubious && trap.engineNote) {
    noteParts.push(`Engine: ${trap.engineNote}`);
  }
  byId('trap-note').textContent = noteParts.join('\n');

  // Move label.
  byId('trap-move').textContent = step > 0
    ? `${lastPly.san}`
    : 'Your move — find the trapper’s idea.';

  // Lazy, trap-aware eval. Use /api/move when we have a prior ply (gives the
  // move-relative eval), else /api/analyze on the position. Either way the
  // quality label is suppressed in the panel.
  const token = ++studyEvalToken;
  const fen = trap.fens[step];

  if (step > 0) {
    const before = trap.fens[step - 1];
    hub.postJSON('/api/move', { fen: before, move: trap.lastUcis[step] })
      .then((d) => {
        if (token !== studyEvalToken) return;
        if (state().mode !== 'trap-practice') return;
        renderAnalysisPanel(d && d.legal ? d.analysis : null, { suppressQuality: true, suppressRetro: true });
      })
      .catch(() => { /* eval is best-effort */ });
  } else {
    hub.postJSON('/api/analyze', { fen })
      .then((d) => {
        if (token !== studyEvalToken) return;
        if (state().mode !== 'trap-practice') return;
        renderAnalysisPanel(d && d.analysis, { suppressQuality: true, suppressRetro: true });
      })
      .catch(() => { /* eval is best-effort */ });
  }
}

// --- init ----------------------------------------------------------------------

export function initTraps(api) {
  _api = api;

  // Traps browse filters
  byId('traps-name-filter').addEventListener('input', () => renderTraps());
  byId('traps-color-filter').addEventListener('change', () => renderTraps());

  // Trap chip: dismiss (sticky for this position) + drill
  byId('trap-chip-dismiss').addEventListener('click', () => {
    const s = state();
    const moves = s.moves.slice(0, s.cursor);
    trapChipDismissedFen = s.baseFen + '|' + moves.join(',');
    byId('trap-chip').hidden = true;
  });
  byId('trap-chip-drill').addEventListener('click', () => {
    const trapId = byId('trap-chip').dataset.trapId;
    if (trapId) enterTrap(trapId);
  });

  // Trap bar: return + stepper (trap-watch mode).
  byId('trap-return').addEventListener('click', exitTrap);
  byId('trap-first').addEventListener('click', () => goToTrapStep(0));
  byId('trap-prev').addEventListener('click', () => goToTrapStep(trap ? trap.step - 1 : 0));
  byId('trap-next').addEventListener('click', () => goToTrapStep(trap ? trap.step + 1 : 0));
  byId('trap-last').addEventListener('click', () => goToTrapStep(trap ? trap.max : 0));

  // Trap bar: practice-mode controls (TT6).
  byId('trap-mode-toggle').addEventListener('click', toggleTrapMode);
  byId('trap-variation').addEventListener('change', (e) => selectTrapVariation(Number(e.target.value)));
  byId('trap-back').addEventListener('click', trapBack);
  byId('trap-reveal-move').addEventListener('click', revealTrapMove);
  byId('trap-show-refutation').addEventListener('click', showTrapRefutation);

  // The hub's dispatcher and ensurePlay() route through these registrations.
  api.hub.registerModeHandlers('trap-watch', { exit: exitTrap });
  api.hub.registerModeHandlers('trap-practice', { onMove: onTrapMove, exit: exitTrap });

  // The hub emits 'traps:check' after each opening refresh (sequenced so the
  // two network calls never burst simultaneously); the chip check runs then.
  api.on('traps:check', refreshTrapsAvailable);

  // Load browse data (non-blocking — the section degrades gracefully).
  loadTraps();
}
