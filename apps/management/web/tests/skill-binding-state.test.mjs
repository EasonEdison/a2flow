import assert from 'node:assert/strict';
import test from 'node:test';
import {
  bindingKey,
  bindingRows,
  filterBindingAssets,
  addBinding,
  removeBinding,
} from '../src/skill-binding-state.js';

const assets = [
  { key: 'ability.search', name: 'Search orders', description: 'Find an order', versionId: 'v3' },
  { key: 'ability.refund', name: 'Refund', description: 'Issue a refund' },
];

test('filters authoritative binding catalog by name, key, and description', () => {
  assert.deepEqual(filterBindingAssets(assets, ' ORDER '), [assets[0]]);
  assert.deepEqual(filterBindingAssets(assets, 'ability.refund'), [assets[1]]);
  assert.deepEqual(filterBindingAssets(assets, 'issue'), [assets[1]]);
  assert.deepEqual(filterBindingAssets(assets, ''), assets);
});

test('maps known, unavailable, duplicate, and malformed bindings without pruning', () => {
  const malformed = { retained: true };
  const rows = bindingRows(['ability.search', 'missing.key', 'ability.search', malformed], assets);
  assert.equal(rows.length, 4);
  assert.deepEqual(rows.map((row) => row.status), ['available', 'unavailable', 'duplicate', 'malformed']);
  assert.equal(rows[1].key, 'missing.key');
  assert.equal(rows[1].asset, undefined);
  assert.equal(rows[3].value, malformed);
});

test('adds only a new non-empty logical key without mutating input', () => {
  const current = ['ability.search'];
  assert.deepEqual(addBinding(current, 'ability.refund'), ['ability.search', 'ability.refund']);
  assert.equal(addBinding(current, 'ability.search'), current);
  assert.equal(addBinding(current, '  '), current);
  assert.deepEqual(current, ['ability.search']);
});

test('removes only the explicitly selected stable row', () => {
  const malformed = { retained: true };
  const current = ['ability.search', malformed, 'ability.search'];
  const rows = bindingRows(current, assets);
  assert.deepEqual(removeBinding(current, rows[2].identity), ['ability.search', malformed]);
  assert.deepEqual(current, ['ability.search', malformed, 'ability.search']);
});

test('does not invent a key for malformed catalog entries', () => {
  assert.equal(bindingKey({ name: 'No key' }), null);
  assert.deepEqual(filterBindingAssets([{ name: 'No key' }, ...assets], 'no key'), []);
});
