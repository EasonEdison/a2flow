import assert from 'node:assert/strict';
import test from 'node:test';
import {
  acceptsAsyncTarget,
  activateAsyncLifecycle,
  applyPendingText,
  asyncTarget,
  checkPackage,
  createTextResource,
  inspectResource,
  inspectResourceVerified,
  pathIssue,
  pendingText,
  resourceIdentity,
  resourceIdentityIssue,
  saveBodyIssue,
} from '../src/skill-resource-state.js';

const encoder = new TextEncoder();
const digest = async (text) => `sha256:${Buffer.from(await crypto.subtle.digest('SHA-256', encoder.encode(text))).toString('hex')}`;

function entry(overrides = {}) {
  return {
    handleId: 'guide-md', logicalPath: 'guides/guide.md', mediaType: 'text/markdown',
    byteSize: 5, contentDigest: 'sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
    base64: 'aGVsbG8=', extension: { keep: true }, ...overrides,
  };
}

test('StrictMode effect setup reactivates lifecycle and invalidates stale generations', () => {
  const mounted = { current: false };
  const operationSequence = { current: 4 };
  const inspectionSequence = { current: 7 };
  const cleanup = activateAsyncLifecycle(mounted, operationSequence, inspectionSequence);
  assert.equal(mounted.current, true);
  cleanup();
  assert.equal(mounted.current, false);
  assert.equal(operationSequence.current, 5);
  assert.equal(inspectionSequence.current, 8);
  const secondCleanup = activateAsyncLifecycle(mounted, operationSequence, inspectionSequence);
  assert.equal(mounted.current, true);
  assert.equal(acceptsAsyncTarget(asyncTarget('skill', 1, 'resource', 4), asyncTarget('skill', 1, 'resource', operationSequence.current)), false);
  secondCleanup();
});

test('Unicode text is encoded byte-accurately and roundtrips with sha256 evidence', async () => {
  const value = await createTextResource({ handleId: 'unicode', logicalPath: 'notes/unicode.md', mediaType: 'text/markdown', text: '你好🙂' });
  assert.equal(value.byteSize, encoder.encode('你好🙂').byteLength);
  assert.equal(value.contentDigest, await digest('你好🙂'));
  assert.equal(Buffer.from(value.base64, 'base64').toString('utf8'), '你好🙂');
  assert.deepEqual(await inspectResourceVerified(value), { status: 'editable', text: '你好🙂' });
});

test('invalid base64, UTF-8, size and digest are preserved and marked for repair', async () => {
  for (const value of [
    entry({ base64: '%%%'}),
    entry({ base64: '/w==', byteSize: 1, contentDigest: 'sha256:' + 'a'.repeat(64) }),
    entry({ byteSize: 99 }),
    entry({ contentDigest: 'sha256:' + '0'.repeat(64) }),
  ]) {
    const before = structuredClone(value);
    assert.equal((await inspectResourceVerified(value)).status, 'repair');
    assert.deepEqual(value, before);
  }
});

test('binary and unknown entries remain readonly without replacement decoding', () => {
  const binary = entry({ mediaType: 'application/octet-stream', base64: '/w==', byteSize: 1, contentDigest: 'sha256:a8100ae6aa1940d0b663bb31cd466142ebbdbd5187131b92d93818987832eb89' });
  assert.deepEqual(inspectResource(binary), { status: 'readonly', reason: 'BINARY_RESOURCE' });
  assert.equal(inspectResource({ future: true }).status, 'repair');
});

test('binary digest is verified before readonly integrity is reported', async () => {
  const valid = entry({ mediaType: 'application/octet-stream', base64: '/w==', byteSize: 1, contentDigest: 'sha256:a8100ae6aa1940d0b663bb31cd466142ebbdbd5187131b92d93818987832eb89' });
  assert.deepEqual(await inspectResourceVerified(valid), { status: 'readonly', reason: 'BINARY_RESOURCE', integrity: 'verified' });
  assert.deepEqual(await inspectResourceVerified({ ...valid, contentDigest: `sha256:${'0'.repeat(64)}` }), { status: 'repair', reason: 'DECLARED_DIGEST_MISMATCH' });
});

