// Stockfish Analysis Board — frontend.
//
// chessground = board rendering (no chess rules).
// chessops    = chess rules: legal-move generation (dests), FEN, UCI parsing.
// The Python server is the authority on move legality + analysis; chessops here
// gives instant legal-dest highlighting / snap-back without a round-trip.
//
// FSM states (state.mode):
//   'play'          — one legal move at a time, evaluator on (the default).
//   'setup'         — free piece placement / palette editor, evaluator paused. On
//                     "Begin Game" the position is validated + committed as the new
//                     starting position (reusing the /api/load path).
//   'trap-watch'    — read-only step-through of a trap variation (view-only board).
//   'trap-practice' — interactive drill: the app auto-plays the victim's scripted
//                     replies; the user must find each trapper move. Legal-but-wrong
//                     moves snap back ("try again"); no quality label is ever shown.
//   'blunder-practice' — spaced-repetition drill over your own recorded blunders
//                     (trainer.js): board at the pre-blunder position, your move is
//                     checked server-side (/api/trainer/check). Transient like the
//                     other practice modes — never persisted.
//
// TODO(vendor): imported from a CDN (esm.sh resolves deps). To go offline,
// vendor chessground + chessops into static/vendor/ and update these imports.
import { Chessground } from 'https://esm.sh/chessground@9.1.1';
import { Chess } from 'https://esm.sh/chessops@0.14.2/chess';
import { parseFen, makeFen, INITIAL_FEN } from 'https://esm.sh/chessops@0.14.2/fen';
import { chessgroundDests } from 'https://esm.sh/chessops@0.14.2/compat';
import { parseSquare, parseUci } from 'https://esm.sh/chessops@0.14.2/util';
import { initPanel, renderAnalysisPanel, renderBookMovePanel, renderSkippedPanel } from './panel.js';
import { formatEval } from './format.js';
import { readUiPrefs, writeUiPref } from './prefs.js';
import { initMovelist } from './movelist.js';
import { initFeedback } from './feedback.js';
import { initShortcuts } from './shortcuts.js';
import { initReview, openGame } from './review.js';
import { initInsights } from './insights.js';
import { initSetup, enterSetupUI, EMPTY_PLACEMENT, INITIAL_PLACEMENT } from './setup.js';
import { initRepertoire } from './repertoire.js';
import { initTraps } from './traps.js';
import { initTrainer } from './trainer.js';
import { initBotplay } from './botplay.js';
import { initCmdk } from './cmdk.js';

// EMPTY_PLACEMENT / INITIAL_PLACEMENT are imported from setup.js (their home
// since the setup-editor extraction); persist() and init() still use them.

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  mode: 'play',     // 'play' | 'setup' | 'trap-watch' | 'trap-practice'
  baseFen: INITIAL_FEN,
  moves: [],        // UCI strings applied from baseFen
  cursor: 0,        // how many of `moves` are currently applied
  moveQuality: [],  // quality label per played move (transient; NOT persisted)
  moveRetro: [],    // { retroBest, retroSecond } per played move — carry-over cache (transient; NOT persisted)
  orientation: 'white',
  setupColor: 'white', // side-to-move while in setup mode
};

let ground = null;
let playSnapshot = null;   // saved play state captured when entering setup (for Cancel)
let reviewSnapshot = null; // saved play state captured when entering review mode (transient)
// --- bot-play carriers (owned here; consumed by botplay.js via the api hub) ---
// The prior play session to restore when the bot game exits. Set in-memory when
// botplay.js enters bot-play (same-session exit), or rehydrated from the
// persisted `priorPlay` on restore() (exit after a refresh). Shape = snapshotPlay().
let botPriorPlay = null;
// Latest bot-game descriptor, so persist() can re-serialize the game on every
// board change without botplay.js re-passing the whole thing. Shape:
// { baseFen, movesUci, cursor, userColor, personaLabel, personaId|'',
//   seed (number), result|null,
//   startedAt|'' (ISO minted at game start), saved (bool), rated (bool) }.
let botGame = null;
// Set true by restore() when a persisted bot game came back on the bot's turn
// (the user's move was saved but the reply never landed before refresh).
// botplay.js reads this once on init and schedules the pending bot move.
let botResumePending = false;
// Analysis request coalescing — prevents pile-ups during rapid undo/redo/move-list navigation.
let analysisInFlight = false; // true while a refreshAnalysis fetch is in progress
let analysisPending = false;  // true if another refresh was requested while in-flight
let analysisToken = 0;        // monotonic counter; stale responses are dropped
// Monotonic guard for the move-WRITE path (mirrors analysisToken). Bumped by every
// onUserMove and by every wholesale play-state swap (reset/loadFen/review/restore),
// so a slow /api/move response for a move the user abandoned mid-flight (undo, mode
// switch, a newer move) never writes stale history. See onUserMove's stale().
let moveToken = 0;
// Analyze-my-color preference: 'both' | 'white' | 'black'
let analyzeColor = (readUiPrefs().analyzeColor) || 'both';
// Engine speed preset: 'fast' | 'balanced' | 'deep'. Persisted (like analyzeColor).
// Sent on every /api/move and /api/analyze call in this module's play-mode path.
const VALID_ENGINE_SPEEDS = ['fast', 'balanced', 'deep'];
const _savedSpeed = readUiPrefs().engineSpeed;
let engineSpeed = VALID_ENGINE_SPEEDS.includes(_savedSpeed) ? _savedSpeed : 'balanced';
// Analysis mode: 'full' (evaluate + label everything) | 'blunders' (evaluate
// everything, only surface Blunder/Checkmate/Draw/Book) | 'off' (Stockfish never
// called; the Analysis panel FREEZES its last eval). Persisted — deliberately
// supersedes the old eval-toggle's session-only rule; the collapsed settings
// header shows a hint when the restored mode isn't 'full'.
const VALID_ANALYSIS_MODES = ['full', 'blunders', 'off'];
const _savedAnalysisMode = readUiPrefs().analysisMode;
let analysisMode = VALID_ANALYSIS_MODES.includes(_savedAnalysisMode) ? _savedAnalysisMode : 'full';

function shouldAnalyzeMove(moverColor) {
  if (analysisMode === 'off') return false;
  return analyzeColor === 'both' || moverColor === analyzeColor;
}

function shouldAnalyzeCursor(cursor) {
  if (analysisMode === 'off') return false;
  if (analyzeColor === 'both') return true;
  if (cursor === 0) return true; // cursor 0 EXEMPT — always show opening eval
  const before = positionAt(cursor - 1);
  return before.pos.turn === analyzeColor;
}

const byId = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Tiny event bus (used by the injected api and internal emitters).
// ---------------------------------------------------------------------------
const _busListeners = Object.create(null); // { [evt]: fn[] }

function on(evt, fn) {
  if (!_busListeners[evt]) _busListeners[evt] = [];
  _busListeners[evt].push(fn);
}

function emit(evt, ...args) {
  const fns = _busListeners[evt];
  if (fns) fns.forEach((fn) => { try { fn(...args); } catch (_) {} });
}

// ---------------------------------------------------------------------------
// Mode handler registry. Feature modules (setup/traps/repertoire) register the
// board-move handler and teardown for the modes they own; the ground
// events.after dispatcher and ensurePlay() look handlers up here instead of
// hard-referencing module functions. The bus can't carry these flows — they
// need ordered, awaitable control, and emit() swallows handler errors.
// ---------------------------------------------------------------------------
const _modeHandlers = Object.create(null); // { [mode]: { onMove?, exit? } }

// Modes whose board moves MUST have a registered handler — falling through to
// onUserMove would silently no-op (its early-returns), hiding a wiring bug.
// 'bot-play' is included: its user-move path lives in botplay.js's onMove (the
// play path treats every non-play response as stale), so a missing handler
// there must fail loudly rather than route to onUserMove.
const PRACTICE_MODES = new Set(['trap-practice', 'rep-practice', 'blunder-practice', 'bot-play']);

function registerModeHandlers(mode, handlers) {
  _modeHandlers[mode] = handlers;
}

// Set state.mode, reflect it on the body attribute, and emit the mode:change event.
// All mode transitions should go through this helper so listeners (tab-switch,
// body class watchers, etc.) are always notified.
function setMode(mode) {
  state.mode = mode;
  document.body.dataset.mode = mode;
  emit('mode:change', mode);
}

