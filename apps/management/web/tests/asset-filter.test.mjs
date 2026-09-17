import assert from 'node:assert/strict';
import test from 'node:test';
import { filterAssets } from '../src/asset-filter.js';

const assets = [
  { key: 'skill.alpha', name: 'Alpha Helper', versionId: 'v1', assetId: 'asset-001' },
  { skillKey: 'skill.beta', name: 'Beta Tool', versionId: 'release-2', assetId: 'asset-002' },
];

test('returns all assets for an empty or whitespace-only query', () => {
  assert.deepEqual(filterAssets(assets, ''), assets);
  assert.deepEqual(filterAssets(assets, '   '), assets);
});

test('matches displayed names and identifiers case-insensitively', () => {
  assert.deepEqual(filterAssets(assets, '  ALPHA  '), [assets[0]]);
  assert.deepEqual(filterAssets(assets, 'SKILL.BETA'), [assets[1]]);
  assert.deepEqual(filterAssets(assets, 'RELEASE-2'), [assets[1]]);
  assert.deepEqual(filterAssets(assets, 'asset-001'), [assets[0]]);
});

test('returns no assets when displayed fields do not match', () => {
  assert.deepEqual(filterAssets(assets, 'missing'), []);
});
