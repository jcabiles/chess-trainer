// insights.js — Insights tab: a triage-router dashboard over already-persisted
// game-review data (openings / recurring-mistakes / endgames diagnostics).
//
// Injected-api module: all app dependencies arrive via `api` (no imports from
// app.js — mirrors review.js's one-directional contract). Copies small idioms
// (el()) as module-private helpers rather than importing them from review.js.
//
// T1.5 — Openings panel: renders GET /api/insights/openings (win% by opening,
// repertoire adherence, named-theory fallback). Data is fetched lazily, the
// first time the Insights tab button is clicked (via the already-injected
// api.mounts.tabs element — no new wiring added to app.js). Deep-links reuse
// api.actions.openGameAtPly (T0.2). Phase 2/3 (mistakes/endgames) reuse
// renderThinData() + the .insights-trend CSS class for their single
// de-emphasized long-run trend slot.

const byId = (id) => document.getElementById(id);

let _api = null;
let _loaded = false; // true once the openings fetch has been kicked off

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

function fmt1(v, unit = '') {
  return v == null ? '—' : `${Math.round(v * 10) / 10}${unit}`;
}

function scorePct(score) {
  return `${Math.round(score * 100)}%`;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// T0.3 — honesty / min-sample UI convention
// ---------------------------------------------------------------------------

// Shared muted "not enough games yet" render for any panel section whose
// sample count `n` is below the min-sample gate (backend default: 5 — see
// app/insights.py's {value, n, sufficient} records). Returns a detached DOM
// node; callers append it wherever their honest section belongs instead of
// fabricating a pattern from a too-small sample.
function renderThinData(n, minSample = 5) {
  return el('p', { className: 'insights-thin-data' }, [
    `Not enough games yet (n=${n}, need ${minSample}+).`,
  ]);
}

// ---------------------------------------------------------------------------
// Empty / loading states
// ---------------------------------------------------------------------------

function renderEmptyState(message) {
  const root = byId('insights-root');
  if (!root) return;
  root.replaceChildren(
    el('div', { className: 'empty-state' }, [
      el('p', {}, [message || 'No insights yet — analyzed games will surface opening, mistake, and endgame diagnostics here.']),
    ])
  );
}

function renderLoading() {
  const root = byId('insights-root');
  if (!root) return;
  root.replaceChildren(el('p', { className: 'insights-loading' }, ['Loading insights…']));
}

// ---------------------------------------------------------------------------
// Deep-link buttons (T0.2 seam: api.actions.openGameAtPly)
// ---------------------------------------------------------------------------

function renderDeepLinkButton(gameId, ply, label) {
  const btn = el('button', {
    type: 'button',
    className: 'insights-deep-link',
    'data-game-id': String(gameId),
    'data-ply': String(ply),
  }, [label]);
  btn.addEventListener('click', () => {
    if (_api && _api.actions && _api.actions.openGameAtPly) {
      _api.actions.openGameAtPly(gameId, ply);
    }
  });
  return btn;
}

// ---------------------------------------------------------------------------
// Win% by opening (family rows, expandable to per-line rows)
// ---------------------------------------------------------------------------

function renderLineRow(line) {
  const row = el('div', { className: 'insights-row' + (line.sufficient ? '' : ' insights-row-thin') });
  row.appendChild(el('span', { className: 'insights-row-name' }, [line.opening]));
  row.appendChild(el('span', {}, [`${line.wins}-${line.draws}-${line.losses}`]));
  row.appendChild(el('span', {}, [scorePct(line.score)]));
  row.appendChild(el('span', {}, [`n=${line.n}`]));
  return row;
}

function renderFamilyRow(fam, allLines, idx) {
  const linesId = `insights-fam-lines-${idx}`;
  const wrap = el('div', { className: 'insights-fam' });

  const toggle = el('button', {
    type: 'button',
    className: 'insights-fam-toggle' + (fam.sufficient ? '' : ' insights-row-thin'),
    'aria-expanded': 'false',
    'aria-controls': linesId,
    'data-family': fam.opening,
    'data-color': fam.color,
  }, [
    el('span', { className: 'insights-row-name' }, [`${fam.opening} · ${fam.color}`]),
    el('span', {}, [`${fam.wins}-${fam.draws}-${fam.losses}`]),
    el('span', {}, [scorePct(fam.score)]),
    el('span', {}, [`n=${fam.n}`]),
  ]);

  const lines = allLines.filter((l) => l.family === fam.opening && l.color === fam.color);
  const linesBox = el('div', { className: 'insights-fam-lines', id: linesId });
  linesBox.hidden = true;
  if (lines.length) {
    lines.forEach((line) => linesBox.appendChild(renderLineRow(line)));
  } else {
    linesBox.appendChild(el('p', { className: 'insights-empty-note' }, ['No individual lines recorded yet.']));
  }

  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!open));
    linesBox.hidden = open;
  });

  wrap.append(toggle, linesBox);
  return wrap;
}

