import { strict as assert } from 'assert';

const cases = [
  { status: 'SUCCEEDED', expected: 'SUCCESS' },
  { status: 'PUBLISHED', expected: 'SUCCESS' },
  { status: 'ACTIVE', expected: 'SUCCESS' },
  { status: 'APPROVED', expected: 'FAILURE' },
  { status: 'PUBLISHING', expected: 'PENDING' },
  { status: 'PLATFORM_PENDING', expected: 'PENDING' },
  { status: 'PREPARING', expected: 'PENDING' },
  { status: 'PENDING', expected: 'PENDING' },
  { status: 'FAILED', expected: 'FAILURE' },
  { status: 'UNKNOWN_STATUS', expected: 'FAILURE' },
] as const;

const run = async () => {
  const modulePath = ['./releaseOperationFeedback', 'ts'].join('.');
  const { classifyReleaseOperation, executeReleaseOperation } = await import(modulePath);
  cases.forEach(({ status, expected }) => {
    const feedback = classifyReleaseOperation({
      operationId: `operation-${status}`,
      status,
      message: `message-${status}`,
    });
    assert.equal(feedback.kind, expected, `${status} feedback kind`);
    assert.equal(feedback.message, `message-${status}`, `${status} backend message`);
    assert.equal(feedback.status, status, `${status} normalized status`);
  });
  let refreshCount = 0;
  const execution = await executeReleaseOperation(
    async () => ({
      operationId: 'deployment-success',
      status: 'SUCCEEDED',
      message: '预发发布成功',
    }),
    async () => {
      refreshCount += 1;
      throw new Error('overview unavailable');
    },
  );
  assert.equal(refreshCount, 1, 'overview refresh count');
  assert.equal(execution.feedback?.kind, 'SUCCESS', 'refresh failure preserves operation success');
  assert.equal(
    execution.feedback?.message,
    '预发发布成功',
    'refresh failure preserves backend message',
  );
  assert.ok(execution.refreshError instanceof Error, 'refresh failure is returned separately');
  console.log('PASS compact release operation feedback classification');
};

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
