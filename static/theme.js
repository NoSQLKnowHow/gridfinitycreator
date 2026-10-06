/**
 * Gridfinity Creator - light/dark theme toggle
 * The initial theme is applied synchronously in <head> (see base.html.j2)
 * to avoid a flash of the wrong theme. This file only wires up the toggle
 * button and notifies the rest of the app (e.g. the 3D viewer) of changes.
 */

const GFG_THEME_STORAGE_KEY = 'gfg-theme';

function gfgCurrentTheme() {
  return document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light';
}

function gfgSetTheme(theme) {
  document.documentElement.setAttribute('data-bs-theme', theme);
  try {
    localStorage.setItem(GFG_THEME_STORAGE_KEY, theme);
  } catch (e) {
    // Storage may be unavailable (e.g. private browsing); theme just won't persist.
  }
  document.dispatchEvent(new CustomEvent('gfg-theme-change', { detail: { theme: theme } }));
}

function gfgToggleTheme() {
  gfgSetTheme(gfgCurrentTheme() === 'dark' ? 'light' : 'dark');
}

document.addEventListener('DOMContentLoaded', function () {
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) {
    btn.addEventListener('click', gfgToggleTheme);
  }
});