// ---------------------------------------------------------------------------
// Session persistence (localStorage). Mode-aware: in setup we save the working
// placement + the snapshot so a refresh keeps an in-progress setup AND its
// Cancel target. Legacy {baseFen,moves,...} entries (no `mode`) load as play.
// ---------------------------------------------------------------------------
const STORAGE_KEY = 'chess-training:session:v1';

function persist() {
  // bot-play: survive-refresh persistence. The single STORAGE_KEY slot means the
  // bot entry must EMBED the prior play snapshot (priorPlay) rather than coexist
  // with a separate play entry — otherwise exit-after-refresh has nothing to
  // restore. This branch sits ABOVE the practice-mode early-returns because those
  // modes are transient; bot-play is not. botGame/botPriorPlay are kept current by
  // botplay.js through the api hub; if either is missing (persist fired before the
  // game was set up) we skip rather than write a malformed entry.
  if (state.mode === 'bot-play') {
    if (!botGame || !botPriorPlay) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        mode: 'bot-play',
        botGame: {
          baseFen: botGame.baseFen,
          movesUci: (botGame.movesUci || []).slice(),
          cursor: botGame.cursor | 0,
          userColor: botGame.userColor === 'black' ? 'black' : 'white',
          personaLabel: botGame.personaLabel || '',
          personaId: botGame.personaId || '',
          seed: botGame.seed | 0,
          result: botGame.result || null,
          startedAt: botGame.startedAt || '',
          saved: !!botGame.saved,
          rated: !!botGame.rated,
          takebacksUsed: botGame.takebacksUsed | 0,
          ratedFlipped: !!botGame.ratedFlipped,
          timeControl: botGame.timeControl
            ? { baseSec: botGame.timeControl.baseSec | 0, incSec: botGame.timeControl.incSec | 0 }
            : null,
          clockWhite: botGame.clockWhite == null ? null : botGame.clockWhite | 0,
          clockBlack: botGame.clockBlack == null ? null : botGame.clockBlack | 0,
          moveTimes: (botGame.moveTimes || []).slice(),
        },
        priorPlay: {
          baseFen: botPriorPlay.baseFen,
          moves: (botPriorPlay.moves || []).slice(),
          cursor: botPriorPlay.cursor | 0,
          orientation: botPriorPlay.orientation === 'black' ? 'black' : 'white',
        },
      }));
    } catch (_) { /* best-effort */ }
    return;
  }
  if (state.mode === 'trap-watch') return;   // trap modes are transient — never persisted
  if (state.mode === 'trap-practice') return;// (both watch + practice)
  if (state.mode === 'rep-practice') return; // repertoire practice is transient too
  if (state.mode === 'blunder-practice') return; // blunder drill is transient too
  if (state.mode === 'review') return;       // review replay is transient — same precedent
  try {
    let data;
    if (state.mode === 'setup') {
      data = {
        mode: 'setup',
        orientation: state.orientation,
        setupPlacement: ground ? ground.getFen() : INITIAL_PLACEMENT,
        setupColor: state.setupColor,
        snapshot: playSnapshot,
      };
    } else {
      data = {
        mode: 'play',
        baseFen: state.baseFen,
        moves: state.moves,
        cursor: state.cursor,
        orientation: state.orientation,
      };
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (_) {
    // Storage full / disabled (e.g. private mode) — saving is best-effort.
  }
}

// Load saved session into `state`. Returns a descriptor ({mode, setupPlacement?})
// or null. Malformed data is ignored so a corrupt entry can't wedge the app.
function restore() {
  let data;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    data = JSON.parse(raw);
  } catch (_) {
    return null;
  }
  try {
    if (!data) return null;

    if (data.mode === 'bot-play') {
      // Validate the embedded shape. A malformed entry falls through to null so
      // the app boots into a clean play session rather than a half-loaded bot game.
      const bg = data.botGame;
      const pp = data.priorPlay;
      if (!bg || typeof bg.baseFen !== 'string' || !Array.isArray(bg.movesUci)) return null;
      if (!pp || typeof pp.baseFen !== 'string' || !Array.isArray(pp.moves)) return null;
      // Replay the bot game onto state.{baseFen,moves,cursor}; an illegal/unparseable
      // move throws → caught by the outer try → null (clean fallback).
      const pos = positionFromFen(bg.baseFen);
      for (const uci of bg.movesUci) {
        if (typeof uci !== 'string') return null;
        pos.play(parseUci(uci));
      }
      // Validate the embedded priorPlay the SAME way — it is replayed by
      // botExit()→restorePlay()→syncBoard() later, so a shaped-but-malformed
      // snapshot (bad FEN / illegal move) must be rejected here, not crash on exit.
      const ppPos = positionFromFen(pp.baseFen);
      for (const uci of pp.moves) {
        if (typeof uci !== 'string') return null;
        ppPos.play(parseUci(uci));
      }
      const cursor = Math.min(Math.max(0, bg.cursor | 0), bg.movesUci.length);
      const userColor = bg.userColor === 'black' ? 'black' : 'white';
      state.mode = 'bot-play';
      state.baseFen = bg.baseFen;
      state.moves = bg.movesUci.slice();
      state.moveQuality = [];
      state.moveRetro = [];
      state.cursor = cursor;
      state.orientation = userColor;
      // Keep the hub carriers current so a subsequent persist() re-serializes cleanly
      // and botplay.js's exit can restore the prior play session post-refresh.
      botGame = {
        baseFen: bg.baseFen,
        movesUci: bg.movesUci.slice(),
        cursor,
        userColor,
        personaLabel: bg.personaLabel || '',
        personaId: bg.personaId || '',
        seed: bg.seed | 0,
        result: bg.result || null,
        startedAt: bg.startedAt || '',
        saved: !!bg.saved,
        rated: !!bg.rated,
        takebacksUsed: bg.takebacksUsed | 0,
        ratedFlipped: !!bg.ratedFlipped,
        // Clocks are defensive: a missing/malformed timeControl coerces to
        // untimed (null); moveTimes MUST round-trip as an array (never the
        // scalar `| 0`/`!!` coercions, which would mangle it to 0).
        timeControl: (bg.timeControl && typeof bg.timeControl === 'object')
          ? { baseSec: bg.timeControl.baseSec | 0, incSec: bg.timeControl.incSec | 0 }
          : null,
        clockWhite: bg.clockWhite == null ? null : bg.clockWhite | 0,
        clockBlack: bg.clockBlack == null ? null : bg.clockBlack | 0,
        moveTimes: Array.isArray(bg.moveTimes) ? bg.moveTimes.slice() : [],
      };
      botPriorPlay = {
        baseFen: pp.baseFen,
        moves: pp.moves.slice(),
        cursor: pp.cursor | 0,
        orientation: pp.orientation === 'black' ? 'black' : 'white',
      };
      // Turn check: if the game isn't already over and it is the BOT's turn, the
      // reply never came back before the refresh — flag it so botplay.js schedules
      // the pending bot move on init. (positionAt() uses state, set above.)
      const botColor = userColor === 'white' ? 'black' : 'white';
      botResumePending = !botGame.result && (positionAt(cursor).pos.turn === botColor);
      return { mode: 'bot-play' };
    }

    if (data.mode === 'setup') {
      if (typeof data.setupPlacement !== 'string') return null;
      state.mode = 'setup';
      state.orientation = data.orientation === 'black' ? 'black' : 'white';
      state.setupColor = data.setupColor === 'black' ? 'black' : 'white';
      playSnapshot =
        data.snapshot && typeof data.snapshot.baseFen === 'string' && Array.isArray(data.snapshot.moves)
          ? { baseFen: data.snapshot.baseFen, moves: data.snapshot.moves, cursor: data.snapshot.cursor | 0 }
          : { baseFen: INITIAL_FEN, moves: [], cursor: 0 };
      return { mode: 'setup', setupPlacement: data.setupPlacement };
    }

    // play (also handles legacy entries with no `mode`)
    if (typeof data.baseFen !== 'string' || !Array.isArray(data.moves)) return null;
    const pos = positionFromFen(data.baseFen);
    for (const uci of data.moves) {
      if (typeof uci !== 'string') return null;
      pos.play(parseUci(uci));
    }
    state.mode = 'play';
    state.baseFen = data.baseFen;
    state.moves = data.moves;
    state.cursor = Math.min(Math.max(0, data.cursor | 0), data.moves.length);
    state.orientation = data.orientation === 'black' ? 'black' : 'white';
    return { mode: 'play' };
  } catch (_) {
    return null; // unparseable FEN / illegal move → fall back to defaults
  }
}

