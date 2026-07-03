// panel.js — Analysis panel rendering module.
// Receives all dependencies via the injected `api` argument (no imports from app.js).
// Exports: initPanel(api), renderAnalysisPanel(analysis, opts), renderBookMovePanel(data), renderSkippedPanel()

import { formatEval } from './format.js';

const byId = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Module-level api reference — set by initPanel, used by render functions.
// ---------------------------------------------------------------------------
let _api = null;

// ---------------------------------------------------------------------------
// Eval bar helpers
// ---------------------------------------------------------------------------

// Compute fill percentage (0–100) for the eval bar from White's POV.
// White advantage fills from the bottom; 50% = equal.
// Clamp at ±500 cp → 5%..95% range. Mate → 95% or 5%.
function evalBarFill(a) {
  if (a == null) return 50;
  if (a.mate != null) {
    return a.mate > 0 ? 95 : 5;
  }
  if (a.evalCp != null) {
    const clamped = Math.max(-500, Math.min(500, a.evalCp));
    // 0 cp → 50%, +500 cp → 95%, -500 cp → 5%
    return 50 + (clamped / 500) * 45;
  }
  return 50;
}

// Drive the #eval-bar fill via a CSS custom property.
function setEvalBar(fillPct) {
  const bar = byId('eval-bar');
  if (!bar) return;
  bar.style.setProperty('--fill', fillPct.toFixed(2) + '%');
}

// ---------------------------------------------------------------------------
// PV numbering helpers
// ---------------------------------------------------------------------------

// Given baseFen + cursor (number of plies applied from baseFen), compute the
// fullmove number and side-to-move AT the resulting position.
// Returns { fullMove: number, isWhite: boolean }.
function fenSideAtCursor(baseFen, cursor) {
  // FEN fields: placement turn castling ep halfmove fullmove
  const parts = (baseFen || '').split(' ');
  const baseTurnW = (parts[1] || 'w') === 'w';
  const baseFullMove = parseInt(parts[5] || '1', 10) || 1;

  // Count plies from baseFen forward by `cursor`.
  // White moves first within a fullmove → after White's ply fullmove unchanged,
  // after Black's ply fullmove increments.
  let isWhite = baseTurnW;
  let fullMove = baseFullMove;
  for (let i = 0; i < cursor; i++) {
    if (!isWhite) {
      // Black just moved → increment fullmove
      fullMove += 1;
    }
    isWhite = !isWhite;
  }
  return { fullMove, isWhite };
}

// Build a tokenized PV element from pvSan array + position info.
// Returns a DocumentFragment with <span class="pv-move"> tokens + optional caption.
function buildPvFragment(pvSan, fullMove, isWhite, depth) {
  const frag = document.createDocumentFragment();
  if (!pvSan || !pvSan.length) {
    const dash = document.createElement('span');
    dash.textContent = '—';
    frag.appendChild(dash);
    return frag;
  }

  let curMove = fullMove;
  let curWhite = isWhite;

  pvSan.forEach((san, idx) => {
    // Prefix: move number + dot/ellipsis
    let prefix = '';
    if (curWhite) {
      prefix = `${curMove}. `;
    } else if (idx === 0) {
      // Black to move on first PV token: show "N…"
      prefix = `${curMove}… `;
    }
    // Subsequent black moves get no prefix (number already shown for White's ply above)

    if (prefix) {
      const numSpan = document.createElement('span');
      numSpan.className = 'pv-num';
      numSpan.textContent = prefix;
      frag.appendChild(numSpan);
    }

    const moveSpan = document.createElement('span');
    moveSpan.className = 'pv-move';
    moveSpan.textContent = san;
    frag.appendChild(moveSpan);

    // Space separator (except after last token)
    if (idx < pvSan.length - 1) {
      frag.appendChild(document.createTextNode(' '));
    }

    // Advance side/move
    if (!curWhite) curMove += 1;
    curWhite = !curWhite;
  });

  // Depth caption if available
  if (depth != null && depth > 0) {
    const cap = document.createElement('span');
    cap.className = 'pv-depth';
    cap.textContent = `  depth ${depth}`;
    frag.appendChild(cap);
  }

  return frag;
}

// ---------------------------------------------------------------------------
// Quality icon map — small inline SVG glyphs per quality label.
// Each returns a <span> element containing the icon.
// ---------------------------------------------------------------------------
const QUALITY_ICONS = {
  best: () => svgIcon(
    // Checkmark circle
    `<circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/>`,
    'var(--q-best)'
  ),
  good: () => svgIcon(
    // Simple check
    `<polyline points="20 6 9 17 4 12"/>`,
    'var(--q-good)'
  ),
  inaccuracy: () => svgIcon(
    // Triangle warning — light
    `<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>`,
    'var(--q-inaccuracy)'
  ),
  mistake: () => svgIcon(
    // Alert circle — distinct from the inaccuracy triangle
    `<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>`,
    'var(--q-mistake)'
  ),
  blunder: () => svgIcon(
    // X circle
    `<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>`,
    'var(--q-blunder)'
  ),
  book: () => svgIcon(
    // Book
    `<path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>`,
    'var(--q-book)'
  ),
};

