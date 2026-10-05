import assert from 'node:assert/strict';
import test from 'node:test';

import { appendComposerDraft } from '../src/composerDraft.mjs';

test('composer draft appends without replacing existing user input', () => {
  assert.equal(appendComposerDraft('', '姓名：张三'), '姓名：张三');
  assert.equal(
    appendComposerDraft('我已有的输入', '姓名：张三'),
    '我已有的输入\n姓名：张三',
  );
});

test('composer draft rejects empty and oversized additions', () => {
  assert.equal(appendComposerDraft('原稿', ''), null);
  assert.equal(appendComposerDraft('原稿', 'x'.repeat(4000)), null);
  assert.equal(appendComposerDraft('', 'x'.repeat(4000)), 'x'.repeat(4000));
});