// --- play-state snapshots ---------------------------------------------------
// Canonical 5-field snapshot used by every mode transition (setup/trap/rep/
// review). Trainers keep their own copies; setup's Cancel target lives in the
// hub-owned `playSnapshot` because persist()/restore() serialize it.

function snapshotPlay() {
  return {
    baseFen: state.baseFen,
    moves: state.moves.slice(),
    moveQuality: state.moveQuality.slice(),
    moveRetro: state.moveRetro.slice(),
    cursor: state.cursor,
    orientation: state.orientation,
  };
}

// Tolerates the legacy 3-field shape restore() rebuilds from localStorage —
// moveQuality/moveRetro are transient and never persisted, so a snapshot that
// crossed a page reload arrives without them.
function restorePlay(snap) {
  moveToken++; // wholesale play-state swap — invalidate any move still in flight
  state.baseFen = snap.baseFen;
  state.moves = (snap.moves || []).slice();
  state.moveQuality = (snap.moveQuality || []).slice();
  state.moveRetro = (snap.moveRetro || []).slice();
  state.cursor = snap.cursor | 0;
  // Round-trip orientation so exiting bot-play restores the prior board side
  // (bot entry flipped it to the user's color). Tolerate the legacy shape.
  if (snap.orientation) state.orientation = snap.orientation === 'black' ? 'black' : 'white';
}

function getPlaySnapshot() { return playSnapshot; }
function setPlaySnapshot(snap) { playSnapshot = snap; }

// ---------------------------------------------------------------------------
// Bot-play hub seam (owned here; the whole surface botplay.js — T5 — compiles
// against). botplay.js receives the injected `api` and NEVER imports app.js, so
// everything it needs is reachable through these functions.
//
//   botEnter(prior)          — enter bot-play. `prior` = a snapshotPlay()-shaped
//                              object (or omitted → capture the current play
//                              session). Stashed in-memory for same-session exit.
//   botExit()                — leave bot-play: restore the prior play session
//                              (in-memory snapshot, or the persisted priorPlay
//                              after a refresh) and setMode('play').
//   botSetGame(game)         — set/replace the current bot-game descriptor
//                              { baseFen, movesUci, cursor, userColor,
//                              personaLabel, personaId, seed, result|null,
//                              startedAt, saved, rated, takebacksUsed,
//                              ratedFlipped, timeControl ({baseSec,incSec}|null
//                              untimed), clockWhite/clockBlack (remaining centis
//                              int, null when untimed), moveTimes (int[] per-ply
//                              remaining centis pre-increment, defaults []) }.
//                              Persisted by persist().
//   botGetGame()             — read the current bot-game descriptor (or null).
//   botAppendMove(uci)       — truncate history at cursor (redo suffix), push
//                              `uci`, advance cursor; mirrors state into botGame.
//   botSetResult(result)     — record a terminal result string (or null) on the
//                              bot game (drives persist + resume turn-check).
//   botMarkSaved(startedAt)  — identity-guarded: mark the current bot game saved
//                              (to the review pipeline) only if its startedAt
//                              still matches, then persist.
//   botConsumeResumePending()— read-and-clear the restore-time "bot to move" flag
//                              (true when a refresh landed on the bot's turn).
//   setBoardPosition(fen)    — set the chessground board to a raw FEN (board part).
//   setOrientation(color)    — orient the board to 'white' | 'black'.
//   setMovable(color, dests) — set which side may move + its legal dests
//                              (Map<string,string[]>); pass color=null to freeze
//                              the board (bot's turn / finished game).
// (persist, refreshAnalysis, setMode, snapshotPlay/restorePlay, positionFromFen,
//  positionAt, fenOf, isPromotion, askPromotion, postJSON are already on the hub.)
// ---------------------------------------------------------------------------

// Enter bot-play. Captures the prior play session (in-memory) for same-session
// exit; botplay.js calls this before setMode('bot-play'). If a snapshot is passed
// it is used verbatim (e.g. a caller that already snapshotted).
function botEnter(prior) {
  botPriorPlay = prior || snapshotPlay();
  botResumePending = false;
}

// Restore the prior play session and return to play mode. Prefers the in-memory
// snapshot (same session); falls back to the persisted priorPlay rehydrated by
// restore() after a refresh. Clears bot carriers, then normal play persist()
// resumes ownership of the STORAGE_KEY slot.
function botExit() {
  // Invalidate any analysis started while in bot-play: restorePlay bumps
  // moveToken, but an in-flight refreshAnalysis keys off analysisToken and would
  // otherwise render a bot-position eval onto the restored play board.
  analysisToken++;
  const snap = botPriorPlay || { baseFen: INITIAL_FEN, moves: [], cursor: 0 };
  restorePlay(snap);
  botGame = null;
  botPriorPlay = null;
  botResumePending = false;
  setMode('play');
  syncBoard();
  persist();
}

function botSetGame(game) {
  botGame = game ? {
    baseFen: game.baseFen,
    movesUci: (game.movesUci || []).slice(),
    cursor: game.cursor | 0,
    userColor: game.userColor === 'black' ? 'black' : 'white',
    personaLabel: game.personaLabel || '',
    personaId: game.personaId || '',
    seed: game.seed | 0,
    result: game.result || null,
    startedAt: game.startedAt || '',
    saved: !!game.saved,
    rated: !!game.rated,
    takebacksUsed: game.takebacksUsed | 0,
    ratedFlipped: !!game.ratedFlipped,
    timeControl: (game.timeControl && typeof game.timeControl === 'object')
      ? { baseSec: game.timeControl.baseSec | 0, incSec: game.timeControl.incSec | 0 }
      : null,
    clockWhite: game.clockWhite == null ? null : game.clockWhite | 0,
    clockBlack: game.clockBlack == null ? null : game.clockBlack | 0,
    moveTimes: Array.isArray(game.moveTimes) ? game.moveTimes.slice() : [],
  } : null;
  // Mirror into the canonical play-state so syncBoard/refreshAnalysis operate on it.
  // This is a wholesale state swap (like restorePlay): bump both guards so a
  // play-mode move-write or analysis response still in flight from BEFORE the swap
  // (e.g. a late /api/move when both old and new cursor are 0) is dropped, not
  // committed onto the bot game.
  if (botGame) {
    moveToken++;
    analysisToken++;
    state.baseFen = botGame.baseFen;
    state.moves = botGame.movesUci.slice();
    state.cursor = botGame.cursor;
  }
}

function botGetGame() { return botGame; }

// Append a user/bot move to the bot game's client history: truncate any redo
// suffix at the cursor, push, advance. Keeps state.moves and botGame in lockstep.
function botAppendMove(uci) {
  if (!botGame) return;
  const at = botGame.cursor;
  botGame.movesUci = botGame.movesUci.slice(0, at);
  botGame.movesUci.push(uci);
  botGame.cursor = at + 1;
  state.moves = botGame.movesUci.slice();
  state.cursor = botGame.cursor;
}

