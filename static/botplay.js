// botplay.js — bot-play mode (B2 walking skeleton). Play one full untimed game
// against one default weakened-Stockfish bot in the browser. Receives the
// injected `api` hub at init and NEVER imports app.js back (hub → feature leaf).
//
// Owns: the module-scoped `busy` single-flight gate and `replyToken` staleness
// counter. Everything about app state (history, board, persistence, analysis
// refresh) is reached ONLY through the injected api hub's bot-play seam (T3):
//   botEnter/botExit/botSetGame/botGetGame/botAppendMove/botSetResult/
//   botConsumeResumePending, setBoardPosition/setOrientation/setMovable,
//   plus the shared persist/refreshAnalysis/setMode/setStatus/postJSON and
//   positionFromFen/positionAt/fenOf/isPromotion/askPromotion.
//
// Staleness discipline (the whole risk of this ticket): a bot reply is a token
// minted BEFORE the think-timer. It is re-checked inside the timer callback AND
// again after the /api/bot/move await (the traps.js scheduled-callback idiom +
// app.js's mint-token-before-await pattern). The token is INVALIDATED on: mode
// exit, new game, color change, resign, an already-recorded terminal result,
// and restart. Any callback whose token no longer matches drops silently.

import { INITIAL_FEN } from 'https://esm.sh/chessops@0.14.2/fen';
import { chessgroundDests } from 'https://esm.sh/chessops@0.14.2/compat';
import { readUiPrefs, writeUiPref } from './prefs.js';

let _api = null;
let busy = false;          // single-flight: one in-flight bot request/timer max
let replyToken = 0;        // staleness guard for the scheduled bot reply
let thinkTimer = null;     // handle of the pending think-delay timer (if any)
let retryFen = null;       // FEN we owe a bot move for (engine-down Retry target)
let personaCatalog = [];   // [{id,name,elo,style,description}] from /api/bot/status
let defaultPersonaId = ''; // status.defaultPersonaId (picker fallback)

const byId = (id) => document.getElementById(id);
const state = () => _api.actions.getState();
const hub = () => _api.hub;

const THINK_MIN_MS = 400;
const THINK_MAX_MS = 800;

// --- helpers ---------------------------------------------------------------

// Invalidate any scheduled/in-flight bot reply. Called on every event that must
// abandon a pending bot move: exit, new game, color change, resign, terminal,
// restart. Bumping the token makes both the timer callback and the post-await
// re-check fail their equality test and drop silently; we also clear the timer
// so a not-yet-fired think-delay never fires at all.
function invalidateReply() {
  replyToken++;
  if (thinkTimer !== null) {
    clearTimeout(thinkTimer);
    thinkTimer = null;
  }
}

// Current game FEN (full FEN) from the client-owned history via the hub.
function currentFen() {
  const { pos } = hub().positionAt(state().cursor);
  return hub().fenOf(pos);
}

// chessops position at the current cursor.
function currentPos() {
  return hub().positionAt(state().cursor).pos;
}

// Does `pos` end the game automatically (mate / stalemate / insufficient)?
// Returns a result string for botSetResult + a status line, or null if live.
// Claimable draws (threefold / 50-move) are OUT of scope for the skeleton.
function autoOutcome(pos) {
  if (pos.isCheckmate()) {
    // The side to move is checkmated → the OTHER side won.
    const winner = pos.turn === 'white' ? 'black' : 'white';
    return { result: winner === 'white' ? '1-0' : '0-1', text: `Checkmate — ${winner} wins.` };
  }
  if (pos.isStalemate()) return { result: '1/2-1/2', text: 'Stalemate — draw.' };
  if (pos.isInsufficientMaterial()) return { result: '1/2-1/2', text: 'Insufficient material — draw.' };
  return null;
}

// Freeze the board to no side (bot's turn or finished game).
function freezeBoard() {
  hub().setMovable(null, null);
}

// Human-readable line for a finished game from the user's perspective. Used when
// a completed game is restored after a refresh (the exact end-reason isn't
// persisted, only the result string).
function resultLine(result, userColor) {
  if (result === '1/2-1/2') return 'Game over — draw.';
  const userWon = (result === '1-0' && userColor === 'white')
               || (result === '0-1' && userColor === 'black');
  return userWon ? 'Game over — you win.' : 'Game over — bot wins.';
}

