// Tests for static/tabs.js. Run with: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const { centeredScrollLeft } = require('../../static/tabs.js');

test('an item is scrolled to the middle of the strip', () => {
  // a 100 px tab at x=500 in a 300 px strip: its left edge belongs at 100 px from the strip's left
  assert.equal(centeredScrollLeft(500, 100, 300), 400);
});

test('the strip is never scrolled before its start', () => {
  assert.equal(centeredScrollLeft(10, 100, 300), 0);
  assert.equal(centeredScrollLeft(0, 80, 375), 0);
});

test('an item as wide as the strip lines up with its left edge', () => {
  assert.equal(centeredScrollLeft(250, 300, 300), 250);
});
