import test from 'node:test';
import assert from 'node:assert/strict';
import { downloadText, MAX_TEXT_DOWNLOAD_BYTES, textDownloadError,
  validateTextDownload } from '../src/textDownload.mjs';

const markdown = { filename: '创作稿.md', mediaType: 'text/markdown; charset=utf-8', content: '# 标题\n\n正文' };

test('accepts only bounded inline Markdown and plain text downloads', () => {
  assert.equal(validateTextDownload(markdown), '');
  assert.equal(validateTextDownload({ filename: 'draft.txt', mediaType: 'text/plain; charset=utf-8', content: 'text' }), '');
  for (const invalid of [
    { ...markdown, filename: '../draft.md' },
    { ...markdown, filename: 'draft.txt' },
    { ...markdown, mediaType: 'text/html; charset=utf-8' },
    { ...markdown, content: '' },
    { ...markdown, content: 'x'.repeat(MAX_TEXT_DOWNLOAD_BYTES + 1) },
  ]) assert.notEqual(validateTextDownload(invalid), '');
});

test('a failed declarative check blocks even an otherwise valid stale export', () => {
  assert.equal(textDownloadError(markdown, true, []), '');
  assert.equal(textDownloadError(markdown, false, ['导出版本已过期']), '导出版本已过期');
});

test('downloads through a short-lived object URL without accepting a remote URL', () => {
  const calls = [];
  const anchor = { click: () => calls.push('click'), remove: () => calls.push('remove') };
  const platform = {
    Blob: class { constructor(parts, options) { this.parts = parts; this.options = options; } },
    URL: { createObjectURL: blob => { calls.push(['create', blob]); return 'blob:local'; },
      revokeObjectURL: url => calls.push(['revoke', url]) },
    document: { createElement: tag => { assert.equal(tag, 'a'); return anchor; },
      body: { append: value => { assert.equal(value, anchor); calls.push('append'); } } },
    setTimeout: callback => { calls.push('schedule-revoke'); callback(); },
  };
  downloadText(markdown, platform);
  assert.equal(anchor.href, 'blob:local');
  assert.equal(anchor.download, '创作稿.md');
  assert.deepEqual(calls.map(item => Array.isArray(item) ? item[0] : item),
    ['create', 'append', 'click', 'remove', 'schedule-revoke', 'revoke']);
});
