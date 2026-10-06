/**
 * Gridfinity Creator - the tab strip.
 *
 * On a phone the six tabs do not fit side by side, so the strip scrolls sideways. This keeps
 * the active tab in view: after the page loads on a tab at the far end (a failed submit
 * re-renders with that tab open) and whenever another one is opened.
 *
 * The arithmetic is separate from the page so that it can be tested under Node (see tests/js).
 */
(function (root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) {
    module.exports = api; // Node, for the tests
  } else {
    root.GfgTabs = api;   // the browser
    api.start(root);
  }
})(typeof self !== 'undefined' ? self : this, function () {

  /** How far to scroll a strip so that an item sits in the middle of it (never before the start) */
  function centeredScrollLeft(itemLeft, itemWidth, stripWidth) {
    return Math.max(0, itemLeft - (stripWidth - itemWidth) / 2);
  }

  /** Scroll the strip holding this tab, sideways only, so that the tab is centred */
  function reveal(tab, instant) {
    const strip = tab && tab.closest('.nav-tabs');
    if (!strip || strip.scrollWidth <= strip.clientWidth) return; // everything fits already

    const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    strip.scrollTo({
      left: centeredScrollLeft(tab.offsetLeft, tab.offsetWidth, strip.clientWidth),
      behavior: instant || reduceMotion ? 'auto' : 'smooth'
    });
  }

  function start(win) {
    const doc = win.document;
    doc.addEventListener('shown.bs.tab', event => reveal(event.target));
    const revealActive = () => reveal(doc.querySelector('.nav-tabs .nav-link.active'), true);
    if (doc.readyState === 'loading') {
      doc.addEventListener('DOMContentLoaded', revealActive);
    } else {
      revealActive();
    }
  }

  return { centeredScrollLeft, reveal, start };
});
