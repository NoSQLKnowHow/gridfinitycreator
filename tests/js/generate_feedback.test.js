// Tests for static/generate_feedback.js. Run with: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const { createToken, cookieHasToken, expireCookie, COOKIE_NAME } = require('../../static/generate_feedback.js');

test('a token is a plain random string of a sensible length', () => {
  const token = createToken();
  assert.match(token, /^[A-Za-z0-9]{16,64}$/);
});

test('tokens do not repeat', () => {
  const seen = new Set();
  for (let i = 0; i < 500; i += 1) seen.add(createToken());
  assert.equal(seen.size, 500);
});

test('the cookie holding the token is found among others', () => {
  assert.equal(cookieHasToken('gridspec=42,42,7; download_token=abc123; theme=dark', 'abc123'), true);
  assert.equal(cookieHasToken('download_token=abc123', 'abc123'), true);
});

test('a different token, or none, is not a match', () => {
  assert.equal(cookieHasToken('download_token=other', 'abc123'), false);
  assert.equal(cookieHasToken('', 'abc123'), false);
  assert.equal(cookieHasToken('gridspec=42,42,7', 'abc123'), false);
});

test('a cookie that merely ends in the same name is not the token cookie', () => {
  assert.equal(cookieHasToken('my_download_token=abc123', 'abc123'), false);
  assert.equal(cookieHasToken('download_token_old=abc123', 'abc123'), false);
});

test('a token that contains regular-expression characters is compared literally', () => {
  assert.equal(cookieHasToken('download_token=abc123', '.*'), false);
  assert.equal(cookieHasToken('download_token=abc123', 'abc12(3'), false);
});

test('a token only matches whole, not as the start of a longer value', () => {
  assert.equal(cookieHasToken('download_token=abc1234', 'abc123'), false);
});

test('the cookie is removed by expiring it on the same path', () => {
  assert.match(expireCookie(), new RegExp(`^${COOKIE_NAME}=; .*expires=Thu, 01 Jan 1970`));
  assert.match(expireCookie(), /path=\//);
});