// Roll the board back to the current game position after a rejected/failed user
// move. Restores the FEN, and if it is still the user's live turn re-establishes
// their legal dests (a rejected drag otherwise leaves the board un-interactive).
function rollback() {
  hub().setBoardPosition(currentFen());
  const game = hub().botGetGame();
  if (game && !game.result && !busy && state().mode === 'bot-play'
      && currentPos().turn === game.userColor) {
    giveUserTurn();
  }
}

// Hand the turn to the user: movable = their color with legal dests (only when
// it is actually their turn; chessground's turnColor already reflects the FEN).
function giveUserTurn() {
  const game = hub().botGetGame();
  if (!game) return;
  const pos = currentPos();
  hub().setMovable(game.userColor, chessgroundDests(pos));
}

function setStatusLine(msg) {
  const el = byId('botplay-status');
  if (el) el.textContent = msg || '';
}

function showRetry(show) {
  const el = byId('botplay-retry');
  if (el) el.hidden = !show;
}

function showResign(show) {
  const el = byId('botplay-resign');
  if (el) el.hidden = !show;
}

// --- takeback policy + guard (B6) ------------------------------------------
//
// Per-match policy persisted via prefs.js (`takebackPolicy`, default "three").
// Normalized on read against the allowlist so a stale/unknown value falls back
// to the default (mirrors normChessCom's normalize-on-read precedent). The
// selector is a pre-game setting locked mid-game like the persona/color pickers.

const TAKEBACK_POLICIES = ['never', 'three', 'anytime'];

function takebackPolicy() {
  const v = readUiPrefs().takebackPolicy;
  return TAKEBACK_POLICIES.includes(v) ? v : 'three';
}

// Is a takeback currently allowed? Only when idle (`!busy`), on the user's turn,
// in a live bot game with ≥2 plies played, and the policy permits it:
//   never → never; three → used < 3; anytime → always.
function canTakeback() {
  const g = hub().botGetGame();
  if (!(g && !g.result && !busy && state().mode === 'bot-play'
        && currentPos().turn === g.userColor && (g.movesUci || []).length >= 2)) {
    return false;
  }
  const policy = takebackPolicy();
  if (policy === 'never') return false;
  if (policy === 'three') return (g.takebacksUsed || 0) < 3;
  return true; // anytime
}

// Take back the last full move pair (button handler). The hub truncates 2 plies,
// mirrors state, bumps tokens (dropping a stale eval), flips rated→casual, and
// re-renders the board. We then restore the user's dests and fetch a FRESH eval
// (the token bump only DROPS the stale one; every other position change calls
// refreshAnalysis), and reflect the controls.
function takeback() {
  if (!canTakeback()) return;
  const res = hub().botTakeback();
  if (!res) return;
  giveUserTurn();
  hub().refreshAnalysis();
  reflectControls();
}

// Lock/unlock the takeback policy selector (disabled attribute — like the
// persona picker). Inert while busy or a game is live.
function reflectTakebackLock() {
  const sel = byId('bot-takeback-policy');
  if (!sel) return;
  const game = hub().botGetGame();
  const live = state().mode === 'bot-play' && game && !game.result;
  sel.disabled = !!(busy || live);
}

// Reflect the takeback button/counter/note from descriptor state. The counter
// text depends on the policy; the note is DERIVED from the persisted
// `ratedFlipped` flag (set only when a takeback flipped a RATED game to casual)
// so it survives a refresh and never shows for a casual-from-start game.
function reflectTakeback() {
  const game = hub().botGetGame();
  const live = state().mode === 'bot-play' && game && !game.result;
  const n = (game && game.takebacksUsed) || 0;

  const btn = byId('botplay-takeback');
  if (btn) btn.hidden = !canTakeback();

  const count = byId('botplay-takeback-count');
  if (count) {
    const policy = takebackPolicy();
    if (live && policy === 'three') count.textContent = `Takebacks: ${n}/3`;
    else if (live && policy === 'anytime') count.textContent = `Takebacks: ${n}`;
    else count.textContent = ''; // never, or not a live bot game
  }

  const note = byId('botplay-takeback-note');
  // Only for a game that was RATED and a takeback flipped it to casual — the
  // persisted `ratedFlipped` flag survives refresh and never fires for a
  // casual-from-start game (which never counted toward the rating).
  if (note) note.hidden = !(game && game.ratedFlipped);

  reflectTakebackLock();
}

