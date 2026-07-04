// insights.js — Insights tab: a triage-router dashboard over already-persisted
// game-review data (openings / recurring-mistakes / endgames diagnostics).
//
// Injected-api module: all app dependencies arrive via `api` (no imports from
// app.js — mirrors review.js's one-directional contract). Copies small idioms
// (el()) as module-private helpers rather than importing them from review.js.
//
// Layout: the Insights tab hosts one internal sub-tab bar ("Openings" /
// "Mistakes", Endgames to follow in Phase 3) rather than stacking all three
// slices' full panels in one long scroll. Each slice has its own /api/insights/*
// coverage line, so stacking would repeat "X of Y games analyzed…" once per
// slice — a sub-tab switcher avoids that and scales cleanly as more phases
// land. The sub-tabs are built lazily (see wireLazyLoad/buildShell below).
//
// Fetch strategy: per-section lazy, not "fetch everything on first open".
// GET /api/insights/openings fires the first time the OUTER Insights tab is
// shown (Openings is the default active sub-tab); GET /api/insights/mistakes
// fires the first time the Mistakes sub-tab itself is clicked. Each fetch
// happens at most once per page load.
//
// Deep-links reuse api.actions.openGameAtPly (T0.2). renderThinData() + the
// .insights-trend CSS class are the shared honesty/min-sample convention
// (T0.3) reused across every section below and by the upcoming Endgames slice.

const byId = (id) => document.getElementById(id);

let _api = null;
let _shellBuilt = false;   // true once the Openings/Mistakes sub-tab shell exists
let _mistakesLoaded = false;

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
  return score == null ? '—' : `${Math.round(score * 100)}%`;
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

// A gated {value, n, sufficient} metric rendered as a compact metric row
// (label · big mono value · n=N), muted with renderThinData() when
// insufficient — the per-metric gating line renders exactly as before.
// `value` is a plain number (e.g. a ply count or a percentage already on a
// 0-100 scale) — formatted via fmt1. Fraction-based rates (0-1) are rendered
// inline with scorePct() instead, since their surrounding sentence needs
// more than "label: value".
function renderGatedLine(label, metric, unit = '') {
  const frag = document.createDocumentFragment();
  frag.appendChild(el('div', { className: 'insights-metric' }, [
    el('span', { className: 'insights-metric-label' }, [label]),
    el('span', { className: 'insights-metric-value' }, [fmt1(metric.value, unit)]),
    el('span', { className: 'insights-metric-n' }, [`n=${metric.n}`]),
  ]));
  if (!metric.sufficient) frag.appendChild(renderThinData(metric.n));
  return frag;
}

// ---------------------------------------------------------------------------
// Presentation helpers (markup only — no data reads)
// ---------------------------------------------------------------------------

// Lucide chevron-right, inlined (theme.js precedent) — disclosure caret.
const CARET_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>';

function caretIcon() {
  const s = el('span', { className: 'insights-caret', 'aria-hidden': 'true' });
  s.innerHTML = CARET_SVG;
  return s;
}

// 0-1 score → clamped integer percent for bar widths (null-safe).
function pctOf(score) {
  return score == null ? null : Math.max(0, Math.min(100, Math.round(score * 100)));
}

// CSS-only horizontal bar: token-colored fill at an inline width %. The bar
// is an enhancement — every value it encodes is also always visible as text.
function barTrack(pct, extraClass = '') {
  const track = el('div', { className: 'insights-bar-track' + (extraClass ? ` ${extraClass}` : '') });
  if (pct != null) track.appendChild(el('div', { className: 'insights-bar-fill', style: `width: ${pct}%` }));
  return track;
}

// Stat block: big tabular-nums figure + tracked label + context sub-line.
function statBlock(value, label, sub) {
  const box = el('div', { className: 'insights-stat' });
  box.appendChild(el('span', { className: 'insights-stat-value' }, [value]));
  box.appendChild(el('span', { className: 'insights-stat-label' }, [label]));
  if (sub) box.appendChild(el('span', { className: 'insights-stat-sub' }, [sub]));
  return box;
}

// Signature motion, one-shot: adds .insights-enter (staggered section rise +
// bar-fill sweep, see insights.css) and removes it once the animation window
// has passed. Removal is the replay guard — sub-tab switches toggle
// display:none, which would otherwise restart CSS animations. Called only
// from the full panel renders, which run exactly once per page load (the
// _shellBuilt/_mistakesLoaded guards). Reduced-motion zeroes all durations
// globally (style.css) + insights.css disables these animations explicitly.
function playEntrance(root) {
  if (!root) return;
  root.classList.add('insights-enter');
  window.setTimeout(() => root.classList.remove('insights-enter'), 1100);
}

