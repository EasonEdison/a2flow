import test from 'node:test';
import assert from 'node:assert/strict';
import { diffValues } from '../src/structured-diff.js';

test('object key order is semantic while missing, null and type changes differ', () => {
  assert.deepEqual(diffValues({ b: 2, a: null }, { a: null, b: 2 }), []);
  assert.deepEqual(diffValues({ a: null }, {}), [{ path: '/a', kind: 'removed', before: null }]);
  assert.deepEqual(diffValues({ a: 1 }, { a: '1' }), [{ path: '/a', kind: 'type', before: 1, after: '1' }]);
});

test('arrays preserve order and paths escape JSON Pointer tokens', () => {
  assert.deepEqual(diffValues({ 'a/b~c': [1, 2] }, { 'a/b~c': [2, 1] }), [
    { path: '/a~1b~0c/0', kind: 'changed', before: 1, after: 2 },
    { path: '/a~1b~0c/1', kind: 'changed', before: 2, after: 1 },
  ]);
});

test('large and base64-like strings are summarized', () => {
  const [change] = diffValues({ value: 'a'.repeat(500) }, { value: 'b'.repeat(500) });
  assert.match(change.before, /^\[string 500 chars/);
  assert.match(change.after, /^\[string 500 chars/);
});

test('nested added and type-changed values are recursively bounded', () => {
  const huge = 'A'.repeat(10000);
  const added = diffValues({}, { nested: { resource: huge } });
  assert.match(JSON.stringify(added), /detail omitted/);
  assert.ok(JSON.stringify(added).length < 2000);
  const changed = diffValues({ value: { nested: huge } }, { value: false });
  assert.match(JSON.stringify(changed), /detail omitted/);
  assert.ok(JSON.stringify(changed).length < 2000);
});

test('depth and entry budgets emit visible truncation entries', () => {
  let deep = { value: 'end' };
  for (let index = 0; index < 40; index += 1) deep = { nested: deep };
  const depthChanges = diffValues({}, deep);
  assert.match(JSON.stringify(depthChanges), /truncated/);

  const before = Object.fromEntries(Array.from({ length: 1000 }, (_, index) => [`key-${index}`, index]));
  const after = Object.fromEntries(Array.from({ length: 1000 }, (_, index) => [`key-${index}`, index + 1]));
  const changes = diffValues(before, after);
  assert.ok(changes.length <= 201);
  assert.equal(changes.at(-1).kind, 'truncated');
  assert.match(changes.at(-1).after, /remaining differences omitted/);
});
