// Tests for the address handling in static/tabs.js. Run with: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const { tabFromHash, hashForTab } = require('../../static/tabs.js');

const TABS = ['home', 'baseplate', 'classicbin', 'holeybin', 'lightbin', 'solidbin'];

test('a hash that names a tab selects it', () => {
  assert.equal(tabFromHash('#solidbin', TABS), 'solidbin');
  assert.equal(tabFromHash('#home', TABS), 'home');
});

test('anything else in the hash is not a tab', () => {
  assert.equal(tabFromHash('#main', TABS), null);        // the "skip to content" link
  assert.equal(tabFromHash('#nonsense', TABS), null);
  assert.equal(tabFromHash('#settings', TABS), null);    // an element id that is not a tab
  assert.equal(tabFromHash('', TABS), null);
  assert.equal(tabFromHash('#', TABS), null);
  assert.equal(tabFromHash(undefined, TABS), null);
});

test('matching is exact and case-sensitive, so a lookalike does not select a tab', () => {
  assert.equal(tabFromHash('#SolidBin', TABS), null);
  assert.equal(tabFromHash('#solidbin2', TABS), null);
  assert.equal(tabFromHash('#solid', TABS), null);
});

test('an address with broken escapes is ignored rather than failing', () => {
  assert.equal(tabFromHash('#%E0%A4%A', TABS), null);
  assert.equal(tabFromHash('#%', TABS), null);
});

test('an escaped name still counts', () => {
  assert.equal(tabFromHash('#solid%62in', TABS), 'solidbin');
});

test('the Home tab leaves the address plain; the others are recorded', () => {
  assert.equal(hashForTab('home'), '');
  assert.equal(hashForTab('holeybin'), '#holeybin');
  assert.equal(hashForTab(''), '');
  assert.equal(hashForTab(undefined), '');
});
