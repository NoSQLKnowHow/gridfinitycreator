/**
 * Gridfinity Creator - validation and escaping for saved configurations.
 *
 * A configuration can come from outside this page's own code: a library file the
 * user imports, a library string someone shares, or a link with ?cfg=... Any of them
 * can carry hostile text. Everything that is read from such a source goes through
 * the functions here before it is shown or applied.
 *
 * No DOM access in this file, so it also runs under Node (see tests/js).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api; // Node, for the tests
  } else {
    root.GfgSafe = api;   // the browser
  }
})(typeof self !== 'undefined' ? self : this, function () {

  // Ids are made by the library itself as "<timestamp>_<random>"; form ids are
  // the generator folder names. Nothing else is ever needed in an id.
  const SAFE_ID = /^[A-Za-z0-9_-]{1,100}$/;

  // Form field names (Python identifiers, camelCase)
  const SAFE_FIELD_NAME = /^[A-Za-z][A-Za-z0-9_]{0,60}$/;

  const MAX_NAME_LENGTH = 200;
  const MAX_NOTES_LENGTH = 2000;
  const MAX_FIELDS = 100;
  const MAX_VALUE_LENGTH = 100000; // the compartment layout (removedWalls) can be long

  const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };

  /** Make text safe to place in HTML content or in a quoted attribute */
  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => HTML_ESCAPES[character]);
  }

  function isSafeId(value) {
    return typeof value === 'string' && SAFE_ID.test(value);
  }

  function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function isSimpleValue(value) {
    if (typeof value === 'string') return value.length <= MAX_VALUE_LENGTH;
    if (typeof value === 'number') return Number.isFinite(value);
    return typeof value === 'boolean';
  }

  /**
   * Whether this is form data as the page captures it: a flat object of field
   * names to strings, numbers, booleans, or lists of strings.
   */
  function isConfigData(data) {
    if (!isPlainObject(data)) return false;

    const names = Object.keys(data);
    if (names.length > MAX_FIELDS) return false;

    return names.every(name => {
      if (!SAFE_FIELD_NAME.test(name)) return false;
      const value = data[name];
      if (Array.isArray(value)) {
        return value.length <= MAX_FIELDS && value.every(item => typeof item === 'string' && item.length <= MAX_VALUE_LENGTH);
      }
      return isSimpleValue(value);
    });
  }

  /** A clean copy of a saved configuration, or null if it is not a valid one */
  function sanitizeConfig(config) {
    if (!isPlainObject(config)) return null;
    if (!isSafeId(config.id) || !isSafeId(config.formId)) return null;
    if (typeof config.name !== 'string' || !isConfigData(config.data)) return null;

    const name = config.name.trim().slice(0, MAX_NAME_LENGTH);
    if (!name) return null;

    const created = config.createdAt;
    const hasDate = (typeof created === 'string' || typeof created === 'number') && !Number.isNaN(new Date(created).getTime());

    return {
      id: config.id,
      name: name,
      formId: config.formId,
      data: Object.assign({}, config.data),
      createdAt: hasDate ? created : '',
      notes: typeof config.notes === 'string' ? config.notes.slice(0, MAX_NOTES_LENGTH) : ''
    };
  }

  /**
   * A clean copy of a whole library: invalid entries are dropped, duplicate ids keep
   * their first occurrence. Anything that is not a library at all gives an empty one.
   * `dropped` says how many entries were rejected.
   */
  function sanitizeLibrary(raw, defaultVersion = '1.0') {
    const clean = { version: defaultVersion, configs: [], dropped: 0 };
    if (!isPlainObject(raw) || !Array.isArray(raw.configs)) return clean;

    if (typeof raw.version === 'string' || typeof raw.version === 'number') {
      clean.version = String(raw.version).slice(0, 20);
    }

    const seen = new Set();
    for (const entry of raw.configs) {
      const config = sanitizeConfig(entry);
      if (config === null || seen.has(config.id)) {
        clean.dropped += 1;
        continue;
      }
      seen.add(config.id);
      clean.configs.push(config);
    }
    return clean;
  }

  return { escapeHtml, isSafeId, isConfigData, sanitizeConfig, sanitizeLibrary };
});