// ---------------------------------------------------------------------------
// Empty / loading states
// ---------------------------------------------------------------------------

function renderEmptyState(container, message) {
  if (!container) return;
  container.replaceChildren(
    el('div', { className: 'empty-state' }, [
      el('p', {}, [message || 'No insights yet — analyzed games will surface opening, mistake, and endgame diagnostics here.']),
    ])
  );
}

function renderLoading(container) {
  if (!container) return;
  container.replaceChildren(el('p', { className: 'insights-loading' }, ['Loading insights…']));
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
// Openings — win% by opening (family rows, expandable to per-line rows)
// ---------------------------------------------------------------------------

function renderLineRow(line) {
  const row = el('div', { className: 'insights-bar-row' + (line.sufficient ? '' : ' insights-row-thin') });
  row.appendChild(el('div', { className: 'insights-bar-head' }, [
    el('span', { className: 'insights-row-name' }, [line.opening]),
    el('span', { className: 'insights-bar-wdl' }, [`${line.wins}-${line.draws}-${line.losses}`]),
    el('span', { className: 'insights-bar-pct' }, [scorePct(line.score)]),
    el('span', { className: 'insights-bar-n' }, [`n=${line.n}`]),
  ]));
  row.appendChild(barTrack(pctOf(line.score)));
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
    el('div', { className: 'insights-bar-head' }, [
      caretIcon(),
      el('span', { className: 'insights-row-name' }, [fam.opening]),
      el('span', { className: 'insights-fam-color' }, [fam.color]),
      el('span', { className: 'insights-bar-wdl' }, [`${fam.wins}-${fam.draws}-${fam.losses}`]),
      el('span', { className: 'insights-bar-pct' }, [scorePct(fam.score)]),
      el('span', { className: 'insights-bar-n' }, [`n=${fam.n}`]),
    ]),
    barTrack(pctOf(fam.score)),
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
  section.appendChild(el('h2', { className: 'insights-hdr' }, ['Win% by Opening']));

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
// Openings — repertoire adherence
// ---------------------------------------------------------------------------

function renderAdherenceLineRow(line) {
  const row = el('div', { className: 'insights-row' + (line.sufficient ? '' : ' insights-row-thin') });
  row.appendChild(el('span', { className: 'insights-row-name' }, [line.name + (line.color ? ` (${line.color})` : '')]));
  row.appendChild(el('span', { className: 'insights-row-mono' }, [`prep depth ${fmt1(line.avg_followed_prep_depth)}`]));
  row.appendChild(el('span', { className: 'insights-row-mono' }, [`${line.deviations} deviation${line.deviations === 1 ? '' : 's'}`]));
  row.appendChild(el('span', { className: 'insights-bar-n' }, [`n=${line.n}`]));
  return row;
}

function renderAdherenceGameRow(game) {
  const row = el('div', { className: 'insights-row' });
  row.appendChild(el('span', { className: 'insights-row-game' }, [`Game #${game.game_id}`]));
  row.appendChild(el('span', { className: 'insights-row-mono' }, [`followed ${game.followed_prep_depth} plies`]));
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
  section.appendChild(el('h2', { className: 'insights-hdr' }, ['Repertoire Adherence']));

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
// Openings — theory / soundness (off-repertoire games)
// ---------------------------------------------------------------------------

function renderTheoryGameRow(game) {
  const row = el('div', { className: 'insights-row' });
  row.appendChild(el('span', { className: 'insights-row-game' }, [`Game #${game.game_id}`]));
  // book_exit_ply === 0 means the game never entered book — "book-exit ply 0" /
  // "Open at book exit (ply 0)" would wrongly imply an exit event happened.
  const neverInBook = game.book_exit_ply === 0;
  row.appendChild(el('span', { className: 'insights-row-mono' }, [neverInBook ? 'never reached named theory' : `book-exit ply ${game.book_exit_ply}`]));
  row.appendChild(el('span', { className: 'insights-row-mono' }, [game.opening_accuracy != null ? `accuracy ${fmt1(game.opening_accuracy, '%')}` : 'accuracy —']));
  const label = neverInBook ? 'Open game (no book moves)' : `Open at book exit (ply ${game.book_exit_ply})`;
  row.appendChild(renderDeepLinkButton(game.game_id, game.book_exit_ply, label));
  return row;
}

function renderTheory(theory) {
  const section = el('section', { className: 'insights-section', 'data-section': 'theory' });
  section.appendChild(el('h2', { className: 'insights-hdr' }, ['Theory / Soundness']));

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
// Mistakes — ranked recurring-mistake clusters
// ---------------------------------------------------------------------------

// coaching.name_cluster appends its own " (N× so far)" suffix once count >= 5
// (app/coaching.py:352-353) — strip it so our own appended "— {count}×" (the
// styled, always-present count) is never doubled up.
function clusterDisplayName(item) {
  return item.name.replace(/\s*\(\d+× so far\)\s*$/, '');
}

function renderClusterRow(item, rank) {
  const row = el('div', { className: 'insights-cluster-card', 'data-category': item.category, 'data-phase': item.phase });
  row.appendChild(el('span', { className: 'insights-cluster-rank', 'aria-hidden': 'true' }, [String(rank)]));
  row.appendChild(el('div', { className: 'insights-cluster-body' }, [
    el('span', { className: 'insights-row-name' }, [clusterDisplayName(item)]),
    el('span', { className: 'insights-cluster-count' }, [`${item.count}× recorded`]),
  ]));
  row.appendChild(renderDeepLinkButton(item.example.game_id, item.example.ply, `Open example (ply ${item.example.ply})`));
  return row;
}

function renderClusters(clusters) {
  const section = el('section', { className: 'insights-section', 'data-section': 'clusters' });
  section.appendChild(el('h2', { className: 'insights-hdr' }, ['Recurring Mistakes']));

  const items = (clusters && clusters.items) || [];
  if (!items.length) {
    section.appendChild(el('p', { className: 'insights-empty-note' }, ['No recurring-mistake clusters yet.']));
    return section;
  }

  const list = el('div', { className: 'insights-cluster-list' });
  items.forEach((item, idx) => list.appendChild(renderClusterRow(item, idx + 1)));
  section.appendChild(list);

  const supp = clusters.suppressed;
  if (supp && supp.cells > 0) {
    // `gate` is landing on the API in parallel — fall back to today's backend
    // constant (CLUSTER_GATE = 4, app/insights.py) until it's present.
    const gate = supp.gate != null ? supp.gate : 4;
    section.appendChild(el('p', { className: 'insights-empty-note' }, [
      `${supp.cells} smaller pattern${supp.cells === 1 ? '' : 's'} (${supp.leaks} mistake${supp.leaks === 1 ? '' : 's'}) below the ${gate}-mistake naming threshold.`,
    ]));
  }

  return section;
}

// ---------------------------------------------------------------------------
// Mistakes — foreseeable-rate headline
// ---------------------------------------------------------------------------

function renderForeseeable(foreseeable) {
  const section = el('section', { className: 'insights-section', 'data-section': 'foreseeable' });
  section.appendChild(el('h2', { className: 'insights-hdr' }, ['Foreseeable Mistakes']));

  if (!foreseeable || !foreseeable.rate) {
    section.appendChild(el('p', { className: 'insights-empty-note' }, ['No foreseeable-rate data yet.']));
    return section;
  }

  const rate = foreseeable.rate;
  section.appendChild(el('div', { className: 'insights-stat-row' }, [
    statBlock(scorePct(rate.value), 'foreseeable', `of mistakes had a warning sign (n=${rate.n})`),
  ]));
  if (!rate.sufficient) section.appendChild(renderThinData(rate.n));

  if (foreseeable.dominant_motif) {
    section.appendChild(el('p', { className: 'insights-metric-line' }, [`Most common warning sign: ${foreseeable.dominant_motif.replace(/_/g, ' ')}.`]));
  }
  if (foreseeable.note) section.appendChild(el('p', { className: 'insights-note' }, [foreseeable.note]));

  return section;
}

// ---------------------------------------------------------------------------
// Mistakes — time-trouble card
// ---------------------------------------------------------------------------

function renderTimeTroubleBucketRow(bucket, baselinePct) {
  const row = el('div', { className: 'insights-bar-row' + (bucket.sufficient ? '' : ' insights-row-thin'), 'data-bucket': bucket.bucket });
  row.appendChild(el('div', { className: 'insights-bar-head' }, [
    el('span', { className: 'insights-row-name insights-tt-bucket' }, [bucket.bucket]),
    el('span', { className: 'insights-bar-pct' }, [scorePct(bucket.rate)]),
    el('span', { className: 'insights-bar-n' }, [`${bucket.leaks}/${bucket.moves} moves`]),
  ]));
  const track = barTrack(pctOf(bucket.rate), 'insights-tt-track');
  if (baselinePct != null) {
    track.appendChild(el('span', {
      className: 'insights-tt-baseline',
      style: `left: ${baselinePct}%`,
      'aria-hidden': 'true',
    }));
  }
  row.appendChild(track);
  return row;
}

function renderTimeTrouble(tt) {
  const section = el('section', { className: 'insights-section', 'data-section': 'time-trouble' });
  section.appendChild(el('h2', { className: 'insights-hdr' }, ['Time Trouble']));

  if (!tt) {
    section.appendChild(el('p', { className: 'insights-empty-note' }, ['No clock data yet.']));
    return section;
  }

  // The payoff: a prominent "<10s vs baseline" comparison, ahead of the
  // full per-bucket breakdown.
  const baseline = tt.baseline_rate;
  const lowClock = (tt.buckets || []).find((b) => b.bucket === '<10s');
  if (lowClock && lowClock.rate != null && baseline && baseline.value != null) {
    section.appendChild(el('p', { className: 'insights-highlight' }, [
      `Blunders when <10s left: ${scorePct(lowClock.rate)} vs ${scorePct(baseline.value)} baseline.`,
    ]));
    if (!baseline.sufficient) section.appendChild(renderThinData(baseline.n));
  } else {
    section.appendChild(el('p', { className: 'insights-empty-note' }, ['No moves with <10s on the clock yet.']));
  }

  const buckets = tt.buckets || [];
  if (buckets.length) {
    const list = el('div', { className: 'insights-tt-buckets' });
    // Baseline tick position for each bucket's mini bar (already-read metric).
    const baselinePct = baseline && baseline.value != null ? pctOf(baseline.value) : null;
    buckets.forEach((b) => list.appendChild(renderTimeTroubleBucketRow(b, baselinePct)));
    section.appendChild(list);
  }

  if (tt.note) section.appendChild(el('p', { className: 'insights-note' }, [tt.note]));

  return section;
}

// ---------------------------------------------------------------------------
// Mistakes — advantage-capitalization card
// ---------------------------------------------------------------------------

function renderCapitalization(cap) {
  const section = el('section', { className: 'insights-section', 'data-section': 'capitalization' });
  section.appendChild(el('h2', { className: 'insights-hdr' }, ['Advantage Capitalization']));

  if (!cap || !cap.winning_games) {
    section.appendChild(el('p', { className: 'insights-empty-note' }, ['No sustained-advantage games yet.']));
    return section;
  }

  section.appendChild(el('div', { className: 'insights-stat-row' }, [
    statBlock(scorePct(cap.rate.value), 'converted', `${cap.converted} of ${cap.winning_games} winning games`),
  ]));
  if (!cap.rate.sufficient) section.appendChild(renderThinData(cap.rate.n));
  if (cap.note) section.appendChild(el('p', { className: 'insights-note' }, [cap.note]));

  return section;
}

// ---------------------------------------------------------------------------
// Panel assembly + fetch — Openings
// ---------------------------------------------------------------------------

function renderCoverage(coverage) {
  return el('div', { className: 'insights-coverage insights-stat-row', id: 'insights-coverage' }, [
    statBlock(`${coverage.qualified} / ${coverage.total}`, 'games qualified', 'analyzed + color-tagged'),
  ]);
}

function renderOpeningsPanel(data) {
  const root = byId('insights-panel-openings');
  if (!root) return;

  const coverage = data && data.coverage;
  if (!coverage || !coverage.qualified) {
    renderEmptyState(root, 'No analyzed, color-tagged games yet — analyze + tag a game to see openings insights.');
    return;
  }

  root.replaceChildren(
    renderCoverage(coverage),
    renderWinRates(data.win_rates),
    renderAdherence(data.adherence),
    renderTheory(data.theory),
  );
  playEntrance(root);
}

async function loadOpenings() {
  const root = byId('insights-panel-openings');
  renderLoading(root);
  try {
    const data = await fetchJSON('/api/insights/openings');
    renderOpeningsPanel(data);
  } catch (_) {
    // Degraded — an honest empty state, never a raw error (matches review.js's
    // fetch-failure precedent, e.g. loadTraps()).
    renderEmptyState(root, "Couldn't load insights right now.");
  }
}

// ---------------------------------------------------------------------------
// Panel assembly + fetch — Mistakes
// ---------------------------------------------------------------------------

function renderMistakesPanel(data) {
  const root = byId('insights-panel-mistakes');
  if (!root) return;

  const coverage = data && data.coverage;
  if (!coverage || !coverage.qualified) {
    renderEmptyState(root, 'No analyzed, color-tagged games yet — analyze + tag a game to see mistake diagnostics.');
    return;
  }

  root.replaceChildren(
    renderCoverage(coverage),
    renderClusters(data.clusters),
    renderForeseeable(data.foreseeable),
    renderTimeTrouble(data.time_trouble),
    renderCapitalization(data.capitalization),
  );
  playEntrance(root);
}

async function loadMistakes() {
  const root = byId('insights-panel-mistakes');
  renderLoading(root);
  try {
    const data = await fetchJSON('/api/insights/mistakes');
    renderMistakesPanel(data);
  } catch (_) {
    renderEmptyState(root, "Couldn't load insights right now.");
  }
}

// ---------------------------------------------------------------------------
// Sub-tab shell (Openings / Mistakes) + lazy fetch wiring
// ---------------------------------------------------------------------------

// Builds the Openings/Mistakes sub-tab bar once, the first time the outer
// Insights tab is shown. Sub-panels use role="tabpanel" + the `.is-active`
// class specifically so they're hidden by style.css's existing generic rule
// (`[role="tabpanel"]:not(.is-active) { display: none }`, style.css:435) —
// no new show/hide CSS needed in insights.css.
function buildShell() {
  const root = byId('insights-root');
  if (!root) return;

  const tabs = el('div', { className: 'insights-subtabs', role: 'tablist', 'aria-label': 'Insights sections' });
  const openingsTab = el('button', {
    type: 'button', className: 'insights-subtab', role: 'tab', 'data-subtab': 'openings',
    'aria-selected': 'true', 'aria-controls': 'insights-panel-openings', id: 'insights-subtab-openings',
  }, ['Openings']);
  const mistakesTab = el('button', {
    type: 'button', className: 'insights-subtab', role: 'tab', 'data-subtab': 'mistakes',
    'aria-selected': 'false', 'aria-controls': 'insights-panel-mistakes', id: 'insights-subtab-mistakes',
  }, ['Mistakes']);
  tabs.append(openingsTab, mistakesTab);

  const openingsPanel = el('div', {
    className: 'insights-subpanel is-active', role: 'tabpanel', id: 'insights-panel-openings',
    'aria-labelledby': 'insights-subtab-openings',
  });
  const mistakesPanel = el('div', {
    className: 'insights-subpanel', role: 'tabpanel', id: 'insights-panel-mistakes',
    'aria-labelledby': 'insights-subtab-mistakes',
  });
  renderEmptyState(mistakesPanel, 'Click "Mistakes" to load mistake diagnostics.');

  tabs.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-subtab]');
    if (!btn) return;
    const name = btn.dataset.subtab;
    tabs.querySelectorAll('button[data-subtab]').forEach((b) => b.setAttribute('aria-selected', String(b === btn)));
    openingsPanel.classList.toggle('is-active', name === 'openings');
    mistakesPanel.classList.toggle('is-active', name === 'mistakes');
    if (name === 'mistakes' && !_mistakesLoaded) {
      _mistakesLoaded = true;
      loadMistakes();
    }
  });

  root.replaceChildren(tabs, openingsPanel, mistakesPanel);
}

// First activation of the OUTER Insights tab: build the sub-tab shell and
// kick off the Openings fetch (the default active sub-tab). Mistakes fetches
// separately, lazily, on its own first sub-tab click (see buildShell above).
function activateInsightsTab() {
  if (_shellBuilt) return;
  _shellBuilt = true;
  buildShell();
  loadOpenings();
}

// Lazily fetch the first time the Insights tab is actually shown, using the
// already-injected api.mounts.tabs element (no new wiring in app.js). Mirrors
// app.js's own tab-click gate: switching tabs is a no-op outside 'play' mode,
// so a click there would not actually reveal this panel either.
function wireLazyLoad(api) {
  const tabsEl = api && api.mounts && api.mounts.tabs;
  if (!tabsEl) { activateInsightsTab(); return; }
  tabsEl.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-tab="insights"]');
    if (!btn) return;
    if (document.body.dataset.mode !== 'play') return;
    activateInsightsTab();
  });
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

export function initInsights(api) {
  _api = api;
  renderEmptyState(byId('insights-root')); // placeholder shown only until the first tab activation
  wireLazyLoad(api);
}

export { renderThinData };