function svgIcon(pathData, color) {
  const wrap = document.createElement('span');
  wrap.className = 'quality-icon';
  wrap.setAttribute('aria-hidden', 'true');
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '1em');
  svg.setAttribute('height', '1em');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', color);
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.innerHTML = pathData;
  wrap.appendChild(svg);
  return wrap;
}

// ---------------------------------------------------------------------------
// initPanel — called after Chessground is created; stores api reference.
// ---------------------------------------------------------------------------
export function initPanel(api) {
  _api = api;
  // Initialize eval bar to neutral (50%).
  setEvalBar(50);
}

// ---------------------------------------------------------------------------
// Dual best-move helpers — current 2nd-best + the retrospective block.
// ---------------------------------------------------------------------------

// Keep the retrospective PV compact ("short PV" per spec): a few plies of context.
const RETRO_PV_MAX = 6;

// Format a BestLine's eval as " (+0.20)" / " (M+3)", or '' when unavailable.
// BestLine carries the same {evalCp, mate} White-POV shape formatEval expects.
function fmtLineEval(line) {
  const s = formatEval(line);
  return s === '—' ? '' : ` (${s})`;
}

// Render a compact "· or Nf3 (+0.2)" 2nd-best entry into `el`; blank when absent.
function renderSecond(el, line) {
  if (!el) return;
  el.textContent = line && line.moveSan ? `· or ${line.moveSan}${fmtLineEval(line)}` : '';
}

// Render the retrospective block from a BestLine (+ optional 2nd). PV numbering
// is computed from the position at `pvCursor` (the mover's own turn — a different
// side-to-move than the current PV). `label` sets the block heading. Hides the
// whole block when there's no move or `pvCursor` is out of range (guards cursor 0).
function renderRetroBlock(retroBest, retroSecond, pvCursor, label) {
  const block = byId('retro-block');
  if (!block) return;
  if (!retroBest || !retroBest.moveSan || pvCursor < 0) {
    block.hidden = true;
    return;
  }
  block.hidden = false;

  const labelEl = byId('retro-label');
  if (labelEl && label) labelEl.textContent = label;

  const bmEl = byId('retro-best');
  if (bmEl) bmEl.textContent = retroBest.moveSan;

  renderSecond(byId('retro-second'), retroSecond);

  const pvEl = byId('retro-pv');
  if (pvEl) {
    pvEl.textContent = '';
    const pvSan = (retroBest.pvSan || []).slice(0, RETRO_PV_MAX);
    if (pvSan.length) {
      let fullMove = 1;
      let isWhite = true;
      const state = _api && _api.actions && _api.actions.getState ? _api.actions.getState() : null;
      if (state) {
        const info = fenSideAtCursor(state.baseFen, pvCursor);
        fullMove = info.fullMove;
        isWhite = info.isWhite;
      }
      pvEl.appendChild(buildPvFragment(pvSan, fullMove, isWhite, null));
    } else {
      pvEl.textContent = '—';
    }
  }
}

// Hide/clear ALL new dual-best DOM (retro block + both 2nd-best entries).
function clearDualBest() {
  const block = byId('retro-block');
  if (block) block.hidden = true;
  const bs = byId('best-second');
  if (bs) bs.textContent = '';
  const rs = byId('retro-second');
  if (rs) rs.textContent = '';
}

