// Tests for static/holeybin_form.js: the number of holes and the bin size follow each other.
// Run with: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');

// The script wires itself to the document when it loads; give it a document that records the listener
const listeners = {};
global.document = { addEventListener: (type, listener) => { listeners[type] = listener; } };
require('../../static/holeybin_form.js');

/** An <input>: whatever is assigned to its value comes back as text */
function input(value) {
  let text = String(value);
  return { get value() { return text; }, set value(assigned) { text = String(assigned); } };
}

function holeyForm(values) {
  const elements = {};
  for (const [name, value] of Object.entries(values)) elements[name] = input(value);
  return { elements };
}

/** The user changes `name` to `value` in a form; the page reacts to the change event */
function change(form, name, value, action) {
  form.elements[name].value = String(value);
  listeners.change({ target: { dataset: action ? { change: action } : {}, form } });
}

const values = (form) => Object.fromEntries(Object.entries(form.elements).map(([name, field]) => [name, field.value]));

test('the page listens for changes', () => {
  assert.equal(typeof listeners.change, 'function');
});

test('more holes make the bin grow to fit them (rounded up to whole grid units)', () => {
  const form = holeyForm({ numHolesX: 3, numHolesY: 3, sizeUnitsX: 1, sizeUnitsY: 1, keepoutDiameter: 12 });

  change(form, 'numHolesX', 9, 'num-holes-changed');

  assert.equal(form.elements.sizeUnitsX.value, '3');   // ceil((9 * 12 + 2 * 1.9 + 0.5) / 42)
  assert.equal(form.elements.sizeUnitsY.value, '1');   // ceil((3 * 12 + 2 * 1.9 + 0.5) / 42)
});

test('a bigger bin takes as many holes as fit (rounded down)', () => {
  const form = holeyForm({ numHolesX: 3, numHolesY: 3, sizeUnitsX: 1, sizeUnitsY: 1, keepoutDiameter: 12 });

  change(form, 'sizeUnitsX', 2, 'bin-size-changed');

  assert.equal(form.elements.numHolesX.value, '6');    // floor((2 * 42 - 2 * 1.9 - 0.5) / 12)
  assert.equal(form.elements.numHolesY.value, '3');    // floor((1 * 42 - 2 * 1.9 - 0.5) / 12)
});

test('the setting that was changed last leads: the hole size goes back to following the number of holes', () => {
  const form = holeyForm({ numHolesX: 3, numHolesY: 3, sizeUnitsX: 1, sizeUnitsY: 1, keepoutDiameter: 12 });
  change(form, 'sizeUnitsX', 2, 'bin-size-changed');       // the bin size leads now
  assert.equal(form.elements.numHolesX.value, '6');

  change(form, 'keepoutDiameter', 20, 'hole-size-changed');

  assert.equal(form.elements.numHolesX.value, '6');        // the holes were left alone...
  assert.equal(form.elements.sizeUnitsX.value, '3');       // ...and the bin grew to fit them: ceil((6 * 20 + 4.3) / 42)
});

test('a change to a field that carries no action does nothing', () => {
  const form = holeyForm({ numHolesX: 3, numHolesY: 3, sizeUnitsX: 1, sizeUnitsY: 1, keepoutDiameter: 12 });
  const before = values(form);

  change(form, 'numHolesX', 9, null);

  assert.deepEqual(values(form), { ...before, numHolesX: '9' });
});

test('a field outside any form is left alone rather than breaking the page', () => {
  assert.doesNotThrow(() => listeners.change({ target: { dataset: { change: 'num-holes-changed' }, form: null } }));
  assert.doesNotThrow(() => listeners.change({ target: {} }));
});
