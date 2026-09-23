import { strict as assert } from 'assert';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { buildAssetOwnerManagementView, normalizeAssetOwnerIds } from './assetOwnerManagementModel';
import type { AssetAccessResult } from '../types';

const access = (canManageOwner: boolean): AssetAccessResult => ({
  assetType: 'ORCHESTRATION_CONFIG',
  assetKey: 'wf_owner_management_test',
  owners: [
    { principalType: 'USER', principalId: 'owner-a', roleType: 'OWNER' },
    { principalType: 'USER', principalId: 'owner-b', roleType: 'OWNER' },
  ],
  role: canManageOwner ? 'ADMIN' : 'VIEWER',
  permissions: {
    canView: true,
    canEdit: canManageOwner,
    canPublish: canManageOwner,
    canForcePublish: canManageOwner,
    canOffline: canManageOwner,
    canManageOwner,
  },
});

assert.deepEqual(
  buildAssetOwnerManagementView(access(false)),
  { ownerIds: ['owner-a', 'owner-b'], canManageOwner: false },
  'all viewers can see owners without receiving an owner-management entry',
);
assert.deepEqual(
  buildAssetOwnerManagementView(access(true)),
  { ownerIds: ['owner-a', 'owner-b'], canManageOwner: true },
  'management ADMIN permission exposes the owner-management entry',
);
assert.deepEqual(
  normalizeAssetOwnerIds(' owner-a, owner-b,owner-a ,, '),
  ['owner-a', 'owner-b'],
  'owner replacement trims blanks and removes duplicates deterministically',
);

const orchestrationSource = readFileSync(
  resolve(process.cwd(), 'workflow/WorkflowOrchestrationPage.tsx'),
  'utf8',
);
const releaseSource = readFileSync(
  resolve(process.cwd(), 'shared/AssetReleaseTab.tsx'),
  'utf8',
);
assert.equal(
  orchestrationSource.includes('<AssetOwnerManagement'),
  true,
  'Workflow configuration renders the shared owner-management entry',
);
assert.equal(
  releaseSource.includes('<AssetOwnerManagement'),
  true,
  'the publication view reuses the same owner-management entry',
);

console.log('assetOwnerManagement.test.ts PASS');