// Wire the policy selector: init from the pref; on change, revert if locked
// (mid-game/busy) else persist + reflect (mirrors wirePersonaPicker).
function wireTakebackPolicy() {
  const sel = byId('bot-takeback-policy');
  if (!sel) return;
  sel.value = takebackPolicy();
  sel.addEventListener('change', () => {
    const game = hub().botGetGame();
    const locked = busy || (game && !game.result && state().mode === 'bot-play');
    if (locked) {
      sel.value = takebackPolicy();
      return;
    }
    writeUiPref('takebackPolicy', sel.value);
    reflectControls();
  });
}

// Sync the Resign/Retry/Start visibility + status for the current game phase.
function reflectControls() {
  const game = hub().botGetGame();
  const active = state().mode === 'bot-play' && game && !game.result;
  showResign(!!active);
  const startBtn = byId('botplay-start');
  if (startBtn) startBtn.textContent = (game && game.result) ? 'New game' : 'Start';
  reflectPersonaLock();
  reflectTakeback();
}

// --- collapse toggle + color radiogroup ------------------------------------

function wireToggle() {
  const block = byId('botplay-block');
  const toggle = byId('botplay-toggle');
  if (!block || !toggle) return;
  toggle.addEventListener('click', () => {
    const collapsed = block.classList.toggle('collapsed');
    toggle.setAttribute('aria-expanded', String(!collapsed));
  });
}

function chosenColor() {
  const white = byId('botplay-color-white');
  return (white && white.getAttribute('aria-checked') === 'true') ? 'white' : 'black';
}

function wireColorPicker() {
  const white = byId('botplay-color-white');
  const black = byId('botplay-color-black');
  if (!white || !black) return;
  const pick = (color) => {
    // Inert while a request/timer is pending (single-flight) or a game is live.
    if (busy) return;
    const game = hub().botGetGame();
    if (game && !game.result && state().mode === 'bot-play') return; // can't switch mid-game
    white.setAttribute('aria-checked', String(color === 'white'));
    black.setAttribute('aria-checked', String(color === 'black'));
  };
  white.addEventListener('click', () => pick('white'));
  black.addEventListener('click', () => pick('black'));
}

// --- persona picker --------------------------------------------------------

// The persona id chosen in the picker (or the persisted/default fallback if the
// picker isn't populated yet). Mirrors chosenColor()'s "read the UI" idiom.
function chosenPersonaId() {
  const sel = byId('bot-persona');
  if (sel && sel.value) return sel.value;
  return readUiPrefs().botPersona || defaultPersonaId;
}

// Fill #botplay-persona-caption with a persona's description.
function setPersonaCaption(id) {
  const cap = byId('botplay-persona-caption');
  if (!cap) return;
  const p = personaCatalog.find((x) => x.id === id);
  cap.textContent = p ? (p.description || '') : '';
}

// Reflect the selected persona's NAME in the #botplay-persona label so the
// in-game opponent shown matches the chosen persona (not the server default).
function setPersonaName(id) {
  const el = byId('botplay-persona');
  if (!el) return;
  const p = personaCatalog.find((x) => x.id === id);
  if (p && p.name) el.textContent = p.name;
}

// The catalog name for a persona id (used as the descriptor's display label).
function personaNameFor(id) {
  const p = personaCatalog.find((x) => x.id === id);
  return p ? p.name : '';
}

