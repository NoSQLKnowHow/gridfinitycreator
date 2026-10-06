// Tests for static/latest_request.js. Run with: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const { createLatestRequest, isAbort } = require('../../static/latest_request.js');

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

/** A stand-in for fetch(): answers after `ms`, or rejects the way fetch does if the signal aborts first */
function fakeFetch(answer, ms, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('The operation was aborted.', 'AbortError')); };
    const timer = setTimeout(() => { signal && signal.removeEventListener('abort', abort); resolve(answer); }, ms);
    if (signal) {
      if (signal.aborted) return abort();
      signal.addEventListener('abort', abort, { once: true });
    }
  });
}

/** What the page does: ask, wait for the answer, and only use it if it is still the newest question */
async function load(latest, answer, ms, drawn) {
  const request = latest.begin();
  try {
    const result = await fakeFetch(answer, ms, request.signal);
    if (!request.isCurrent()) return;
    drawn.push(result);
  } catch (error) {
    if (!isAbort(error)) throw error;
  }
}

test('a single request is current and its signal stays live', () => {
  const latest = createLatestRequest();
  const request = latest.begin();

  assert.equal(request.isCurrent(), true);
  assert.equal(request.signal.aborted, false);
});

test('starting a new request abandons the previous one', () => {
  const latest = createLatestRequest();
  const first = latest.begin();
  const second = latest.begin();

  assert.equal(first.isCurrent(), false);
  assert.equal(first.signal.aborted, true);
  assert.equal(second.isCurrent(), true);
  assert.equal(second.signal.aborted, false);
});

test('cancel abandons the outstanding request and leaves nothing current', () => {
  const latest = createLatestRequest();
  const request = latest.begin();

  latest.cancel();

  assert.equal(request.isCurrent(), false);
  assert.equal(request.signal.aborted, true);
  latest.cancel(); // and doing it again, or with nothing outstanding, is harmless
});

test('independent trackers do not affect each other', () => {
  const preview = createLatestRequest();
  const dimensions = createLatestRequest();
  const a = preview.begin();
  const b = dimensions.begin();

  preview.begin();

  assert.equal(a.isCurrent(), false);
  assert.equal(b.isCurrent(), true);
});

test('only AbortError counts as an abort', () => {
  assert.equal(isAbort(new DOMException('x', 'AbortError')), true);
  assert.equal(isAbort(Object.assign(new Error('x'), { name: 'AbortError' })), true);
  assert.equal(isAbort(new TypeError('Failed to fetch')), false);
  assert.equal(isAbort(new Error('boom')), false);
  assert.equal(isAbort(null), false);
  assert.equal(isAbort(undefined), false);
  assert.equal(isAbort('AbortError'), false);
});

// ---------------------------------------------------------------- the race itself

test('an older, slower answer cannot overwrite a newer one (the preview race)', async () => {
  const latest = createLatestRequest();
  const drawn = [];

  const big = load(latest, 'big bin', 60, drawn);     // asked first, slow to build
  await sleep(10);
  const small = load(latest, 'small bin', 5, drawn);  // the user changed their mind
  await Promise.all([big, small]);
  await sleep(80);

  assert.deepEqual(drawn, ['small bin']);
});

test('without the guard the same sequence does draw the stale answer (the test can fail)', async () => {
  const drawn = [];
  const unguarded = async (answer, ms) => { drawn.push(await fakeFetch(answer, ms)); };

  await Promise.all([unguarded('big bin', 60), (async () => { await sleep(10); await unguarded('small bin', 5); })()]);

  assert.deepEqual(drawn, ['small bin', 'big bin']); // last one drawn is the stale one
});

test('answers arriving in order are all fine, and each new request cancels its predecessor', async () => {
  const latest = createLatestRequest();
  const drawn = [];

  await load(latest, 'first', 5, drawn);
  await load(latest, 'second', 5, drawn);

  assert.deepEqual(drawn, ['first', 'second']);
});

test('a request cancelled while in flight draws nothing and does not throw', async () => {
  const latest = createLatestRequest();
  const drawn = [];

  const pending = load(latest, 'never wanted', 50, drawn);
  await sleep(5);
  latest.cancel(); // e.g. the preview was switched off
  await pending;

  assert.deepEqual(drawn, []);
});

test('a burst of requests leaves only the last one alive', async () => {
  const latest = createLatestRequest();
  const drawn = [];

  const burst = [40, 30, 20, 10, 1].map((ms, i) => load(latest, `request ${i}`, ms, drawn));
  await Promise.all(burst);

  assert.deepEqual(drawn, ['request 4']);
});

test('real errors are not swallowed', async () => {
  const latest = createLatestRequest();
  const request = latest.begin();

  await assert.rejects(async () => {
    try { throw new TypeError('Failed to fetch'); } catch (error) { if (!isAbort(error)) throw error; }
  }, TypeError);
  assert.equal(request.isCurrent(), true);
});
