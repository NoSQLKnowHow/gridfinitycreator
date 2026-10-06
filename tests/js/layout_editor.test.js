// Tests for the keyboard side of static/layout_editor.js. Run with: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const { layoutSegmentLabel, layoutNextIndex } = require('../../static/layout_editor.js');

// ---------------------------------------------------------------- what a screen reader announces

test('a wall between two columns names the columns and the row (counted from the front, from 1)', () => {
  assert.equal(layoutSegmentLabel('v', 1, 0), 'Divider wall between column 1 and column 2, row 1');
  assert.equal(layoutSegmentLabel('v', 2, 3), 'Divider wall between column 2 and column 3, row 4');
});

test('a wall between two rows names the rows and the column', () => {
  assert.equal(layoutSegmentLabel('h', 0, 1), 'Divider wall between row 1 and row 2, column 1');
  assert.equal(layoutSegmentLabel('h', 3, 2), 'Divider wall between row 2 and row 3, column 4');
});

// ---------------------------------------------------------------- moving between the walls

test('right and down go to the next wall, left and up to the previous one', () => {
  assert.equal(layoutNextIndex(2, 10, 'ArrowRight'), 3);
  assert.equal(layoutNextIndex(2, 10, 'ArrowDown'), 3);
  assert.equal(layoutNextIndex(2, 10, 'ArrowLeft'), 1);
  assert.equal(layoutNextIndex(2, 10, 'ArrowUp'), 1);
});

test('the ends stop rather than wrap round', () => {
  assert.equal(layoutNextIndex(9, 10, 'ArrowRight'), 9);
  assert.equal(layoutNextIndex(0, 10, 'ArrowLeft'), 0);
});

test('Home and End jump to the first and last wall', () => {
  assert.equal(layoutNextIndex(5, 10, 'Home'), 0);
  assert.equal(layoutNextIndex(5, 10, 'End'), 9);
});

test('other keys, and an empty layout, are left alone', () => {
  assert.equal(layoutNextIndex(2, 10, 'a'), null);
  assert.equal(layoutNextIndex(2, 10, 'Tab'), null);
  assert.equal(layoutNextIndex(0, 0, 'ArrowRight'), null);
});