// Rewind the last full move pair (user move + bot reply → 2 plies) so it's the
// user's turn again. Bot-mode-local — reached only via the hub (botplay.js never
// imports app.js); the global undo()/redo() stay untouched. Truncates botGame +
// state in lockstep, bumps both guards (drop a stale in-flight bot-position eval
// landing on the rewound board), re-renders via syncBoard() (renders from
// state.cursor → correct fen/turnColor/lastMove, NOT a bare board-only reset),
// and flips a rated game to casual once (idempotent). Returns the new counter +
// rated state + whether THIS call flipped it, so botplay.js can update the UI;
// returns null if fewer than 2 plies exist (no full pair to take back).
function botTakeback() {
  if (!botGame || botGame.movesUci.length < 2) return null;
  botGame.movesUci = botGame.movesUci.slice(0, botGame.movesUci.length - 2);
  botGame.cursor = botGame.movesUci.length;
  // botGame↔state lockstep (same dual-write as botAppendMove).
  state.moves = botGame.movesUci.slice();
  state.cursor = botGame.cursor;
  botGame.takebacksUsed = (botGame.takebacksUsed | 0) + 1;
  let flippedToCasual = false;
  if (botGame.rated) { botGame.rated = false; flippedToCasual = true; botGame.ratedFlipped = true; }
  // Clock restore (timed games only): keep moveTimes aligned with the truncated
  // movesUci, then reset each side's live clock to its remaining centis after its
  // last SURVIVING move. Parity is by ABSOLUTE ply index from game start (even =
  // White, odd = Black), independent of userColor. A side with no surviving move
  // resets to its full base time.
  if (botGame.timeControl) {
    const len = botGame.movesUci.length;
    botGame.moveTimes = (botGame.moveTimes || []).slice(0, len);
    const base = (botGame.timeControl.baseSec | 0) * 100;
    // last even index < len, and last odd index < len.
    const lastEven = len > 0 ? (len - 1) - ((len - 1) % 2) : -1;
    const lastOdd = len > 1 ? (len - 1) - (1 - ((len - 1) % 2)) : -1;
    botGame.clockWhite = lastEven >= 0 ? (botGame.moveTimes[lastEven] | 0) : base;
    botGame.clockBlack = lastOdd >= 0 ? (botGame.moveTimes[lastOdd] | 0) : base;
  }
  // Wholesale truncation: drop any move-write / analysis response still in flight
  // from before the rewind (as botSetGame does on a state swap).
  moveToken++;
  analysisToken++;
  syncBoard(); // full ground.set from state.cursor: fen + turnColor + lastMove.
  persist();
  return {
    takebacksUsed: botGame.takebacksUsed,
    rated: botGame.rated,
    flippedToCasual,
    clockWhite: botGame.clockWhite,
    clockBlack: botGame.clockBlack,
  };
}

function botSetResult(result) {
  if (botGame) botGame.result = result || null;
}

// Mark the current bot game as saved to the review pipeline — identity-guarded so
// a stale save POST completing AFTER a New-game (which replaced botGame) can't
// mark the NEW game saved. Only sets when the live descriptor's startedAt still
// matches the one the save was launched for; then persists the flag.
function botMarkSaved(startedAt) {
  if (botGame && botGame.startedAt === startedAt) {
    botGame.saved = true;
    persist();
  }
}

function botConsumeResumePending() {
  const v = botResumePending;
  botResumePending = false;
  return v;
}

// --- board control helpers (bot-play; thin wrappers over ground.set) ---------

function setBoardPosition(fen) {
  if (ground) ground.set({ fen: fen.split(' ')[0] });
}

function setOrientation(color) {
  state.orientation = color === 'black' ? 'black' : 'white';
  if (ground) ground.set({ orientation: state.orientation });
}

// color=null freezes the board (no side may move — bot's turn or finished game).
function setMovable(color, dests) {
  if (!ground) return;
  ground.set({
    movable: { free: false, color: color || undefined, dests: color ? dests : undefined },
    draggable: { enabled: !!color, deleteOnDropOff: false },
  });
}

// --- position helpers ------------------------------------------------------

function positionFromFen(fen) {
  const setup = parseFen(fen).unwrap();
  return Chess.fromSetup(setup).unwrap();
}

// Replay `count` moves from the base FEN; return { pos, lastMove }.
function positionAt(count) {
  const pos = positionFromFen(state.baseFen);
  let lastMove = null;
  for (let i = 0; i < count; i++) {
    const move = parseUci(state.moves[i]);
    pos.play(move);
    lastMove = state.moves[i];
  }
  return { pos, lastMove };
}

function fenOf(pos) {
  return makeFen(pos.toSetup());
}

function lastMoveSquares(uci) {
  if (!uci) return undefined;
  return [uci.slice(0, 2), uci.slice(2, 4)];
}

// --- board sync (play mode + review mode) -----------------------------------
//
// In review mode the board is view-only (no movable dests, no drag).
// In play mode the board shows legal dests for the side to move.
// Both modes emit 'position:change' so movelist re-renders.

function syncBoard() {
  const { pos, lastMove } = positionAt(state.cursor);
  const fen = fenOf(pos);
  if (state.mode === 'review') {
    ground.set({
      fen: fen.split(' ')[0],
      turnColor: pos.turn,
      orientation: state.orientation,
      lastMove: lastMoveSquares(lastMove),
      movable: { free: false, color: undefined, dests: undefined },
      draggable: { enabled: false },
    });
    emit('position:change');
    emit('review:ply', state.cursor);
    return;
  }
  ground.set({
    fen: fen.split(' ')[0],
    turnColor: pos.turn,
    orientation: state.orientation,
    lastMove: lastMoveSquares(lastMove),
    movable: { free: false, color: pos.turn, dests: chessgroundDests(pos) },
    draggable: { enabled: true, deleteOnDropOff: false },
  });
  emit('position:change');
}

// --- promotion picker ------------------------------------------------------

function isPromotion(pos, from, to) {
  const piece = pos.board.get(parseSquare(from));
  if (!piece || piece.role !== 'pawn') return false;
  const rank = to[1];
  return (piece.color === 'white' && rank === '8') ||
         (piece.color === 'black' && rank === '1');
}

function askPromotion() {
  // Prefer the <dialog id="promo-dialog"> introduced by T1. Fall back to the
  // legacy #promo-overlay if the dialog is absent (isolation / old HTML).
  const dialog = byId('promo-dialog');
  if (dialog) {
    return new Promise((resolve, reject) => {
      // Clean up any prior listeners before re-opening.
      const clone = dialog.cloneNode(true);
      dialog.parentNode.replaceChild(clone, dialog);
      const d = byId('promo-dialog');

      d.returnValue = '';

      // A piece click records the choice in returnValue, then closes the dialog.
      d.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-piece]');
        if (!btn) return;
        d.returnValue = btn.dataset.piece;
        d.close();
      });

      // 'close' is the SOLE settlement point — it fires for both a piece-pick
      // close() and an Esc/backdrop cancel. returnValue distinguishes them, so
      // the Promise settles exactly once (no double-settle).
      d.addEventListener('close', () => {
        if (d.returnValue) resolve(d.returnValue);
        else reject(new Error('promotion-cancelled'));
      });

      d.showModal();
    });
  }

  // Fallback: legacy overlay (graceful degradation when #promo-dialog absent).
  const overlay = byId('promo-overlay');
  if (overlay) {
    return new Promise((resolve) => {
      overlay.hidden = false;
      const handler = (e) => {
        const btn = e.target.closest('button[data-piece]');
        if (!btn) return;
        overlay.hidden = true;
        overlay.removeEventListener('click', handler);
        resolve(btn.dataset.piece);
      };
      overlay.addEventListener('click', handler);
    });
  }

  // Last resort: no UI available — resolve with queen.
  return Promise.resolve('q');
}

// --- server calls ----------------------------------------------------------

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.status === 503) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Engine unavailable.');
  }
  return res.json();
}

async function refreshAnalysis() {
  // Coalesce rapid calls (undo/redo/move-list clicks): if a fetch is already
  // in progress, mark that another is wanted and return immediately. The
  // finally block below will re-invoke once the current request settles,
  // picking up whatever position the user ended up at — so the final position
  // always gets analyzed, never silently dropped.
  // Bump the stale-guard token on EVERY call — including coalesced ones below.
  // A rapid undo/redo that hits the in-flight early-return must still invalidate
  // the request already running, or its response renders analysis for a cursor
  // the board has since moved past (illegal "best" moves flash on screen).
  const myToken = ++analysisToken;
  if (analysisInFlight) {
    analysisPending = true;
    return;
  }
  analysisInFlight = true;

  emit('analysis:start');
  setStatus('Analyzing…');
  try {
    // Analysis off → FREEZE: leave the panel's last-rendered eval untouched.
    // Must NOT renderSkipped() (that blanks it); just clear status + balance the event.
    if (analysisMode === 'off') { setStatus(''); emit('analysis:end'); return; }
    if (!shouldAnalyzeCursor(state.cursor)) { renderSkipped(); setStatus(''); emit('analysis:end'); return; }
    if (state.cursor === 0) {
      const data = await postJSON('/api/analyze', { fen: state.baseFen, speed: engineSpeed });
      if (myToken !== analysisToken) { emit('analysis:end'); return; } // stale — drop
      renderAnalysis(data.analysis, analysisOpts(data.analysis));
    } else {
      const before = positionAt(state.cursor - 1);
      const data = await postJSON('/api/move', {
        fen: fenOf(before.pos),
        move: state.moves[state.cursor - 1],
        useBook: true,
        speed: engineSpeed,
      });
      if (myToken !== analysisToken) { emit('analysis:end'); return; } // stale — drop
      applyMoveResponse(data);
      // Refresh the retro cache for this already-played move (index = cursor - 1).
      state.moveRetro[state.cursor - 1] = (!data.book && data.analysis)
        ? { retroBest: data.analysis.retroBest, retroSecond: data.analysis.retroSecond }
        : null;
    }
    setStatus('');
    emit('analysis:end');
  } catch (err) {
    emit('analysis:end');
    // Non-OK / 503 / network failure: show a clear recovery prompt and stop.
    // Do NOT auto-retry — the user must restart the engine explicitly.
    if (myToken !== analysisToken) return; // stale error from a superseded request
    setStatus('Engine stopped responding — click Restart engine', true);
  } finally {
    analysisInFlight = false;
    if (analysisPending) {
      analysisPending = false;
      // Re-read current state fresh so we analyze wherever the user ended up,
      // not a position captured at call time.
      refreshAnalysis();
    }
  }
}

