// review.js — Game library, import, profile dashboard, and foresight cards.
//
// Injected-api module: all app dependencies arrive via `api` (no imports from app.js).
// Owns the #tab-review panel, #review-foresight, and reacts to the review:ply event.
//
// One-directional: review.js → api (never api.js → review.js directly).
// Contract: never modifies the localStorage session shape, never persists review state.

const byId = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Module-level state
// ---------------------------------------------------------------------------
let _api = null;
let _reviewData = null;  // ReviewResponse from GET /api/games/{id}/review (leaks + plies)
let _openedGameId = null;
let _analyzeAllInterval = null;  // polling interval while any game is pending/analyzing
let _openStatusInterval = null;  // polling interval for a game opened mid-analysis
let _narrativeData = null;       // {enabled, narrative} from GET /api/games/{id}/narrative
let _narrativeGenerating = false;
let _narrativeExpanded = false;  // read-more/show-less toggle state for the story panel

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'className') e.className = v;
    else if (k === 'textContent') e.textContent = v;
    else e.setAttribute(k, v);
  }
  for (const child of children) {
    if (typeof child === 'string') e.appendChild(document.createTextNode(child));
    else if (child) e.appendChild(child);
  }
  return e;
}

function fmt(val, fallback = '—') {
  if (val === null || val === undefined || val === '') return fallback;
  return String(val);
}

// ---------------------------------------------------------------------------
// API calls (all fetch — no postJSON from app.js to keep modules one-directional)
// ---------------------------------------------------------------------------

// Attach {status, detail} from a non-2xx JSON error body onto the thrown
// Error (best-effort — a non-JSON or empty body just omits `detail`). The
// message string stays exactly as before so existing call sites that only
// read err.message are unaffected.
async function attachErrorDetail(err, res) {
  err.status = res.status;
  try {
    const body = await res.json();
    if (body && typeof body.detail === 'string') err.detail = body.detail;
  } catch (_) {
    // No/invalid JSON body — leave err.detail undefined.
  }
  return err;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw await attachErrorDetail(new Error(`HTTP ${res.status}: ${url}`), res);
  return res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await attachErrorDetail(new Error(`HTTP ${res.status}: ${url}`), res);
  return res.json();
}

async function patchJSON(url, body) {
  const res = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
  return res.json();
}

