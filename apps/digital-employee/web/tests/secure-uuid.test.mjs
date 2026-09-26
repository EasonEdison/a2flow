import test from 'node:test';
import assert from 'node:assert/strict';
import { createUuidV4 } from '../src/secureUuid.mjs';

test('creates an RFC 4122 UUID v4 from getRandomValues bytes', () => {
  let calls = 0;
  const source = {
    getRandomValues(bytes) {
      calls += 1;
      assert.ok(bytes instanceof Uint8Array);
      assert.equal(bytes.length, 16);
      for (let index = 0; index < bytes.length; index++) bytes[index] = index;
      return bytes;
    },
  };

  const id = createUuidV4(source);
  assert.equal(id, '00010203-0405-4607-8809-0a0b0c0d0e0f');
  assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u);
  assert.equal(calls, 1);
});

test('fails closed without Web Crypto random values', () => {
  assert.throws(() => createUuidV4(null), /SECURE_RANDOM_UNAVAILABLE/u);
  assert.throws(() => createUuidV4({}), /SECURE_RANDOM_UNAVAILABLE/u);
});