// Build the <option> list from the status catalog and select the persisted
// persona (readUiPrefs().botPersona) or the server default. Called from the
// status-probe path once personas are known.
function populatePersonaPicker(personas, defId) {
  personaCatalog = Array.isArray(personas) ? personas : [];
  defaultPersonaId = defId || '';
  const sel = byId('bot-persona');
  if (!sel) return;
  if (personaCatalog.length === 0) return; // leave placeholder if none

  const persisted = readUiPrefs().botPersona;
  const wanted = personaCatalog.some((p) => p.id === persisted)
    ? persisted
    : (personaCatalog.some((p) => p.id === defaultPersonaId) ? defaultPersonaId : personaCatalog[0].id);

  sel.innerHTML = '';
  for (const p of personaCatalog) {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = `${p.name} (≈${p.elo}) — ${p.description}`;
    sel.appendChild(opt);
  }
  sel.value = wanted;
  setPersonaCaption(wanted);
  setPersonaName(wanted);
}

function wirePersonaPicker() {
  const sel = byId('bot-persona');
  if (!sel) return;
  sel.addEventListener('change', () => {
    // Inert while a request/timer is pending (single-flight) or a game is live —
    // mirror the color-picker guard. Revert the visible selection to the pref.
    const game = hub().botGetGame();
    const locked = busy || (game && !game.result && state().mode === 'bot-play');
    if (locked) {
      sel.value = readUiPrefs().botPersona || defaultPersonaId || sel.value;
      return;
    }
    writeUiPref('botPersona', sel.value);
    setPersonaCaption(sel.value);
    setPersonaName(sel.value);
  });
}

// Lock/unlock the persona picker (disabled attribute — T4's CSS targets
// :disabled). Called alongside reflectControls so the picker is inert mid-game.
function reflectPersonaLock() {
  const sel = byId('bot-persona');
  if (!sel) return;
  const game = hub().botGetGame();
  const live = state().mode === 'bot-play' && game && !game.result;
  sel.disabled = !!(busy || live);
}

// --- personal ELO readout + chess.com anchor (B8) --------------------------
//
// Bot-ELO is a server read-model (GET /api/rating, recomputed from history);
// the chess.com rating is a client-only display reference persisted via prefs.js
// (chess-training:ui:v1). The chess.com value is NEVER sent to the server.

// Normalize a chess.com input value to a finite positive integer, or null.
// Used on BOTH read (init) and change so a stored "NaN"/"abc"/null never renders
// as a rating. Empty / non-numeric / NaN / <= 0 → null.
function normChessCom(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  const i = Math.trunc(n);
  return i > 0 ? i : null;
}

// Render the chess.com anchor line from the current pref (a normalized int or
// null). Toggles visibility via the `hidden` attribute (T3 contract).
function renderChessCom() {
  const el = byId('botplay-chesscom');
  if (!el) return;
  const n = normChessCom(readUiPrefs().chessComRating);
  if (n !== null) {
    el.textContent = `chess.com: ${n}`;
    el.removeAttribute('hidden');
  } else {
    el.setAttribute('hidden', '');
  }
}

// Render the bot-ELO readout + the chess.com anchor from a /api/rating payload.
function renderRating(data) {
  const el = byId('botplay-elo');
  if (el) {
    if (typeof data.botElo === 'number') {
      el.textContent = `Bot rating: ${data.botElo} (${data.gamesCounted} game(s))`;
    } else {
      el.textContent = 'Bot rating: — play a rated game to start';
    }
  }
  renderChessCom();
}

// Best-effort fetch of the running bot-ELO; on failure leave the readout as-is.
async function refreshRating() {
  try {
    const res = await fetch('/api/rating');
    const data = await res.json();
    renderRating(data);
  } catch (_) { /* best-effort — keep the current readout */ }
}

// Initialize the chess.com input from the persisted pref (normalized) and wire
// its change listener. Persists the normalized int (or null to clear) + re-renders.
function wireChessComInput() {
  const input = byId('chesscom-rating');
  const stored = normChessCom(readUiPrefs().chessComRating);
  if (input) input.value = stored === null ? '' : String(stored);
  renderChessCom();
  if (!input) return;
  input.addEventListener('change', () => {
    const n = normChessCom(input.value);
    writeUiPref('chessComRating', n);
    renderChessCom();
  });
}

// --- status probe (persona label + Maia dot + Start availability) ----------