// --- move handling (play mode) ---------------------------------------------

async function onUserMove(orig, dest) {
  // trap-watch is view-only — ignore any board interaction.
  if (state.mode === 'trap-watch') return;
  // trap-practice has its own input path (onTrapMove, wired separately) — the
  // play handler must never fire there.
  if (state.mode === 'trap-practice') return;
  // In setup mode, drags just rearrange pieces — no server call, no history.
  if (state.mode === 'setup') { persist(); return; }

  const before = positionAt(state.cursor);
  // Capture where this move belongs BEFORE any await. `onUserMove` awaits the
  // engine (and maybe a promotion dialog); meanwhile undo/redo/goto, a mode switch,
  // or a wholesale state swap can move the cursor or replace the whole line. If any
  // of that happened by the time a response lands, the move was abandoned — drop it
  // rather than writing history against a cursor/base that no longer matches. Keying
  // the commit off `insertAt` (not a re-read of state.cursor) is the actual fix.
  const insertAt = state.cursor;
  const myMove = ++moveToken;
  // Mode gate accepts play OR bot-play (Gate-1: live eval stays on during bot
  // games). The token + cursor checks are the real staleness discipline: a late
  // response after a bot reply moved the position (or after a mode exit) fails
  // myMove/cursor and is dropped. botplay.js owns bot moves via its own onMove,
  // so onUserMove won't normally run in bot-play, but the gate stays consistent.
  const stale = () => (state.mode !== 'play' && state.mode !== 'bot-play') || myMove !== moveToken || state.cursor !== insertAt;

  let promo = '';
  if (isPromotion(before.pos, orig, dest)) {
    try {
      promo = await askPromotion();
    } catch (_) {
      // Promotion dialog dismissed (Esc/cancel) — restore the board and abort.
      syncBoard();
      return;
    }
    // Undo / mode switch can fire while the promotion <dialog> is open — bail here
    // before we waste an /api/move round-trip and flash "Analyzing…".
    if (stale()) { syncBoard(); return; }
  }
  const uci = orig + dest + promo;
  const fenBefore = fenOf(before.pos);
  const moverColor = before.pos.turn;
  const doAnalyze = shouldAnalyzeMove(moverColor);

  // Analysis off still round-trips /api/move (legality + move-write), but no engine
  // runs — so don't flash "Analyzing…". Analyze-color skip (on, wrong color) keeps it.
  if (analysisMode !== 'off') setStatus('Analyzing…');
  let data;
  try {
    data = await postJSON('/api/move', { fen: fenBefore, move: uci, useBook: true, analyze: doAnalyze, speed: engineSpeed });
  } catch (err) {
    // A stale failure (move already abandoned mid-flight) must not stomp the status
    // bar with an error — the navigating action owns the status line now.
    if (stale()) { syncBoard(); return; }
    setStatus(err.message, true);
    syncBoard();
    return;
  }

  // Navigated away / superseded while analyzing → drop the write so the move list
  // (and whose-turn-it-is) stays intact. This is the corruption fix.
  if (stale()) { syncBoard(); return; }

  if (!data.legal) {
    setStatus('Illegal move.', true);
    syncBoard();
    return;
  }

  // Commit at the captured `insertAt`, NOT a re-read of state.cursor — a re-read is
  // exactly what the race corrupted (a late response truncating against a moved cursor).
  // stale() above guarantees state.cursor === insertAt here, so this is equivalent on
  // the happy path and safe on the racy one.
  state.moves = state.moves.slice(0, insertAt);
  state.moveQuality = state.moveQuality.slice(0, insertAt);
  state.moveRetro = state.moveRetro.slice(0, insertAt);  // lockstep with moveQuality
  state.moves.push(uci);
  // Index-assign (not push): if moveQuality is shorter than the history — e.g. after a
  // restore/jump where prior moves have no recorded quality — this still lands the new
  // move's quality at the correct index (gaps stay undefined → render neutral).
  state.moveQuality[insertAt] = data.book ? 'book' : (doAnalyze ? ((data.analysis && data.analysis.quality) || null) : null);
  // Cache the retrospective (what the mover should have played) at the same index;
  // null on book/skipped moves so the carry-over scan walks past them.
  state.moveRetro[insertAt] = (!data.book && doAnalyze && data.analysis)
    ? { retroBest: data.analysis.retroBest, retroSecond: data.analysis.retroSecond }
    : null;
  state.cursor = insertAt + 1;

  syncBoard();
  // Claim the analysis panel: invalidate any refreshAnalysis still in flight from an
  // earlier undo/redo. Without this, its late response passes its own analysisToken
  // check and repaints THIS position's panel with the previous position's eval/PV —
  // the engine result for the wrong side. (onUserMove renders directly, outside the
  // refreshAnalysis token machinery, so it must bump the token itself.)
  analysisToken++;
  // Render gate re-reads the CURRENT mode (doAnalyze was captured pre-await): a
  // switch to Off while /api/move was in flight must keep the panel frozen, not
  // repaint it. Off → FREEZE. Analyze-color skip → renderSkipped().
  if (analysisMode === 'off') { /* freeze */ }
  else if (doAnalyze) applyMoveResponse(data);
  else renderSkipped();
  setStatus('');
  persist();
  refreshOpeningThenTraps(); // fire-and-forget: opening then traps check, sequential
}

// --- rendering -------------------------------------------------------------

// `opts.suppressQuality` forces the quality label to '—' regardless of the
// engine's verdict. Trap practice passes it so a real "Blunder!" on a
// deliberately dubious trapper move never contradicts the lesson.
// Delegates to the panel module — this wrapper keeps internal call sites stable.
function renderAnalysis(a, opts = {}) {
  renderAnalysisPanel(a, opts);
}

// Blunders-only display filter. Computed at RENDER time (current mode, not one
// captured pre-await) and threaded only at this module's play-path call sites —
// never a flag inside panel.js, which is shared with review replay (via
// hub.renderAnalysis) and trap practice (direct renderAnalysisPanel calls);
// those paths must not inherit the filter. Checkmate/Draw stay visible (they
// are game-enders, not quality coaching); eval number/bar stay too, but the
// best move + PV are suppressed so a quiet non-blunder never reveals the top line.
function analysisOpts(a) {
  if (analysisMode !== 'blunders') return {};
  const q = a && a.quality;
  if (q === 'blunder' || q === 'checkmate' || q === 'draw') return {};
  return { suppressQuality: true, suppressRetro: true, suppressBest: true };
}

// Book move: the server skipped Stockfish (the line is known theory), so there is
// no eval/best/PV — show a calm "Book Move" badge in the quality slot, naming the
// line when the server identified one ("Book Move · Ruy Lopez").
// Delegates to the panel module — this wrapper keeps internal call sites stable.
function renderBookMove(data) {
  renderBookMovePanel(data);
}

// Opponent's move was skipped per analyze-color preference — show neutral panel,
// but carry over your last analyzed move's retrospective so it isn't fully blank.
// Scan down from the current move index for the nearest cached retro (the literal
// test is "cache entry exists" — book/skipped plies leave a falsy hole to walk past).
function renderSkipped() {
  let carried = null;
  let pvCursor = -1;
  for (let j = state.cursor - 1; j >= 0; j--) {
    if (state.moveRetro[j]) { carried = state.moveRetro[j]; pvCursor = j; break; }
  }
  // Blunders-only: a filtered non-blunder's "should've played" must not resurface
  // via this carry-over after a skipped opponent ply — drop it unless the carried
  // move actually was a blunder.
  if (analysisMode === 'blunders' && carried && state.moveQuality[pvCursor] !== 'blunder') {
    carried = null;
    pvCursor = -1;
  }
  renderSkippedPanel(carried, pvCursor);
}

