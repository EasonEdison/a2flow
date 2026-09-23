import {
  isActionablePatchProposal,
  isPatchReviewEvent,
  patchReviewStatus,
} from './patchProjection';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function test(description: string, callback: () => void) {
  callback();
  console.log(`PASS ${description}`);
}

test('failed patch artifact does not enter review', () => {
  const event = {
    eventType: 'ARTIFACT_CREATED',
    eventCode: 'FAILED',
    payloadType: 'PATCH_ARTIFACT',
    patchId: 'patch_failed',
    success: false,
    errorMsg: 'Patch 应用失败',
    content: {},
  };

  assertEqual(isPatchReviewEvent(event), false, 'failed artifact review visibility');
  assertEqual(patchReviewStatus(event), undefined, 'failed artifact review status');
});

test('pending patch proposal with actual changes is actionable without approval metadata', () => {
  const event = {
    eventType: 'ARTIFACT_CREATED',
    eventCode: 'PATCH_PROPOSED',
    payloadType: 'PATCH_ARTIFACT',
    patchId: 'patch_pending',
    content: {
      changedFiles: [{ path: 'SKILL.md', changeType: 'MODIFY' }],
    },
  };

  assertEqual(isPatchReviewEvent(event), true, 'pending proposal review visibility');
  assertEqual(isActionablePatchProposal(event), true, 'pending proposal actionability');
  assertEqual(patchReviewStatus(event), 'PENDING', 'pending proposal review status');
});

test('proposal without changed files is not pending review', () => {
  const event = {
    eventType: 'ARTIFACT_CREATED',
    eventCode: 'PATCH_PROPOSED',
    payloadType: 'PATCH_ARTIFACT',
    patchId: 'patch_empty',
    content: {
      changedFiles: [],
    },
  };

  assertEqual(isPatchReviewEvent(event), false, 'empty proposal review visibility');
  assertEqual(isActionablePatchProposal(event), false, 'empty proposal actionability');
});

test('patch conflict keeps its custom terminal status', () => {
  const event = {
    eventType: 'ARTIFACT_CREATED',
    eventCode: 'PATCH_CONFLICT',
    payloadType: 'PATCH_ARTIFACT',
    patchId: 'patch_conflict',
    success: false,
    errorMsg: '工作区已发生变化',
  };

  assertEqual(isPatchReviewEvent(event), true, 'conflict review visibility');
  assertEqual(patchReviewStatus(event), 'CONFLICTED', 'conflict review status');
});

test('generic tool failure is not mistaken for a patch review', () => {
  const event = {
    eventType: 'TOOL_CALL_FINISHED',
    eventCode: 'TOOL_CALL_FINISHED',
    payloadType: 'TOOL_RESULT',
    toolCallId: 'tool_001',
    toolSuccess: false,
  };

  assertEqual(isPatchReviewEvent(event), false, 'generic Tool failure review visibility');
  assertEqual(patchReviewStatus(event), undefined, 'generic Tool failure review status');
});