async function probeStatus() {
  let data;
  try {
    const res = await fetch('/api/bot/status');
    data = await res.json();
  } catch (_) {
    data = { available: false, personaLabel: '', personas: [], defaultPersonaId: '', maia: { lc0: false, weights: [] } };
  }

  const persona = byId('botplay-persona');
  if (persona && data.personaLabel) persona.textContent = data.personaLabel;

  // Populate the persona picker from the catalog + select persisted/default.
  populatePersonaPicker(data.personas, data.defaultPersonaId);

  const indicator = byId('botplay-maia-indicator');
  const maiaLabel = byId('botplay-maia-label');
  const ready = !!(data.maia && data.maia.lc0 && data.maia.weights && data.maia.weights.length);
  if (indicator) indicator.dataset.ready = String(ready);
  if (maiaLabel) maiaLabel.textContent = ready ? 'Maia: ready' : 'Maia: not installed';

  const startBtn = byId('botplay-start');
  const hint = byId('botplay-hint');
  if (!data.available) {
    if (startBtn) startBtn.classList.add('is-disabled');
    if (hint) { hint.hidden = false; hint.textContent = 'Bot engine unavailable — install Stockfish to play.'; }
  } else {
    if (startBtn) startBtn.classList.remove('is-disabled');
    if (hint) { hint.hidden = true; hint.textContent = ''; }
  }
  return data;
}

// --- save into the review pipeline -----------------------------------------
//
// snapshot = { movesUci, userColor, personaLabel, personaId, result, startedAt,
// rated } —
// captured SYNCHRONOUSLY by the caller BEFORE any teardown (botExit() nulls the
// descriptor, New-game replaces it). We must never re-read botGetGame() after an
// await here. Fire-and-forget: never blocks the UI. Success is an ImportResponse
// with imported+duplicates >= 1 (a 400 resolves via postJSON with a
// non-ImportResponse body → treated as failure). The identity-guarded
// botMarkSaved prevents a stale save from marking a newer game.
function saveGame(snapshot) {
  if (!snapshot || !snapshot.movesUci || snapshot.movesUci.length === 0) return;
  hub().postJSON('/api/bot/save', {
    movesUci: snapshot.movesUci,
    userColor: snapshot.userColor,
    personaLabel: snapshot.personaLabel,
    personaId: snapshot.personaId,
    result: snapshot.result,
    startedAt: snapshot.startedAt,
    rated: snapshot.rated,
  }).then((res) => {
    // postJSON only throws on 503; a 400 (empty moves / result '*') resolves
    // with a non-ImportResponse body. Require an ImportResponse that inserted
    // or deduped at least one game.
    const ok = res && typeof res.imported === 'number' && typeof res.duplicates === 'number'
      && (res.imported + res.duplicates) >= 1;
    if (ok) {
      hub().botMarkSaved(snapshot.startedAt);
      // Only a RATED save moves the bot-ELO — refresh the readout without reload.
      // Both finish paths and the rated-abandon saveOnLeave funnel through here,
      // so this single hook covers all rated saves; casual saves must NOT refresh.
      if (snapshot.rated) void refreshRating();
    } else console.warn('[botplay] save failed — game left unsaved', res);
  }).catch((err) => {
    console.warn('[botplay] save failed — game left unsaved', err);
  });
}

// Snapshot the CURRENT bot game synchronously (before any await/teardown) so a
// save can outlive the descriptor. `resultOverride` supplies the result to
// persist when it differs from the descriptor (rated-abandon loss).
function snapshotGame(game, resultOverride) {
  return {
    movesUci: (game.movesUci || []).slice(),
    userColor: game.userColor,
    personaLabel: game.personaLabel || '',
    personaId: game.personaId || null,
    result: resultOverride || game.result,
    startedAt: game.startedAt,
    rated: !!game.rated,
  };
}

