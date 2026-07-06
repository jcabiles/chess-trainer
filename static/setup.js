// setup.js — pregame position editor (brush stamping, palette, castling
// inference, enter/begin/cancel). Receives the injected `api` from app.js at
// init and never imports app.js back (one-directional: hub → feature → leaf).
//
// Owns: the `brush` tool state and all setup-mode DOM wiring, including the
// capture-phase board pointer listeners (chessground's `select` event doesn't
// reliably fire on EMPTY squares, so we own the click: map coordinates →
// square and stamp/erase, stopping chessground's own drag/selection).
//
// The play snapshot that Cancel restores stays HUB-owned (persist()/restore()
// serialize it across page reloads) — accessed only through the api's
// getPlaySnapshot/setPlaySnapshot/snapshotPlay/restorePlay seam.

import { INITIAL_FEN } from 'https://esm.sh/chessops@0.14.2/fen';

export const EMPTY_PLACEMENT = '8/8/8/8/8/8/8/8';
export const INITIAL_PLACEMENT = INITIAL_FEN.split(' ')[0];

// Palette piece codes → chessground piece objects.
const PIECE_CODES = {
  wK: { color: 'white', role: 'king' },   wQ: { color: 'white', role: 'queen' },
  wR: { color: 'white', role: 'rook' },    wB: { color: 'white', role: 'bishop' },
  wN: { color: 'white', role: 'knight' },  wP: { color: 'white', role: 'pawn' },
  bK: { color: 'black', role: 'king' },    bQ: { color: 'black', role: 'queen' },
  bR: { color: 'black', role: 'rook' },     bB: { color: 'black', role: 'bishop' },
  bN: { color: 'black', role: 'knight' },   bP: { color: 'black', role: 'pawn' },
};

let _api = null;
let brush = null; // setup tool: null = move/drag, 'erase', or a piece object

const byId = (id) => document.getElementById(id);
const state = () => _api.actions.getState();
const ground = () => _api.actions.getGround();

// --- brush stamping ----------------------------------------------------------

function eventSquare(e) {
  const boardEl = byId('board');
  const r = boardEl.getBoundingClientRect();
  const point = e.touches && e.touches[0] ? e.touches[0] : e;
  const col = Math.floor(((point.clientX - r.left) / r.width) * 8);
  const row = Math.floor(((point.clientY - r.top) / r.height) * 8);
  if (col < 0 || col > 7 || row < 0 || row > 7) return null;
  let fileIdx, rank;
  if (state().orientation === 'white') { fileIdx = col; rank = 8 - row; }
  else { fileIdx = 7 - col; rank = 1 + row; }
  return 'abcdefgh'[fileIdx] + rank;
}

function onBoardPointerDown(e) {
  if (state().mode !== 'setup' || !brush) return; // move tool → let chessground handle
  const sq = eventSquare(e);
  if (!sq) return;
  e.preventDefault();
  e.stopPropagation();
  ground().setPieces(new Map([[sq, brush === 'erase' ? undefined : brush]]));
  _api.hub.persist();
}

// --- transitions + tools -----------------------------------------------------

function showSetupUI(on) {
  byId('setup-bar').hidden = !on;
  byId('setup-toggle').hidden = on;
  document.body.classList.toggle('setup-mode', on);
}

function updatePaletteActive(tool) {
  document.querySelectorAll('#palette [data-tool], #palette [data-piece]').forEach((b) => {
    const id = b.dataset.tool || b.dataset.piece;
    b.classList.toggle('active', id === tool);
  });
}

// Switch the active editing tool. `tool` is 'move', 'erase', or a piece code.
function setTool(tool) {
  if (tool === 'move') brush = null;
  else if (tool === 'erase') brush = 'erase';
  else brush = PIECE_CODES[tool] || null;

  if (brush) {
    // Stamp mode: clicks place/erase; dragging disabled so no accidental moves.
    ground().set({
      movable: { free: false, color: undefined, dests: undefined },
      draggable: { enabled: false },
      selectable: { enabled: true },
    });
  } else {
    // Move tool: free drag to rearrange; drag off-board to delete.
    ground().set({
      movable: { free: true, color: 'both', dests: undefined },
      draggable: { enabled: true, deleteOnDropOff: true },
      selectable: { enabled: true },
    });
  }
  updatePaletteActive(tool);
}

function setSide(color) {
  state().setupColor = color === 'black' ? 'black' : 'white';
  byId('side-white').classList.toggle('active', state().setupColor === 'white');
  byId('side-black').classList.toggle('active', state().setupColor === 'black');
  _api.hub.persist();
}

function showSetupError(msg) {
  const el = byId('setup-error');
  el.textContent = msg;
  el.hidden = false;
}
function clearSetupError() { byId('setup-error').hidden = true; }

