import { strict as assert } from 'assert';
import {
  buildWorkspaceResetOptionGroups,
  defaultWorkspaceResetValue,
  parseWorkspaceResetValue,
  resetSourceDisplayName,
} from './workspaceResetSource';

const groups = buildWorkspaceResetOptionGroups(
  [
    {
      sourceType: 'BUILD',
      sourceId: 'build-7',
      buildNumber: 7,
      targetVersion: 4,
      completionTime: 1787580000000,
      operator: 'tangxiaohan',
      packageDigest: 'sha256:1234567890abcdef',
    },
  ],
  [2, 4],
);

assert.equal(groups.length, 2);
assert.equal(groups?.[0]?.label, 'PRT 成功 Build');
assert.equal(groups?.[0]?.options?.[0]?.value, 'BUILD:build-7');
assert.match(groups?.[0]?.options?.[0]?.label, /PRT Build #7/);
assert.equal(groups?.[0]?.options?.[0]?.displayName, 'PRT Build #7（目标版本 4）');
assert.match(groups?.[0]?.options?.[0]?.description, /完成于/);
assert.match(groups?.[0]?.options?.[0]?.description, /tangxiaohan/);
assert.match(groups?.[0]?.options?.[0]?.description, /sha256:1234567890abcdef/);
assert.equal(groups?.[1]?.label, '线上正式版本');
assert.deepEqual(
  groups?.[1]?.options?.map?.((option) => option.value),
  ['VERSION:4', 'VERSION:2'],
);
assert.equal(defaultWorkspaceResetValue(groups), 'BUILD:build-7');
assert.deepEqual(parseWorkspaceResetValue('BUILD:build-7'), {
  sourceType: 'BUILD',
  sourceId: 'build-7',
});
assert.deepEqual(parseWorkspaceResetValue('VERSION:4'), {
  sourceType: 'VERSION',
  sourceId: '4',
});
assert.equal(parseWorkspaceResetValue('FAILED:build-7'), null);
assert.equal(
  resetSourceDisplayName({ sourceType: 'BUILD', sourceId: 'build-7' }),
  'PRT Build build-7',
);
assert.equal(resetSourceDisplayName({ sourceType: 'VERSION', sourceId: '4' }), '线上正式版本 4');

console.log('PASS workspace reset source contract');