// Render a play-mode /api/move response: a book move shows the badge (no engine
// ran); otherwise the normal analysis panel. Check `book` BEFORE the legal/analysis
// fallback so undo back into book restores the badge instead of a blank panel.
function applyMoveResponse(data) {
  if (data && data.book) { renderBookMove(data); return; }
  const a = data && data.legal ? data.analysis : null;
  renderAnalysis(a, analysisOpts(a));
}

function setStatus(msg, isError = false) {
  const el = byId('status');
  el.textContent = msg || '';
  el.classList.toggle('error', !!isError);
}

// --- play controls ---------------------------------------------------------

function undo() {
  if (state.mode !== 'play' || state.cursor === 0) return;
  state.cursor -= 1;
  syncBoard();
  refreshAnalysis();
  refreshOpeningThenTraps();
  persist();
}

function redo() {
  if (state.mode !== 'play' || state.cursor >= state.moves.length) return;
  state.cursor += 1;
  syncBoard();
  refreshAnalysis();
  refreshOpeningThenTraps();
  persist();
}

// Jump to an arbitrary ply (move-list click / Home / End). Mirrors undo/redo.
// Broadened to support 'review' mode (Refuter resolution #3): in review mode
// we sync the board and emit review:ply instead of refreshing analysis/opening.
function goto(n) {
  if (state.mode !== 'play' && state.mode !== 'review') return;
  const target = Math.min(Math.max(0, n | 0), state.moves.length);
  if (target === state.cursor) return;
  state.cursor = target;
  syncBoard();
  if (state.mode === 'review') {
    emit('review:ply', state.cursor);
    return; // no analysis refresh or persist in review mode
  }
  refreshAnalysis();
  refreshOpeningThenTraps();
  persist();
}

function flip() {
  state.orientation = state.orientation === 'white' ? 'black' : 'white';
  ground.set({ orientation: state.orientation });
  persist();
}

function reset() {
  if (state.mode !== 'play') return;
  moveToken++; // invalidate any in-flight move against the old line
  state.baseFen = INITIAL_FEN;
  state.moves = [];
  state.moveQuality = [];
  state.moveRetro = [];
  state.cursor = 0;
  byId('fen-error').hidden = true;
  syncBoard();
  refreshAnalysis();
  refreshOpeningThenTraps();
  persist();
}

async function loadFen() {
  const input = byId('fen-input');
  const errEl = byId('fen-error');
  const fen = input.value.trim();
  if (!fen) return;

  try {
    positionFromFen(fen);
  } catch {
    errEl.textContent = 'Invalid FEN.';
    errEl.hidden = false;
    return;
  }

  let data;
  try {
    data = await postJSON('/api/load', { fen });
  } catch (err) {
    errEl.textContent = err.message;
    errEl.hidden = false;
    return;
  }
  if (!data.valid) {
    errEl.textContent = data.error || 'Invalid FEN.';
    errEl.hidden = false;
    return;
  }

  errEl.hidden = true;
  moveToken++;     // invalidate any in-flight move against the previous base position
  analysisToken++; // ...and any in-flight refreshAnalysis, so it can't repaint the
                   // loaded position's panel with the old position's eval.
  state.baseFen = data.fen;
  state.moves = [];
  state.moveQuality = [];
  state.moveRetro = [];
  state.cursor = 0;
  syncBoard();
  // Off → keep the frozen panel (the server analyzed anyway — /api/load has no
  // analyze flag; that engine cost is a pre-existing gap, display-gated here).
  if (analysisMode !== 'off') renderAnalysis(data.analysis, analysisOpts(data.analysis));
  persist();
  refreshOpeningThenTraps();
  emit('toast:show', 'Position loaded');
}

// (Setup editor lives in setup.js — extracted whole; it registers its own
// mode handlers and DOM wiring via initSetup(api).)

// --- opening trainer: live name detection ----------------------------------

// Fire-and-forget after any play-line change. Fully isolated: a slow/failed
// opening call never blocks or breaks move handling or the eval render.
// Returns its promise so callers (e.g. refreshOpeningThenTraps) can sequence
// the traps check AFTER this resolves — but callers need NOT await it.
async function refreshOpening() {
  if (state.mode !== 'play') return;
  try {
    const body = { baseFen: state.baseFen, moves: state.moves.slice(0, state.cursor) };
    const data = await postJSON('/api/opening', body);
    renderOpening(data);
  } catch (_) {
    // Isolated by design — opening data is non-critical.
  }
}

// Sequentially fire refreshOpening then the traps chip check so both network
// calls don't burst simultaneously. Always fire-and-forget at the call site.
// The chip check lives in traps.js, which listens for 'traps:check' on the bus
// (fire-and-forget with its own try/catch + token — the bus's exact contract).
async function refreshOpeningThenTraps() {
  await refreshOpening();
  emit('traps:check');
}

// Passive readout only: name + ECO of the current line, or "—".
function renderOpening(data) {
  const nameEl = byId('opening-name');
  if (data && data.current) {
    nameEl.textContent = `${data.current.name} (${data.current.eco})`;
  } else {
    nameEl.textContent = '—';
  }
}

// (Traps trainer — browse, live chip, watch, practice — lives in traps.js;
// extracted whole. It registers its own mode handlers, DOM wiring, and the
// bus listener for 'traps:check' via initTraps(api).)

// (Repertoire trainer lives in repertoire.js — extracted whole; it registers
// its own mode handlers and DOM wiring via initRepertoire(api).)


// Ensure we are back in clean play mode before a jump/practice entry.
// Dispatches to the exit handler registered for the current mode; modes with
// no registration (play, review) are a no-op — same as the old if/else chain.
function ensurePlay() {
  const h = _modeHandlers[state.mode];
  if (h && h.exit) h.exit();
}

// Per-mode confirm copy (only for modes that register isDirty and report dirty)
// and the contextual line shown in #mode-indicator while the mode is active.
const MODE_CONFIRM = {
  setup: 'Leave setup? Your in-progress position will be discarded.',
  'rep-practice': 'Leave this practice line? Your progress in it will be lost.',
  'blunder-practice': 'Leave this drill? Progress on the current puzzle is lost.',
};
const MODE_INDICATOR = {
  setup: 'Setting up a position — pick any tab to leave setup.',
  'trap-watch': 'Watching a trap — pick any tab to leave.',
  'trap-practice': 'Practising a trap — pick any tab to leave.',
  'rep-practice': 'Practising a prepared line — pick any tab to leave.',
  'blunder-practice': 'In a blunder drill — pick any tab to leave.',
  'bot-play': 'Playing vs a bot — pick any tab to leave.',
  review: 'Reviewing a saved game — pick any tab to leave.',
};

// Attempt to leave the current special mode back to play so a tab switch (or any
// caller) can proceed. Returns true if we end up in play (already were, or the
// exit ran), false only if the user cancels a dirty-mode confirm. Routes through
// the registered exit() via ensurePlay() so mode side effects are preserved
// (e.g. exitTrainer's Leitner flush) — never a bare setMode('play').
function requestModeExit() {
  const mode = state.mode;
  if (mode === 'play') return true;
  const h = _modeHandlers[mode];
  const dirty = h && h.isDirty ? h.isDirty() : false;
  if (dirty && !window.confirm(MODE_CONFIRM[mode] || 'Leave this mode? Your progress here will be lost.')) {
    return false;
  }
  ensurePlay();
  return true;
}


// --- review mode -----------------------------------------------------------
//
// Enters a transient 'review' mode that loads a saved game's {baseFen, moves}
// onto the existing board. Mirrors the trap/rep snapshot pattern: the play
// session is saved into reviewSnapshot and is NEVER persisted.
// `goto()` emits 'review:ply' so review.js can drive foresight cards.

function showReviewUI(on) {
  byId('review-bar').hidden = !on;
  // The AI commentary + foresight/moment cards now live in the Analysis panel's
  // right column (not under #review-bar), so they no longer inherit #review-bar's
  // hidden — toggle that column with review mode so it collapses in play mode.
  byId('analysis-review-col').hidden = !on;
  if (on) byId('trap-chip').hidden = true;
}