// ---------------------------------------------------------------------------
// renderAnalysisPanel — main analysis render.
// `opts.suppressQuality` forces the quality label to '—' regardless of the
// engine's verdict. Trap practice passes it so a real "Blunder!" on a
// deliberately dubious trapper move never contradicts the lesson.
// ---------------------------------------------------------------------------
export function renderAnalysisPanel(a, opts = {}) {
  // --- Eval bar ---
  setEvalBar(evalBarFill(a));

  // --- Eval text ---
  const evalEl = byId('eval');
  if (evalEl) evalEl.textContent = formatEval(a);

  // --- Quality (color + icon + text) ---
  const qEl = byId('quality');
  if (qEl) {
    qEl.className = 'quality';
    // Clear previous icon + text
    qEl.textContent = '';
    if (a && a.quality && !opts.suppressQuality) {
      const iconFn = QUALITY_ICONS[a.quality];
      if (iconFn) qEl.appendChild(iconFn());
      const label = document.createElement('span');
      label.className = 'quality-label';
      label.textContent = a.quality;
      qEl.appendChild(label);
      qEl.classList.add(`q-${a.quality}`);
    } else {
      qEl.textContent = '—';
    }
  }

  // --- Best move ---
  const bmEl = byId('best-move');
  if (bmEl) bmEl.textContent = (a && a.bestMoveSan) || '—';

  // --- PV (numbered, tokenized) ---
  const pvEl = byId('pv');
  if (pvEl) {
    pvEl.textContent = '';
    if (a && a.pvSan && a.pvSan.length) {
      // Derive the fullmove + side-to-move at the current position.
      // The PV describes moves from THIS resulting position onward.
      let fullMove = 1;
      let isWhite = true;
      const state = _api && _api.actions && _api.actions.getState ? _api.actions.getState() : null;
      if (state) {
        const info = fenSideAtCursor(state.baseFen, state.cursor);
        fullMove = info.fullMove;
        isWhite = info.isWhite;
      }
      const depth = (a && a.depth != null) ? a.depth : null;
      pvEl.appendChild(buildPvFragment(a.pvSan, fullMove, isWhite, depth));
    } else {
      pvEl.textContent = '—';
    }
  }

  // --- Dual best-move extras: current 2nd-best + retrospective block ---
  // suppressRetro (trap-practice) hides ALL new DOM, leaving today's behavior.
  if (opts.suppressRetro) {
    clearDualBest();
    return;
  }
  renderSecond(byId('best-second'), a && a.secondLine);
  const st = _api && _api.actions && _api.actions.getState ? _api.actions.getState() : null;
  const cursor = st ? st.cursor : 0;
  // Retro PV is from the mover's own turn → the position at cursor - 1.
  renderRetroBlock(a && a.retroBest, a && a.retroSecond, cursor - 1, 'Your move — best');
}

// ---------------------------------------------------------------------------
// renderBookMovePanel — book move: no engine eval/best/PV.
// Shows "Book Move" badge (+ opening name) in the quality slot.
// Resets eval bar to neutral 50%.
// ---------------------------------------------------------------------------
export function renderBookMovePanel(data) {
  // Eval bar → neutral
  setEvalBar(50);

  const evalEl = byId('eval');
  if (evalEl) evalEl.textContent = '—';

  const qEl = byId('quality');
  if (qEl) {
    qEl.className = 'quality q-book';
    qEl.textContent = '';
    // Book icon
    const iconFn = QUALITY_ICONS.book;
    if (iconFn) qEl.appendChild(iconFn());
    const label = document.createElement('span');
    label.className = 'quality-label';
    const name = data && data.openingName;
    label.textContent = name ? `Book Move · ${name}` : 'Book Move';
    qEl.appendChild(label);
  }

  const bmEl = byId('best-move');
  if (bmEl) bmEl.textContent = '—';

  const pvEl = byId('pv');
  if (pvEl) pvEl.textContent = '—';

  // Book move = no engine analysis → no retrospective / 2nd-best.
  clearDualBest();
}

// ---------------------------------------------------------------------------
// renderSkippedPanel — skipped evaluation: opponent's move with eval skipped.
// No engine eval/best/PV for the CURRENT position. Shows a calm "Not evaluated"
// badge in the quality slot, and — when available — CARRIES OVER the last
// own-move retrospective (`carriedRetro = { retroBest, retroSecond }`) so the
// panel isn't blank about your play. `pvCursor` is the position index of that
// prior own move (its own turn) for correct PV numbering.
// ---------------------------------------------------------------------------
export function renderSkippedPanel(carriedRetro = null, pvCursor = -1) {
  // Eval bar → neutral
  setEvalBar(50);

  const evalEl = byId('eval');
  if (evalEl) evalEl.textContent = '—';

  const qEl = byId('quality');
  if (qEl) {
    qEl.className = 'quality';
    qEl.textContent = '';
    const label = document.createElement('span');
    label.className = 'quality-label';
    label.textContent = 'Not evaluated · opponent\'s move';
    qEl.appendChild(label);
  }

  // Current position best is unknown on a skipped ply.
  const bmEl = byId('best-move');
  if (bmEl) bmEl.textContent = '—';

  const pvEl = byId('pv');
  if (pvEl) pvEl.textContent = '—';

  const bs = byId('best-second');
  if (bs) bs.textContent = '';

  // Carry over your last analyzed move's retrospective, if cached.
  if (carriedRetro && carriedRetro.retroBest) {
    renderRetroBlock(
      carriedRetro.retroBest,
      carriedRetro.retroSecond,
      pvCursor,
      'Your last move — best',
    );
  } else {
    const block = byId('retro-block');
    if (block) block.hidden = true;
  }
}
