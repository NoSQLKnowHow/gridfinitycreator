// Tests for static/safe_config.js. Run with: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const { escapeHtml, isSafeId, isConfigData, sanitizeConfig, sanitizeLibrary } = require('../../static/safe_config.js');

const validConfig = () => ({
  id: '1721234567890_k3j2h1g9f',
  name: 'Small parts bin',
  formId: 'classicbin',
  data: { sizeUnitsX: '2', compartmentsX: '3', addStackingLip: true, removedWalls: '[["v",1,0]]', tags: ['a', 'b'] },
  createdAt: '2026-07-09T10:00:00.000Z',
  notes: ''
});

// ---------------------------------------------------------------- escaping

test('escapeHtml escapes every character that matters in HTML and attributes', () => {
  assert.equal(escapeHtml(`<img src=x onerror="alert('1')"> & more`),
    '&lt;img src=x onerror=&quot;alert(&#039;1&#039;)&quot;&gt; &amp; more');
});

test('escapeHtml copes with values that are not strings', () => {
  assert.equal(escapeHtml(5), '5');
  assert.equal(escapeHtml(null), 'null');
  assert.equal(escapeHtml(undefined), 'undefined');
  assert.equal(escapeHtml({ toString: () => '<b>' }), '&lt;b&gt;');
});

// ---------------------------------------------------------------- ids

test('ids made by the library are accepted', () => {
  assert.ok(isSafeId('1721234567890_k3j2h1g9f'));
  assert.ok(isSafeId('classicbin'));
  assert.ok(isSafeId('a-b_C9'));
});

test('ids that could break out of HTML, attributes or script strings are rejected', () => {
  for (const bad of ["');alert(1);//", '<img src=x onerror=alert(1)>', 'a b', 'a"b', "a'b", 'a;b', 'a/b', '', 'x'.repeat(101), 5, null, undefined, {}, ['a']]) {
    assert.equal(isSafeId(bad), false, `should reject ${JSON.stringify(bad)}`);
  }
});

// ---------------------------------------------------------------- form data

test('data as captured from a form is accepted', () => {
  assert.ok(isConfigData(validConfig().data));
  assert.ok(isConfigData({}));
  assert.ok(isConfigData({ size: 3, ratio: 0.5, on: false, text: '' }));
});

test('data that is not a flat object of simple values is rejected', () => {
  assert.equal(isConfigData(null), false);
  assert.equal(isConfigData([]), false);
  assert.equal(isConfigData('text'), false);
  assert.equal(isConfigData({ nested: { a: 1 } }), false);
  assert.equal(isConfigData({ list: [1, 2] }), false);          // lists are lists of strings
  assert.equal(isConfigData({ n: Infinity }), false);
  assert.equal(isConfigData({ n: null }), false);
  assert.equal(isConfigData({ big: 'x'.repeat(100001) }), false);
});

test('field names that are not plain identifiers are rejected, including prototype tricks', () => {
  for (const name of ['a"b', 'a b', '1abc', '', '__proto__', 'constructor.x', '<b>']) {
    const data = JSON.parse(`{${JSON.stringify(name)}: "x"}`);  // JSON.parse keeps "__proto__" as an own key
    assert.equal(isConfigData(data), false, `should reject field name ${JSON.stringify(name)}`);
  }
});

test('an absurd number of fields is rejected', () => {
  const data = {};
  for (let i = 0; i < 101; i += 1) data[`field${i}`] = 'x';
  assert.equal(isConfigData(data), false);
});

// ---------------------------------------------------------------- one configuration

test('a valid configuration passes through unchanged', () => {
  assert.deepEqual(sanitizeConfig(validConfig()), validConfig());
});

test('each required part is checked', () => {
  const breakIt = changes => Object.assign(validConfig(), changes);
  assert.equal(sanitizeConfig(null), null);
  assert.equal(sanitizeConfig('config'), null);
  assert.equal(sanitizeConfig(breakIt({ id: "');alert(1);//" })), null);
  assert.equal(sanitizeConfig(breakIt({ formId: '<img src=x onerror=alert(1)>' })), null);
  assert.equal(sanitizeConfig(breakIt({ name: 42 })), null);
  assert.equal(sanitizeConfig(breakIt({ name: '   ' })), null);
  assert.equal(sanitizeConfig(breakIt({ data: { nested: {} } })), null);
});

test('names are trimmed and limited, odd dates dropped, unknown properties ignored', () => {
  const config = sanitizeConfig(Object.assign(validConfig(), {
    name: `  ${'n'.repeat(500)}  `, createdAt: 'not a date', notes: 7, extra: '<script>', onclick: 'x'
  }));

  assert.equal(config.name.length, 200);
  assert.equal(config.createdAt, '');
  assert.equal(config.notes, '');
  assert.deepEqual(Object.keys(config).sort(), ['createdAt', 'data', 'formId', 'id', 'name', 'notes']);
});

test('the copy does not share its data object with the input', () => {
  const input = validConfig();
  const config = sanitizeConfig(input);
  config.data.sizeUnitsX = '99';
  assert.equal(input.data.sizeUnitsX, '2');
});

// ---------------------------------------------------------------- whole library

test('hostile entries are dropped and good ones kept', () => {
  const good = validConfig();
  const library = sanitizeLibrary({
    version: '1.0',
    configs: [
      good,
      Object.assign(validConfig(), { id: "');alert(document.domain);//" }),
      Object.assign(validConfig(), { id: 'another', formId: '<img src=x onerror=alert(1)>' }),
      'not even an object',
      null,
    ]
  });

  assert.deepEqual(library.configs, [good]);
  assert.equal(library.dropped, 4);
});

test('duplicate ids keep the first entry', () => {
  const first = validConfig();
  const second = Object.assign(validConfig(), { name: 'Imposter' });

  const library = sanitizeLibrary({ version: '1.0', configs: [first, second] });

  assert.deepEqual(library.configs.map(config => config.name), ['Small parts bin']);
  assert.equal(library.dropped, 1);
});

test('anything that is not a library gives an empty one', () => {
  for (const junk of [null, undefined, 'text', 5, [], {}, { configs: 'x' }, { version: '1.0' }]) {
    const library = sanitizeLibrary(junk);
    assert.deepEqual(library.configs, [], `for ${JSON.stringify(junk)}`);
    assert.equal(library.version, '1.0');
  }
});

test('the version is kept when it is sensible', () => {
  assert.equal(sanitizeLibrary({ version: '2.1', configs: [] }).version, '2.1');
  assert.equal(sanitizeLibrary({ version: 3, configs: [] }).version, '3');
  assert.equal(sanitizeLibrary({ version: { a: 1 }, configs: [] }).version, '1.0');
});