// The exit / New-game save predicate — ONE ordered decision, evaluated on the
// game being left. The ordering is load-bearing: a finished-but-unsaved game
// (finish-POST failed) must be re-saved with its REAL result and must NOT be
// mistaken for an abandon-loss. Captures the snapshot synchronously, then saves.
function saveOnLeave(game) {
  if (!game) return;
  const hasMoves = (game.movesUci || []).length >= 1;
  if (!hasMoves || game.saved) return; // 0 moves / already saved → discard.
  if (game.result) {
    // (a) Finished but unsaved (finish-POST failed) → retry with the REAL result.
    saveGame(snapshotGame(game));
  } else if (game.rated) {
    // (b) Unfinished rated game genuinely abandoned → user loses.
    const loss = game.userColor === 'white' ? '0-1' : '1-0';
    saveGame(snapshotGame(game, loss));
  }
  // (c) casual with no result → discard, no save.
}

// --- start / new game ------------------------------------------------------

function startGame() {
  if (busy) return;
  const startBtn = byId('botplay-start');
  if (startBtn && startBtn.classList.contains('is-disabled')) return;

  // New-game re-entry: the game we're leaving may need saving BEFORE its
  // descriptor is replaced below (finished-retry or rated-abandon-loss).
  saveOnLeave(hub().botGetGame());

  // Any prior scheduled reply is dead the moment a new game begins.
  invalidateReply();
  retryFen = null;
  showRetry(false);

  const userColor = chosenColor();
  const rated = !!(byId('bot-rated') || {}).checked;
  const startedAt = new Date().toISOString();
  const personaId = chosenPersonaId();
  const seed = Math.floor(Math.random() * 1e9); // per-game seed for opening sampling

  // Enter bot-play: capture the prior play session ONCE. If we're already in
  // bot-play (a "New game" / mid-game restart), botEnter() must NOT re-run —
  // by now the bot line has been mirrored into play-state, so a fresh
  // snapshotPlay() would overwrite the real prior play session with the bot
  // position and permanently lose the user's exit target. Only capture on the
  // genuine play→bot transition. botEnter() must precede setMode (T3 contract).
  const alreadyInBot = state().mode === 'bot-play' && hub().botGetGame();
  if (!alreadyInBot) hub().botEnter();
  hub().botSetGame({
    baseFen: INITIAL_FEN,
    movesUci: [],
    cursor: 0,
    userColor,
    personaLabel: personaNameFor(personaId),
    personaId,
    seed,
    result: null,
    startedAt,
    rated,
    saved: false,
  });
  hub().setMode('bot-play');
  hub().setOrientation(userColor);
  hub().setBoardPosition(INITIAL_FEN);

  reflectControls();
  hub().persist();
  hub().refreshAnalysis();

  if (userColor === 'black') {
    // Bot is White → it moves first.
    setStatusLine('Bot is thinking…');
    freezeBoard();
    scheduleBotReply();
  } else {
    setStatusLine('Your move.');
    giveUserTurn();
  }
}

// --- user move (onMove handler) --------------------------------------------
//
// Mirrors app.js onUserMove's promotion + legality flow, but writes to the
// bot game's client history via the hub. There is no cross-await staleness risk
// on the user's own move here beyond the promotion dialog: after promotion we
// re-validate mode + that the game is still live before committing.

async function onMove(orig, dest) {
  const game = hub().botGetGame();
  if (state().mode !== 'bot-play' || !game) return;
  // Finished game or bot's turn or an in-flight request → reject, snap back.
  if (game.result || busy) { rollback(); return; }

  const pos = currentPos();
  // The user may only move their own color.
  if (pos.turn !== game.userColor) { rollback(); return; }

  let promo = '';
  if (hub().isPromotion(pos, orig, dest)) {
    try {
      promo = await hub().askPromotion();
    } catch (_) {
      rollback(); // dialog cancelled — restore board + user dests
      return;
    }
    // Mode/game may have changed while the dialog was open.
    const g2 = hub().botGetGame();
    if (state().mode !== 'bot-play' || !g2 || g2.result || busy) {
      rollback();
      return;
    }
  }

  const uci = orig + dest + promo;

  // Validate legality against the current position's legal dests.
  const dests = chessgroundDests(currentPos());
  const fromDests = dests.get(orig);
  if (!fromDests || !fromDests.includes(dest)) {
    hub().setBoardPosition(currentFen());
    return;
  }

  // Commit: append to client history, detect terminal, persist, refresh eval.
  // ORDERING CONTRACT (T3): botAppendMove → botSetResult(if terminal) →
  // persist → refreshAnalysis.
  hub().botAppendMove(uci);
  const after = currentPos();
  const outcome = autoOutcome(after);
  if (outcome) hub().botSetResult(outcome.result);
  hub().persist();
  hub().refreshAnalysis();

  if (outcome) {
    // User's move ended the game — no bot reply. Save it (casual + rated) once;
    // snapshot captured synchronously from the just-updated descriptor.
    saveGame(snapshotGame(hub().botGetGame()));
    invalidateReply();
    setStatusLine(outcome.text);
    freezeBoard();
    reflectControls();
    return;
  }

  // Hand the turn to the bot: freeze the board and schedule the reply.
  setStatusLine('Bot is thinking…');
  freezeBoard();
  scheduleBotReply();
  reflectControls(); // hide the takeback button while the bot is thinking (busy)
}

