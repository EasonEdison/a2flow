import {
  captureFormPatchBaseline,
  formPatchProposalOf,
  resolveFormPatchBaseline,
  type AuthoringFormAdapter,
} from './index';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

async function test(description: string, callback: () => void | Promise<void>) {
  await callback();
  console.log(`PASS ${description}`);
}

async function main() {
  await test('normalizes a legacy capability snapshot into form patch operations', () => {
    const proposal = formPatchProposalOf({
      formKey: 'capability-center.action.v1',
      entityId: 'capability-draft:cap_draft_example',
      baseRevision: 1,
      baseDraftFingerprint: '12345678',
      summary: '补全能力草稿',
      changedPaths: ['/basicInfo', '/apiSource'],
      draft: {
        schemaVersion: 'capabilityActionDraft.v1',
        payloadType: 'CAPABILITY_DRAFT_SNAPSHOT',
        mode: 'CREATE',
        basicInfo: { actionCode: 'live.plan.create', nameCn: '创建直播计划' },
        apiSource: { sourceType: 'API_CENTER' },
      },
    });

    assertEqual(proposal?.baseFingerprint, 'fnv1a32:12345678', 'legacy fingerprint alias');
    assertEqual(proposal?.operations?.length, 2, 'snapshot operation count');
    assertEqual(proposal?.operations?.[0]?.op, 'replace', 'snapshot operation type');
    assertEqual(proposal?.operations?.[0]?.path, '/basicInfo', 'first snapshot path');
    assertEqual(proposal?.operations?.[1]?.path, '/apiSource', 'second snapshot path');
  });

  await test('accepts legacy capability patch fingerprint naming', () => {
    const proposal = formPatchProposalOf({
      formKey: 'capability-center.action.v1',
      entityId: 'capability-draft:cap_draft_example',
      baseRevision: 2,
      baseDraftFingerprint: 'fnv1a32:87654321',
      operations: [{ op: 'replace', path: '/basicInfo/nameCn', value: '直播计划' }],
    });

    assertEqual(proposal?.baseFingerprint, 'fnv1a32:87654321', 'patch fingerprint alias');
    assertEqual(proposal?.operations?.length, 1, 'patch operation count');
  });

  await test('rebuilds a missing history baseline only when the current form still matches', () => {
    const snapshot = { basicInfo: { nameCn: '当前名称' } };
    const adapter: AuthoringFormAdapter<typeof snapshot> = {
      formKey: 'capability-center.action.v1',
      entityId: 'capability-draft:cap_draft_example',
      revision: 3,
      schema: {},
      allowedPaths: ['/basicInfo/nameCn'],
      snapshot: () => snapshot,
      normalize: (value) => value as typeof snapshot,
      validateOperation: () => [],
      describePath: () => ({ label: '中文名' }),
      apply: () => undefined,
    };
    const currentBaseline = captureFormPatchBaseline(adapter);
    const matchingProposal = formPatchProposalOf({
      formKey: adapter.formKey,
      entityId: adapter.entityId,
      baseRevision: adapter.revision,
      baseFingerprint: currentBaseline.fingerprint,
      operations: [{ op: 'replace', path: '/basicInfo/nameCn', value: 'AI 名称' }],
    });
    // 改用 if 语句，避免 `a && {...}` 简写触发 no-chaining-call 规则 bug
    let staleProposal: typeof matchingProposal | undefined;
    if (matchingProposal) {
      staleProposal = {
        ...matchingProposal,
        baseRevision: matchingProposal.baseRevision - 1,
      };
    }

    assertEqual(
      resolveFormPatchBaseline(adapter, new Map(), matchingProposal!)?.fingerprint,
      currentBaseline.fingerprint,
      'matching current baseline',
    );
    assertEqual(
      resolveFormPatchBaseline(adapter, new Map(), staleProposal!),
      null,
      'stale current baseline',
    );
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
