import { SKILL_FACTORY_CHAT_BIZ_KEYS } from './api';
import { createA2uiApplicationAuthoringAdapter } from './shared/authoringChat/adapters/a2uiApplicationAdapter';

function assertEqual<T>(actual: T, expected: T, label: string): void {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function assertDeepEqual(actual: unknown, expected: unknown, label: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${label}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`,
    );
  }
}

function test(description: string, callback: () => void): void {
  callback();
  console.log(`PASS ${description}`);
}

test('A2UI authoring uses the dedicated bizKey and stable application scope', () => {
  assertEqual(
    SKILL_FACTORY_CHAT_BIZ_KEYS.A2UI_COMPONENT_AUTHORING,
    'HADES_A2UI_COMPONENT_AUTHORING',
    'A2UI authoring bizKey',
  );

  const adapter = createA2uiApplicationAuthoringAdapter({
    applicationId: 'application-1',
    draftId: 'a2ui_application_application-1',
    appCode: 'demo_application',
    agentId: 'agent-1',
    ownerId: 'owner-1',
  });

  assertEqual(adapter.domain, 'A2UI_APPLICATION', 'A2UI authoring domain');
  assertDeepEqual(
    adapter.sessionScope,
    {
      bizKey: 'HADES_A2UI_COMPONENT_AUTHORING',
      scopeType: 'A2UI_APPLICATION',
      scopeId: 'application-1',
      workspaceId: 'application-1',
      assetId: 'application-1',
      draftId: 'a2ui_application_application-1',
      appCode: 'demo_application',
      authoringDomain: 'A2UI_APPLICATION',
    },
    'A2UI authoring session scope',
  );

  const request = adapter.buildRequest({
    message: '请补充一个确认按钮',
    sessionId: 'session-1',
    messageId: 'message-1',
    runId: 'run-1',
  });
  assertEqual(request.bizKey, 'HADES_A2UI_COMPONENT_AUTHORING', 'A2UI request bizKey');
  assertEqual(request.authoringDomain, 'A2UI_APPLICATION', 'A2UI request domain');
  assertEqual(request.scopeType, 'A2UI_APPLICATION', 'A2UI request scope type');
  assertEqual(request.applicationId, 'application-1', 'A2UI request application id');
  assertEqual(request.appCode, 'demo_application', 'A2UI request appCode');
  assertEqual(request.agentId, 'agent-1', 'A2UI request agent id');
  assertEqual(request.message, '请补充一个确认按钮', 'A2UI request message');
});