// --- auto-reply (bot move) -------------------------------------------------
//
// Staleness idiom: mint `myToken` BEFORE the timer. Re-check inside the timer
// callback (mode still bot-play, token current, no result). Then POST. After the
// await, re-check the token again — if superseded, drop silently.

function scheduleBotReply() {
  const myToken = ++replyToken; // mint before the timer
  busy = true;
  const fen = currentFen();
  retryFen = fen;

  const delay = THINK_MIN_MS + Math.floor(Math.random() * (THINK_MAX_MS - THINK_MIN_MS + 1));
  thinkTimer = setTimeout(() => {
    thinkTimer = null;
    // Guard: exit/new-game/color/resign/terminal/restart may have fired while
    // we waited (traps.js scheduled-callback idiom). If our token is superseded,
    // a NEWER operation owns the busy gate — return WITHOUT clearing busy (the
    // owner clears it; the invalidating events all reset busy at their call site).
    if (myToken !== replyToken) return;
    const game = hub().botGetGame();
    if (state().mode !== 'bot-play' || !game || game.result) { busy = false; return; }
    void requestBotMove(myToken, fen);
  }, delay);
}

async function requestBotMove(myToken, fen) {
  let data;
  // Thread the persona/seed from the descriptor + ply = half-moves already
  // played before this bot move. Read BEFORE the await; the busy/replyToken
  // staleness machinery below is orthogonal and untouched.
  const g = hub().botGetGame();
  const body = { fen };
  if (g) {
    if (g.personaId) body.personaId = g.personaId;
    if (typeof g.seed === 'number') body.seed = g.seed;
    body.ply = (g.movesUci || []).length;
  }
  try {
    data = await hub().postJSON('/api/bot/move', body);
  } catch (err) {
    // Engine down / network failure. The token may already be stale (resign,
    // exit) — in that case a newer op owns the gate, so drop WITHOUT clearing
    // busy and DON'T surface an error.
    if (myToken !== replyToken) return;
    if (state().mode !== 'bot-play') { busy = false; return; }
    const game = hub().botGetGame();
    if (!game || game.result) { busy = false; return; }
    busy = false;
    retryFen = fen;
    setStatusLine('Bot engine unavailable — your move is saved. Retry?');
    showRetry(true);
    return;
  }

  // Re-check the token AFTER the await (app.js mint-before-await pattern). If
  // superseded, a newer op owns the gate — return without clearing busy.
  if (myToken !== replyToken) return;
  if (state().mode !== 'bot-play') { busy = false; return; }
  const game = hub().botGetGame();
  if (!game || game.result) { busy = false; return; }

  // Defensive: the reply must apply to the position we asked about. If the
  // client history moved on (shouldn't happen while the board is frozen), drop.
  if (currentFen() !== fen) { busy = false; return; }

  showRetry(false);
  retryFen = null;

  // Apply the bot move. ORDERING CONTRACT (T3): botAppendMove →
  // botSetResult(if terminal) → persist → refreshAnalysis → hand turn back.
  hub().botAppendMove(data.moveUci);
  const after = currentPos();
  const outcome = autoOutcome(after);
  if (outcome) hub().botSetResult(outcome.result);
  hub().persist();
  hub().refreshAnalysis();
  busy = false;

  if (outcome) {
    // Bot's move ended the game — save it (casual + rated) once; snapshot
    // captured synchronously from the just-updated descriptor.
    saveGame(snapshotGame(hub().botGetGame()));
    invalidateReply();
    setStatusLine(outcome.text);
    freezeBoard();
    reflectControls();
    return;
  }

  setStatusLine('Your move.');
  giveUserTurn();
  reflectControls(); // refresh the takeback button/counter now it's the user's turn
}

