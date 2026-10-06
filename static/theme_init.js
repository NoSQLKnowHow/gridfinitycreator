/**
 * Gridfinity Creator - apply the saved theme before the first paint, defaulting to light,
 * to avoid a flash of the wrong theme. Loaded (and run) in the <head> on purpose.
 *
 * This used to be an inline script; the Content-Security-Policy the server sends allows
 * scripts from this server only.
 */
(function () {
  var stored = null;
  try { stored = localStorage.getItem('gfg-theme'); } catch (e) { /* ignore */ }
  document.documentElement.setAttribute('data-bs-theme', stored === 'dark' ? 'dark' : 'light');
})();
