/**
 * Gridfinity Creator - feedback while a model is being generated.
 *
 * Generating takes seconds to minutes and the button gave no sign that anything was happening, so
 * people pressed it again, and every press started another full build.
 *
 * The page cannot simply wait for the response: Generate is an ordinary form submit and the answer
 * is a file, so the page stays where it is and the browser reports nothing when the file arrives.
 * So each submit carries a random token, the server hands it back in a cookie on the response
 * (gfg_main.echo_download_token), and the page watches for that cookie.
 *
 * While waiting, the button is aria-disabled rather than disabled: a disabled submit button is left
 * out of the form data (the server finds out WHICH form was sent by the button's name), and it
 * loses keyboard focus. Further submits are simply refused.
 *
 * The parts that need no page are separate so that they can be tested under Node (see tests/js).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;   // Node, for the tests
  } else {
    root.GfgGenerate = api; // the browser
    api.start(root);
  }
})(typeof self !== 'undefined' ? self : this, function () {

  const COOKIE_NAME = 'download_token';
  const POLL_MS = 300;
  // A build is stopped after 300 s unless the server was told otherwise (GFG_BUILD_TIMEOUT)
  const GIVE_UP_MS = 330000;

  /** A random string the server can safely echo: letters and digits only */
  function createToken() {
    const bytes = new Uint8Array(12);
    const source = typeof crypto !== 'undefined' && crypto.getRandomValues ? crypto : null;
    if (source) {
      source.getRandomValues(bytes);
    } else {
      for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    }
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  }

  /** Whether document.cookie holds the token cookie with exactly this value (compared literally) */
  function cookieHasToken(cookieString, token) {
    return cookieString.split(';').some(pair => {
      const separator = pair.indexOf('=');
      return separator > -1 && pair.slice(0, separator).trim() === COOKIE_NAME && pair.slice(separator + 1).trim() === token;
    });
  }

  /** A cookie string that deletes the token cookie */
  function expireCookie() {
    return `${COOKIE_NAME}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  }

  function start(win) {
    const doc = win.document;

    // A polite live region for screen readers; it has to exist before its text changes
    const status = doc.createElement('div');
    status.setAttribute('role', 'status');
    status.className = 'visually-hidden';
    doc.body.appendChild(status);

    const forms = [...doc.querySelectorAll('form[id$="_form"]')].filter(form => form.querySelector('button[type="submit"][name]'));
    const resets = [];

    forms.forEach(form => {
      const button = form.querySelector('button[type="submit"][name]');
      const idleLabel = button.innerHTML;
      let waiting = null;

      const finish = message => {
        if (!waiting) return;
        win.clearInterval(waiting.poll);
        win.clearTimeout(waiting.giveUp);
        doc.cookie = expireCookie();
        waiting = null;
        button.innerHTML = idleLabel;
        button.removeAttribute('aria-disabled');
        button.classList.remove('gfg-busy');
        status.textContent = message;
      };
      resets.push(() => finish(''));

      form.addEventListener('submit', event => {
        if (waiting) {          // already on its way: a second press must not start a second build
          event.preventDefault();
          return;
        }

        const token = createToken();
        const field = doc.createElement('input');
        field.type = 'hidden';
        field.name = 'download_token';
        field.value = token;
        form.appendChild(field);
        // The browser reads the form after this handler returns; take the field out again straight
        // afterwards so that the previews, which post the whole form, do not carry the token
        win.setTimeout(() => field.remove(), 0);

        button.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> <span>Generating&hellip;</span>';
        button.setAttribute('aria-disabled', 'true');
        button.classList.add('gfg-busy');
        status.textContent = 'Generating. This can take a while.';

        waiting = {
          poll: win.setInterval(() => { if (cookieHasToken(doc.cookie, token)) finish('Your model is ready.'); }, POLL_MS),
          giveUp: win.setTimeout(() => finish(''), GIVE_UP_MS)
        };
      });
    });

    // Back to a page the browser kept as it was (the back button): nothing is being generated any more
    win.addEventListener('pageshow', event => {
      if (event.persisted) resets.forEach(reset => reset());
    });
  }

  return { createToken, cookieHasToken, expireCookie, start, COOKIE_NAME };
});
