// theme.js — light/dark/system theme toggle. Self-initializing; imports
// prefs.js only (leaf module — never app.js). The inline <head> script owns
// the pre-paint dataset.theme write; this module keeps it live afterwards:
// wires the header button (cycles system → light → dark), persists the
// choice, and tracks OS scheme changes while the stored pref is 'system'.

import { readUiPrefs, writeUiPref } from './prefs.js';

const CYCLE = ['system', 'light', 'dark'];

// Inline Lucide icons (monitor / sun / moon) — icon shows the stored
// PREFERENCE, not the resolved theme, so 'system' stays distinguishable.
const ICONS = {
  system: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/></svg>',
  light:  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
  dark:   '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>',
};

const LABELS = {
  system: 'Theme: system — click for light',
  light:  'Theme: light — click for dark',
  dark:   'Theme: dark — click for system',
};

const lightQuery = window.matchMedia('(prefers-color-scheme: light)');

function storedPref() {
  const t = readUiPrefs().theme;
  return t === 'light' || t === 'dark' ? t : 'system';
}

function resolve(pref) {
  if (pref === 'system') return lightQuery.matches ? 'light' : 'dark';
  return pref;
}

function apply(pref) {
  document.documentElement.dataset.theme = resolve(pref);
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.innerHTML = ICONS[pref];
  btn.setAttribute('aria-label', LABELS[pref]);
  btn.title = LABELS[pref];
}

// Header button: cycle system → light → dark → system, persist, apply.
const btn = document.getElementById('theme-toggle');
if (btn) {
  btn.addEventListener('click', () => {
    const next = CYCLE[(CYCLE.indexOf(storedPref()) + 1) % CYCLE.length];
    writeUiPref('theme', next);
    apply(next);
  });
}

// OS scheme flips: re-read the stored pref every fire and no-op unless it is
// 'system' — an OS change must never override an explicit manual choice.
lightQuery.addEventListener('change', () => {
  if (storedPref() === 'system') apply('system');
});

// Sync button icon/label with the pre-paint state.
apply(storedPref());
