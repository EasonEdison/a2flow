import assert from 'node:assert/strict';
import test from 'node:test';

import { copyText } from '../src/clipboard.mjs';

test('uses Clipboard API only after a confirmed write', async () => {
  const writes = [];
  const copied = await copyText('完整结果', {
    isSecureContext: true,
    navigator: { clipboard: { writeText: async value => writes.push(value) } },
  });
  assert.equal(copied, true);
  assert.deepEqual(writes, ['完整结果']);
});

test('falls back to selection copy on public HTTP and reports the real result', async () => {
  let selected = false;
  let removed = false;
  const node = {
    value: '', readOnly: false, style: {},
    setAttribute() {}, focus() {}, select() { selected = true; }, remove() { removed = true; },
  };
  const copied = await copyText('plain text', {
    isSecureContext: false,
    navigator: { clipboard: { writeText: async () => assert.fail('secure API must not run') } },
    document: {
      body: { appendChild() {} },
      createElement: () => node,
      execCommand: command => command === 'copy',
    },
  });
  assert.equal(copied, true);
  assert.equal(node.value, 'plain text');
  assert.equal(selected, true);
  assert.equal(removed, true);
});

test('returns false when both copy paths fail', async () => {
  const copied = await copyText('result', {
    isSecureContext: true,
    navigator: { clipboard: { writeText: async () => { throw new Error('denied'); } } },
  });
  assert.equal(copied, false);
});
