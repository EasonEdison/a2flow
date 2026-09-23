import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { assertManualManagementMethod, MANAGEMENT_AI_PAUSE_REASON } from './managementAuthoringPolicy';
import { callSkillFactory, callSkillFactoryBizRender, streamSkillFactoryEvents, SkillFactoryMethod, skillFactoryApi } from '../api';

let fetchCount = 0;
const originalFetch = globalThis.fetch;
globalThis.fetch = async () => { fetchCount++; throw new Error('unexpected network request'); };
try {
  for (const method of Object.values(SkillFactoryMethod)) {
    if (/^(CODING_|AUTHORING_)/.test(method) ||
        method === 'CAPABILITY_SKILL_CREATOR_CONTEXT') {
      assert.throws(() => assertManualManagementMethod(method), { message: MANAGEMENT_AI_PAUSE_REASON });
      await assert.rejects(callSkillFactory(method), { message: MANAGEMENT_AI_PAUSE_REASON });
      await assert.rejects(callSkillFactoryBizRender(method), { message: MANAGEMENT_AI_PAUSE_REASON });
    } else {
      assert.doesNotThrow(() => assertManualManagementMethod(method));
    }
  }
  await assert.rejects(streamSkillFactoryEvents({}, () => {}), { message: MANAGEMENT_AI_PAUSE_REASON });
  assert.equal(fetchCount, 0, 'paused Agent APIs must fail before network activity');
  const runtimeResult = { status: 'PARTIAL', errors: [], warnings: ['fixture'], samples: [] };
  globalThis.fetch = async (url, options) => {
    fetchCount++;
    assert.equal(url, '/api/management/v2/handler');
    const request = JSON.parse(String(options?.body));
    assert.equal(request.method, 'RUNTIME_VALIDATE');
    assert.equal(request.params.sampleSource, 'MANUAL');
    assert.equal(request.params.samplePayload, '{"params":{}}');
    return new Response(JSON.stringify({ result: 1, data: runtimeResult }));
  };
  const actual = await skillFactoryApi.runtimeValidate('workspace-test', 'skill-test', {
    sampleSource: 'MANUAL',
    samplePayload: '{"params":{}}',
  });
  assert.deepEqual(actual, runtimeResult, 'deterministic sample validation preserves backend result');
  assert.equal(fetchCount, 1, 'deterministic sample validation reaches the backend');
} finally {
  globalThis.fetch = originalFetch;
}
const layout = readFileSync(new URL('./AuthoringWorkbenchLayout.tsx', import.meta.url), 'utf8');
assert.match(layout, /<main[^>]*>\{children\}<\/main>/);
assert.doesNotMatch(layout, /\{chat\}|\{review\}|addEventListener|<Button/);
const hook = readFileSync(new URL('./authoringChat/index.tsx', import.meta.url), 'utf8');
assert.match(hook, /const sessionDisabledReason = MANAGEMENT_AI_PAUSE_REASON/);
assert.match(hook, /if \(sessionDisabledReason \|\|/);
console.log('PASS manual management allows deterministic methods and prevents Agent requests');
