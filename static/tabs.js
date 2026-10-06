/**
 * Gridfinity Creator - the tab strip.
 *
 * On a phone the six tabs do not fit side by side, so the strip scrolls sideways. This keeps
 * the active tab in view: after the page loads on a tab at the far end (a failed submit
 * re-renders with that tab open) and whenever another one is opened.
 *
 * The open tab is also kept in the address (https://host/#solidbin), so that a generator can be
 * linked to, bookmarked, and survives a reload. A shared configuration link (?gen=...&cfg=...)
 * still wins: it is applied later, when the page has loaded.
 *
 * The arithmetic and the reading of the address are separate from the page so that they can be
 * tested under Node (see tests/js).
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

  /** The tab a URL hash names, or null if it names anything else (the #main skip link, say) */
  function tabFromHash(hash, tabIds) {
    let id;
    try {
      id = decodeURIComponent(String(hash || '').replace(/^#/, ''));
    } catch (e) {
      return null; // broken escapes: not ours
    }
    return tabIds.includes(id) ? id : null;
  }

  /** The hash that records the open tab. The Home tab is the default, so it leaves the address plain. */
  function hashForTab(id, homeId = 'home') {
    return id && id !== homeId ? '#' + id : '';
  }

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
    const tabButtons = () => [...doc.querySelectorAll('.nav-tabs [data-bs-toggle="tab"]')];
    const idOf = button => button.dataset.bsTarget.slice(1);

    // Record the open tab in the address, without adding a history entry for every click
    doc.addEventListener('shown.bs.tab', event => {
      reveal(event.target);
      const hash = hashForTab(idOf(event.target));
      if (win.location.hash !== hash) {
        win.history.replaceState(null, '', win.location.pathname + win.location.search + hash);
      }
    });

    // Open the tab the address names. The browser also scrolls to the element with that id (the
    // panel), which would hide the title and the tabs, so go back to the top once it has done so.
    const openTabFromAddress = () => {
      const wanted = tabFromHash(win.location.hash, tabButtons().map(idOf));
      const button = tabButtons().find(candidate => idOf(candidate) === wanted);
      if (!button) return;
      if (!button.classList.contains('active')) win.bootstrap.Tab.getOrCreateInstance(button).show();
      win.setTimeout(() => win.scrollTo(0, 0), 0);
    };

    const onReady = () => {
      reveal(doc.querySelector('.nav-tabs .nav-link.active'), true);
      openTabFromAddress();
    };
    if (doc.readyState === 'loading') {
      doc.addEventListener('DOMContentLoaded', onReady);
    } else {
      onReady();
    }
    win.addEventListener('load', () => { if (tabFromHash(win.location.hash, tabButtons().map(idOf))) win.scrollTo(0, 0); });
    win.addEventListener('hashchange', openTabFromAddress);
  }

  return { centeredScrollLeft, tabFromHash, hashForTab, reveal, start };
});