function renderWinRates(winRates) {
  const section = el('section', { className: 'insights-section', 'data-section': 'win-rates' });
  section.appendChild(el('h3', { className: 'eval-label' }, ['Win% by Opening']));

  const families = (winRates && winRates.families) || [];
  if (!families.length) {
    section.appendChild(el('p', { className: 'insights-empty-note' }, ['No opening data yet.']));
    return section;
  }

  const list = el('div', { className: 'insights-fam-list' });
  families.forEach((fam, idx) => list.appendChild(renderFamilyRow(fam, (winRates && winRates.lines) || [], idx)));
  section.appendChild(list);
  return section;
}

// ---------------------------------------------------------------------------
// Repertoire adherence
// ---------------------------------------------------------------------------

function renderGatedLine(label, metric, unit = '') {
  const frag = document.createDocumentFragment();
  frag.appendChild(el('p', { className: 'insights-metric-line' }, [`${label}: ${fmt1(metric.value, unit)} (n=${metric.n})`]));
  if (!metric.sufficient) frag.appendChild(renderThinData(metric.n));
  return frag;
}

function renderAdherenceLineRow(line) {
  const row = el('div', { className: 'insights-row' + (line.sufficient ? '' : ' insights-row-thin') });
  row.appendChild(el('span', { className: 'insights-row-name' }, [line.name + (line.color ? ` (${line.color})` : '')]));
  row.appendChild(el('span', {}, [`prep depth ${fmt1(line.avg_followed_prep_depth)}`]));
  row.appendChild(el('span', {}, [`${line.deviations} deviation${line.deviations === 1 ? '' : 's'}`]));
  row.appendChild(el('span', {}, [`n=${line.n}`]));
  return row;
}

function renderAdherenceGameRow(game) {
  const row = el('div', { className: 'insights-row' });
  row.appendChild(el('span', {}, [`Game #${game.game_id}`]));
  row.appendChild(el('span', {}, [`followed ${game.followed_prep_depth} plies`]));
  if (game.deviation_ply != null) {
    const detail = game.deviation_move
      ? `deviated at ply ${game.deviation_ply} (${game.deviation_move}${game.prepared_san ? ` vs prep ${game.prepared_san}` : ''})`
      : `deviated at ply ${game.deviation_ply}`;
    row.appendChild(el('span', {}, [detail]));
    row.appendChild(renderDeepLinkButton(game.game_id, game.deviation_ply, `Open at deviation (ply ${game.deviation_ply})`));
  } else {
    row.appendChild(el('span', { className: 'insights-row-thin' }, ['Followed prep fully — no deviation']));
  }
  return row;
}

function renderAdherence(adherence) {
  const section = el('section', { className: 'insights-section', 'data-section': 'adherence' });
  section.appendChild(el('h3', { className: 'eval-label' }, ['Repertoire Adherence']));

  if (!adherence || !adherence.n) {
    section.appendChild(el('p', { className: 'insights-empty-note' }, ['No games matched your prepared repertoire yet.']));
    return section;
  }

  section.appendChild(renderGatedLine('Avg. prep depth followed', adherence.avg_followed_prep_depth, ' plies'));

  const lines = adherence.lines || [];
  if (lines.length) {
    const list = el('div', { className: 'insights-adherence-lines' });
    lines.forEach((line) => list.appendChild(renderAdherenceLineRow(line)));
    section.appendChild(list);
  }

  const games = adherence.games || [];
  if (games.length) {
    const list = el('div', { className: 'insights-adherence-games' });
    games.forEach((g) => list.appendChild(renderAdherenceGameRow(g)));
    section.appendChild(list);
  }

  return section;
}

