/**
 * Gridfinity Creator - "only the newest request counts".
 *
 * Building a preview takes seconds, so while one is on its way the user will usually
 * change the form again and ask for another. Requests do not necessarily come back in
 * the order they were sent, and the one that comes back last wins the screen: an old,
 * slow answer would replace the newer model and leave a preview that does not match
 * the form.
 *
 * Each kind of request (the preview of one form, the dimensions of one form, ...) gets
 * its own tracker. begin() abandons whatever was outstanding, and hands back a signal
 * for fetch() plus isCurrent(), which the caller checks after every await before it
 * touches the page.
 *
 * Aborting spares the browser the download and the redraw; it cannot stop a build the
 * server has already started.
 *
 * No DOM access in this file, so it also runs under Node (see tests/js).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api; // Node, for the tests
  } else {
    root.GfgLatest = api; // the browser
  }
})(typeof self !== 'undefined' ? self : this, function () {

  function createLatestRequest() {
    let current = null;

    return {
      /** Start a request. Any earlier one is aborted and stops being current. */
      begin() {
        if (current) current.abort();
        const controller = new AbortController();
        current = controller;
        return {
          signal: controller.signal,
          isCurrent: () => current === controller
        };
      },

      /** Abandon the outstanding request, if any, without starting another */
      cancel() {
        if (current) current.abort();
        current = null;
      }
    };
  }

  /** Whether an error is just a request we cancelled ourselves, as opposed to a real failure */
  function isAbort(error) {
    return Boolean(error) && typeof error === 'object' && error.name === 'AbortError';
  }

  return { createLatestRequest, isAbort };
});