// Enter review mode for a saved game. Called from review.js via api.actions.
// `gameDetail` is a GameDetail object from GET /api/games/{id}: {id, white, black,
//  result, baseFen?, moves?, plies, analysis_status, ...}
// We reconstruct baseFen from the first ply's fen_before (or the standard start),
// and moves from the plies' uci fields.
function enterReview(gameDetail) {
  // Snapshot current play session (same precedent as trap/rep).
  if (state.mode === 'play') {
    reviewSnapshot = {
      baseFen: state.baseFen,
      moves: state.moves.slice(),
      moveQuality: state.moveQuality.slice(),
      moveRetro: state.moveRetro.slice(),
      cursor: state.cursor,
    };
  }

  // Derive baseFen + moves from the plies array or fallback to INITIAL_FEN.
  const plies = (gameDetail.plies && gameDetail.plies.length) ? gameDetail.plies : [];
  const baseFen = (plies.length && plies[0].fen_before) ? plies[0].fen_before : INITIAL_FEN;
  const moves = plies.map((p) => p.uci).filter(Boolean);

  moveToken++; // a play move still analyzing must not write into the review game
  state.baseFen = baseFen;
  state.moves = moves;
  state.moveQuality = [];
  state.moveRetro = [];
  state.cursor = 0;

  setMode('review');
  showReviewUI(true);

  // Set the game title.
  const white = gameDetail.white || '?';
  const black = gameDetail.black || '?';
  const result = gameDetail.result || '';
  byId('review-game-title').textContent = `${white} vs ${black}${result ? ' · ' + result : ''}`;

  // Sync the board to the start position (view-only — no legal dests).
  const pos = positionFromFen(baseFen);
  ground.set({
    fen: baseFen.split(' ')[0],
    turnColor: pos.turn,
    orientation: state.orientation,
    lastMove: undefined,
    movable: { free: false, color: undefined, dests: undefined },
    draggable: { enabled: false },
  });

  // Emit position:change so movelist re-renders (broadened to accept review mode).
  emit('position:change');
  // Emit review:ply at ply 0 so foresight initializes.
  emit('review:ply', 0);
}

// Deep-link action for feature modules (e.g. insights.js): open a saved game
// in review-replay mode, then jump straight to a given ply. Wraps review.js's
// openGame (fetch + enterReview, which lands on ply 0) + the goto seam.
async function openGameAtPly(gameId, ply) {
  await openGame(gameId);
  goto(ply);
}

// Exit review mode and restore the saved play snapshot.
function exitReview() {
  const snap = reviewSnapshot || { baseFen: INITIAL_FEN, moves: [], cursor: 0 };
  moveToken++; // returning to play with a restored cursor — invalidate stale in-flight moves
  state.baseFen = snap.baseFen;
  state.moves = snap.moves;
  state.moveQuality = snap.moveQuality || [];
  state.moveRetro = snap.moveRetro || [];
  state.cursor = snap.cursor;
  setMode('play');
  reviewSnapshot = null;
  showReviewUI(false);
  ground.set({ highlight: { lastMove: true, check: true } });
  syncBoard();
  refreshAnalysis();
  refreshOpeningThenTraps();
  persist();
}

// Review's enter/exit live in the hub (not a feature module), so register its
// exit here — this lets ensurePlay()/requestModeExit() dispatch review uniformly
// with every other special mode. Review replay is cheap (only a ply cursor), so
// isDirty is always false → a tab switch leaves review without a confirm.
registerModeHandlers('review', { exit: exitReview, isDirty: () => false });

// --- init ------------------------------------------------------------------