// ---------------------------------------------------------------------------
// Theory / soundness (off-repertoire games)
// ---------------------------------------------------------------------------

function renderTheoryGameRow(game) {
  const row = el('div', { className: 'insights-row' });
  row.appendChild(el('span', {}, [`Game #${game.game_id}`]));
  // book_exit_ply === 0 means the game never entered book — "book-exit ply 0" /
  // "Open at book exit (ply 0)" would wrongly imply an exit event happened.
  const neverInBook = game.book_exit_ply === 0;
  row.appendChild(el('span', {}, [neverInBook ? 'never reached named theory' : `book-exit ply ${game.book_exit_ply}`]));
  row.appendChild(el('span', {}, [game.opening_accuracy != null ? `accuracy ${fmt1(game.opening_accuracy, '%')}` : 'accuracy —']));
  const label = neverInBook ? 'Open game (no book moves)' : `Open at book exit (ply ${game.book_exit_ply})`;
  row.appendChild(renderDeepLinkButton(game.game_id, game.book_exit_ply, label));
  return row;
}

function renderTheory(theory) {
  const section = el('section', { className: 'insights-section', 'data-section': 'theory' });
  section.appendChild(el('h3', { className: 'eval-label' }, ['Theory / Soundness']));

  if (!theory || !theory.n) {
    section.appendChild(el('p', { className: 'insights-empty-note' }, ['No off-repertoire games yet.']));
    return section;
  }

  section.appendChild(renderGatedLine('Avg. book-exit ply', theory.avg_book_exit_ply));
  section.appendChild(renderGatedLine('Avg. opening accuracy', theory.avg_opening_accuracy, '%'));
  if (theory.note) section.appendChild(el('p', { className: 'insights-note' }, [theory.note]));

  const games = theory.games || [];
  if (games.length) {
    const list = el('div', { className: 'insights-theory-games' });
    games.forEach((g) => list.appendChild(renderTheoryGameRow(g)));
    section.appendChild(list);
  }

  return section;
}

// ---------------------------------------------------------------------------
// Panel assembly + fetch
// ---------------------------------------------------------------------------

function renderCoverage(coverage) {
  return el('p', { className: 'insights-coverage', id: 'insights-coverage' }, [
    `${coverage.qualified} of ${coverage.total} games analyzed + color-tagged.`,
  ]);
}

function renderOpeningsPanel(data) {
  const coverage = data && data.coverage;
  if (!coverage || !coverage.qualified) {
    renderEmptyState('No analyzed, color-tagged games yet — analyze + tag a game to see openings insights.');
    return;
  }

  const root = byId('insights-root');
  if (!root) return;
  root.replaceChildren(
    renderCoverage(coverage),
    renderWinRates(data.win_rates),
    renderAdherence(data.adherence),
    renderTheory(data.theory),
  );
}

async function loadOpenings() {
  renderLoading();
  try {
    const data = await fetchJSON('/api/insights/openings');
    renderOpeningsPanel(data);
  } catch (_) {
    // Degraded — an honest empty state, never a raw error (matches review.js's
    // fetch-failure precedent, e.g. loadTraps()).
    renderEmptyState("Couldn't load insights right now.");
  }
}

// Lazily fetch the first time the Insights tab is actually shown, using the
// already-injected api.mounts.tabs element (no new wiring in app.js). Mirrors
// app.js's own tab-click gate: switching tabs is a no-op outside 'play' mode,
// so a click there would not actually reveal this panel either.
function wireLazyLoad(api) {
  const tabsEl = api && api.mounts && api.mounts.tabs;
  if (!tabsEl) { if (!_loaded) { _loaded = true; loadOpenings(); } return; }
  tabsEl.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-tab="insights"]');
    if (!btn) return;
    if (document.body.dataset.mode !== 'play') return;
    if (_loaded) return;
    _loaded = true;
    loadOpenings();
  });
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

export function initInsights(api) {
  _api = api;
  renderEmptyState(); // placeholder shown only until the first tab activation
  wireLazyLoad(api);
}

export { renderThinData };