// --- resign / retry --------------------------------------------------------

function resign() {
  const game = hub().botGetGame();
  if (state().mode !== 'bot-play' || !game || game.result) return;
  // Resign kills any in-flight/scheduled bot reply — the reply, if it lands,
  // must be dropped (token invalidated), and the result stands.
  invalidateReply();
  busy = false;
  retryFen = null;
  showRetry(false);
  // Opponent (the bot) wins.
  const result = game.userColor === 'white' ? '0-1' : '1-0';
  hub().botSetResult(result);
  hub().persist();
  // Resign is a real result — save it (casual + rated) once; snapshot captured
  // synchronously from the just-updated descriptor.
  saveGame(snapshotGame(hub().botGetGame()));
  setStatusLine('You resigned — bot wins.');
  freezeBoard();
  reflectControls();
}

function retry() {
  const game = hub().botGetGame();
  if (state().mode !== 'bot-play' || !game || game.result || busy) return;
  if (!retryFen) return;
  showRetry(false);
  setStatusLine('Bot is thinking…');
  freezeBoard();
  scheduleBotReply();
}

// --- exit (mode handler) ---------------------------------------------------
//
// botExit() (T3) restores the prior play session and returns to play mode. We
// must invalidate any pending reply first so a late callback can't fire against
// the restored play position.

function exit() {
  // Save-on-leave BEFORE teardown: botExit() nulls the descriptor, so the
  // snapshot must be captured synchronously here (finished-retry or rated-
  // abandon-loss; casual-no-result / 0-move / already-saved discard).
  saveOnLeave(hub().botGetGame());
  invalidateReply();
  busy = false;
  retryFen = null;
  showResign(false);
  showRetry(false);
  setStatusLine('');
  hub().botExit();
}

// --- resume after refresh --------------------------------------------------
//
// On init, if restore() landed on the bot's turn (a refresh killed a pending
// reply), botConsumeResumePending() returns true. We are already in bot-play
// mode with the game restored — schedule the bot move.

function resumeIfPending() {
  if (state().mode !== 'bot-play') return;
  const game = hub().botGetGame();
  if (!game) return;
  if (game.result) {
    // A finished game was restored after a refresh — show its result and offer
    // "New game" rather than a blank status + "Start".
    reflectControls();
    setStatusLine(resultLine(game.result, game.userColor));
    freezeBoard();
    return;
  }
  if (hub().botConsumeResumePending()) {
    setStatusLine('Bot is thinking…');
    freezeBoard();
    scheduleBotReply();
  } else {
    // Restored on the user's turn — show controls + hand them the board.
    reflectControls();
    setStatusLine('Your move.');
    giveUserTurn();
  }
}

// --- init ------------------------------------------------------------------

export function initBotplay(api) {
  _api = api;

  wireToggle();
  wireColorPicker();
  wirePersonaPicker();
  wireTakebackPolicy();
  wireChessComInput();

  byId('botplay-start').addEventListener('click', startGame);
  byId('botplay-resign').addEventListener('click', resign);
  byId('botplay-retry').addEventListener('click', retry);
  byId('botplay-takeback').addEventListener('click', takeback);

  // The hub dispatcher routes bot-play board moves here; exit is botExit.
  api.hub.registerModeHandlers('bot-play', { onMove, exit });

  // Probe engine status (persona label, Maia dot, Start availability), THEN —
  // if a refresh restored a bot game on the bot's turn — resume the reply.
  // Also fetch the running bot-ELO once (best-effort) to populate the readout.
  probeStatus().finally(() => {
    resumeIfPending();
    void refreshRating();
  });
}