function emptyBoard() { ground().set({ fen: EMPTY_PLACEMENT }); _api.hub.persist(); }
function startPosition() { ground().set({ fen: INITIAL_PLACEMENT }); _api.hub.persist(); }

function enterSetup() {
  const { hub } = _api;
  // Non-destructive: snapshot the current game so Cancel can restore it.
  hub.setPlaySnapshot(hub.snapshotPlay());
  const { pos } = hub.positionAt(state().cursor);
  hub.setMode('setup');
  state().setupColor = pos.turn;
  ground().set({ fen: hub.fenOf(pos).split(' ')[0], lastMove: undefined, highlight: { lastMove: false, check: false } });
  enterSetupUI();
  hub.persist();
}

export function enterSetupUI() {
  showSetupUI(true);
  setSide(state().setupColor);
  setTool('move');
  clearSetupError();
  _api.hub.setStatus('Setup mode — arrange pieces, set side to move, then Begin Game.');
}

function exitSetupToPlay() {
  const { hub } = _api;
  brush = null;
  showSetupUI(false);
  ground().set({ highlight: { lastMove: true, check: true } });
  hub.syncBoard();        // restores play board config (legal dests, no free drag)
  hub.refreshAnalysis();  // evaluator back on
  hub.refreshOpeningThenTraps();
  hub.persist();
}

// Expand a FEN rank ("4P3") to 8 chars ("....P...").
function expandRank(r) { return r.replace(/\d/g, (d) => '.'.repeat(+d)); }

// Infer castling rights from a placement: rights only where king+rook sit home.
function inferCastling(placement) {
  const ranks = placement.split('/');
  if (ranks.length !== 8) return '-';
  const r1 = expandRank(ranks[7]); // white back rank (rank 1)
  const r8 = expandRank(ranks[0]); // black back rank (rank 8)
  let c = '';
  if (r1[4] === 'K') { if (r1[7] === 'R') c += 'K'; if (r1[0] === 'R') c += 'Q'; }
  if (r8[4] === 'k') { if (r8[7] === 'r') c += 'k'; if (r8[0] === 'r') c += 'q'; }
  return c || '-';
}

function friendlyPosError(e) {
  const m = String((e && e.message) || e || '');
  if (/empty/i.test(m)) return 'The board is empty.';
  if (/king/i.test(m)) return 'Need exactly one king of each color.';
  if (/opposite|impossible.*check|other.*check/i.test(m)) return 'The side NOT to move is in check — illegal.';
  if (/pawn/i.test(m)) return 'Illegal pawn placement (e.g. a pawn on the back rank).';
  if (/check/i.test(m)) return 'Illegal position (check rule violated).';
  return 'Illegal position — a game can’t start from here.';
}

function beginGame() {
  const { hub } = _api;
  const s = state();
  const placement = ground().getFen();
  const fen = `${placement} ${s.setupColor === 'white' ? 'w' : 'b'} ${inferCastling(placement)} - 0 1`;

  // Validate fully client-side before committing (chessops enforces kings,
  // check rules, pawns-on-backrank, etc.). The server re-validates on analyze.
  try {
    hub.positionFromFen(fen);
  } catch (e) {
    showSetupError(friendlyPosError(e));
    return;
  }

  s.baseFen = fen;
  s.moves = [];
  s.moveQuality = [];
  s.moveRetro = [];
  s.cursor = 0;
  hub.setMode('play');
  hub.setPlaySnapshot(null);
  exitSetupToPlay();
}

function cancelSetup() {
  const { hub } = _api;
  hub.restorePlay(hub.getPlaySnapshot() || { baseFen: INITIAL_FEN, moves: [], cursor: 0 });
  hub.setMode('play');
  hub.setPlaySnapshot(null);
  exitSetupToPlay();
}

// --- init ----------------------------------------------------------------------

export function initSetup(api) {
  _api = api;

  // Own board clicks for setup stamping (capture phase, before chessground).
  const boardEl = byId('board');
  boardEl.addEventListener('mousedown', onBoardPointerDown, true);
  boardEl.addEventListener('touchstart', onBoardPointerDown, { capture: true, passive: false });

  // Setup controls
  byId('setup-toggle').addEventListener('click', enterSetup);
  byId('begin-game').addEventListener('click', beginGame);
  byId('cancel-setup').addEventListener('click', cancelSetup);
  byId('empty-board').addEventListener('click', emptyBoard);
  byId('start-pos').addEventListener('click', startPosition);
  byId('side-white').addEventListener('click', () => setSide('white'));
  byId('side-black').addEventListener('click', () => setSide('black'));
  document.querySelectorAll('#palette [data-tool], #palette [data-piece]').forEach((b) => {
    b.addEventListener('click', () => setTool(b.dataset.tool || b.dataset.piece));
  });

  // The hub's dispatcher and ensurePlay() route through this registration.
  api.hub.registerModeHandlers('setup', { exit: cancelSetup });
}
