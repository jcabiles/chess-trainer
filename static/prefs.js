// prefs.js — shared UI preference helpers. No DOM, no imports from app.js.

const UI_PREFS_KEY = 'chess-training:ui:v1';

export function readUiPrefs() {
  try { return JSON.parse(localStorage.getItem(UI_PREFS_KEY) || '{}') || {}; } catch (_) { return {}; }
}

export function writeUiPref(key, val) {
  try {
    const prefs = readUiPrefs();
    prefs[key] = val;
    localStorage.setItem(UI_PREFS_KEY, JSON.stringify(prefs));
  } catch (_) { /* best-effort */ }
}