function init() {
  const restored = restore();

  // Sync body attribute from the restored state (before any mode transitions fire).
  document.body.dataset.mode = state.mode;

  const initialFen = state.mode === 'setup'
    ? ((restored && restored.setupPlacement) || EMPTY_PLACEMENT)
    : fenOf(positionAt(state.cursor).pos).split(' ')[0];

  ground = Chessground(byId('board'), {
    fen: initialFen,
    orientation: state.orientation,
    movable: {
      free: false,
      color: 'white',
      dests: undefined,
      showDests: true,
      events: {
        after: (orig, dest) => {
          // trap-practice and rep-practice each have their own validated move
          // path (registered in the mode-handler registry); everything else
          // (play/setup) goes through onUserMove (study/trap-watch early-return).
          const h = _modeHandlers[state.mode];
          if (h && h.onMove) { h.onMove(orig, dest); return; }
          if (PRACTICE_MODES.has(state.mode)) {
            // A practice mode with no registered handler is a wiring bug —
            // fail loudly; falling through to onUserMove would silently no-op.
            console.error(`No move handler registered for mode "${state.mode}"`);
            setStatus('Internal error: move handler missing — reload the page.', true);
            return;
          }
          onUserMove(orig, dest);
        },
      },
    },
    draggable: { deleteOnDropOff: true },
    highlight: { lastMove: true, check: true },
    animation: { enabled: true, duration: 150 },
    events: {
      change: () => { if (state.mode === 'setup') persist(); },
    },
  });

  // Build the injected api — after ground is created so getGround() is valid.
  function closeAnyDialog() {
    document.querySelectorAll('dialog[open]').forEach((d) => d.close());
  }

  const api = {
    actions: {
      undo,
      redo,
      flip,
      reset,
      goto,
      stepBack: undo,       // stepBack/stepForward = undo/redo (cursor −/+)
      stepForward: redo,
      getState: () => state,
      getGround: () => ground,
      getAnalysisMode: () => analysisMode, // movelist reads this to filter quality dots
      closeAnyDialog,
      enterReview,           // called by review.js when the user opens a saved game
      exitReview,            // called by review.js "Return to my game"
      openGameAtPly,         // deep-link seam: insights.js → game+ply in review mode
    },
    // Shared hub services for extracted feature modules (setup/traps/
    // repertoire). One-directional contract: modules receive this api and
    // never import app.js. Position/promotion helpers live here so modules
    // never duplicate them (a promotion-dialog fix must land exactly once).
    hub: {
      syncBoard,
      postJSON,
      refreshAnalysis,
      renderAnalysis,       // paint a {evalCp,mate,...} object into the panel (review replay uses stored evals)
      persist,
      setMode,
      setStatus,
      snapshotPlay,
      restorePlay,
      getPlaySnapshot,
      setPlaySnapshot,
      ensurePlay,
      requestModeExit,
      registerModeHandlers,
      isPromotion,
      askPromotion,
      positionFromFen,
      positionAt,
      fenOf,
      lastMoveSquares,
      refreshOpeningThenTraps,
      // --- bot-play seam (consumed by botplay.js / T5) ---
      botEnter,
      botExit,
      botSetGame,
      botGetGame,
      botAppendMove,
      botTakeback,
      botSetResult,
      botMarkSaved,
      botConsumeResumePending,
      setBoardPosition,
      setOrientation,
      setMovable,
    },
    on,
    emit,
    mounts: {
      evalBar: byId('eval-bar'),
      toasts: byId('toasts'),
      analysisStatus: byId('analysis-status'),
      tabs: byId('panel-tabs'),
    },
  };

  // (Mode registrations all live in the feature modules now — setup.js,
  // repertoire.js, and traps.js each register their own inside initX(api).)

  // Tab-switch wiring: clicking a [data-tab] button activates the matching panel.
  // In a special mode the tab strip is still shown, so leave that mode first
  // (confirming if it has meaningful in-progress state); bail if the user
  // cancels. After a successful exit we are synchronously back in play mode and
  // fall through to the normal activation below. Null-guarded if #panel-tabs is
  // absent.
  const tabsEl = api.mounts.tabs;
  if (tabsEl) {
    tabsEl.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-tab]');
      if (!btn) return;
      if (document.body.dataset.mode !== 'play' && !requestModeExit()) return;
      const tabName = btn.dataset.tab;

      // Deactivate all tab buttons and panels, activate the clicked one.
      tabsEl.querySelectorAll('button[data-tab]').forEach((b) => {
        const on = b === btn;
        b.classList.toggle('is-active', on);
        b.setAttribute('aria-selected', String(on));
      });
      ['analysis', 'opening', 'traps', 'repertoire', 'review', 'insights'].forEach((name) => {
        const panel = byId(`tab-${name}`);
        if (panel) panel.classList.toggle('is-active', name === tabName);
      });
    });
  }

  // Mode indicator: show a contextual line in the panel while a special mode is
  // active (:empty CSS hides it in play). Set on every mode:change plus once now
  // to cover a session restored directly into a special mode.
  const indicatorEl = byId('mode-indicator');
  if (indicatorEl) {
    const paintIndicator = (mode) => {
      indicatorEl.textContent = mode === 'play' ? '' : (MODE_INDICATOR[mode] || '');
    };
    on('mode:change', paintIndicator);
    paintIndicator(state.mode);
  }

  // Init modules AFTER ground is created so api.getGround() returns a live instance.
  initPanel(api);
  initMovelist(api);
  initFeedback(api);
  initShortcuts(api);
  initReview(api);
  initInsights(api);
  initSetup(api);
  initRepertoire(api);
  initTraps(api);
  initTrainer(api);
  initBotplay(api);
  initCmdk(api);

  // Play controls
  byId('undo').addEventListener('click', undo);
  byId('redo').addEventListener('click', redo);
  byId('flip').addEventListener('click', flip);
  // Undo/redo are disabled in bot-play until B6 adds a real takeback control.
  // undo()/redo() already no-op outside play mode (and shortcuts.js gates ArrowKeys
  // + Ctrl-Z to play mode), so this only reflects that state on the buttons.
  // Re-enabled on any transition back to a non-bot mode.
  const undoBtnEl = byId('undo');
  const redoBtnEl = byId('redo');
  const syncTakebackButtons = (mode) => {
    const disabled = mode === 'bot-play';
    if (undoBtnEl) undoBtnEl.disabled = disabled;
    if (redoBtnEl) redoBtnEl.disabled = disabled;
  };
  on('mode:change', syncTakebackButtons);
  syncTakebackButtons(state.mode); // reflect a session restored directly into bot-play
  byId('reset').addEventListener('click', reset);
  byId('load-fen').addEventListener('click', loadFen);
  byId('fen-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') loadFen(); });

  // Engine restart button: POSTs to /api/engine/restart, then re-analyzes the
  // current position. Game/board state is untouched — only the engine process
  // restarts. Guards for the element existing so older HTML stays compatible.
  const engineRestartBtn = byId('engine-restart-btn');
  if (engineRestartBtn) {
    engineRestartBtn.addEventListener('click', async () => {
      engineRestartBtn.disabled = true;
      engineRestartBtn.classList.add('is-busy');
      setStatus('Restarting engine…');
      try {
        const res = await fetch('/api/engine/restart', { method: 'POST' });
        if (!res.ok) throw new Error(`Restart failed (${res.status})`);
        emit('toast:show', 'Engine restarted');
        setStatus('');
        refreshAnalysis(); // re-analyze current position (game is untouched)
      } catch (err) {
        setStatus(`Restart failed — ${err.message}`, true);
      } finally {
        engineRestartBtn.disabled = false;
        engineRestartBtn.classList.remove('is-busy');
      }
    });
  }

  // Analyze-my-color selector
  const analyzeColorEl = byId('analyze-color');
  if (analyzeColorEl) {
    analyzeColorEl.value = analyzeColor;
    analyzeColorEl.addEventListener('change', () => {
      analyzeColor = analyzeColorEl.value;
      writeUiPref('analyzeColor', analyzeColor);
      refreshAnalysis();
    });
  }

  // Engine speed preset selector (Fast / Balanced / Deep)
  const engineSpeedEl = byId('engine-speed');
  if (engineSpeedEl) {
    engineSpeedEl.value = engineSpeed;
    engineSpeedEl.addEventListener('change', () => {
      engineSpeed = engineSpeedEl.value;
      writeUiPref('engineSpeed', engineSpeed);
      // Same supersede-then-refresh pattern as the eval toggle's re-enable path:
      // invalidate any in-flight refreshAnalysis so its late (old-speed) response
      // can't race the new one, then re-evaluate the current position at the new speed.
      analysisToken++;
      refreshAnalysis();
    });
  }

  // Analysis-mode settings: collapsible block (collapsed by default; pref-restored)
  // holding the Full / Blunders only / Off selector and the win-chances bar toggle.
  const settingsToggleEl = byId('analysis-settings-toggle');
  const settingsBlockEl = settingsToggleEl ? settingsToggleEl.closest('.analysis-settings-block') : null;
  if (settingsToggleEl && settingsBlockEl) {
    if (readUiPrefs().analysisPanelCollapsed === false) {
      settingsBlockEl.classList.remove('collapsed');
      settingsToggleEl.setAttribute('aria-expanded', 'true');
    }
    settingsToggleEl.addEventListener('click', () => {
      const isNowCollapsed = settingsBlockEl.classList.toggle('collapsed');
      settingsToggleEl.setAttribute('aria-expanded', String(!isNowCollapsed));
      writeUiPref('analysisPanelCollapsed', isNowCollapsed);
    });
  }

  // Mode selector (replaces the old eval-toggle button; 'off' keeps its freeze
  // semantics). The header hint names a non-Full mode even while collapsed.
  const modeSegEl = byId('analysis-mode-seg');
  const modeHintEl = byId('analysis-mode-hint');
  const MODE_HINTS = { blunders: '· Blunders only', off: '· Off' };
  const syncAnalysisMode = () => {
    if (modeSegEl) {
      modeSegEl.querySelectorAll('button[data-mode]').forEach((b) => {
        b.setAttribute('aria-pressed', String(b.dataset.mode === analysisMode));
      });
    }
    if (modeHintEl) modeHintEl.textContent = MODE_HINTS[analysisMode] || '';
  };
  const setAnalysisMode = (mode) => {
    if (!VALID_ANALYSIS_MODES.includes(mode) || mode === analysisMode) return;
    analysisMode = mode;
    writeUiPref('analysisMode', mode);
    syncAnalysisMode();
    emit('analysis-mode:change', mode); // movelist re-renders its quality dots
    if (mode === 'off') {
      // Off → invalidate any in-flight refreshAnalysis so its late response can't
      // render and un-freeze the panel (same supersede signal onUserMove/loadFen use).
      analysisToken++;
    } else if (state.mode === 'play' || state.mode === 'bot-play') {
      // Full↔Blunders (or leaving Off): supersede any in-flight response rendered
      // under the old mode's filter, then catch the panel up. Gated to play/bot-play
      // (Gate-1: eval panel stays usable during bot games) — flipping the selector
      // during review replay must never hit the live engine. refreshAnalysis()'s
      // own analysisToken guard drops a superseded response (e.g. after a bot reply).
      analysisToken++;
      refreshAnalysis();
    }
  };
  if (modeSegEl) {
    syncAnalysisMode(); // reflect the restored mode on first paint
    modeSegEl.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-mode]');
      if (btn) setAnalysisMode(btn.dataset.mode);
    });
  }

  // Win-chances bar show/hide. Pure CSS hide (class on .board-wrap) — setEvalBar
  // keeps painting underneath so a re-show is instantly current.
  const evalBarCheckEl = byId('eval-bar-visible');
  const boardWrapEl = document.querySelector('.board-wrap');
  let evalBarHidden = readUiPrefs().evalBarHidden === true;
  const syncEvalBarHidden = () => {
    if (boardWrapEl) boardWrapEl.classList.toggle('eval-bar-hidden', evalBarHidden);
    if (evalBarCheckEl) evalBarCheckEl.checked = !evalBarHidden;
  };
  syncEvalBarHidden(); // apply the restored pref before first paint
  if (evalBarCheckEl) {
    evalBarCheckEl.addEventListener('change', () => {
      evalBarHidden = !evalBarCheckEl.checked;
      writeUiPref('evalBarHidden', evalBarHidden);
      syncEvalBarHidden();
    });
  }

  // (Setup controls + board stamp listeners are wired by initSetup above.)

  // (Traps browse filters, chip, and bar controls are wired by initTraps above.)

  // Review replay bar controls
  byId('review-return').addEventListener('click', exitReview);

  // (Repertoire bar controls are wired by initRepertoire above.)

  if (state.mode === 'setup') {
    enterSetupUI();           // resume an in-progress setup session
  } else {
    syncBoard();
    refreshAnalysis();
    refreshOpeningThenTraps();
  }

  // (Traps + repertoire browse data are loaded by their modules' initX.)
}

init();