async function deleteGame(id) {
  const res = await fetch(`/api/games/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`HTTP ${res.status}: DELETE /api/games/${id}`);
}

// ---------------------------------------------------------------------------
// Game Library — list + import
// ---------------------------------------------------------------------------

function resultBadge(result, myColor) {
  if (!result) return '';
  // Determine if the user won/lost/drew based on my_color + PGN result.
  const r = result.trim();
  if (r === '1/2-1/2') return 'draw';
  if (!myColor) return r;
  if (myColor === 'white') return r === '1-0' ? 'win' : 'loss';
  if (myColor === 'black') return r === '0-1' ? 'win' : 'loss';
  return r;
}

function statusLabel(status) {
  const labels = { pending: 'Pending', analyzing: 'Analyzing…', done: 'Analyzed', failed: 'Failed' };
  return labels[status] || status;
}

function renderCoverageHint(games, profile) {
  const total = profile ? profile.games_total : (games ? games.length : 0);
  const tagged = profile ? profile.games_tagged : (games ? games.filter((g) => g.my_color).length : 0);
  const analyzed = profile ? profile.games_analyzed : 0;

  const wrap = el('div', { className: 'review-coverage' });

  const hint = el('div', { className: 'review-coverage-line' });
  hint.appendChild(el('span', {
    className: 'review-coverage-stat',
    textContent: `${tagged} of ${total} games tagged`,
  }));
  hint.appendChild(el('span', { className: 'review-coverage-sep', textContent: '·' }));
  hint.appendChild(el('span', {
    className: 'review-coverage-stat',
    textContent: `${analyzed} analyzed`,
  }));
  wrap.appendChild(hint);

  // Nudge when many games are untagged and total > 0.
  const untagged = total - tagged;
  if (total > 0 && untagged > 0) {
    const nudge = el('div', { className: 'review-coverage-nudge' });
    nudge.textContent =
      `${untagged} game${untagged !== 1 ? 's' : ''} have no color tag — ` +
      'the profile only counts tagged games. Use "Set my color from username" below to tag them in bulk.';
    wrap.appendChild(nudge);
  }

  return wrap;
}

function renderBulkControls() {
  const wrap = el('div', { className: 'review-bulk' });

  // --- "Set my color from username" ---
  const retagSection = el('div', { className: 'review-bulk-section' });
  retagSection.appendChild(el('div', { className: 'review-import-title', textContent: 'Set my color from username' }));

  const retagRow = el('div', { className: 'review-bulk-row' });
  const retagInput = el('input', {
    type: 'text',
    className: 'review-bulk-input',
    placeholder: 'username (or alias1,alias2)',
  });
  retagInput.setAttribute('aria-label', 'Chess username for bulk color tagging');
  const retagBtn = el('button', { className: 'review-btn review-btn-primary', textContent: 'Tag games' });
  retagRow.append(retagInput, retagBtn);

  const retagStatus = el('div', { className: 'review-import-status' });

  retagBtn.addEventListener('click', async () => {
    const username = retagInput.value.trim();
    if (!username) {
      retagStatus.textContent = 'Enter a username first.';
      retagStatus.className = 'review-import-status error';
      return;
    }
    retagBtn.disabled = true;
    retagStatus.textContent = 'Tagging…';
    retagStatus.className = 'review-import-status';
    try {
      const data = await postJSON('/api/games/retag-color', { username });
      retagStatus.textContent = `${data.updated} game${data.updated !== 1 ? 's' : ''} tagged.`;
      retagStatus.className = 'review-import-status success';
      showToast(`${data.updated} games tagged.`);
      await refreshLibraryAndProfile();
    } catch (err) {
      retagStatus.textContent = `Failed: ${err.message}`;
      retagStatus.className = 'review-import-status error';
    } finally {
      retagBtn.disabled = false;
    }
  });

  retagSection.append(retagRow, retagStatus);

  wrap.append(retagSection);
  return wrap;
}

function renderLibrary(games, profile) {
  const host = byId('review-library');
  if (!host) return;
  // Full rebuild clobbers anything the user is typing (retag username, pasted
  // PGN) — auto-poll ticks and action-triggered refreshes both land here, so
  // preserve text-field state across the rebuild.
  const inputSnap = snapshotLibraryInputs();
  host.replaceChildren();

  // Section header
  const hdr = el('div', { className: 'review-section-hdr' });
  hdr.appendChild(el('span', { className: 'review-section-title', textContent: 'Game Library' }));
  host.appendChild(hdr);

  // Coverage hint
  host.appendChild(renderCoverageHint(games, profile));

  // Bulk controls (retag only — analysis is automatic)
  host.appendChild(renderBulkControls());

  // Import controls
  host.appendChild(renderImportControls());

  // Game list
  const listWrap = el('div', { className: 'review-game-list' });

  if (!games || games.length === 0) {
    listWrap.appendChild(el('div', { className: 'review-empty', textContent: 'No games imported yet. Paste a PGN below to get started.' }));
    host.appendChild(listWrap);
    return;
  }

  for (const game of games) {
    const badge = resultBadge(game.result, game.my_color);
    const row = el('div', { className: 'review-game-row' });

    // Players + result
    const players = el('div', { className: 'review-game-players' });
    const white = el('span', { className: 'review-player review-player-white', textContent: fmt(game.white) });
    const vs = el('span', { className: 'review-vs', textContent: 'vs' });
    const black = el('span', { className: 'review-player review-player-black', textContent: fmt(game.black) });
    players.append(white, vs, black);

    const meta = el('div', { className: 'review-game-meta' });

    if (badge) {
      const badgeEl = el('span', { className: `review-badge review-badge-${badge}`, textContent: badge });
      meta.appendChild(badgeEl);
    }
    if (game.opening) {
      meta.appendChild(el('span', { className: 'review-game-opening', textContent: game.opening }));
    }
    if (game.date) {
      meta.appendChild(el('span', { className: 'review-game-date', textContent: game.date }));
    }
    meta.appendChild(el('span', { className: `review-status review-status-${game.analysis_status}`, textContent: statusLabel(game.analysis_status) }));

    // Per-game color control
    const colorRow = el('div', { className: 'review-game-color-row' });
    const colorLabel = el('span', { className: 'review-game-color-label', textContent: 'My color:' });
    const colorSel = el('select', { className: 'review-color-select review-color-select-sm' });
    colorSel.setAttribute('aria-label', 'Set my color for this game');
    [
      { value: '', text: '— unknown' },
      { value: 'white', text: 'White' },
      { value: 'black', text: 'Black' },
    ].forEach(({ value, text }) => {
      const opt = document.createElement('option');
      opt.value = value;
      opt.textContent = text;
      if ((game.my_color || '') === value) opt.selected = true;
      colorSel.appendChild(opt);
    });

    const colorStatus = el('span', { className: 'review-game-color-status' });

    colorSel.addEventListener('change', async () => {
      const newColor = colorSel.value || null;
      colorStatus.textContent = 'Saving…';
      colorStatus.className = 'review-game-color-status';
      try {
        await patchJSON(`/api/games/${game.id}`, { my_color: newColor });
        colorStatus.textContent = 'Saved — pending re-analysis';
        colorStatus.className = 'review-game-color-status review-game-color-status-ok';
        await refreshLibraryAndProfile();
      } catch (err) {
        colorStatus.textContent = `Failed: ${err.message}`;
        colorStatus.className = 'review-game-color-status review-game-color-status-err';
      }
    });

    colorRow.append(colorLabel, colorSel, colorStatus);

    // Actions
    const actions = el('div', { className: 'review-game-actions' });

    const openBtn = el('button', { className: 'review-btn review-btn-primary', textContent: 'Open' });
    openBtn.addEventListener('click', () => openGame(game.id));

    // Status (live polling placeholder)
    const statusEl = el('span', { className: 'review-game-status-live' });

    actions.appendChild(openBtn);

    // pending/analyzing are automation-owned — no manual button.
    if (game.analysis_status === 'done' || game.analysis_status === 'failed') {
      const analyzeBtn = el('button', {
        className: 'review-btn',
        textContent: game.analysis_status === 'done' ? 'Re-analyze' : 'Retry',
      });
      analyzeBtn.addEventListener('click', () => triggerAnalysis(game.id, analyzeBtn, statusEl));
      actions.appendChild(analyzeBtn);
    }

    const deleteBtn = el('button', { className: 'review-btn review-btn-danger', textContent: 'Delete' });
    deleteBtn.addEventListener('click', () => deleteAndRefresh(game.id));
    actions.appendChild(deleteBtn);

    row.append(players, meta, colorRow, actions, statusEl);
    listWrap.appendChild(row);
  }

  host.appendChild(listWrap);

  restoreLibraryInputs(inputSnap);

  // Auto-poll while any listed game is pending/analyzing (automation owns those states).
  maybeStartAutoPoll(games);
}

function renderImportControls() {
  const wrap = el('div', { className: 'review-import' });

  const title = el('div', { className: 'review-import-title', textContent: 'Import PGN' });

  const textarea = el('textarea', {
    className: 'review-pgn-input',
    placeholder: 'Paste PGN text here (one or more games)…',
    'aria-label': 'PGN text to import',
    rows: '5',
  });

  // File upload
  const fileRow = el('div', { className: 'review-import-file-row' });
  const fileInput = el('input', { type: 'file', accept: '.pgn,.txt', className: 'review-file-input', id: 'review-file-input' });
  const fileLabel = el('label', { 'for': 'review-file-input', className: 'review-btn review-btn-file', textContent: 'Choose file' });

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    const text = await file.text();
    textarea.value = text;
  });
  fileRow.append(fileLabel, fileInput);

  // Color override
  const colorRow = el('div', { className: 'review-import-options' });
  const colorLabel = el('label', { className: 'review-option-label', textContent: 'My color: ' });
  const colorSel = el('select', { className: 'review-color-select', 'aria-label': 'My color' });
  ['(auto-detect)', 'white', 'black'].forEach((v) => {
    const opt = document.createElement('option');
    opt.value = v === '(auto-detect)' ? '' : v;
    opt.textContent = v;
    colorSel.appendChild(opt);
  });
  colorRow.append(colorLabel, colorSel);

  const importBtn = el('button', { className: 'review-btn review-btn-primary', textContent: 'Import' });
  const importStatus = el('div', { className: 'review-import-status' });

  importBtn.addEventListener('click', async () => {
    const pgn = textarea.value.trim();
    if (!pgn) {
      importStatus.textContent = 'Please paste a PGN first.';
      importStatus.className = 'review-import-status error';
      return;
    }
    importBtn.disabled = true;
    importStatus.textContent = 'Importing…';
    importStatus.className = 'review-import-status';
    try {
      const body = { pgn };
      const myColor = colorSel.value;
      if (myColor) body.my_color = myColor;
      const data = await postJSON('/api/games/import', body);
      importStatus.textContent = `Imported ${data.imported} game(s). ${data.duplicates ? data.duplicates + ' duplicate(s) skipped.' : ''}`;
      importStatus.className = 'review-import-status success';
      textarea.value = '';
      await refreshLibraryAndProfile();
    } catch (err) {
      importStatus.textContent = `Import failed: ${err.message}`;
      importStatus.className = 'review-import-status error';
    } finally {
      importBtn.disabled = false;
    }
  });

  wrap.append(title, textarea, fileRow, colorRow, importBtn, importStatus);
  return wrap;
}

async function triggerAnalysis(gameId, btn, statusEl) {
  btn.disabled = true;
  if (statusEl) statusEl.textContent = 'Starting…';
  try {
    await postJSON(`/api/games/${gameId}/analyze`, {});
    if (statusEl) statusEl.textContent = 'Analysis started.';
    // Poll status briefly.
    pollStatus(gameId, btn, statusEl);
  } catch (err) {
    if (statusEl) statusEl.textContent = `Failed: ${err.message}`;
    btn.disabled = false;
  }
}

function pollStatus(gameId, btn, statusEl) {
  let attempts = 0;
  const max = 60; // poll up to ~60s
  const interval = setInterval(async () => {
    attempts++;
    try {
      const data = await fetchJSON(`/api/games/${gameId}/status`);
      if (statusEl) statusEl.textContent = statusLabel(data.analysis_status);
      if (data.analysis_status === 'done' || data.analysis_status === 'failed' || attempts >= max) {
        clearInterval(interval);
        if (btn) btn.disabled = false;
        await refreshLibraryAndProfile();
      }
    } catch (_) {
      clearInterval(interval);
      if (btn) btn.disabled = false;
    }
  }, 1000);
}

function hasPendingOrAnalyzing(games) {
  return (games || []).some((g) => g.analysis_status === 'pending' || g.analysis_status === 'analyzing');
}

// renderLibrary rebuilds the whole panel, clobbering anything the user is
// typing (retag username, pasted PGN, import color choice). Snapshot the
// fields with a unique aria-label before the rebuild and restore value +
// focus + cursor after. Duplicate labels (per-game color selects) are
// skipped — their values mirror server state anyway.
function snapshotLibraryInputs() {
  const host = byId('review-library');
  if (!host) return null;
  const byLabel = new Map();
  for (const f of host.querySelectorAll('input[type="text"], textarea, select')) {
    const label = f.getAttribute('aria-label');
    if (!label) continue;
    byLabel.set(label, byLabel.has(label) ? null : f);
  }
  const active = document.activeElement;
  const snap = [];
  for (const [label, f] of byLabel) {
    if (f === null) continue; // duplicate label — ambiguous, skip
    snap.push({
      label,
      value: f.value,
      focused: f === active,
      selStart: f.selectionStart,
      selEnd: f.selectionEnd,
    });
  }
  return snap;
}

function restoreLibraryInputs(snap) {
  if (!snap) return;
  const host = byId('review-library');
  if (!host) return;
  for (const s of snap) {
    const f = host.querySelector(`[aria-label="${s.label}"]`);
    if (!f) continue;
    f.value = s.value;
    if (s.focused) {
      f.focus();
      if (s.selStart != null && typeof f.setSelectionRange === 'function') {
        try { f.setSelectionRange(s.selStart, s.selEnd); } catch (_) { /* selects */ }
      }
    }
  }
}

// Start the auto-analysis poll if any listed game is pending/analyzing and no
// poll is already running. Analysis itself is kicked off server-side
// (import/retag/color-change/boot/engine-restart) — this only reflects progress.
function maybeStartAutoPoll(games) {
  if (_analyzeAllInterval !== null) return; // already running — guard against double intervals
  if (!hasPendingOrAnalyzing(games)) return; // nothing pending — a poll here would never toast

  _analyzeAllInterval = setInterval(async () => {
    try {
      const [polledGames, profile] = await Promise.all([
        fetchJSON('/api/games').catch(() => []),
        fetchJSON('/api/profile').catch(() => null),
      ]);
      renderLibrary(polledGames, profile);
      renderProfile(profile);
      if (!hasPendingOrAnalyzing(polledGames)) {
        clearInterval(_analyzeAllInterval);
        _analyzeAllInterval = null;
        showToast('All games analyzed.');
      }
    } catch (_) {
      // Network blip — keep polling, do not stop.
    }
  }, 1500);
}

function showToast(message) {
  const container = byId('toasts');
  if (!container) return;
  const toast = el('div', { className: 'review-toast', textContent: message });
  container.appendChild(toast);
  // Auto-remove after 3.5s.
  setTimeout(() => {
    toast.classList.add('review-toast-fade');
    setTimeout(() => toast.remove(), 400);
  }, 3100);
}

async function deleteAndRefresh(gameId) {
  try {
    await deleteGame(gameId);
    await refreshLibraryAndProfile();
  } catch (err) {
    // Degraded — just refresh.
    await refreshLibraryAndProfile().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Open a game → enter review mode
// ---------------------------------------------------------------------------

export async function openGame(gameId) {
  let gameDetail;
  try {
    gameDetail = await fetchJSON(`/api/games/${gameId}`);
  } catch (err) {
    return;
  }

  _openedGameId = gameId;
  _reviewData = null; // clear stale data

  // Enter review mode (sets board + state via api.actions).
  if (_api && _api.actions && _api.actions.enterReview) {
    _api.actions.enterReview(gameDetail);
  }

  // Activate the Analysis panel directly (the tab-click handler is gated to play
  // mode only, so clicking the button is a no-op in review mode).
  const tabsEl = byId('panel-tabs');
  if (tabsEl) {
    tabsEl.querySelectorAll('button[data-tab]').forEach((b) => {
      const on = b.dataset.tab === 'analysis';
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', String(on));
    });
  }
  ['analysis', 'opening', 'traps', 'repertoire', 'review', 'insights'].forEach((name) => {
    const panel = byId(`tab-${name}`);
    if (panel) panel.classList.toggle('is-active', name === 'analysis');
  });

  // Clear the previous game's summary/foresight/narrative before the new data arrives.
  renderGameSummary(null);
  const foresightHost = byId('review-foresight');
  if (foresightHost) foresightHost.replaceChildren();
  _narrativeData = null;
  _narrativeGenerating = false;
  _narrativeExpanded = false;
  renderNarrativePanel();

  // Load review data (leaks + foresight) in the background if analysis is
  // done; a game opened mid-analysis has no data yet, so poll and load the
  // moment analysis completes (otherwise the replay shows no evals forever).
  if (gameDetail.analysis_status === 'done') {
    loadReviewData(gameId);
  } else {
    awaitAnalysisThenLoad(gameId);
  }
}

// Poll an opened game that is still pending/analyzing; show a progress note
// and pull in evals/leaks/summary as soon as the background analysis lands.
function awaitAnalysisThenLoad(gameId) {
  if (_openStatusInterval !== null) {
    clearInterval(_openStatusInterval);
    _openStatusInterval = null;
  }
  renderAnalyzingNote('Analyzing this game — evaluations will appear when ready…');
  let attempts = 0;
  const max = 300; // give up after ~5 min; a single game never takes that long
  _openStatusInterval = setInterval(async () => {
    attempts++;
    try {
      const data = await fetchJSON(`/api/games/${gameId}/status`);
      if (_openedGameId !== gameId || attempts >= max) {
        clearInterval(_openStatusInterval);
        _openStatusInterval = null;
        return;
      }
      if (data.analysis_status === 'done') {
        clearInterval(_openStatusInterval);
        _openStatusInterval = null;
        loadReviewData(gameId);
      } else if (data.analysis_status === 'failed') {
        clearInterval(_openStatusInterval);
        _openStatusInterval = null;
        renderAnalyzingNote('Analysis failed — use Retry in the game library.');
      }
    } catch (_) {
      // Network blip — keep polling until the attempt cap.
    }
  }, 1000);
}

// Progress note shown in the review bar's summary slot. renderGameSummary
// overwrites it when real data arrives; replay navigation never touches it.
function renderAnalyzingNote(message) {
  const el_ = document.getElementById('review-game-summary');
  if (!el_) return;
  el_.replaceChildren(el('div', { className: 'review-analyzing-note', textContent: message }));
  el_.hidden = false;
}

async function loadReviewData(gameId) {
  try {
    _reviewData = await fetchJSON(`/api/games/${gameId}/review`);
    // Trigger foresight + stored-eval render for current ply (0 at entry). The
    // data lands asynchronously after enterReview, so this is the first chance
    // to paint the real eval — before this the panel shows stale play analysis.
    const currentState = _api && _api.actions && _api.actions.getState();
    if (currentState) {
      renderForesight(currentState.cursor);
      renderReplayEval(currentState.cursor);
    }
    renderGameSummary(_reviewData && _reviewData.summary ? _reviewData.summary : null);
  } catch (_) {
    _reviewData = null;
  }

  // Narrative fetch failure (network blip, or route not yet deployed) degrades
  // silently to the disabled state — no console noise, no toast spam.
  try {
    _narrativeData = await fetchJSON(`/api/games/${gameId}/narrative`);
  } catch (_) {
    _narrativeData = { enabled: false, narrative: null };
  }
  _narrativeExpanded = false;
  renderNarrativePanel();
  // Re-render foresight so any moment cards for the current ply appear once
  // the narrative arrives (it lands after the /review fetch above).
  const currentState = _api && _api.actions && _api.actions.getState();
  if (currentState) renderForesight(currentState.cursor);
}

// ---------------------------------------------------------------------------
// Game summary — shown in #review-game-summary in the review-bar
// ---------------------------------------------------------------------------

function renderGameSummary(summary) {
  const el_ = document.getElementById('review-game-summary');
  if (!el_) return;

  if (!summary || (summary.white_accuracy == null && summary.black_accuracy == null)) {
    el_.hidden = true;
    el_.replaceChildren();
    return;
  }

  // Determine display order and labels based on my_color.
  let first, second;
  if (summary.my_color === 'white') {
    first  = { label: 'You',      acc: summary.white_accuracy, elo: summary.white_elo };
    second = { label: 'Opponent', acc: summary.black_accuracy, elo: summary.black_elo };
  } else if (summary.my_color === 'black') {
    first  = { label: 'You',      acc: summary.black_accuracy, elo: summary.black_elo };
    second = { label: 'Opponent', acc: summary.white_accuracy, elo: summary.white_elo };
  } else {
    first  = { label: 'White', acc: summary.white_accuracy, elo: summary.white_elo };
    second = { label: 'Black', acc: summary.black_accuracy, elo: summary.black_elo };
  }

  const fmtAcc = (acc) => (acc == null ? '—' : acc.toFixed(1) + '%');
  const fmtElo = (elo) => (elo == null ? '—' : '~' + elo);

  const buildSide = ({ label, acc, elo }) => {
    const side = el('div', { className: 'rgs-side' });
    side.appendChild(el('span', { className: 'rgs-label', textContent: label }));
    side.appendChild(el('span', { className: 'rgs-acc',   textContent: fmtAcc(acc) }));

    const eloSpan = el('span', {
      className: 'rgs-elo',
      title: 'Estimated from this single game — a rough heuristic, not an official rating.',
    });
    eloSpan.appendChild(document.createTextNode(fmtElo(elo) + ' '));
    eloSpan.appendChild(el('span', { className: 'rgs-est', textContent: 'est.' }));
    side.appendChild(eloSpan);

    return side;
  };

  el_.replaceChildren(buildSide(first), buildSide(second));
  el_.hidden = false;
}

// ---------------------------------------------------------------------------
// Replay eval — paint the STORED per-ply eval into the analysis panel + eval
// bar for the current replay position. review mode never re-runs the live
// engine (goto skips refreshAnalysis), so without this the panel stays frozen
// on whatever it last showed. `eval_cp_white` is the eval of that ply's
// `fen_before` (position BEFORE the move), and the plies array is ply-ordered,
// so plies[cursor] is exactly the position at `cursor` (after `cursor` plies).
// The final position (cursor === plies.length) and any ply skipped by
// analyze-my-color (eval_cp_white === null) render as a neutral bar + '—'.
// best-move / PV aren't stored per ply, so renderAnalysis shows '—' for them.
// ---------------------------------------------------------------------------

function renderReplayEval(cursor) {
  if (!_api || !_api.hub || typeof _api.hub.renderAnalysis !== 'function') return;
  const plies = _reviewData && _reviewData.plies;
  if (!plies) return; // review data not loaded yet — leave the panel untouched
  const ply = plies[cursor];
  const a = (ply && (ply.eval_cp_white != null || ply.mate_white != null))
    ? { evalCp: ply.eval_cp_white ?? null, mate: ply.mate_white ?? null }
    : null;
  _api.hub.renderAnalysis(a);
}

// ---------------------------------------------------------------------------
// Foresight cards — shown in #review-foresight, now in the Analysis panel's
// review column (#analysis-review-col, right of the eval readouts), not under
// #review-bar. AI narrative moment cards are appended here too.
// ---------------------------------------------------------------------------

function renderForesight(ply) {
  const host = byId('review-foresight');
  if (!host) return;
  host.replaceChildren();

  if (_reviewData && _reviewData.leaks && _reviewData.leaks.length > 0) {
    const leaks = _reviewData.leaks;

    // Check if the current ply matches any lead_in_ply (show warning card BEFORE the blunder).
    const leadInLeaks = leaks.filter((l) => l.lead_in_ply === ply);
    // Check if the current ply matches any blunder ply (tie-back warning).
    const blunderLeaks = leaks.filter((l) => l.ply === ply);

    // Lead-in warnings (highest priority — shown before the blunder occurs).
    for (const leak of leadInLeaks) {
      host.appendChild(renderForesightCard(leak, 'lead-in'));
    }

    // Blunder tie-back (gentler — the foresight already warned you).
    for (const leak of blunderLeaks) {
      // Only show tie-back if we haven't already shown a lead-in for this exact leak.
      const alreadyShown = leadInLeaks.some((l) => l.id === leak.id);
      if (!alreadyShown) {
        host.appendChild(renderForesightCard(leak, 'tie-back'));
      }
    }
  }

  // AI narrative moment cards — appended after any foresight cards, never
  // replacing them. Distinct styling (review-moment-card) + a small "AI" tag.
  const moments = _narrativeData && _narrativeData.narrative && _narrativeData.narrative.moments;
  if (moments && moments.length > 0) {
    for (const moment of moments.filter((m) => m.ply === ply)) {
      host.appendChild(renderMomentCard(moment));
    }
  }
}

function renderMomentCard(moment) {
  const card = el('div', { className: 'review-moment-card' });
  const hdr = el('div', { className: 'review-moment-hdr' });
  hdr.appendChild(el('span', { className: 'review-moment-tag', textContent: 'AI' }));
  card.appendChild(hdr);
  card.appendChild(el('p', { className: 'review-moment-text', textContent: moment.text }));
  return card;
}

function renderForesightCard(leak, kind) {
  const card = el('div', { className: `review-foresight-card review-foresight-${kind}` });

  // Header row: severity badge + phase.
  const hdr = el('div', { className: 'review-foresight-hdr' });
  const badge = el('span', {
    className: `review-severity review-severity-${leak.severity}`,
    textContent: kind === 'tie-back' ? 'Here it cost you' : `Watch out — ${leak.severity}`,
  });
  const phase = el('span', { className: 'review-foresight-phase', textContent: leak.phase });
  hdr.append(badge, phase);
  card.appendChild(hdr);

  if (kind === 'tie-back') {
    const tieBack = el('p', {
      className: 'review-foresight-tieback',
      textContent: `This is the ${leak.severity} (ply ${leak.ply}). The warning was shown at ply ${leak.lead_in_ply}.`,
    });
    if (leak.best_san) {
      const best = el('p', { className: 'review-foresight-best', textContent: `Best: ${leak.best_san}` });
      card.append(tieBack, best);
    } else {
      card.appendChild(tieBack);
    }
    return card;
  }

  // Lead-in card: narration buckets (Threat / Hanging / Plan / Summary).
  const narration = leak.narration || {};

  if (narration.threat) {
    const section = el('div', { className: 'review-narration-bucket' });
    section.appendChild(el('div', { className: 'review-bucket-label', textContent: 'Threat' }));
    section.appendChild(el('p', { className: 'review-bucket-text', textContent: narration.threat }));
    card.appendChild(section);
  }

  if (narration.hanging) {
    const section = el('div', { className: 'review-narration-bucket' });
    section.appendChild(el('div', { className: 'review-bucket-label', textContent: 'Hanging' }));
    section.appendChild(el('p', { className: 'review-bucket-text', textContent: narration.hanging }));
    card.appendChild(section);
  }

  if (narration.plan) {
    const section = el('div', { className: 'review-narration-bucket' });
    section.appendChild(el('div', { className: 'review-bucket-label', textContent: 'Plan' }));
    section.appendChild(el('p', { className: 'review-bucket-text', textContent: narration.plan }));
    card.appendChild(section);
  }

  if (narration.summary) {
    const section = el('div', { className: 'review-narration-bucket review-narration-summary' });
    section.appendChild(el('p', { className: 'review-bucket-text', textContent: narration.summary }));
    card.appendChild(section);
  }

  // Category + win-prob drop (context, not a scolding).
  const ctx = el('div', { className: 'review-foresight-ctx' });
  if (leak.category) ctx.appendChild(el('span', { className: 'review-category', textContent: leak.category }));
  if (typeof leak.win_prob_drop === 'number') {
    const pct = Math.round(leak.win_prob_drop * 100);
    ctx.appendChild(el('span', { className: 'review-win-drop', textContent: `Win% −${pct}%` }));
  }
  if (ctx.children.length) card.appendChild(ctx);

  return card;
}

// ---------------------------------------------------------------------------
// Narrative panel — shown in #review-narrative, which now lives in the
// Analysis panel (`.analysis-eval-row`, right of the eval readouts), not
// under #review-bar (never rendered inside #review-game-summary — that host
// is owned by renderGameSummary/renderAnalyzingNote).
// ---------------------------------------------------------------------------

function renderNarrativePanel() {
  const host = byId('review-narrative');
  if (!host) return;
  host.replaceChildren();

  if (!_narrativeData) {
    host.hidden = true;
    return;
  }
  host.hidden = false;

  if (_narrativeGenerating) {
    host.appendChild(renderNarrativeCta('Generating…', { disabled: true }));
    return;
  }

  const { enabled, narrative } = _narrativeData;

  if (narrative) {
    host.appendChild(renderNarrativeStory(narrative));
    return;
  }

  if (!enabled) {
    host.appendChild(renderNarrativeCta('Generate commentary', {
      disabled: true,
      hint: 'Set ANTHROPIC_API_KEY to enable AI commentary',
    }));
    return;
  }

  host.appendChild(renderNarrativeCta('Generate commentary', {
    onClick: () => generateNarrative(),
  }));
}

function renderNarrativeCta(label, { disabled = false, hint = null, onClick = null } = {}) {
  const wrap = el('div', { className: 'review-narrative-cta' });
  const btn = el('button', { className: 'review-btn review-btn-primary', textContent: label });
  btn.disabled = disabled;
  if (onClick) btn.addEventListener('click', onClick);
  wrap.appendChild(btn);
  if (hint) wrap.appendChild(el('div', { className: 'review-narrative-hint', textContent: hint }));
  return wrap;
}

function renderNarrativeStory(narrative) {
  const wrap = el('div', { className: 'review-narrative-story' });

  const hdr = el('div', { className: 'review-narrative-hdr' });
  hdr.appendChild(el('h3', { className: 'review-narrative-title', textContent: 'AI Game Commentary' }));
  const regenBtn = el('button', { className: 'review-btn review-narrative-regen', textContent: 'Regenerate' });
  regenBtn.addEventListener('click', () => generateNarrative());
  hdr.appendChild(regenBtn);
  wrap.appendChild(hdr);

  const body = el('div', { className: 'review-narrative-body' });
  if (!_narrativeExpanded) body.classList.add('review-narrative-collapsed');

  for (const chapter of narrative.chapters || []) {
    const chapterEl = el('div', { className: 'review-narrative-chapter' });
    if (chapter.phase) {
      chapterEl.appendChild(el('div', { className: 'review-narrative-phase', textContent: chapter.phase }));
    }
    chapterEl.appendChild(el('p', { className: 'review-narrative-text', textContent: chapter.text }));
    body.appendChild(chapterEl);
  }
  if (narrative.overall) {
    const overallEl = el('div', { className: 'review-narrative-chapter' });
    overallEl.appendChild(el('p', { className: 'review-narrative-text', textContent: narrative.overall }));
    body.appendChild(overallEl);
  }
  wrap.appendChild(body);

  const toggle = el('button', {
    className: 'review-narrative-toggle',
    textContent: _narrativeExpanded ? 'Show less' : 'Read more',
  });
  toggle.addEventListener('click', () => {
    _narrativeExpanded = !_narrativeExpanded;
    renderNarrativePanel();
  });
  wrap.appendChild(toggle);

  return wrap;
}

async function generateNarrative() {
  if (!_openedGameId || _narrativeGenerating) return;
  _narrativeGenerating = true;
  renderNarrativePanel();
  try {
    const data = await postJSON(`/api/games/${_openedGameId}/narrative`, {});
    _narrativeData = data;
    _narrativeExpanded = false;
    const currentState = _api && _api.actions && _api.actions.getState();
    if (currentState) renderForesight(currentState.cursor);
  } catch (err) {
    showToast(`Commentary failed: ${err.detail || err.message}`);
  } finally {
    _narrativeGenerating = false;
    renderNarrativePanel();
  }
}

// ---------------------------------------------------------------------------
// Profile dashboard
// ---------------------------------------------------------------------------

async function refreshLibraryAndProfile() {
  try {
    const [games, profile] = await Promise.all([
      fetchJSON('/api/games').catch(() => []),
      fetchJSON('/api/profile').catch(() => null),
    ]);
    renderLibrary(games, profile);
    renderProfile(profile);
  } catch (_) {
    // Degraded — render empty states.
    renderLibrary([], null);
    renderProfile(null);
  }
}

function renderProfile(profile) {
  const host = byId('review-profile');
  if (!host) return;
  host.replaceChildren();

  if (!profile || profile.games_analyzed === 0) {
    const emptyWrap = el('div', { className: 'review-profile-wrap' });
    // Show coverage header even when no analysis yet (so user knows what to do).
    emptyWrap.appendChild(el('div', { className: 'review-section-hdr' }, [
      el('span', { className: 'review-section-title', textContent: 'Your Coaching Profile' }),
    ]));
    if (profile && profile.games_total > 0) {
      const statsRow = el('div', { className: 'review-stats-row' });
      statsRow.appendChild(reviewStat('Total Games', profile.games_total));
      statsRow.appendChild(reviewStat('Tagged', profile.games_tagged));
      statsRow.appendChild(reviewStat('Analyzed', profile.games_analyzed));
      emptyWrap.appendChild(statsRow);
    }
    emptyWrap.appendChild(el('div', { className: 'review-profile-empty', textContent: 'No analyzed games yet. Import some games to see your coaching profile — analysis starts automatically.' }));
    host.appendChild(emptyWrap);
    return;
  }

  const wrap = el('div', { className: 'review-profile-wrap' });

  // Header
  wrap.appendChild(el('div', { className: 'review-section-hdr' }, [
    el('span', { className: 'review-section-title', textContent: 'Your Coaching Profile' }),
  ]));

  // Stats row: total / tagged / analyzed + hope-chess rate.
  const statsRow = el('div', { className: 'review-stats-row' });
  if (profile.games_total > 0) {
    statsRow.appendChild(reviewStat('Total Games', profile.games_total));
    statsRow.appendChild(reviewStat('Tagged', profile.games_tagged));
  }
  statsRow.appendChild(reviewStat('Games Analyzed', profile.games_analyzed));
  const hopeRate = typeof profile.hope_chess_rate === 'number'
    ? Math.round(profile.hope_chess_rate * 100) + '%'
    : '—';
  statsRow.appendChild(reviewStat('Hope Chess Rate', hopeRate, 'Games where you missed a developing threat'));
  wrap.appendChild(statsRow);

  // Top leaks.
  if (profile.top_leaks && profile.top_leaks.length > 0) {
    wrap.appendChild(el('div', { className: 'review-subsection-title', textContent: 'Top Recurring Mistakes' }));
    const leakList = el('div', { className: 'review-leak-list' });
    for (const leak of profile.top_leaks) {
      const row = el('div', { className: 'review-leak-row' });
      const name = el('span', { className: 'review-leak-category', textContent: leak.category || leak.coach || '—' });
      const count = el('span', { className: 'review-leak-count', textContent: `${leak.count}×` });
      if (leak.coach && leak.category && leak.coach !== leak.category) {
        const coach = el('span', { className: 'review-leak-coach', textContent: leak.coach });
        row.append(name, coach, count);
      } else {
        row.append(name, count);
      }
      leakList.appendChild(row);
    }
    wrap.appendChild(leakList);
  }

  // By phase.
  if (profile.by_phase && Object.keys(profile.by_phase).length > 0) {
    wrap.appendChild(el('div', { className: 'review-subsection-title', textContent: 'By Game Phase' }));
    const phaseWrap = el('div', { className: 'review-phase-list' });
    for (const [phase, count] of Object.entries(profile.by_phase)) {
      phaseWrap.appendChild(el('div', { className: 'review-phase-row' }, [
        el('span', { className: 'review-phase-name', textContent: phase }),
        el('span', { className: 'review-phase-count', textContent: String(count) }),
      ]));
    }
    wrap.appendChild(phaseWrap);
  }

  // By color.
  if (profile.by_color && Object.keys(profile.by_color).length > 0) {
    wrap.appendChild(el('div', { className: 'review-subsection-title', textContent: 'By Color' }));
    const colorWrap = el('div', { className: 'review-phase-list' });
    for (const [color, count] of Object.entries(profile.by_color)) {
      colorWrap.appendChild(el('div', { className: 'review-phase-row' }, [
        el('span', { className: 'review-phase-name', textContent: color }),
        el('span', { className: 'review-phase-count', textContent: String(count) }),
      ]));
    }
    wrap.appendChild(colorWrap);
  }

  // By opening.
  if (profile.by_opening && profile.by_opening.length > 0) {
    wrap.appendChild(el('div', { className: 'review-subsection-title', textContent: 'By Opening' }));
    const opList = el('div', { className: 'review-opening-list' });
    for (const op of profile.by_opening.slice(0, 5)) {
      opList.appendChild(el('div', { className: 'review-opening-row' }, [
        el('span', { className: 'review-opening-name', textContent: op.opening || op.eco || '—' }),
        el('span', { className: 'review-opening-count', textContent: `${op.count}×` }),
      ]));
    }
    wrap.appendChild(opList);
  }

  // Trend.
  if (profile.trend && profile.trend.length > 0) {
    wrap.appendChild(el('div', { className: 'review-subsection-title', textContent: 'Trend' }));
    const trendWrap = el('div', { className: 'review-trend' });
    for (const bucket of profile.trend) {
      const bucketEl = el('div', { className: 'review-trend-bucket' });
      bucketEl.appendChild(el('span', { className: 'review-trend-date', textContent: bucket.bucket || '' }));
      bucketEl.appendChild(el('span', { className: 'review-trend-count', textContent: String(bucket.count || 0) }));
      trendWrap.appendChild(bucketEl);
    }
    wrap.appendChild(trendWrap);
  }

  host.appendChild(wrap);
}

function reviewStat(label, value, subtitle) {
  const stat = el('div', { className: 'review-stat' });
  stat.appendChild(el('div', { className: 'review-stat-value', textContent: String(value) }));
  stat.appendChild(el('div', { className: 'review-stat-label', textContent: label }));
  if (subtitle) stat.appendChild(el('div', { className: 'review-stat-sub', textContent: subtitle }));
  return stat;
}

// ---------------------------------------------------------------------------
// Keyboard navigation in review mode (← →)
// ---------------------------------------------------------------------------

function onKeyDown(e) {
  const state = _api && _api.actions && _api.actions.getState();
  if (!state || state.mode !== 'review') return;
  if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT')) return;

  if (e.key === 'ArrowLeft') {
    e.preventDefault();
    _api.actions.goto(Math.max(0, state.cursor - 1));
  } else if (e.key === 'ArrowRight') {
    e.preventDefault();
    _api.actions.goto(Math.min(state.moves.length, state.cursor + 1));
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export function initReview(api) {
  _api = api;

  // Subscribe to review:ply to drive foresight cards + the stored-eval readout.
  if (api && api.on) {
    api.on('review:ply', (ply) => {
      renderForesight(ply);
      renderReplayEval(ply);
    });
  }

  // Keyboard nav.
  document.addEventListener('keydown', onKeyDown);

  // Initial load of library + profile.
  refreshLibraryAndProfile();
}
