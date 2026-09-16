import assert from 'node:assert/strict';
import test from 'node:test';
import {
  publicationConfirmation, rollbackConfirmation, rollbackTarget,
  settleSaveBuffer, shouldChangeKind,
} from '../src/draft-state.js';

test('keeps the current list when the active kind is clicked again', () => {
  assert.equal(shouldChangeKind('SKILL', 'SKILL'), false);
  assert.equal(shouldChangeKind('SKILL', 'ABILITY'), true);
  assert.equal(shouldChangeKind(null, 'SKILL'), true);
});

test('describes explicit publish and configuration-only rollback', () => {
  const target = rollbackTarget('ONLINE', 'v1');
  assert.equal(target.channel, 'STABLE');
  assert.match(publicationConfirmation({ ...target, versionId: 'v2' }), /清除当前灰度/);
  assert.match(rollbackConfirmation(target), /不补偿任何业务操作/);
});

const saved = {
  revision: 3,
  document: { name: 'saved' },
  contentDigest: 'sha256:saved',
  updatedBy: 'admin',
};

test('settles an unchanged buffer to the saved snapshot', () => {
  const submitted = '{\n  "name": "submitted"\n}';
  const result = settleSaveBuffer({
    text: submitted,
    revision: 2,
    dirty: true,
    conflict: false,
    contentDigest: 'sha256:old',
    updatedBy: 'admin',
  }, submitted, saved);

  assert.equal(result.text, JSON.stringify(saved.document, null, 2));
  assert.equal(result.revision, 3);
  assert.equal(result.dirty, false);
});

test('keeps edits made while a save request is pending', () => {
  const result = settleSaveBuffer({
    text: '{\n  "name": "newer local edit"\n}',
    revision: 2,
    dirty: true,
    conflict: false,
    contentDigest: 'sha256:old',
    updatedBy: 'admin',
  }, '{\n  "name": "submitted"\n}', saved);

  assert.match(result.text, /newer local edit/);
  assert.equal(result.revision, 3);
  assert.equal(result.dirty, true);
  assert.equal(result.contentDigest, 'sha256:saved');
});