test('reserved descriptor and duplicate identity remain explicit repair conditions', () => {
  assert.equal(checkPackage([entry({ logicalPath: 'SKILL.md' })]).issues.includes('RESERVED_SKILL_MD'), true);
  const duplicate = [entry(), entry({ logicalPath: 'other.md' })];
  assert.equal(resourceIdentityIssue(duplicate[0], duplicate), 'DUPLICATE_HANDLE_ID');
  assert.equal(resourceIdentityIssue(entry(), [entry()]), null);
});
test('path checks match authoritative traversal, duplicate and reserved rules', () => {
  const resources = [entry()];
  assert.equal(pathIssue('../secret', resources), 'INVALID_LOGICAL_PATH');
  assert.equal(pathIssue('/absolute', resources), 'INVALID_LOGICAL_PATH');
  assert.equal(pathIssue('a\\b', resources), 'INVALID_LOGICAL_PATH');
  assert.equal(pathIssue('a\nb', resources), 'INVALID_LOGICAL_PATH');
  assert.equal(pathIssue('SKILL.md', resources), 'RESERVED_SKILL_MD');
  assert.equal(pathIssue('guides/guide.md', resources), 'DUPLICATE_LOGICAL_PATH');
});

test('package preflight enforces count, per-entry, total and one MiB save request boundaries', () => {
  assert.equal(checkPackage(Array(128).fill(entry())).issues.includes('ENTRY_COUNT_LIMIT_EXCEEDED'), true);
  assert.equal(checkPackage([entry({ byteSize: 4 * 1024 * 1024 + 1 })]).issues.includes('ENTRY_BYTES_LIMIT_EXCEEDED'), true);
  assert.equal(checkPackage(Array(5).fill(entry({ byteSize: 4 * 1024 * 1024 }))).issues.includes('TOTAL_BYTES_LIMIT_EXCEEDED'), true);
  assert.equal(checkPackage([entry({ base64: 'A'.repeat(1024 * 1024) })]).issues.includes('SAVE_BODY_BUDGET_EXCEEDED'), true);
});

test('save body preflight uses encoded UTF-8 bytes for the complete request envelope', () => {
  assert.equal(saveBodyIssue({ expectedRevision: 1, document: { text: '你'.repeat(400000) } }), 'SAVE_BODY_BUDGET_EXCEEDED');
  assert.equal(saveBodyIssue({ expectedRevision: 1, document: { text: 'small' } }), null);
});

test('failed text apply does not mutate source and canonical change creates conflict', async () => {
  const original = entry();
  const pending = pendingText(original, 'changed');
  const changedCanonical = entry({ base64: 'd29ybGQ=', contentDigest: 'sha256:486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73f41b2b21cf763ee4e9cb', byteSize: 5 });
  assert.equal((await applyPendingText(changedCanonical, pending)).error, 'RESOURCE_CONFLICT');
  assert.deepEqual(original, entry());
});

test('text apply preserves unknown fields and updates content evidence atomically', async () => {
  const original = entry();
  const result = await applyPendingText(original, pendingText(original, '更新'));
  assert.equal(result.error, undefined);
  assert.equal(result.resource.extension.keep, true);
  assert.equal(result.resource.byteSize, encoder.encode('更新').byteLength);
  assert.equal(result.resource.contentDigest, await digest('更新'));
  assert.equal(inspectResource(result.resource).text, '更新');
});

test('resource identity is stable across list reorder and rejects handle collisions', async () => {
  assert.equal(resourceIdentity(entry()), 'handle:guide-md');
  await assert.rejects(() => createTextResource({ handleId: 'guide-md', logicalPath: 'other.txt', mediaType: 'text/plain', text: '', resources: [entry()] }), /DUPLICATE_HANDLE_ID/);
});
